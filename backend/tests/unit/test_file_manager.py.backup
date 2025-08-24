"""
File Manager Test Suite

Tests for file storage and retrieval operations including variable storage,
image storage, answer templates, and cleanup. Integrates existing file storage test patterns.
"""

import unittest
import tempfile
import shutil
import uuid
import pickle
import json
from unittest.mock import patch, MagicMock
from pathlib import Path

from src.agent.tasks.file_manager import (
    save_planner_variable,
    get_planner_variable,
    save_planner_image,
    get_planner_image,
    save_answer_template,
    load_answer_template,
    save_wip_answer_template,
    load_wip_answer_template,
    save_worker_message_history,
    load_worker_message_history,
    append_to_worker_message_history,
    cleanup_planner_files,
    generate_variable_path,
    generate_image_path,
    clean_image_name
)
from src.agent.config.settings import settings


class TestFileManager(unittest.TestCase):
    """Test file storage and retrieval operations."""

    def setUp(self):
        """Set up test environment with temporary directories."""
        self.test_dir = tempfile.mkdtemp()
        self.original_base_path = settings.collaterals_base_path
        settings.collaterals_base_path = self.test_dir
        
        # Test data
        self.planner_id = f"test_planner_{uuid.uuid4().hex[:8]}"
        self.test_variable_data = {"analysis": "results", "count": 42, "valid": True}
        self.test_image_data = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

    def tearDown(self):
        """Clean up test environment."""
        settings.collaterals_base_path = self.original_base_path
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_variable_storage_and_retrieval(self):
        """Test variable save and load operations."""
        # Save variable
        file_path, final_key = save_planner_variable(
            self.planner_id,
            "test_variable",
            self.test_variable_data,
            check_existing=False
        )
        
        # Verify file was created
        self.assertTrue(Path(file_path).exists())
        self.assertEqual(final_key, "test_variable")
        
        # Load variable
        loaded_data = get_planner_variable(self.planner_id, "test_variable")
        self.assertEqual(loaded_data, self.test_variable_data)

    def test_variable_collision_avoidance(self):
        """Test variable storage with collision avoidance."""
        # Save initial variable
        save_planner_variable(
            self.planner_id,
            "collision_test",
            {"version": 1},
            check_existing=False
        )
        
        # Save with collision checking (should create new name)
        file_path, final_key = save_planner_variable(
            self.planner_id,
            "collision_test",
            {"version": 2},
            check_existing=True
        )
        
        # Should have different key with hex suffix
        self.assertNotEqual(final_key, "collision_test")
        self.assertTrue(final_key.startswith("collision_test_"))
        self.assertEqual(len(final_key), len("collision_test_") + 3)  # 3-char hex suffix
        
        # Verify both variables exist and have different values
        original_data = get_planner_variable(self.planner_id, "collision_test")
        new_data = get_planner_variable(self.planner_id, final_key)
        
        self.assertEqual(original_data["version"], 1)
        self.assertEqual(new_data["version"], 2)

    def test_image_storage_and_retrieval(self):
        """Test image save and load operations."""
        # Save image
        file_path, final_name = save_planner_image(
            self.planner_id,
            "test_chart",
            self.test_image_data,
            check_existing=False
        )
        
        # Verify file was created
        self.assertTrue(Path(file_path).exists())
        self.assertEqual(final_name, "test_chart")
        
        # Load image
        loaded_image = get_planner_image(self.planner_id, "test_chart")
        self.assertEqual(loaded_image, self.test_image_data)

    def test_image_name_cleaning(self):
        """Test image name cleaning removes invalid characters."""
        dirty_names = [
            "chart (final).png",
            "data-analysis/results.jpg", 
            "summary file with spaces.gif",
            "special@chars#here.png"
        ]
        
        expected_cleaned = [
            "chart_final",
            "data_analysis_results",
            "summary_file_with_spaces",
            "special_chars_here"
        ]
        
        for dirty_name, expected in zip(dirty_names, expected_cleaned):
            cleaned = clean_image_name(dirty_name)
            self.assertEqual(cleaned, expected)

    def test_image_collision_avoidance(self):
        """Test image storage with collision avoidance."""
        # Save initial image
        save_planner_image(
            self.planner_id,
            "duplicate_chart",
            "initial_image_data",
            check_existing=False
        )
        
        # Save with collision checking
        file_path, final_name = save_planner_image(
            self.planner_id,
            "duplicate_chart",
            "updated_image_data",
            check_existing=True
        )
        
        # Should have different name with hex suffix
        self.assertNotEqual(final_name, "duplicate_chart")
        self.assertTrue(final_name.startswith("duplicate_chart_"))
        
        # Verify both images exist with different data
        original_image = get_planner_image(self.planner_id, "duplicate_chart")
        new_image = get_planner_image(self.planner_id, final_name)
        
        self.assertEqual(original_image, "initial_image_data")
        self.assertEqual(new_image, "updated_image_data")

    def test_answer_template_operations(self):
        """Test answer template save and load operations."""
        initial_template = "# Analysis Results\n\n## Overview\n[Pending analysis]\n\n## Key Findings\n- [Finding 1]\n- [Finding 2]"
        
        # Save initial template
        result = save_answer_template(self.planner_id, initial_template)
        self.assertTrue(result)
        
        # Load template
        loaded_template = load_answer_template(self.planner_id)
        self.assertEqual(loaded_template, initial_template)
        
        # Update with WIP template
        wip_template = "# Analysis Results\n\n## Overview\nData analysis shows positive trends\n\n## Key Findings\n- [Finding 1]\n- [Finding 2]"
        
        result = save_wip_answer_template(self.planner_id, wip_template)
        self.assertTrue(result)
        
        # Load WIP template
        loaded_wip = load_wip_answer_template(self.planner_id)
        self.assertEqual(loaded_wip, wip_template)
        
        # Original template should be unchanged
        loaded_original = load_answer_template(self.planner_id)
        self.assertEqual(loaded_original, initial_template)

    def test_worker_message_history_operations(self):
        """Test worker message history management."""
        from src.agent.models.tasks import TaskResponseModel
        
        # Create test task responses
        task_responses = [
            TaskResponseModel(
                task_id="worker_1",
                task_description="Analyse data trends",
                task_status="completed",
                assistance_responses="Identified upward trend in Q3 sales"
            ),
            TaskResponseModel(
                task_id="worker_2", 
                task_description="Generate visualisations",
                task_status="completed",
                assistance_responses="Created 3 charts showing revenue trends"
            )
        ]
        
        # Save message history
        result = save_worker_message_history(self.planner_id, task_responses)
        self.assertTrue(result)
        
        # Load message history
        loaded_responses = load_worker_message_history(self.planner_id)
        self.assertEqual(len(loaded_responses), 2)
        self.assertEqual(loaded_responses[0].task_id, "worker_1")
        self.assertEqual(loaded_responses[1].task_id, "worker_2")

    def test_append_to_worker_message_history(self):
        """Test appending single task response to existing history."""
        from src.agent.models.tasks import TaskResponseModel
        
        # Create initial history
        initial_response = TaskResponseModel(
            task_id="worker_initial",
            task_description="Initial task",
            task_status="completed",
            assistance_responses="Initial task completed"
        )
        
        save_worker_message_history(self.planner_id, [initial_response])
        
        # Append new response
        new_response = TaskResponseModel(
            task_id="worker_appended",
            task_description="Appended task", 
            task_status="completed",
            assistance_responses="Appended task completed"
        )
        
        result = append_to_worker_message_history(self.planner_id, new_response)
        self.assertTrue(result)
        
        # Verify history now contains both responses
        loaded_responses = load_worker_message_history(self.planner_id)
        self.assertEqual(len(loaded_responses), 2)
        self.assertEqual(loaded_responses[0].task_id, "worker_initial")
        self.assertEqual(loaded_responses[1].task_id, "worker_appended")

    def test_variable_path_generation(self):
        """Test variable path generation logic."""
        # Basic path generation
        file_path, final_key = generate_variable_path(self.planner_id, "test_var")
        
        expected_path = str(Path(self.test_dir) / self.planner_id / "variables" / "test_var.pkl")
        self.assertEqual(file_path, expected_path)
        self.assertEqual(final_key, "test_var")

    def test_variable_path_collision_handling(self):
        """Test variable path generation with collision handling."""
        # Create existing file to simulate collision
        variables_dir = Path(self.test_dir) / self.planner_id / "variables"
        variables_dir.mkdir(parents=True, exist_ok=True)
        existing_file = variables_dir / "collision_var.pkl"
        existing_file.write_text("existing content")
        
        # Generate path with collision checking
        file_path, final_key = generate_variable_path(
            self.planner_id, 
            "collision_var", 
            check_existing=True
        )
        
        # Should generate new name with hex suffix
        self.assertNotEqual(final_key, "collision_var")
        self.assertTrue(final_key.startswith("collision_var_"))
        self.assertEqual(len(final_key), len("collision_var_") + 3)

    def test_image_path_generation(self):
        """Test image path generation logic."""
        # Basic path generation
        file_path, final_key = generate_image_path(self.planner_id, "test_image")
        
        expected_path = str(Path(self.test_dir) / self.planner_id / "images" / "test_image.b64")
        self.assertEqual(file_path, expected_path)
        self.assertEqual(final_key, "test_image")

    def test_cleanup_planner_files(self):
        """Test cleanup removes all planner artifacts."""
        # Create various planner files
        save_planner_variable(self.planner_id, "cleanup_var", {"data": "test"})
        save_planner_image(self.planner_id, "cleanup_image", "image_data")
        save_answer_template(self.planner_id, "# Test Template")
        save_wip_answer_template(self.planner_id, "# WIP Template")
        
        from src.agent.models.tasks import TaskResponseModel
        save_worker_message_history(self.planner_id, [
            TaskResponseModel(
                task_id="cleanup_worker",
                task_description="Cleanup test",
                task_status="completed", 
                assistance_responses="Test response"
            )
        ])
        
        # Verify files exist
        planner_dir = Path(self.test_dir) / self.planner_id
        self.assertTrue(planner_dir.exists())
        self.assertTrue((planner_dir / "variables").exists())
        self.assertTrue((planner_dir / "images").exists())
        
        # Cleanup
        result = cleanup_planner_files(self.planner_id)
        self.assertTrue(result)
        
        # Verify files are removed
        self.assertFalse(planner_dir.exists())

    def test_lazy_loading_behaviour(self):
        """Test that file loading only reads from disk when called."""
        # Save variable
        save_planner_variable(self.planner_id, "lazy_test", {"initial": "data"})
        
        # Modify file directly on disk
        variables_dir = Path(self.test_dir) / self.planner_id / "variables"
        variable_file = variables_dir / "lazy_test.pkl"
        
        with open(variable_file, 'wb') as f:
            pickle.dump({"modified": "data"}, f)
        
        # Load should return modified data (proving lazy loading)
        loaded_data = get_planner_variable(self.planner_id, "lazy_test")
        self.assertEqual(loaded_data, {"modified": "data"})

    def test_nonexistent_file_handling(self):
        """Test handling of requests for nonexistent files."""
        # Try to load nonexistent variable
        result = get_planner_variable(self.planner_id, "nonexistent_var")
        self.assertIsNone(result)
        
        # Try to load nonexistent image
        result = get_planner_image(self.planner_id, "nonexistent_image")
        self.assertIsNone(result)
        
        # Try to load nonexistent template
        result = load_answer_template(self.planner_id)
        self.assertIsNone(result)
        
        # Try to load nonexistent history
        result = load_worker_message_history(self.planner_id)
        self.assertEqual(result, [])  # Returns empty list

    def test_concurrent_file_operations(self):
        """Test file operations work correctly under concurrent access."""
        import threading
        import time
        
        results = []
        errors = []
        
        def save_variable_worker(index):
            try:
                file_path, final_key = save_planner_variable(
                    self.planner_id,
                    f"concurrent_var_{index}",
                    {"worker": index, "data": f"data_{index}"}
                )
                results.append((index, final_key))
            except Exception as e:
                errors.append((index, str(e)))
        
        # Run concurrent operations
        threads = []
        for i in range(5):
            thread = threading.Thread(target=save_variable_worker, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for completion
        for thread in threads:
            thread.join()
        
        # Verify no errors occurred
        self.assertEqual(len(errors), 0, f"Errors occurred: {errors}")
        
        # Verify all variables were saved
        self.assertEqual(len(results), 5)
        
        # Verify all variables can be loaded
        for index, final_key in results:
            loaded_data = get_planner_variable(self.planner_id, final_key)
            self.assertIsNotNone(loaded_data)
            self.assertEqual(loaded_data["worker"], index)

    def test_large_data_handling(self):
        """Test handling of large data structures."""
        # Create large data structure
        large_data = {
            "large_list": list(range(10000)),
            "nested_dict": {f"key_{i}": f"value_{i}" for i in range(1000)},
            "text_data": "A" * 50000  # 50KB string
        }
        
        # Save large variable
        file_path, final_key = save_planner_variable(
            self.planner_id,
            "large_variable",
            large_data
        )
        
        # Verify file was created
        self.assertTrue(Path(file_path).exists())
        
        # Load and verify data integrity
        loaded_data = get_planner_variable(self.planner_id, "large_variable")
        self.assertEqual(loaded_data["large_list"], large_data["large_list"])
        self.assertEqual(loaded_data["nested_dict"], large_data["nested_dict"])
        self.assertEqual(loaded_data["text_data"], large_data["text_data"])

    def test_special_character_handling(self):
        """Test handling of special characters in data and filenames."""
        # Test data with special characters
        special_data = {
            "unicode": "Hello 🌍 World! 你好",
            "quotes": 'String with "quotes" and \'apostrophes\'',
            "symbols": "Data with @#$%^&*()_+{}[]|\\:;\"'<>?,./"
        }
        
        # Save and load
        save_planner_variable(self.planner_id, "special_chars", special_data)
        loaded_data = get_planner_variable(self.planner_id, "special_chars")
        
        self.assertEqual(loaded_data, special_data)


if __name__ == '__main__':
    unittest.main(verbosity=2)