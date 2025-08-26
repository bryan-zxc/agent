"""
Async/Await Validation Tests

Tests designed specifically to catch async/await correctness issues that
static analysis might miss or to validate that async execution paths work correctly.

These tests use real async execution (not mocks) to detect:
- Unawaited coroutines (RuntimeWarnings)
- Async context manager issues
- Concurrent execution correctness
- Real database async operations
"""

import unittest
import asyncio
import warnings
import tempfile
import uuid
import os
from unittest.mock import patch, AsyncMock
from contextlib import asynccontextmanager

# Import the functions we need to test
from src.agent.tasks.task_utils import update_planner_next_task_and_queue, queue_worker_task
from src.agent.models.agent_database import AgentDatabase
from src.agent.tasks.planner_tasks import execute_initial_planning, execute_task_creation
from src.agent.tasks.worker_tasks import execute_standard_worker, execute_sql_worker


class AsyncValidationTestCase(unittest.IsolatedAsyncioTestCase):
    """Base test case with async validation utilities."""
    
    async def asyncSetUp(self):
        """Set up async test environment."""
        # Create temporary database for testing (in-memory doesn't work with separate engines)
        self.temp_db = tempfile.NamedTemporaryFile(delete=False)
        self.db_path = self.temp_db.name
        self.temp_db.close()
        
        # Use factory method to create database
        self.db = await AgentDatabase.create(self.db_path)
        
        # Test IDs
        self.planner_id = f"test_planner_{uuid.uuid4().hex[:8]}"
        self.worker_id = f"test_worker_{uuid.uuid4().hex[:8]}"
        self.router_id = f"test_router_{uuid.uuid4().hex[:8]}"
    
    @asynccontextmanager
    async def capture_async_warnings(self):
        """Context manager to capture RuntimeWarnings about unawaited coroutines."""
        with warnings.catch_warnings(record=True) as warning_list:
            # Ensure RuntimeWarnings are always recorded
            warnings.simplefilter("always", RuntimeWarning)
            warnings.filterwarnings("ignore", module="PIL")  # Ignore PIL warnings
            warnings.filterwarnings("ignore", module="matplotlib")  # Ignore matplotlib warnings
            
            yield warning_list
    
    def assert_no_unawaited_coroutines(self, warning_list):
        """Assert that no 'was never awaited' warnings were captured."""
        unawaited_warnings = [
            w for w in warning_list 
            if "was never awaited" in str(w.message).lower()
        ]
        
        if unawaited_warnings:
            warning_messages = [str(w.message) for w in unawaited_warnings]
            self.fail(
                f"Found {len(unawaited_warnings)} unawaited coroutine(s):\n" +
                "\n".join(f"  - {msg}" for msg in warning_messages)
            )
    
    def assert_has_unawaited_coroutines(self, warning_list, expected_count=None):
        """Assert that unawaited coroutine warnings were captured (for negative testing)."""
        unawaited_warnings = [
            w for w in warning_list 
            if "was never awaited" in str(w.message).lower()
        ]
        
        if not unawaited_warnings:
            self.fail("Expected unawaited coroutine warnings but none were found")
        
        if expected_count is not None and len(unawaited_warnings) != expected_count:
            self.fail(
                f"Expected {expected_count} unawaited coroutine warnings, "
                f"but found {len(unawaited_warnings)}"
            )
    
    async def asyncTearDown(self):
        """Clean up test environment."""
        # Close database connections
        await self.db.async_engine.dispose()
        
        # Remove temporary database file
        if hasattr(self, 'db_path') and os.path.exists(self.db_path):
            os.unlink(self.db_path)


