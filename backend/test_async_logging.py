#!/usr/bin/env python3
"""
Test script to verify async error logging functionality.

Run this to test the enhanced error logging utilities.
"""

import asyncio
import logging
import sys
import os

# Add the backend src to path so we can import our modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from agent.utils.async_error_utils import (
    log_taskgroup_errors, 
    TaskGroupWithLogging, 
    AsyncErrorLogger,
    log_async_errors,
    run_with_detailed_logging
)

# Configure logging to see the detailed output
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def failing_task_1():
    """Task that raises ValueError"""
    await asyncio.sleep(0.1)
    raise ValueError("This is a test ValueError from task 1")


async def failing_task_2():
    """Task that raises RuntimeError"""  
    await asyncio.sleep(0.2)
    raise RuntimeError("This is a test RuntimeError from task 2")


async def successful_task():
    """Task that completes successfully"""
    await asyncio.sleep(0.1)
    logger.info("Successful task completed!")
    return "success"


import unittest

class TestAsyncLogging(unittest.IsolatedAsyncioTestCase):
    """Test async logging functionality."""
    
    async def test_taskgroup_logging(self):
        """Test TaskGroup error logging with multiple failing tasks"""
        logger.info("=== Testing TaskGroup with multiple failing tasks ===")
        
        try:
            async with TaskGroupWithLogging("test_multiple_failures") as tg:
                tg.create_task(failing_task_1(), name="failing_task_1")
                tg.create_task(failing_task_2(), name="failing_task_2") 
                tg.create_task(successful_task(), name="successful_task")
        except BaseExceptionGroup as exc_group:
            logger.info("Caught exception group as expected")


    async def test_standard_taskgroup_logging(self):
        """Test standard TaskGroup error logging function"""
        logger.info("=== Testing standard TaskGroup error logging ===")
        
        try:
            async with asyncio.TaskGroup() as tg:
                tg.create_task(failing_task_1())
                tg.create_task(successful_task())
        except BaseExceptionGroup as exc:
            log_taskgroup_errors(exc, "test_standard_taskgroup")


    async def test_context_manager_logging(self):
        """Test the context manager for async error logging"""
        logger.info("=== Testing async context manager logging ===")
        
        try:
            async with log_async_errors("context_manager_test"):
                await failing_task_1()
        except ValueError:
            logger.info("Caught ValueError as expected")


    async def test_function_wrapper_logging(self):
        """Test the function wrapper for detailed logging"""
        logger.info("=== Testing function wrapper logging ===")
        
        try:
            await run_with_detailed_logging(
                failing_task_2, 
                context="function_wrapper_test"
            )
        except RuntimeError:
            logger.info("Caught RuntimeError as expected")


if __name__ == "__main__":
    unittest.main()