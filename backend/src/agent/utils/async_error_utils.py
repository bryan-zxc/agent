"""
Utilities for comprehensive async error logging and debugging.

Provides enhanced error logging for TaskGroup, asyncio tasks, and general async operations.
"""

import asyncio
import logging
import traceback
from typing import Any, Dict, List, Optional, Union
from contextlib import asynccontextmanager


logger = logging.getLogger(__name__)


class AsyncErrorLogger:
    """Enhanced async error logging with detailed traceback support"""
    
    def __init__(self, context_name: str = "async_operation"):
        self.context_name = context_name
    
    def log_exception_group(self, exc: BaseExceptionGroup, context: Optional[str] = None) -> None:
        """
        Log detailed information for ExceptionGroup (from TaskGroup failures)
        
        Args:
            exc: The ExceptionGroup containing sub-exceptions
            context: Optional context string for additional info
        """
        context_msg = f" in {context}" if context else f" in {self.context_name}"
        logger.error(f"ExceptionGroup occurred{context_msg}: {len(exc.exceptions)} sub-exception(s)")
        
        for i, sub_exc in enumerate(exc.exceptions):
            logger.error(f"Sub-exception #{i + 1}: {type(sub_exc).__name__}: {sub_exc}")
            
            # Get full traceback for each sub-exception
            if hasattr(sub_exc, '__traceback__') and sub_exc.__traceback__:
                tb_lines = traceback.format_exception(type(sub_exc), sub_exc, sub_exc.__traceback__)
                logger.error(f"Traceback for sub-exception #{i + 1}:")
                for line in tb_lines:
                    logger.error(f"  {line.rstrip()}")
            else:
                logger.error(f"  No traceback available for sub-exception #{i + 1}")
    
    def log_task_exception(self, task: asyncio.Task, task_name: Optional[str] = None) -> None:
        """
        Log detailed exception information from a failed asyncio.Task
        
        Args:
            task: The failed asyncio task  
            task_name: Optional name/description for the task
        """
        if task.done() and not task.cancelled():
            try:
                task.result()  # This will raise the exception if there was one
            except Exception as exc:
                task_desc = task_name or f"Task {task.get_name()}"
                logger.error(f"Task failed: {task_desc}")
                logger.error(f"Exception: {type(exc).__name__}: {exc}")
                
                # Log full traceback
                if hasattr(exc, '__traceback__') and exc.__traceback__:
                    tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
                    logger.error(f"Task traceback:")
                    for line in tb_lines:
                        logger.error(f"  {line.rstrip()}")
    
    def log_detailed_exception(self, exc: Exception, context: Optional[str] = None) -> None:
        """
        Log detailed exception with full traceback
        
        Args:
            exc: The exception to log
            context: Optional context information
        """
        context_msg = f" in {context}" if context else f" in {self.context_name}"
        logger.error(f"Exception occurred{context_msg}: {type(exc).__name__}: {exc}")
        
        # Log full traceback
        if hasattr(exc, '__traceback__') and exc.__traceback__:
            tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
            logger.error("Full traceback:")
            for line in tb_lines:
                logger.error(f"  {line.rstrip()}")
        else:
            # If no traceback attached, try to get current stack
            logger.error("Traceback:")
            for line in traceback.format_stack():
                logger.error(f"  {line.rstrip()}")


def log_taskgroup_errors(exc: BaseException, context: str = "TaskGroup operation") -> None:
    """
    Standalone function to log TaskGroup/ExceptionGroup errors with full detail
    
    Args:
        exc: Exception (potentially ExceptionGroup) to log
        context: Context string for logging
    """
    error_logger = AsyncErrorLogger(context)
    
    if isinstance(exc, BaseExceptionGroup):
        error_logger.log_exception_group(exc, context)
    else:
        error_logger.log_detailed_exception(exc, context)


@asynccontextmanager
async def log_async_errors(context: str = "async_operation"):
    """
    Context manager that logs detailed async errors
    
    Usage:
        async with log_async_errors("processing tasks"):
            async with asyncio.TaskGroup() as tg:
                tg.create_task(some_async_function())
    """
    try:
        yield
    except BaseExceptionGroup as exc:
        log_taskgroup_errors(exc, context)
        raise
    except Exception as exc:
        error_logger = AsyncErrorLogger(context)
        error_logger.log_detailed_exception(exc, context)
        raise


async def run_with_detailed_logging(
    coro_func, 
    *args, 
    context: str = "async_function",
    **kwargs
) -> Any:
    """
    Run an async function with detailed error logging
    
    Args:
        coro_func: Async function to run
        *args: Arguments for the function
        context: Context for error logging
        **kwargs: Keyword arguments for the function
    
    Returns:
        Result of the async function
        
    Raises:
        Original exception with detailed logging
    """
    try:
        return await coro_func(*args, **kwargs)
    except Exception as exc:
        error_logger = AsyncErrorLogger(context)
        error_logger.log_detailed_exception(exc, context)
        raise


def create_task_with_logging(
    coro, 
    name: Optional[str] = None, 
    context: str = "background_task"
) -> asyncio.Task:
    """
    Create an asyncio task with automatic error logging callback
    
    Args:
        coro: Coroutine to run
        name: Optional task name
        context: Context for error logging
    
    Returns:
        asyncio.Task with error logging callback
    """
    task = asyncio.create_task(coro, name=name)
    
    def log_task_error(task: asyncio.Task):
        if not task.cancelled():
            error_logger = AsyncErrorLogger(context)
            error_logger.log_task_exception(task, name)
    
    task.add_done_callback(log_task_error)
    return task


class TaskGroupWithLogging:
    """
    Enhanced TaskGroup wrapper with comprehensive error logging
    """
    
    def __init__(self, context: str = "TaskGroup"):
        self.context = context
        self.error_logger = AsyncErrorLogger(context)
        self._task_group = None
        self._tasks: List[asyncio.Task] = []
    
    async def __aenter__(self):
        self._task_group = asyncio.TaskGroup()
        await self._task_group.__aenter__()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            return await self._task_group.__aexit__(exc_type, exc_val, exc_tb)
        except BaseExceptionGroup as exc:
            # Log detailed information about all failed tasks
            self.error_logger.log_exception_group(exc, self.context)
            
            # Also log individual task states
            logger.error(f"TaskGroup failure summary for {self.context}:")
            for i, task in enumerate(self._tasks):
                if task.done() and not task.cancelled():
                    try:
                        task.result()
                        logger.error(f"  Task #{i + 1}: Completed successfully")
                    except Exception:
                        logger.error(f"  Task #{i + 1}: Failed (logged above)")
                elif task.cancelled():
                    logger.error(f"  Task #{i + 1}: Cancelled")
                else:
                    logger.error(f"  Task #{i + 1}: Still running/pending")
            
            raise
    
    def create_task(self, coro, *, name: Optional[str] = None):
        """Create a task and track it for logging"""
        task = self._task_group.create_task(coro, name=name)
        self._tasks.append(task)
        return task