class TestUpdatePlannerNextTaskAndQueue(AsyncValidationTestCase):
    """Test update_planner_next_task_and_queue for async correctness."""
    
    async def test_function_is_properly_awaited(self):
        """Test that update_planner_next_task_and_queue works when properly awaited."""
        # Create test planner first
        await self.db.create_planner(
            planner_id=self.planner_id,
            planner_name="Test Planner",
            user_question="Test question",
            instruction="Test instruction",
            status="active"
        )
        
        async with self.capture_async_warnings() as warnings_list:
            # Mock AgentDatabase.create() to use our test database
            with patch('src.agent.tasks.task_utils.AgentDatabase') as mock_db_class:
                # Make create() return our test database instance
                async def mock_create(*args, **kwargs):
                    return self.db
                mock_db_class.create = mock_create
                
                # This should work correctly with await
                result = await update_planner_next_task_and_queue(
                    self.planner_id, 
                    "execute_task_creation"
                )
            
            # Should succeed and produce no async warnings
            self.assertTrue(result)
            self.assert_no_unawaited_coroutines(warnings_list)
    
    async def test_function_without_await_produces_warnings(self):
        """Test that calling without await produces RuntimeWarnings (negative test)."""
        # Create test planner first
        await self.db.create_planner(
            planner_id=self.planner_id,
            planner_name="Test Planner", 
            user_question="Test question",
            instruction="Test instruction",
            status="active"
        )
        
        async with self.capture_async_warnings() as warnings_list:
            # Mock AgentDatabase.create() to use our test database
            with patch('src.agent.tasks.task_utils.AgentDatabase') as mock_db_class:
                # Make create() return our test database instance
                async def mock_create(*args, **kwargs):
                    return self.db
                mock_db_class.create = mock_create
                
                # This is wrong - calling async function without await
                # Should produce a RuntimeWarning when coroutine is garbage collected
                update_planner_next_task_and_queue(
                    self.planner_id,
                    "execute_task_creation"
                )
                
                # Force garbage collection to trigger the warning
                import gc
                gc.collect()
        
        # Should have captured unawaited coroutine warnings
        self.assert_has_unawaited_coroutines(warnings_list)


class TestTaskFunctionAsyncCorrectness(AsyncValidationTestCase):
    """Test that planner and worker task functions handle async correctly."""
    
    async def test_execute_initial_planning_with_real_database(self):
        """Test execute_initial_planning with real database operations."""
        with patch('src.agent.tasks.planner_tasks.llm') as mock_llm, \
             patch('src.agent.tasks.planner_tasks.save_execution_plan_model') as mock_save_plan, \
             patch('src.agent.tasks.planner_tasks.save_answer_template') as mock_save_template, \
             patch('src.agent.tasks.planner_tasks.save_wip_answer_template') as mock_save_wip:
            
            # Configure LLM mock to return proper responses
            from src.agent.models.tasks import InitialExecutionPlan
            
            async def mock_llm_response_1(*args, **kwargs):
                return InitialExecutionPlan(objective="Test objective", todos=["task1", "task2"])
            
            async def mock_llm_response_2(*args, **kwargs):
                return type('MockResponse', (), {'content': "# Test Answer Template"})()
            
            mock_llm.a_get_response.side_effect = [
                mock_llm_response_1(),
                mock_llm_response_2()
            ]
            
            # Configure file operation mocks
            mock_save_plan.return_value = True
            mock_save_template.return_value = True
            mock_save_wip.return_value = True
            
            # Test data - use real database instead of mocking it
            task_data = {
                "entity_id": self.planner_id,
                "payload": {
                    "user_question": "Test question",
                    "instruction": "Test instruction", 
                    "files": [],
                    "planner_name": "Test Planner",
                    "router_id": self.router_id
                }
            }
            
            async with self.capture_async_warnings() as warnings_list:
                # Execute with real database operations (not mocked)
                await execute_initial_planning(task_data)
                
                # Should execute without async warnings
                self.assert_no_unawaited_coroutines(warnings_list)
    
    async def test_queue_worker_task_async_correctness(self):
        """Test that queue_worker_task properly handles async database operations."""
        # Create test planner first
        await self.db.create_planner(
            planner_id=self.planner_id,
            planner_name="Test Planner",
            user_question="Test question", 
            instruction="Test instruction",
            status="active"
        )
        
        async with self.capture_async_warnings() as warnings_list:
            # Mock AgentDatabase.create() to use our test database
            with patch('src.agent.tasks.task_utils.AgentDatabase') as mock_db_class:
                # Make create() return our test database instance
                async def mock_create(*args, **kwargs):
                    return self.db
                mock_db_class.create = mock_create
                
                # Test the queue_worker_task function (now async after fix)
                success = await queue_worker_task(
                    worker_id=self.worker_id,
                    planner_id=self.planner_id,
                    function_name="execute_standard_worker"
                )
            
            # Should succeed and produce no async warnings
            self.assertTrue(success)
            self.assert_no_unawaited_coroutines(warnings_list)


