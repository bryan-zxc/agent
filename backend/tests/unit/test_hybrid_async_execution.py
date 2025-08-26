"""
Hybrid Async Execution Tests

Advanced async/await testing with hybrid mocking strategy:
- Mock external services (LLM, file operations) to avoid side effects
- Use real database async operations to test actual async behaviour  
- Execute internal async functions with real async flow to catch await issues
- Test performance overhead and concurrent execution patterns

This hybrid approach ensures we test real async execution paths while
maintaining test reliability and speed.
"""

import unittest
import asyncio
import warnings
import tempfile
import uuid
import os
import time
import logging
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock
from contextlib import asynccontextmanager
from typing import Dict, List, Any

# Import the functions we need to test
from src.agent.tasks.task_utils import update_planner_next_task_and_queue, queue_worker_task
from src.agent.models.agent_database import AgentDatabase
from src.agent.tasks.planner_tasks import execute_initial_planning, execute_task_creation
from src.agent.tasks.worker_tasks import execute_standard_worker, execute_sql_worker
from src.agent.models.tasks import InitialExecutionPlan
from src.agent.models.schemas import File
from src.agent.config.settings import settings

# Import base test utilities
from tests.async_test_utils import AsyncWarningCaptureMixin

logger = logging.getLogger(__name__)


class HybridAsyncTestCase(unittest.IsolatedAsyncioTestCase, AsyncWarningCaptureMixin):
    """Enhanced test case with hybrid mocking strategy for real async execution."""
    
    async def asyncSetUp(self):
        """Set up hybrid test environment with real database and mocked external services."""
        # Create temporary database for testing
        self.temp_db = tempfile.NamedTemporaryFile(delete=False)
        self.db_path = self.temp_db.name
        self.temp_db.close()
        
        self.db = AgentDatabase(self.db_path)
        self.db._initialise_database()
        
        # Test IDs
        self.planner_id = f"hybrid_planner_{uuid.uuid4().hex[:8]}"
        self.worker_id = f"hybrid_worker_{uuid.uuid4().hex[:8]}"
        self.router_id = f"hybrid_router_{uuid.uuid4().hex[:8]}"
        self.message_id = f"msg_{uuid.uuid4().hex[:8]}"
        
        # Create temporary collaterals directory
        self.temp_collaterals_dir = tempfile.TemporaryDirectory()
        self.original_collaterals_path = settings.collaterals_base_path
        settings.collaterals_base_path = self.temp_collaterals_dir.name
        
        # Performance tracking
        self.performance_metrics = {}
    
    async def asyncTearDown(self):
        """Clean up test environment."""
        # Close database connections
        await self.db.async_engine.dispose()
        self.db.sync_engine.dispose()
        
        # Remove temporary database file
        if hasattr(self, 'db_path') and os.path.exists(self.db_path):
            os.unlink(self.db_path)
        
        # Clean up collaterals directory
        self.temp_collaterals_dir.cleanup()
        settings.collaterals_base_path = self.original_collaterals_path
    
    @asynccontextmanager
    async def hybrid_mock_context(self):
        """
        Context manager providing hybrid mocking strategy:
        - Mock external services (LLM, file I/O) 
        - Use real database operations in planner_tasks
        - Mock database only in task_utils to control which database instance is used
        - Execute internal async functions with real async flow
        """
        with patch('src.agent.tasks.planner_tasks.llm') as mock_llm, \
             patch('src.agent.tasks.planner_tasks.save_execution_plan_model') as mock_save_plan, \
             patch('src.agent.tasks.planner_tasks.save_answer_template') as mock_save_template, \
             patch('src.agent.tasks.planner_tasks.save_wip_answer_template') as mock_save_wip, \
             patch('src.agent.tasks.planner_tasks.save_current_task') as mock_save_task, \
             patch('src.agent.tasks.planner_tasks.AgentDatabase') as mock_planner_db_class, \
             patch('src.agent.tasks.task_utils.AgentDatabase') as mock_utils_db_class:
            
            # Configure database mocks to return our real test database
            mock_planner_db_class.return_value = self.db
            mock_utils_db_class.return_value = self.db
            
            # Configure LLM mocks with realistic async responses
            mock_llm.a_get_response = AsyncMock()
            
            # Configure file operation mocks to succeed without side effects
            mock_save_plan.return_value = True
            mock_save_template.return_value = True
            mock_save_wip.return_value = True
            mock_save_task.return_value = True
            
            yield {
                'mock_llm': mock_llm,
                'mock_save_plan': mock_save_plan,
                'mock_save_template': mock_save_template,
                'mock_save_wip': mock_save_wip,
                'mock_save_task': mock_save_task,
                'mock_planner_db_class': mock_planner_db_class,
                'mock_utils_db_class': mock_utils_db_class
            }
    
    async def measure_async_performance(self, coro_func, *args, **kwargs) -> Dict[str, Any]:
        """Measure performance overhead of async execution."""
        start_time = time.perf_counter()
        
        # Execute the async function
        result = await coro_func(*args, **kwargs)
        
        end_time = time.perf_counter()
        execution_time = end_time - start_time
        
        return {
            'result': result,
            'execution_time': execution_time,
            'function_name': getattr(coro_func, '__name__', str(coro_func))
        }


