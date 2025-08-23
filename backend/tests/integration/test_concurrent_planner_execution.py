"""
Test suite for concurrent planner execution.

This test suite validates that multiple planners can execute concurrently without
interfering with each other, including file storage isolation, task queue management,
and database consistency.
"""

import unittest
import tempfile
import uuid
import shutil
import asyncio
import threading
import time
from pathlib import Path
from unittest.mock import patch, MagicMock
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import the modules under test
from agent.models.agent_database import AgentDatabase
from agent.tasks.planner_tasks import execute_initial_planning, execute_task_creation, execute_synthesis
# File manager imports removed - tests for obsolete architecture patterns
from agent.tasks.task_utils import update_planner_next_task_and_queue, queue_worker_task
from agent.config.settings import settings


class TestConcurrentPlannerExecution(unittest.IsolatedAsyncioTestCase):
    """Test concurrent execution of multiple planners."""
    
    async def asyncSetUp(self):
        """Set up test environment before each test."""
        # Create temporary directory for testing
        self.test_dir = tempfile.mkdtemp()
        self.original_base_path = settings.collaterals_base_path
        
        # Mock settings to use test directory
        settings.collaterals_base_path = self.test_dir
        
        # Set up temporary database for testing
        self.temp_db_file = tempfile.NamedTemporaryFile(delete=False)
        self.db = AgentDatabase(self.temp_db_file.name)
        
        # Test data
        self.test_planners = []
        self.test_variables = {
            "var1": {"data": "value1", "number": 1},
            "var2": {"data": "value2", "number": 2},
            "var3": {"data": "value3", "number": 3}
        }
        self.test_images = {
            "img1": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
            "img2": "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAE0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
            "img3": "iVBORw0KGgoAAAANSUhEUgAAAAMAAAADCAYAAABWKLW/AAAAFklEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        }
        
    def tearDown(self):
        """Clean up after each test."""
        # Restore original settings
        settings.collaterals_base_path = self.original_base_path
        
        # Remove test directory
        shutil.rmtree(self.test_dir, ignore_errors=True)
        
        # Clean up temporary database file
        import os
        try:
            os.unlink(self.temp_db_file.name)
        except (OSError, AttributeError):
            pass  # File already deleted or doesn't exist

    async def create_test_planner(self, suffix: str) -> str:
        """Create a test planner with unique ID."""
        planner_id = f"test_planner_{suffix}_{uuid.uuid4().hex[:8]}"
        
        # Create planner in database
        await self.db.create_planner(
            planner_id=planner_id,
            planner_name=f"Test Planner {suffix}",
            user_question=f"Test question {suffix}",
            instruction=f"Test instruction {suffix}",
            status="executing"
        )
        
        self.test_planners.append(planner_id)
        return planner_id


    async def test_concurrent_task_queue_isolation(self):
        """Test that task queues properly isolate different planners."""
        # Create multiple planners
        planner_ids = []
        for i in range(3):
            planner_id = await self.create_test_planner(f"queue_{i}")
            planner_ids.append(planner_id)
        
        def queue_planner_tasks(planner_id, task_count):
            """Queue multiple tasks for a planner."""
            queued_tasks = []
            
            for i in range(task_count):
                task_id = uuid.uuid4().hex
                function_name = f"test_function_{i}"
                
                success = asyncio.run(self.db.enqueue_task(
                    task_id=task_id,
                    entity_type="planner",
                    entity_id=planner_id,
                    function_name=function_name
                ))
                
                if success:
                    queued_tasks.append((task_id, function_name))
                    
            return queued_tasks
        
        # Execute concurrent task queueing
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(queue_planner_tasks, planner_id, 5) 
                for planner_id in planner_ids
            ]
            
            all_queued_tasks = []
            for future in as_completed(futures):
                all_queued_tasks.extend(future.result())
        
        # Verify each planner has correct tasks
        for i, planner_id in enumerate(planner_ids):
            # Get all pending tasks for this planner
            all_pending = await self.db.get_pending_tasks()
            planner_tasks = [task for task in all_pending if task["entity_id"] == planner_id]
            self.assertEqual(len(planner_tasks), 5, f"Planner {planner_id} should have 5 tasks")
            
            # Verify task entity isolation
            for task in planner_tasks:
                self.assertEqual(task["entity_id"], planner_id)
                self.assertEqual(task["entity_type"], "planner")
                self.assertTrue(task["function_name"].startswith("test_function_"))

    async def test_concurrent_database_consistency(self):
        """Test database consistency during concurrent planner operations."""
        # Create multiple planners
        planner_ids = []
        for i in range(5):
            planner_id = await self.create_test_planner(f"db_{i}")
            planner_ids.append(planner_id)
        
        def update_planner_data(planner_id, updates):
            """Perform multiple database updates for a planner."""
            results = []
            
            for i, update_data in enumerate(updates):
                # Update planner status
                success = asyncio.run(self.db.update_planner(
                    planner_id, 
                    status=update_data["status"],
                    execution_plan=update_data["plan"]
                ))
                results.append(f"update_{i}_success" if success else f"update_{i}_failed")
                
                # Add message
                asyncio.run(self.db.add_message(
                    agent_id=planner_id,
                    agent_type="planner", 
                    role="assistant",
                    content=f"Message {i} for {planner_id}"
                ))
                results.append(f"message_{i}_added")
                
                # Small delay to simulate processing
                time.sleep(0.01)
            
            return results
        
        # Prepare update data for each planner
        update_sets = []
        for i in range(5):
            updates = [
                {"status": "planning", "plan": f"Initial plan {i}"},
                {"status": "executing", "plan": f"Updated plan {i}"},
                {"status": "completed", "plan": f"Final plan {i}"}
            ]
            update_sets.append(updates)
        
        # Execute concurrent database operations
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(update_planner_data, planner_id, updates)
                for planner_id, updates in zip(planner_ids, update_sets)
            ]
            
            all_results = []
            for future in as_completed(futures):
                all_results.append(future.result())
        
        # Verify final database state
        for i, planner_id in enumerate(planner_ids):
            planner_data = await self.db.get_planner(planner_id)
            
            # Check final status
            self.assertEqual(planner_data["status"], "completed")
            self.assertEqual(planner_data["execution_plan"], f"Final plan {i}")
            
            # Check messages were added
            messages = await self.db.get_messages("planner", planner_id)
            assistant_messages = [msg for msg in messages if msg["role"] == "assistant"]
            self.assertEqual(len(assistant_messages), 3, f"Planner {planner_id} should have 3 assistant messages")


    async def test_task_queue_ordering_under_concurrency(self):
        """Test that task queue maintains proper ordering during concurrent operations."""
        # Create a single planner for this test
        planner_id = await self.create_test_planner("ordering")
        
        def queue_sequential_tasks(start_index, count):
            """Queue tasks with sequential function names."""
            queued_tasks = []
            
            for i in range(start_index, start_index + count):
                task_id = uuid.uuid4().hex
                success = asyncio.run(self.db.enqueue_task(
                    task_id=task_id,
                    entity_type="planner",
                    entity_id=planner_id,
                    function_name=f"function_{i:03d}"  # Zero-padded for sorting
                ))
                
                if success:
                    queued_tasks.append((task_id, f"function_{i:03d}"))
                    
                # Small delay to ensure different timestamps
                time.sleep(0.001)
                
            return queued_tasks
        
        # Queue tasks from multiple threads with different start indices
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(queue_sequential_tasks, i * 10, 5)
                for i in range(3)  # 0-4, 10-14, 20-24
            ]
            
            all_queued = []
            for future in as_completed(futures):
                all_queued.extend(future.result())
        
        # Verify all tasks were queued
        self.assertEqual(len(all_queued), 15)  # 3 threads × 5 tasks each
        
        # Get all queued tasks
        queued_tasks = await self.db.get_pending_tasks()
        planner_tasks = [task for task in queued_tasks if task["entity_id"] == planner_id]
        
        # Verify we got all tasks for this planner
        self.assertEqual(len(planner_tasks), 15)
        
        # Verify all tasks are for the correct planner
        for task in planner_tasks:
            self.assertEqual(task["entity_id"], planner_id)
            self.assertEqual(task["entity_type"], "planner")

    async def test_concurrent_worker_task_creation(self):
        """Test concurrent worker task creation from multiple planners."""
        # Create multiple planners
        planner_ids = []
        for i in range(3):
            planner_id = await self.create_test_planner(f"worker_{i}")
            planner_ids.append(planner_id)
        
        def create_worker_tasks(planner_id, worker_count):
            """Create multiple worker tasks for a planner."""
            created_workers = []
            
            for i in range(worker_count):
                worker_id = f"worker_{planner_id}_{i}_{uuid.uuid4().hex[:8]}"
                
                # Create worker in database
                asyncio.run(self.db.create_worker(
                    worker_id=worker_id,
                    planner_id=planner_id,
                    worker_name=f"Test Worker {i}",
                    task_status="created",
                    task_description=f"Worker task {i} for {planner_id}",
                    acceptance_criteria=["Task should complete", "Results should be valid"],
                    user_request="Test concurrent worker creation",
                    wip_answer_template="## Test Results\nPending completion",
                    task_result="",
                    querying_structured_data=False,
                    image_keys=[],
                    variable_keys=[],
                    tools=[],
                    input_variable_filepaths={},
                    input_image_filepaths={},
                    tables=[],
                    filepaths=[]
                ))
                
                # Queue worker task
                success = queue_worker_task(worker_id, planner_id, "worker_initialisation")
                
                if success:
                    created_workers.append(worker_id)
            
            return created_workers
        
        # Execute concurrent worker creation
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(create_worker_tasks, planner_id, 4)
                for planner_id in planner_ids
            ]
            
            all_workers = []
            for future in as_completed(futures):
                all_workers.extend(future.result())
        
        # Verify workers were created correctly
        self.assertEqual(len(all_workers), 12)  # 3 planners × 4 workers each
        
        # Check each planner has the correct workers
        for planner_id in planner_ids:
            workers = await self.db.get_workers_by_planner(planner_id)
            self.assertEqual(len(workers), 4, f"Planner {planner_id} should have 4 workers")
            
            for worker in workers:
                self.assertEqual(worker["planner_id"], planner_id)
                self.assertEqual(worker["task_status"], "created")
                self.assertTrue(worker["task_description"].startswith("Worker task"))



if __name__ == '__main__':
    # Run the tests
    unittest.main(verbosity=2)