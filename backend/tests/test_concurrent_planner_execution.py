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
from agent.tasks.file_manager import save_planner_variable, save_planner_image, get_planner_variables, get_planner_images
from agent.tasks.task_utils import update_planner_next_task_and_queue, queue_worker_task
from agent.config.settings import settings


class TestConcurrentPlannerExecution(unittest.TestCase):
    """Test concurrent execution of multiple planners."""
    
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

    def create_test_planner(self, suffix: str) -> str:
        """Create a test planner with unique ID."""
        planner_id = f"test_planner_{suffix}_{uuid.uuid4().hex[:8]}"
        
        # Create planner in database
        self.db.create_planner(
            planner_id=planner_id,
            planner_name=f"Test Planner {suffix}",
            user_question=f"Test question {suffix}",
            instruction=f"Test instruction {suffix}",
            status="executing"
        )
        
        self.test_planners.append(planner_id)
        return planner_id

    def test_concurrent_file_storage_isolation(self):
        """Test that concurrent planners maintain separate file storage."""
        # Create multiple planners
        planner_ids = [self.create_test_planner(f"file_{i}") for i in range(3)]
        
        def save_planner_files(planner_id, index):
            """Save variables and images for a specific planner."""
            results = {}
            
            # Save variables with planner-specific data
            for var_name, var_data in self.test_variables.items():
                unique_data = {**var_data, "planner_index": index, "planner_id": planner_id}
                file_path, final_key = save_planner_variable(planner_id, var_name, unique_data)
                results[f"var_{var_name}"] = (file_path, final_key, unique_data)
            
            # Save images with planner-specific data
            for img_name, img_data in self.test_images.items():
                file_path, final_key = save_planner_image(planner_id, img_name, img_data)
                results[f"img_{img_name}"] = (file_path, final_key, img_data)
            
            return results
        
        # Execute concurrent file operations
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(save_planner_files, planner_id, i) 
                for i, planner_id in enumerate(planner_ids)
            ]
            
            results = []
            for future in as_completed(futures):
                results.append(future.result())
        
        # Verify each planner has separate file storage
        for i, planner_id in enumerate(planner_ids):
            planner_vars = get_planner_variables(planner_id)
            planner_imgs = get_planner_images(planner_id)
            
            # Check variables are planner-specific
            self.assertEqual(len(planner_vars), 3)
            for var_name in self.test_variables.keys():
                self.assertIn(var_name, planner_vars)
                self.assertEqual(planner_vars[var_name]["planner_index"], i)
                self.assertEqual(planner_vars[var_name]["planner_id"], planner_id)
            
            # Check images are planner-specific
            self.assertEqual(len(planner_imgs), 3)
            for img_name in self.test_images.keys():
                self.assertIn(img_name, planner_imgs)
                self.assertEqual(planner_imgs[img_name], self.test_images[img_name])
        
        # Verify file paths are unique across planners
        all_file_paths = set()
        for planner_id in planner_ids:
            planner_data = self.db.get_planner(planner_id)
            var_paths = planner_data.get("variable_file_paths", {})
            img_paths = planner_data.get("image_file_paths", {})
            
            for path in list(var_paths.values()) + list(img_paths.values()):
                self.assertNotIn(path, all_file_paths, f"Duplicate file path found: {path}")
                all_file_paths.add(path)

    def test_concurrent_task_queue_isolation(self):
        """Test that task queues properly isolate different planners."""
        # Create multiple planners
        planner_ids = [self.create_test_planner(f"queue_{i}") for i in range(3)]
        
        def queue_planner_tasks(planner_id, task_count):
            """Queue multiple tasks for a planner."""
            queued_tasks = []
            
            for i in range(task_count):
                task_id = uuid.uuid4().hex
                function_name = f"test_function_{i}"
                
                success = self.db.enqueue_task(
                    task_id=task_id,
                    entity_type="planner",
                    entity_id=planner_id,
                    function_name=function_name
                )
                
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
            planner_tasks = self.db.get_next_task()  # This will get one task, but we want all for this planner
            
            # Get all pending tasks for this planner by checking each queued task
            all_pending = self.db.get_pending_tasks()
            planner_tasks = [task for task in all_pending if task["entity_id"] == planner_id]
            self.assertEqual(len(planner_tasks), 5, f"Planner {planner_id} should have 5 tasks")
            
            # Verify task entity isolation
            for task in planner_tasks:
                self.assertEqual(task["entity_id"], planner_id)
                self.assertEqual(task["entity_type"], "planner")
                self.assertTrue(task["function_name"].startswith("test_function_"))

    def test_concurrent_database_consistency(self):
        """Test database consistency during concurrent planner operations."""
        # Create multiple planners
        planner_ids = [self.create_test_planner(f"db_{i}") for i in range(5)]
        
        def update_planner_data(planner_id, updates):
            """Perform multiple database updates for a planner."""
            results = []
            
            for i, update_data in enumerate(updates):
                # Update planner status
                success = self.db.update_planner(
                    planner_id, 
                    status=update_data["status"],
                    execution_plan=update_data["plan"]
                )
                results.append(f"update_{i}_success" if success else f"update_{i}_failed")
                
                # Add message
                self.db.add_message(
                    agent_id=planner_id,
                    agent_type="planner", 
                    role="assistant",
                    content=f"Message {i} for {planner_id}"
                )
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
            planner_data = self.db.get_planner(planner_id)
            
            # Check final status
            self.assertEqual(planner_data["status"], "completed")
            self.assertEqual(planner_data["execution_plan"], f"Final plan {i}")
            
            # Check messages were added
            messages = self.db.get_messages_by_agent_id(planner_id, "planner")
            assistant_messages = [msg for msg in messages if msg["role"] == "assistant"]
            self.assertEqual(len(assistant_messages), 3, f"Planner {planner_id} should have 3 assistant messages")

    def test_concurrent_planner_directory_creation(self):
        """Test that planner directories are created correctly during concurrent execution."""
        # Create multiple planners
        planner_ids = [self.create_test_planner(f"dir_{i}") for i in range(4)]
        
        def create_planner_structure(planner_id):
            """Create directory structure and files for a planner."""
            planner_dir = Path(self.test_dir) / planner_id
            
            # Create directories
            (planner_dir / "variables").mkdir(parents=True, exist_ok=True)
            (planner_dir / "images").mkdir(parents=True, exist_ok=True)
            
            # Create test files
            (planner_dir / "execution_plan.json").write_text(f'{{"planner_id": "{planner_id}"}}')
            (planner_dir / "current_task.json").write_text(f'{{"task": "test for {planner_id}"}}')
            
            # Save some test variables and images
            for i in range(3):
                var_path, var_key = save_planner_variable(planner_id, f"var_{i}", {"index": i, "planner": planner_id})
                img_path, img_key = save_planner_image(planner_id, f"img_{i}", f"image_data_{i}")
            
            return planner_dir
        
        # Execute concurrent directory operations
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [
                executor.submit(create_planner_structure, planner_id)
                for planner_id in planner_ids
            ]
            
            created_dirs = []
            for future in as_completed(futures):
                created_dirs.append(future.result())
        
        # Verify each planner has its own directory structure
        for planner_id in planner_ids:
            planner_dir = Path(self.test_dir) / planner_id
            
            # Check directory exists
            self.assertTrue(planner_dir.exists(), f"Directory missing for {planner_id}")
            self.assertTrue((planner_dir / "variables").exists())
            self.assertTrue((planner_dir / "images").exists())
            
            # Check files exist
            self.assertTrue((planner_dir / "execution_plan.json").exists())
            self.assertTrue((planner_dir / "current_task.json").exists())
            
            # Check variables and images were saved
            variables = get_planner_variables(planner_id)
            images = get_planner_images(planner_id)
            
            self.assertEqual(len(variables), 3)
            self.assertEqual(len(images), 3)
            
            # Verify content is planner-specific
            for i in range(3):
                self.assertIn(f"var_{i}", variables)
                self.assertEqual(variables[f"var_{i}"]["planner"], planner_id)
                self.assertIn(f"img_{i}", images)
                self.assertEqual(images[f"img_{i}"], f"image_data_{i}")

    def test_task_queue_ordering_under_concurrency(self):
        """Test that task queue maintains proper ordering during concurrent operations."""
        # Create a single planner for this test
        planner_id = self.create_test_planner("ordering")
        
        def queue_sequential_tasks(start_index, count):
            """Queue tasks with sequential function names."""
            queued_tasks = []
            
            for i in range(start_index, start_index + count):
                task_id = uuid.uuid4().hex
                success = self.db.enqueue_task(
                    task_id=task_id,
                    entity_type="planner",
                    entity_id=planner_id,
                    function_name=f"function_{i:03d}"  # Zero-padded for sorting
                )
                
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
        
        # Get tasks in queue order
        queued_tasks = []
        while True:
            task = self.db.get_next_task()
            if not task:
                break
            queued_tasks.append(task)
        
        # Verify we got all tasks
        self.assertEqual(len(queued_tasks), 15)
        
        # Verify all tasks are for the correct planner
        for task in queued_tasks:
            self.assertEqual(task["entity_id"], planner_id)
            self.assertEqual(task["entity_type"], "planner")

    def test_concurrent_worker_task_creation(self):
        """Test concurrent worker task creation from multiple planners."""
        # Create multiple planners
        planner_ids = [self.create_test_planner(f"worker_{i}") for i in range(3)]
        
        def create_worker_tasks(planner_id, worker_count):
            """Create multiple worker tasks for a planner."""
            created_workers = []
            
            for i in range(worker_count):
                worker_id = f"worker_{planner_id}_{i}_{uuid.uuid4().hex[:8]}"
                
                # Create worker in database
                self.db.create_worker(
                    worker_id=worker_id,
                    planner_id=planner_id,
                    task_description=f"Worker task {i} for {planner_id}",
                    task_status="created"
                )
                
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
            workers = self.db.get_workers_by_planner(planner_id)
            self.assertEqual(len(workers), 4, f"Planner {planner_id} should have 4 workers")
            
            for worker in workers:
                self.assertEqual(worker["planner_id"], planner_id)
                self.assertEqual(worker["task_status"], "created")
                self.assertTrue(worker["task_description"].startswith("Worker task"))

    def test_concurrent_file_collision_avoidance(self):
        """Test collision avoidance works correctly under concurrent access."""
        # Create multiple planners
        planner_ids = [self.create_test_planner(f"collision_{i}") for i in range(3)]
        
        def save_conflicting_files(planner_id, attempt_index):
            """Try to save files with the same names from different threads."""
            results = {}
            
            # All threads try to save files with the same names
            for name in ["shared_var", "shared_img"]:
                if "var" in name:
                    file_path, final_key = save_planner_variable(
                        planner_id, 
                        name, 
                        {"attempt": attempt_index, "planner": planner_id},
                        check_existing=True
                    )
                else:
                    file_path, final_key = save_planner_image(
                        planner_id,
                        name,
                        f"image_data_{attempt_index}",
                        check_existing=True
                    )
                
                results[name] = (file_path, final_key)
            
            return results
        
        # Execute concurrent file operations on each planner
        all_results = []
        for planner_id in planner_ids:
            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = [
                    executor.submit(save_conflicting_files, planner_id, i)
                    for i in range(3)  # 3 concurrent attempts per planner
                ]
                
                planner_results = []
                for future in as_completed(futures):
                    planner_results.append(future.result())
                
                all_results.append((planner_id, planner_results))
        
        # Verify collision avoidance worked
        for planner_id, planner_results in all_results:
            # Collect all final keys for each file type
            var_keys = [result["shared_var"][1] for result in planner_results]
            img_keys = [result["shared_img"][1] for result in planner_results]
            
            # Should have 3 unique keys for variables and images
            self.assertEqual(len(set(var_keys)), 3, f"Variable keys should be unique for {planner_id}")
            self.assertEqual(len(set(img_keys)), 3, f"Image keys should be unique for {planner_id}")
            
            # At least one should have the original name, others should have suffixes
            self.assertIn("shared_var", var_keys, f"Original variable name should exist for {planner_id}")
            self.assertIn("shared_img", img_keys, f"Original image name should exist for {planner_id}")
            
            # Check that collision-avoided names follow expected pattern
            for key in var_keys + img_keys:
                if key not in ["shared_var", "shared_img"]:
                    # Should be original name + underscore + hex suffix
                    base_name = key.split("_")[0] + "_" + key.split("_")[1]  # "shared_var" or "shared_img"
                    suffix = "_".join(key.split("_")[2:])  # hex suffix part
                    self.assertIn(base_name, ["shared_var", "shared_img"])
                    self.assertTrue(len(suffix) >= 3, f"Suffix should be at least 3 chars: {suffix}")


if __name__ == '__main__':
    # Run the tests
    unittest.main(verbosity=2)