"""
Background task processor for the function-based agent system.

This processor runs continuously, scanning for pending tasks every second and executing
one task per router to maintain router-level locking.
"""

import asyncio
import logging
from typing import Dict, Any, Callable
from ..models.agent_database import AgentDatabase
from ..utils.async_error_utils import log_taskgroup_errors, TaskGroupWithLogging, AsyncErrorLogger

logger = logging.getLogger(__name__)


class BackgroundTaskProcessor:
    """
    Background processor that executes queued tasks with router-level locking.
    
    Key features:
    - Scans for pending tasks every second
    - Executes one task per router at a time
    - Multiple routers can run concurrently
    - Function-based task execution with proper error handling
    """
    
    def __init__(self):
        self.db = AgentDatabase()
        self.running = False
        
        # Function registry - maps function names to actual functions
        self.function_registry: Dict[str, Callable] = {}
        
        # Import and register task functions
        self._register_task_functions()
    
    def _register_task_functions(self):
        """Register all available task functions"""
        try:
            # Import planner task functions
            from ..tasks import planner_tasks
            self.function_registry.update({
                "execute_initial_planning": planner_tasks.execute_initial_planning,
                "execute_task_creation": planner_tasks.execute_task_creation,
                "execute_synthesis": planner_tasks.execute_synthesis,
            })
            
            # Import worker task functions  
            from ..tasks import worker_tasks
            self.function_registry.update({
                "worker_initialisation": worker_tasks.worker_initialisation,
                "execute_standard_worker": worker_tasks.execute_standard_worker,
                "execute_sql_worker": worker_tasks.execute_sql_worker,
            })
            
            logger.info(f"Registered {len(self.function_registry)} task functions")
            
        except ImportError as e:
            logger.error(f"Failed to import task functions: {e}")
            # Continue with empty registry - will log errors when tasks are encountered
    
    async def start(self):
        """Start the background processor"""
        if self.running:
            logger.warning("Background processor is already running")
            return
        
        self.running = True
        logger.info("Starting background task processor")
        
        try:
            await self.process_loop()
        except Exception as e:
            logger.error(f"Background processor crashed: {e}")
            raise
        finally:
            self.running = False
            logger.info("Background task processor stopped")
    
    async def stop(self):
        """Stop the background processor"""
        logger.info("Stopping background task processor")
        self.running = False
    
    async def process_loop(self):
        """
        Main processing loop - scans for tasks every second and executes them.
        Processes all pending tasks concurrently.
        """
        while self.running:
            try:
                # Get all pending tasks (now async)
                pending_tasks = await self.db.get_pending_tasks()
                
                if pending_tasks:
                    logger.debug(f"Found {len(pending_tasks)} pending task(s)")
                    
                    # Execute all tasks concurrently using enhanced TaskGroup with logging
                    async with TaskGroupWithLogging("background_task_processor") as tg:
                        for task_data in pending_tasks:
                            task_name = f"task_{task_data['task_id']}_{task_data['function_name']}"
                            tg.create_task(self.execute_task(task_data), name=task_name)
                
                # Sleep for 1 second before next scan
                await asyncio.sleep(1)
                
            except Exception as e:
                # Log detailed error information using enhanced logging
                log_taskgroup_errors(e, "background_processor.process_loop")
                # Continue processing after brief delay
                await asyncio.sleep(5)
    
    async def execute_task(self, task_data: Dict[str, Any]):
        """
        Execute a single task with proper error handling and status updates.
        
        Args:
            task_data: Task information from database
        """
        task_id = task_data["task_id"]
        entity_id = task_data["entity_id"]
        function_name = task_data["function_name"]
        
        logger.info(f"Executing task {task_id}: {function_name} for entity {entity_id}")
        
        try:
            # Mark task as in progress
            self.db.update_task_status(task_id, "IN_PROGRESS")
            
            # Get the function to execute
            if function_name not in self.function_registry:
                raise ValueError(f"Unknown function: {function_name}")
            
            task_function = self.function_registry[function_name]
            
            # Execute the function with complete task_data (all our functions are async)
            await task_function(task_data)
            
            # Mark task as completed
            self.db.update_task_status(task_id, "COMPLETED")
            logger.info(f"Task {task_id} completed successfully")
            
        except Exception as e:
            # Log detailed error information for task failure
            error_logger = AsyncErrorLogger(f"execute_task_{function_name}")
            error_logger.log_detailed_exception(e, f"Task {task_id} execution")
            
            # Mark task as failed with detailed error message
            error_message = f"{type(e).__name__}: {str(e)}"
            self.db.update_task_status(task_id, "FAILED", error_message)
            logger.error(f"Task {task_id} ({function_name}) failed and marked as FAILED in database")
            
            # TODO: Implement retry logic based on retry_count and max_retries
            # For now, just log the failure
    
    async def get_status(self) -> Dict[str, Any]:
        """Get processor status information"""
        pending_tasks = await self.db.get_pending_tasks()
        
        return {
            "running": self.running,
            "registered_functions": list(self.function_registry.keys()),
            "pending_tasks_count": len(pending_tasks),
            "pending_task_ids": [task["task_id"] for task in pending_tasks]
        }


# Global processor instance
_processor_instance = None


async def start_background_processor():
    """Start the global background processor instance"""
    global _processor_instance
    
    if _processor_instance and _processor_instance.running:
        logger.warning("Background processor already running")
        return _processor_instance
    
    _processor_instance = BackgroundTaskProcessor()
    
    # Start processor in background task
    asyncio.create_task(_processor_instance.start())
    
    # Brief delay to ensure it starts
    await asyncio.sleep(0.1)
    
    return _processor_instance


async def stop_background_processor():
    """Stop the global background processor instance"""
    global _processor_instance
    
    if _processor_instance:
        await _processor_instance.stop()
        _processor_instance = None


def get_background_processor() -> BackgroundTaskProcessor:
    """Get the global background processor instance"""
    return _processor_instance