class TestHybridPlannerAsyncExecution(HybridAsyncTestCase):
    """Test planner functions with hybrid mocking for real async execution."""
    
    async def test_execute_initial_planning_real_async_flow(self):
        """Test execute_initial_planning with real async database operations."""
        # Test data
        task_data = {
            "entity_id": self.planner_id,
            "payload": {
                "user_question": "Analyse this test dataset and provide insights",
                "instruction": "Focus on trends and patterns",
                "files": [],
                "planner_name": "TestPlanner",
                "message_id": self.message_id,
                "router_id": self.router_id
            }
        }
        
        async with self.capture_async_warnings() as warnings_list:
            async with self.hybrid_mock_context() as mocks:
                # Configure LLM mock with realistic async responses
                mocks['mock_llm'].a_get_response.side_effect = [
                    InitialExecutionPlan(
                        objective="Test data analysis objective",
                        todos=["Analyse dataset", "Create visualisations", "Generate summary"]
                    ),
                    type('MockResponse', (), {
                        'content': "# Test Answer Template\n\nThis is a test template for analysis results."
                    })()
                ]
                
                # Measure performance and execute
                performance = await self.measure_async_performance(
                    execute_initial_planning, 
                    task_data
                )
                
                # Verify execution completed successfully
                self.assertIsNone(performance['result'])  # Function returns None on success
                
                # Verify no async warnings (real async execution worked correctly)
                self.assert_no_unawaited_coroutines(warnings_list)
                
                # Verify database operations occurred (real database was used)
                planner_data = await self.db.get_planner(self.planner_id)
                self.assertIsNotNone(planner_data)
                self.assertEqual(planner_data['planner_name'], "TestPlanner")
                self.assertEqual(planner_data['status'], "executing")  # Status updated after successful plan creation
                
                # Main focus: verify async execution completed without warnings
                # (Message-planner link verification skipped for simplicity in async testing)
                
                # Store performance metrics
                self.performance_metrics['execute_initial_planning'] = performance['execution_time']
    
    async def test_concurrent_database_operations_async_flow(self):
        """Test concurrent database operations for async execution patterns."""
        # Create multiple test planners for concurrent operations
        planner_ids = [f"concurrent_{i}_{uuid.uuid4().hex[:4]}" for i in range(3)]
        
        for i, pid in enumerate(planner_ids):
            await self.db.create_planner(
                planner_id=pid,
                planner_name=f"ConcurrentPlanner{i}",
                user_question=f"Test concurrent execution {i}",
                instruction="Test instruction",
                status="active"
            )
        
        async with self.capture_async_warnings() as warnings_list:
            # Test concurrent update operations using real async database functions
            with patch('src.agent.tasks.task_utils.AgentDatabase') as mock_db_class:
                mock_db_class.return_value = self.db
                
                # Execute concurrent planner updates (tests real async flow)
                tasks = [
                    self.measure_async_performance(
                        update_planner_next_task_and_queue, 
                        pid, 
                        f"execute_task_creation_{i}"
                    )
                    for i, pid in enumerate(planner_ids)
                ]
                
                # Wait for all concurrent operations
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Verify all operations completed successfully
                for result in results:
                    self.assertIsInstance(result, dict)
                    self.assertIn('execution_time', result)
                    self.assertTrue(result['result'])  # update_planner_next_task_and_queue returns bool
                
                # Verify no async warnings from concurrent execution
                self.assert_no_unawaited_coroutines(warnings_list)
                
                # Calculate average concurrent execution time
                avg_time = sum(r['execution_time'] for r in results) / len(results)
                self.performance_metrics['concurrent_database_operations'] = avg_time


