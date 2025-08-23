"""
Test suite for background processor efficiency validation.

This test suite validates that the background task processor operates efficiently,
handles concurrent tasks properly, and maintains good performance characteristics
under various load conditions.
"""

import unittest
import asyncio
import time
import tempfile
import shutil
import uuid
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import threading

# Import the modules under test
from agent.services.background_processor import BackgroundTaskProcessor
from agent.models.agent_database import AgentDatabase
from agent.config.settings import settings


class TestBackgroundProcessorEfficiency(unittest.TestCase):
    """Test background processor efficiency and performance."""
    
    def setUp(self):
        """Set up test environment before each test."""
        # Create temporary directory for testing
        self.test_dir = tempfile.mkdtemp()
        self.original_base_path = settings.collaterals_base_path
        
        # Mock settings to use test directory
        settings.collaterals_base_path = self.test_dir
        
        # Set up in-memory database for testing
        self.db = AgentDatabase()
        self.db.engine = self.db.create_engine("sqlite:///:memory:")
        self.db.Base.metadata.create_all(self.db.engine)
        self.db.SessionLocal = self.db.sessionmaker(bind=self.db.engine)
        
        # Test data
        self.execution_times = []
        self.processed_tasks = []
        
    def tearDown(self):
        """Clean up after each test."""
        # Restore original settings
        settings.collaterals_base_path = self.original_base_path
        
        # Remove test directory
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def create_mock_processor(self):
        """Create a mock background processor for testing."""
        processor = BackgroundTaskProcessor()
        
        # Replace database with our test database
        processor.db = self.db
        
        # Mock task functions for testing
        async def mock_fast_task(task_data):
            """Mock task that completes quickly."""
            await asyncio.sleep(0.01)  # 10ms task
            self.processed_tasks.append({
                "task_id": task_data["task_id"],
                "type": "fast",
                "completion_time": time.time()
            })
        
        async def mock_medium_task(task_data):
            """Mock task that takes moderate time."""
            await asyncio.sleep(0.05)  # 50ms task
            self.processed_tasks.append({
                "task_id": task_data["task_id"],
                "type": "medium",
                "completion_time": time.time()
            })
        
        async def mock_slow_task(task_data):
            """Mock task that takes longer."""
            await asyncio.sleep(0.1)  # 100ms task
            self.processed_tasks.append({
                "task_id": task_data["task_id"],
                "type": "slow",
                "completion_time": time.time()
            })
        
        # Replace function registry with mock functions
        processor.function_registry = {
            "mock_fast_task": mock_fast_task,
            "mock_medium_task": mock_medium_task,
            "mock_slow_task": mock_slow_task,
        }
        
        return processor

    def queue_test_tasks(self, task_configs):
        """Queue multiple test tasks based on configurations."""
        queued_tasks = []
        
        for config in task_configs:
            task_id = f"task_{uuid.uuid4().hex[:8]}"
            entity_id = config.get("entity_id", f"entity_{uuid.uuid4().hex[:8]}")
            function_name = config.get("function_name", "mock_fast_task")
            
            success = self.db.enqueue_task(
                task_id=task_id,
                entity_type=config.get("entity_type", "planner"),
                entity_id=entity_id,
                function_name=function_name
            )
            
            if success:
                queued_tasks.append({
                    "task_id": task_id,
                    "entity_id": entity_id,
                    "function_name": function_name
                })
        
        return queued_tasks

    @patch('asyncio.sleep')
    async def test_processor_task_scanning_efficiency(self, mock_sleep):
        """Test that processor scans for tasks efficiently."""
        processor = self.create_mock_processor()
        
        # Mock sleep to control timing
        mock_sleep.return_value = None
        
        # Queue some test tasks
        task_configs = [
            {"function_name": "mock_fast_task"},
            {"function_name": "mock_medium_task"},
            {"function_name": "mock_fast_task"},
        ]
        queued_tasks = self.queue_test_tasks(task_configs)
        
        # Track scanning performance
        scan_times = []
        original_get_pending = self.db.get_pending_tasks
        
        def time_get_pending():
            start_time = time.time()
            result = original_get_pending()
            scan_times.append(time.time() - start_time)
            return result
        
        self.db.get_pending_tasks = time_get_pending
        
        # Run processor for a limited time
        async def run_limited_processor():
            scan_count = 0
            while scan_count < 5:  # Limit to 5 scans
                pending_tasks = self.db.get_pending_tasks()
                
                if pending_tasks:
                    async with asyncio.TaskGroup() as tg:
                        for task_data in pending_tasks:
                            tg.create_task(processor.execute_task(task_data))
                
                scan_count += 1
                await asyncio.sleep(0.001)  # Minimal sleep for testing
        
        start_time = time.time()
        await run_limited_processor()
        total_time = time.time() - start_time
        
        # Verify scanning efficiency
        self.assertGreater(len(scan_times), 0, "Should have recorded scan times")
        avg_scan_time = sum(scan_times) / len(scan_times)
        self.assertLess(avg_scan_time, 0.01, f"Average scan time {avg_scan_time:.4f}s should be under 10ms")
        
        # Verify all tasks were processed
        self.assertEqual(len(self.processed_tasks), 3, "All tasks should be processed")

    async def test_concurrent_task_execution_efficiency(self):
        """Test that processor executes multiple tasks concurrently."""
        processor = self.create_mock_processor()
        
        # Queue tasks with different execution times
        task_configs = [
            {"function_name": "mock_slow_task", "entity_id": "entity_1"},   # 100ms
            {"function_name": "mock_slow_task", "entity_id": "entity_2"},   # 100ms  
            {"function_name": "mock_slow_task", "entity_id": "entity_3"},   # 100ms
            {"function_name": "mock_medium_task", "entity_id": "entity_4"}, # 50ms
            {"function_name": "mock_fast_task", "entity_id": "entity_5"},   # 10ms
        ]
        queued_tasks = self.queue_test_tasks(task_configs)
        
        # Execute all tasks concurrently
        start_time = time.time()
        
        pending_tasks = self.db.get_pending_tasks()
        
        async with asyncio.TaskGroup() as tg:
            for task_data in pending_tasks:
                tg.create_task(processor.execute_task(task_data))
        
        total_execution_time = time.time() - start_time
        
        # Verify concurrent execution efficiency
        # If tasks ran sequentially: 100+100+100+50+10 = 360ms
        # With concurrency: ~100ms (time of slowest task)
        self.assertLess(total_execution_time, 0.2, 
                       f"Concurrent execution took {total_execution_time:.3f}s, should be under 200ms")
        
        # Verify all tasks completed
        self.assertEqual(len(self.processed_tasks), 5, "All 5 tasks should complete")
        
        # Verify tasks of different types completed
        task_types = [task["type"] for task in self.processed_tasks]
        self.assertIn("fast", task_types)
        self.assertIn("medium", task_types) 
        self.assertIn("slow", task_types)

    async def test_processor_throughput_under_load(self):
        """Test processor throughput under high task load."""
        processor = self.create_mock_processor()
        
        # Create a large number of tasks
        num_tasks = 50
        task_configs = []
        
        for i in range(num_tasks):
            # Mix of task types
            if i % 3 == 0:
                task_type = "mock_fast_task"
            elif i % 3 == 1:
                task_type = "mock_medium_task"
            else:
                task_type = "mock_slow_task"
                
            task_configs.append({
                "function_name": task_type,
                "entity_id": f"entity_{i}",
                "entity_type": "planner"
            })
        
        queued_tasks = self.queue_test_tasks(task_configs)
        
        # Measure throughput
        start_time = time.time()
        
        # Process in batches to simulate realistic load
        batch_size = 10
        for i in range(0, len(queued_tasks), batch_size):
            batch_tasks = self.db.get_pending_tasks()[:batch_size]
            
            if batch_tasks:
                async with asyncio.TaskGroup() as tg:
                    for task_data in batch_tasks:
                        tg.create_task(processor.execute_task(task_data))
        
        total_time = time.time() - start_time
        
        # Calculate throughput metrics
        throughput = len(self.processed_tasks) / total_time
        avg_task_time = total_time / len(self.processed_tasks)
        
        # Verify good throughput
        self.assertGreater(throughput, 20, f"Throughput {throughput:.1f} tasks/sec should be over 20")
        self.assertLess(avg_task_time, 0.1, f"Average task time {avg_task_time:.3f}s should be under 100ms")
        
        # Verify all tasks processed
        self.assertEqual(len(self.processed_tasks), num_tasks, f"Should process all {num_tasks} tasks")

    async def test_task_error_handling_efficiency(self):
        """Test that task errors don't significantly impact processor efficiency."""
        processor = self.create_mock_processor()
        
        # Add an error-prone task function
        async def mock_error_task(task_data):
            """Mock task that randomly fails."""
            if "fail" in task_data.get("payload", {}):
                raise ValueError("Intentional test error")
            await asyncio.sleep(0.02)  # 20ms for successful tasks
            self.processed_tasks.append({
                "task_id": task_data["task_id"],
                "type": "success_after_error_context",
                "completion_time": time.time()
            })
        
        processor.function_registry["mock_error_task"] = mock_error_task
        
        # Queue mix of successful and failing tasks
        successful_tasks = []
        failing_tasks = []
        
        for i in range(10):
            task_id = f"success_task_{i}"
            self.db.enqueue_task(
                task_id=task_id,
                entity_type="planner",
                entity_id=f"entity_{i}",
                function_name="mock_error_task"
            )
            successful_tasks.append(task_id)
        
        for i in range(5):
            task_id = f"fail_task_{i}"
            self.db.enqueue_task(
                task_id=task_id,
                entity_type="planner", 
                entity_id=f"fail_entity_{i}",
                function_name="mock_error_task",
                payload={"fail": True}
            )
            failing_tasks.append(task_id)
        
        # Execute all tasks
        start_time = time.time()
        
        pending_tasks = self.db.get_pending_tasks()
        
        # Execute with error handling
        results = []
        async with asyncio.TaskGroup() as tg:
            for task_data in pending_tasks:
                results.append(tg.create_task(processor.execute_task(task_data)))
        
        total_time = time.time() - start_time
        
        # Verify successful tasks completed
        self.assertEqual(len(self.processed_tasks), 10, "All successful tasks should complete")
        
        # Verify processing time wasn't significantly impacted by errors
        self.assertLess(total_time, 0.5, f"Processing with errors took {total_time:.3f}s, should be under 500ms")
        
        # Verify failed tasks have correct status
        for fail_task_id in failing_tasks:
            task_status = self.db.get_task(fail_task_id)
            self.assertEqual(task_status["status"], "FAILED", f"Task {fail_task_id} should be marked as failed")

    async def test_memory_efficiency_under_load(self):
        """Test that processor doesn't accumulate memory under sustained load."""
        processor = self.create_mock_processor()
        
        # Track memory usage (simplified - in real testing would use memory profiler)
        task_completion_times = []
        
        # Process tasks in multiple rounds to test memory cleanup
        for round_num in range(5):
            round_start = time.time()
            
            # Queue tasks for this round
            task_configs = [
                {"function_name": "mock_fast_task", "entity_id": f"round_{round_num}_entity_{i}"}
                for i in range(10)
            ]
            queued_tasks = self.queue_test_tasks(task_configs)
            
            # Process all tasks in this round
            pending_tasks = self.db.get_pending_tasks()
            
            async with asyncio.TaskGroup() as tg:
                for task_data in pending_tasks:
                    tg.create_task(processor.execute_task(task_data))
            
            round_time = time.time() - round_start
            task_completion_times.append(round_time)
            
            # Small delay between rounds
            await asyncio.sleep(0.01)
        
        # Verify consistent performance across rounds (no memory leaks causing slowdown)
        first_round_time = task_completion_times[0]
        last_round_time = task_completion_times[-1]
        
        # Performance shouldn't degrade significantly
        time_ratio = last_round_time / first_round_time
        self.assertLess(time_ratio, 2.0, f"Performance degraded {time_ratio:.2f}x from first to last round")
        
        # Verify total tasks processed
        expected_total = 5 * 10  # 5 rounds × 10 tasks each
        self.assertEqual(len(self.processed_tasks), expected_total, f"Should process {expected_total} total tasks")

    async def test_task_queue_polling_efficiency(self):
        """Test that task queue polling is efficient and doesn't waste resources."""
        processor = self.create_mock_processor()
        
        # Monitor database query frequency
        query_times = []
        original_get_pending = self.db.get_pending_tasks
        
        def monitored_get_pending():
            query_start = time.time()
            result = original_get_pending()
            query_times.append(time.time() - query_start)
            return result
        
        self.db.get_pending_tasks = monitored_get_pending
        
        # Test with no tasks queued (empty polling)
        start_time = time.time()
        
        # Simulate polling loop for short duration
        poll_count = 0
        max_polls = 10
        
        while poll_count < max_polls:
            pending_tasks = self.db.get_pending_tasks()
            
            if pending_tasks:
                async with asyncio.TaskGroup() as tg:
                    for task_data in pending_tasks:
                        tg.create_task(processor.execute_task(task_data))
            
            poll_count += 1
            await asyncio.sleep(0.01)  # 10ms between polls
        
        total_polling_time = time.time() - start_time
        
        # Verify polling efficiency
        avg_query_time = sum(query_times) / len(query_times)
        self.assertLess(avg_query_time, 0.005, f"Average query time {avg_query_time:.4f}s should be under 5ms")
        
        # Verify polling doesn't consume excessive time
        expected_time = max_polls * 0.01  # Expected ~100ms for 10 polls at 10ms each
        self.assertLess(total_polling_time, expected_time * 2, 
                       f"Polling overhead too high: {total_polling_time:.3f}s vs expected ~{expected_time:.3f}s")

    async def test_concurrent_entity_processing(self):
        """Test that different entities can have tasks processed concurrently."""
        processor = self.create_mock_processor()
        
        # Create tasks for different entities that should run concurrently
        entity_configs = {
            "planner_1": [
                {"function_name": "mock_slow_task", "entity_id": "planner_1"},
                {"function_name": "mock_medium_task", "entity_id": "planner_1"},
            ],
            "planner_2": [
                {"function_name": "mock_slow_task", "entity_id": "planner_2"},
                {"function_name": "mock_fast_task", "entity_id": "planner_2"},
            ],
            "worker_1": [
                {"function_name": "mock_medium_task", "entity_id": "worker_1", "entity_type": "worker"},
                {"function_name": "mock_fast_task", "entity_id": "worker_1", "entity_type": "worker"},
            ]
        }
        
        all_tasks = []
        for entity_id, configs in entity_configs.items():
            all_tasks.extend(self.queue_test_tasks(configs))
        
        # Process all tasks concurrently
        start_time = time.time()
        
        pending_tasks = self.db.get_pending_tasks()
        
        async with asyncio.TaskGroup() as tg:
            for task_data in pending_tasks:
                tg.create_task(processor.execute_task(task_data))
        
        total_time = time.time() - start_time
        
        # Verify concurrent processing across entities
        # Sequential would be much slower than concurrent
        self.assertLess(total_time, 0.3, f"Multi-entity processing took {total_time:.3f}s, should benefit from concurrency")
        
        # Verify all tasks completed
        self.assertEqual(len(self.processed_tasks), 6, "All 6 tasks should complete")
        
        # Verify tasks from all entities were processed
        entity_ids_processed = set()
        for i, task in enumerate(all_tasks):
            # Find corresponding processed task
            processed_task = next((p for p in self.processed_tasks 
                                 if p["task_id"] == task["task_id"]), None)
            self.assertIsNotNone(processed_task, f"Task {task['task_id']} should be processed")
            entity_ids_processed.add(task["entity_id"])
        
        self.assertEqual(len(entity_ids_processed), 3, "Tasks from all 3 entities should be processed")

    async def test_processor_resource_cleanup(self):
        """Test that processor properly cleans up resources after task completion."""
        processor = self.create_mock_processor()
        
        # Track resource usage through task lifecycle
        resource_states = []
        
        async def monitored_task(task_data):
            """Task that monitors resource state during execution."""
            # Simulate resource allocation
            resource_states.append("allocated")
            await asyncio.sleep(0.02)
            
            # Simulate work
            resource_states.append("working")
            
            # Simulate cleanup
            resource_states.append("cleaned_up")
            
            self.processed_tasks.append({
                "task_id": task_data["task_id"],
                "type": "monitored",
                "completion_time": time.time()
            })
        
        processor.function_registry["monitored_task"] = monitored_task
        
        # Queue and execute monitored tasks
        task_configs = [
            {"function_name": "monitored_task", "entity_id": f"entity_{i}"}
            for i in range(3)
        ]
        queued_tasks = self.queue_test_tasks(task_configs)
        
        pending_tasks = self.db.get_pending_tasks()
        
        async with asyncio.TaskGroup() as tg:
            for task_data in pending_tasks:
                tg.create_task(processor.execute_task(task_data))
        
        # Verify resource lifecycle
        expected_states = ["allocated", "working", "cleaned_up"] * 3  # 3 tasks
        self.assertEqual(len(resource_states), len(expected_states), 
                        "All resource lifecycle states should be recorded")
        
        # Verify proper cleanup occurred for all tasks
        cleanup_count = resource_states.count("cleaned_up")
        self.assertEqual(cleanup_count, 3, "All 3 tasks should have cleaned up resources")


if __name__ == '__main__':
    # Run the tests
    unittest.main(verbosity=2)