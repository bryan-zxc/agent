"""
Utility functions for task queue management and execution.

This module provides functions for queuing tasks, loading next tasks, and managing
the task execution lifecycle in the function-based architecture.
"""

import uuid
import logging
from typing import Optional
from ..models.agent_database import AgentDatabase

logger = logging.getLogger(__name__)



def queue_worker_task(worker_id: str, planner_id: str, function_name: str = "worker_initialisation") -> bool:
    """
    Queue a worker task for execution.
    
    Args:
        worker_id: The worker ID (also the task_id from FullTask)
        planner_id: The parent planner ID  
        function_name: The worker function to execute
    
    Returns True if task was queued, False otherwise.
    """
    db = AgentDatabase()
    
    # Queue the worker task with planner_id in payload
    task_id = uuid.uuid4().hex
    success = db.enqueue_task(
        task_id=task_id,
        entity_type="worker",
        entity_id=worker_id,
        function_name=function_name,
        payload={"planner_id": planner_id}  # Worker needs planner_id context
    )
    
    if success:
        logger.info(f"Queued worker task {task_id} for worker {worker_id}")
        return True
    else:
        logger.warning(f"Failed to queue worker task for worker {worker_id}")
        return False


def update_worker_next_task_and_queue(worker_id: str, next_function_name: str) -> bool:
    """
    Update worker's next task and queue it for execution.
    
    Args:
        worker_id: The worker ID
        next_function_name: The worker function to execute next
        
    Returns True if task was queued, False otherwise.
    """
    db = AgentDatabase()
    
    # Update next task in database using main update_worker method
    if not db.update_worker(worker_id, next_task=next_function_name):
        logger.error(f"Failed to update next task for worker {worker_id}")
        return False
    
    # Queue the worker task
    task_id = uuid.uuid4().hex
    success = db.enqueue_task(
        task_id=task_id,
        entity_type="worker",
        entity_id=worker_id,
        function_name=next_function_name,
        payload=None  # Worker execution tasks don't need payload currently
    )
    
    if success:
        logger.info(f"Queued worker task {task_id} for worker {worker_id}: {next_function_name}")
        return True
    else:
        logger.warning(f"Failed to queue worker task for worker {worker_id}")
        return False


def update_planner_next_task_and_queue(planner_id: str, next_function_name: str) -> bool:
    """
    Update planner's next task and immediately queue it.
    This is the main way task functions chain to the next task.
    Background processor will pick it up within 1 second.
    """
    db = AgentDatabase()
    
    # Update next task in database using main update_planner method
    if not db.update_planner(planner_id, next_task=next_function_name):
        logger.error(f"Failed to update next task for planner {planner_id}")
        return False
    
    # Queue the task directly - background processor will pick it up
    task_id = uuid.uuid4().hex
    success = db.enqueue_task(
        task_id=task_id,
        entity_type="planner",
        entity_id=planner_id,
        function_name=next_function_name,
        payload=None  # Planner tasks don't need payload currently
    )
    
    if success:
        logger.info(f"Updated and queued next task for planner {planner_id}: {next_function_name}")
        return True
    else:
        logger.error(f"Failed to queue next task for planner {planner_id}")
        return False


def get_router_id_for_planner(planner_id: str) -> Optional[str]:
    """Get the router ID for a planner"""
    db = AgentDatabase()
    return db.get_router_id_for_planner(planner_id)


def is_router_busy(router_id: str) -> bool:
    """Check if a router has any active tasks"""
    db = AgentDatabase()
    pending_tasks = db.get_pending_tasks_by_router()
    return router_id in pending_tasks


def get_task_status(task_id: str) -> Optional[str]:
    """Get the status of a specific task"""
    db = AgentDatabase()
    task = db.get_task(task_id)
    return task.get("status") if task else None


def cleanup_router_tasks(router_id: str) -> int:
    """Clean up completed/failed tasks for a router"""
    db = AgentDatabase()
    return db.remove_completed_tasks(router_id)