class TestAsyncContextManagerCorrectness(AsyncValidationTestCase):
    """Test async context managers are used correctly."""
    
    async def test_database_operations_in_context(self):
        """Test that database operations work correctly in async context."""
        async with self.capture_async_warnings() as warnings_list:
            # Test multiple database operations in sequence
            await self.db.create_planner(
                planner_id=self.planner_id,
                planner_name="Test Planner",
                user_question="Test question",
                instruction="Test instruction", 
                status="active"
            )
            
            planner_data = await self.db.get_planner(self.planner_id)
            self.assertIsNotNone(planner_data)
            
            success = await self.db.update_planner(
                self.planner_id,
                status="completed"
            )
            self.assertTrue(success)
            
            # Should complete without async warnings
            self.assert_no_unawaited_coroutines(warnings_list)


class TestConcurrentAsyncOperations(AsyncValidationTestCase):
    """Test concurrent async operations for correctness."""
    
    async def test_concurrent_database_operations(self):
        """Test that concurrent database operations don't cause async issues."""
        async with self.capture_async_warnings() as warnings_list:
            # Create multiple planners concurrently
            planner_ids = [f"test_planner_{i}_{uuid.uuid4().hex[:4]}" for i in range(3)]
            
            # Run database operations concurrently
            tasks = []
            for i, planner_id in enumerate(planner_ids):
                task = self.db.create_planner(
                    planner_id=planner_id,
                    planner_name=f"Test Planner {i}",
                    user_question=f"Test question {i}",
                    instruction=f"Test instruction {i}",
                    status="active"
                )
                tasks.append(task)
            
            # Wait for all to complete
            results = await asyncio.gather(*tasks)
            
            # All should succeed
            for result in results:
                self.assertIsNone(result)  # create_planner returns None on success
            
            # Should complete without async warnings
            self.assert_no_unawaited_coroutines(warnings_list)
    
    async def test_concurrent_task_queue_operations(self):
        """Test concurrent task queue operations."""
        # Create test planner first
        await self.db.create_planner(
            planner_id=self.planner_id,
            planner_name="Test Planner",
            user_question="Test question",
            instruction="Test instruction",
            status="active"
        )
        
        async with self.capture_async_warnings() as warnings_list:
            # Mock AgentDatabase.create() to use our test database
            with patch('src.agent.tasks.task_utils.AgentDatabase') as mock_db_class:
                # Make create() return our test database instance
                async def mock_create(*args, **kwargs):
                    return self.db
                mock_db_class.create = mock_create
                
                # Queue multiple tasks concurrently
                worker_ids = [f"test_worker_{i}_{uuid.uuid4().hex[:4]}" for i in range(3)]
                
                tasks = []
                for i, worker_id in enumerate(worker_ids):
                    task = update_planner_next_task_and_queue(
                        self.planner_id,
                        f"execute_task_{i}"
                    )
                    tasks.append(task)
                
                # Wait for all to complete
                results = await asyncio.gather(*tasks)
            
            # All should succeed
            for result in results:
                self.assertTrue(result)
            
            # Should complete without async warnings  
            self.assert_no_unawaited_coroutines(warnings_list)


if __name__ == '__main__':
    unittest.main()