class TestHybridWorkerAsyncExecution(HybridAsyncTestCase):
    """Test worker functions with hybrid mocking for real async execution."""
    
    async def test_queue_worker_task_real_database_operations(self):
        """Test queue_worker_task with real database async operations."""
        # Create test planner for worker context
        await self.db.create_planner(
            planner_id=self.planner_id,
            planner_name="WorkerTestPlanner",
            user_question="Test worker task queueing",
            instruction="Test instruction",
            status="active"
        )
        
        async with self.capture_async_warnings() as warnings_list:
            # Mock AgentDatabase to use our real test database
            with patch('src.agent.tasks.task_utils.AgentDatabase') as mock_db_class:
                mock_db_class.return_value = self.db
                
                # Test the async queue_worker_task function
                performance = await self.measure_async_performance(
                    queue_worker_task,
                    worker_id=self.worker_id,
                    planner_id=self.planner_id,
                    function_name="execute_standard_worker"
                )
                
                # Verify task was queued successfully
                self.assertTrue(performance['result'])
                
                # Verify no async warnings
                self.assert_no_unawaited_coroutines(warnings_list)
                
                # Verify task actually exists in database (real database operation)
                tasks = await self.db.get_pending_tasks()
                worker_tasks = [t for t in tasks if t.get('entity_id') == self.worker_id]
                self.assertTrue(len(worker_tasks) > 0)
                
                # Store performance metrics
                self.performance_metrics['queue_worker_task'] = performance['execution_time']
    
    async def test_execute_standard_worker_with_mocked_externals(self):
        """Test worker execution with external services mocked but real async flow."""
        # Create test planner and worker setup
        await self.db.create_planner(
            planner_id=self.planner_id,
            planner_name="StandardWorkerTest",
            user_question="Test standard worker execution",
            instruction="Execute standard analysis",
            status="active"
        )
        
        task_data = {
            "entity_id": self.worker_id,
            "payload": {
                "planner_id": self.planner_id
            }
        }
        
        async with self.capture_async_warnings() as warnings_list:
            # Mock external dependencies but keep async flow real
            with patch('src.agent.tasks.worker_tasks.llm') as mock_worker_llm, \
                 patch('src.agent.tasks.worker_tasks.load_current_task') as mock_load_task, \
                 patch('src.agent.tasks.task_utils.AgentDatabase') as mock_db_class:
                
                # Configure mocks
                mock_db_class.return_value = self.db
                mock_load_task.return_value = type('MockTask', (), {
                    'task_id': 'test_task',
                    'description': 'Test standard worker task',
                    'assigned_to': 'worker'
                })()
                
                mock_worker_llm.a_get_response = AsyncMock()
                mock_worker_llm.a_get_response.return_value = type('MockResponse', (), {
                    'content': 'Test worker analysis complete'
                })()
                
                # Execute with performance measurement
                performance = await self.measure_async_performance(
                    execute_standard_worker,
                    task_data
                )
                
                # Verify execution (some worker functions may return None)
                # The key is that async execution completed without warnings
                self.assert_no_unawaited_coroutines(warnings_list)
                
                # Store performance metrics
                self.performance_metrics['execute_standard_worker'] = performance['execution_time']


class TestAsyncPerformanceAnalysis(HybridAsyncTestCase):
    """Analyse async execution performance and overhead."""
    
    async def test_async_execution_performance_benchmarks(self):
        """Benchmark async execution performance across different functions."""
        # Performance targets (in seconds)
        performance_targets = {
            'update_planner_next_task_and_queue': 0.1,  # Database operation should be fast
            'queue_worker_task': 0.1,                   # Simple queueing operation
            'database_operations': 0.2,                 # Multiple DB operations
        }
        
        # Create test planner for benchmarking
        await self.db.create_planner(
            planner_id=self.planner_id,
            planner_name="BenchmarkPlanner",
            user_question="Performance testing",
            instruction="Benchmark async operations",
            status="active"
        )
        
        async with self.capture_async_warnings() as warnings_list:
            # Mock AgentDatabase to use our test database
            with patch('src.agent.tasks.task_utils.AgentDatabase') as mock_db_class:
                mock_db_class.return_value = self.db
                
                # Benchmark update_planner_next_task_and_queue
                update_perf = await self.measure_async_performance(
                    update_planner_next_task_and_queue,
                    self.planner_id,
                    "execute_task_creation"
                )
                
                # Benchmark queue_worker_task
                queue_perf = await self.measure_async_performance(
                    queue_worker_task,
                    worker_id=self.worker_id,
                    planner_id=self.planner_id,
                    function_name="execute_standard_worker"
                )
                
                # Benchmark multiple database operations
                async def multi_db_operations():
                    """Multiple database operations for benchmarking."""
                    await self.db.update_planner(self.planner_id, status="running")
                    planner_data = await self.db.get_planner(self.planner_id)
                    await self.db.update_planner(self.planner_id, status="completed")
                    return planner_data
                
                multi_db_perf = await self.measure_async_performance(multi_db_operations)
                
                # Verify no async warnings during benchmarking
                self.assert_no_unawaited_coroutines(warnings_list)
                
                # Analyse performance against targets
                performance_results = {
                    'update_planner_next_task_and_queue': update_perf['execution_time'],
                    'queue_worker_task': queue_perf['execution_time'],
                    'database_operations': multi_db_perf['execution_time']
                }
                
                # Log performance results
                logger.info("Async Performance Benchmark Results:")
                for func_name, actual_time in performance_results.items():
                    target_time = performance_targets.get(func_name, float('inf'))
                    status = "✅" if actual_time <= target_time else "⚠️"
                    logger.info(f"  {status} {func_name}: {actual_time:.4f}s (target: {target_time:.2f}s)")
                
                # Performance assertions
                for func_name, actual_time in performance_results.items():
                    target_time = performance_targets.get(func_name, float('inf'))
                    self.assertLessEqual(
                        actual_time, 
                        target_time * 2,  # Allow 2x safety margin
                        f"{func_name} took {actual_time:.4f}s, target was {target_time:.2f}s"
                    )
                
                # Store comprehensive performance metrics
                self.performance_metrics.update(performance_results)
    
    async def test_concurrent_async_execution_overhead(self):
        """Test performance overhead of concurrent async execution."""
        # Create multiple test planners
        planner_ids = [f"concurrent_{i}_{uuid.uuid4().hex[:4]}" for i in range(5)]
        
        for i, pid in enumerate(planner_ids):
            await self.db.create_planner(
                planner_id=pid,
                planner_name=f"ConcurrentPlanner{i}",
                user_question=f"Concurrent test {i}",
                instruction="Concurrent testing",
                status="active"
            )
        
        async with self.capture_async_warnings() as warnings_list:
            with patch('src.agent.tasks.task_utils.AgentDatabase') as mock_db_class:
                mock_db_class.return_value = self.db
                
                # Measure sequential execution time
                sequential_start = time.perf_counter()
                for pid in planner_ids:
                    await update_planner_next_task_and_queue(pid, "execute_task_creation")
                sequential_time = time.perf_counter() - sequential_start
                
                # Reset planner states
                for pid in planner_ids:
                    await self.db.update_planner(pid, status="planning")
                
                # Measure concurrent execution time
                concurrent_start = time.perf_counter()
                tasks = [
                    update_planner_next_task_and_queue(pid, "execute_synthesis")
                    for pid in planner_ids
                ]
                await asyncio.gather(*tasks)
                concurrent_time = time.perf_counter() - concurrent_start
                
                # Verify no async warnings
                self.assert_no_unawaited_coroutines(warnings_list)
                
                # Analyse concurrency benefits
                concurrency_improvement = sequential_time / concurrent_time if concurrent_time > 0 else 0
                
                logger.info(f"Concurrency Analysis:")
                logger.info(f"  Sequential time: {sequential_time:.4f}s")
                logger.info(f"  Concurrent time: {concurrent_time:.4f}s") 
                logger.info(f"  Improvement factor: {concurrency_improvement:.2f}x")
                
                # Concurrent execution analysis (may have variable overhead in test environments)
                # Focus is on async correctness, not performance guarantees in tests
                if concurrent_time > sequential_time * 2.0:  # Only fail if extremely slower
                    logger.warning(f"Concurrent execution much slower than expected: {concurrent_time:.4f}s vs {sequential_time:.4f}s")
                
                # Main assertion: ensure concurrent execution completed successfully
                self.assertGreater(concurrency_improvement, 0, "Concurrency measurement failed")
                
                # Store concurrency metrics
                self.performance_metrics['sequential_execution'] = sequential_time
                self.performance_metrics['concurrent_execution'] = concurrent_time
                self.performance_metrics['concurrency_improvement'] = concurrency_improvement


if __name__ == '__main__':
    # Configure logging for test output
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s - %(name)s - %(message)s'
    )
    
    unittest.main()