"""
Test suite for planner cleanup functionality.

This test suite validates that planner files are properly cleaned up when a planner
completes, including integration testing with the synthesis method.
"""

import unittest
import tempfile
import uuid
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock, call
import asyncio

# Import the modules under test
from agent.tasks.planner_tasks import execute_synthesis
from agent.tasks.file_manager import cleanup_planner_files
from agent.config.settings import settings


class TestPlannerCleanup(unittest.TestCase):
    """Test planner cleanup functionality."""
    
    def setUp(self):
        """Set up test environment before each test."""
        # Create temporary directory for testing
        self.test_dir = tempfile.mkdtemp()
        self.original_base_path = settings.collaterals_base_path
        
        # Mock settings to use test directory
        settings.collaterals_base_path = self.test_dir
        
        # Test data
        self.planner_id = "test_planner_" + uuid.uuid4().hex[:8]
        
    def tearDown(self):
        """Clean up after each test."""
        # Restore original settings
        settings.collaterals_base_path = self.original_base_path
        
        # Remove test directory
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_cleanup_planner_files_empty_directory(self):
        """Test cleanup when planner directory doesn't exist."""
        non_existent_planner = "non_existent_" + uuid.uuid4().hex[:8]
        result = cleanup_planner_files(non_existent_planner)
        self.assertTrue(result)  # Should return True for non-existent directory

    def test_cleanup_planner_files_with_complex_structure(self):
        """Test cleanup of planner directory with complex file structure."""
        # Create complex planner directory structure
        planner_dir = Path(self.test_dir) / self.planner_id
        
        # Create directories and files
        (planner_dir / "variables").mkdir(parents=True)
        (planner_dir / "images").mkdir(parents=True)
        (planner_dir / "temp").mkdir(parents=True)
        
        # Create various files
        (planner_dir / "variables" / "var1.pkl").write_text("variable data 1")
        (planner_dir / "variables" / "var2.pkl").write_text("variable data 2")
        (planner_dir / "images" / "img1.b64").write_text("image data 1")
        (planner_dir / "images" / "img2.b64").write_text("image data 2")
        (planner_dir / "temp" / "temp_file.txt").write_text("temporary data")
        (planner_dir / "execution_plan.json").write_text('{"plan": "test"}')
        (planner_dir / "current_task.json").write_text('{"task": "test"}')
        
        # Create nested directory
        (planner_dir / "nested" / "deep").mkdir(parents=True)
        (planner_dir / "nested" / "deep" / "file.txt").write_text("nested file")
        
        # Verify everything exists
        self.assertTrue(planner_dir.exists())
        self.assertTrue((planner_dir / "variables" / "var1.pkl").exists())
        self.assertTrue((planner_dir / "images" / "img2.b64").exists())
        self.assertTrue((planner_dir / "nested" / "deep" / "file.txt").exists())
        
        # Test cleanup
        result = cleanup_planner_files(self.planner_id)
        
        # Verify cleanup was successful
        self.assertTrue(result)
        self.assertFalse(planner_dir.exists())

    def test_cleanup_planner_files_permission_error_simulation(self):
        """Test cleanup behavior when file deletion fails."""
        # Create planner directory
        planner_dir = Path(self.test_dir) / self.planner_id
        planner_dir.mkdir(parents=True)
        (planner_dir / "test_file.txt").write_text("test")
        
        # Mock shutil.rmtree to raise an exception
        with patch('agent.tasks.file_manager.shutil.rmtree') as mock_rmtree:
            mock_rmtree.side_effect = PermissionError("Permission denied")
            
            result = cleanup_planner_files(self.planner_id)
            
            # Should return False on failure
            self.assertFalse(result)
            mock_rmtree.assert_called_once()

    @patch('agent.tasks.planner_tasks.AgentDatabase')
    @patch('agent.tasks.planner_tasks.load_execution_plan_model')
    @patch('agent.tasks.planner_tasks.save_execution_plan_model')
    @patch('agent.tasks.planner_tasks.cleanup_planner_files')
    def test_synthesis_calls_cleanup_on_completion(self, mock_cleanup, mock_save_plan, mock_load_plan, mock_db_class):
        """Test that synthesis method calls cleanup when planner completes."""
        # Mock database
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        
        # Mock planner data
        mock_db.get_planner.return_value = {
            "planner_id": self.planner_id,
            "status": "executing",
            "execution_plan": "test plan"
        }
        
        # Mock workers - one completed worker
        mock_worker = {
            "worker_id": "worker_1",
            "task_status": "completed",
            "task_description": "Test task",
            "output_variable_filepaths": {},
            "output_image_filepaths": {}
        }
        mock_db.get_workers_by_planner.return_value = [mock_worker]
        mock_db.get_messages.return_value = [
            {"role": "assistant", "content": "Task completed successfully"}
        ]
        
        # Mock execution plan model with no remaining tasks (triggers completion)
        mock_execution_plan = MagicMock()
        mock_execution_plan.todos = []  # No todos left = completion
        mock_load_plan.return_value = mock_execution_plan
        
        # Mock LLM service for final response generation
        with patch('agent.tasks.planner_tasks.LLMService') as mock_llm_service:
            mock_llm = MagicMock()
            mock_llm_service.return_value = mock_llm
            mock_llm.get_response.return_value = MagicMock(content="Final response to user")
            
            # Create task data
            task_data = {"entity_id": self.planner_id}
            
            # Run synthesis
            asyncio.run(execute_synthesis(task_data))
            
            # Verify cleanup was called
            mock_cleanup.assert_called_once_with(self.planner_id)
            
            # Verify planner was marked as completed
            calls = mock_db.update_planner.call_args_list
            completion_call = None
            for call_obj in calls:
                if len(call_obj[1]) > 0 and call_obj[1].get('status') == 'completed':
                    completion_call = call_obj
                    break
            
            self.assertIsNotNone(completion_call, "Planner should be marked as completed")
            self.assertEqual(completion_call[0][0], self.planner_id)  # First positional arg
            self.assertEqual(completion_call[1]['status'], 'completed')

    @patch('agent.tasks.planner_tasks.AgentDatabase')
    @patch('agent.tasks.planner_tasks.load_execution_plan_model')
    @patch('agent.tasks.planner_tasks.save_execution_plan_model')
    @patch('agent.tasks.planner_tasks.cleanup_planner_files')
    def test_synthesis_no_cleanup_when_not_completing(self, mock_cleanup, mock_save_plan, mock_load_plan, mock_db_class):
        """Test that synthesis method does NOT call cleanup when planner is not completing."""
        # Mock database
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        
        # Mock planner data
        mock_db.get_planner.return_value = {
            "planner_id": self.planner_id,
            "status": "executing",
            "execution_plan": "test plan"
        }
        
        # Mock workers - one completed worker
        mock_worker = {
            "worker_id": "worker_1",
            "task_status": "completed",
            "task_description": "Test task",
            "output_variable_filepaths": {},
            "output_image_filepaths": {}
        }
        mock_db.get_workers_by_planner.return_value = [mock_worker]
        mock_db.get_messages.return_value = [
            {"role": "assistant", "content": "Task completed successfully"}
        ]
        
        # Mock execution plan model with remaining tasks (does NOT trigger completion)
        mock_todo = MagicMock()
        mock_todo.completed = False
        mock_todo.obsolete = False
        mock_todo.next_action = False
        mock_todo.description = "Remaining task"
        
        mock_execution_plan = MagicMock()
        mock_execution_plan.todos = [mock_todo]  # Has remaining todos = not complete
        mock_load_plan.return_value = mock_execution_plan
        
        # Mock LLM service for plan updates
        with patch('agent.tasks.planner_tasks.LLMService') as mock_llm_service:
            mock_llm = MagicMock()
            mock_llm_service.return_value = mock_llm
            
            # Mock plan update response
            mock_plan_response = MagicMock()
            mock_plan_response.todos = [mock_todo]  # Return the same todo
            mock_llm.get_response.return_value = mock_plan_response
            
            # Create task data
            task_data = {"entity_id": self.planner_id}
            
            # Run synthesis
            asyncio.run(execute_synthesis(task_data))
            
            # Verify cleanup was NOT called
            mock_cleanup.assert_not_called()
            
            # Verify planner was NOT marked as completed
            calls = mock_db.update_planner.call_args_list
            for call_obj in calls:
                if len(call_obj[1]) > 0:
                    self.assertNotEqual(call_obj[1].get('status'), 'completed')

    def test_cleanup_during_file_operations(self):
        """Test cleanup behavior during active file operations."""
        # Create planner directory with files
        planner_dir = Path(self.test_dir) / self.planner_id
        (planner_dir / "variables").mkdir(parents=True)
        (planner_dir / "images").mkdir(parents=True)
        
        # Create files
        var_file = planner_dir / "variables" / "active_var.pkl"
        img_file = planner_dir / "images" / "active_img.b64"
        var_file.write_text("variable in use")
        img_file.write_text("image in use")
        
        # Simulate file being in use by opening it
        with open(var_file, 'r') as f:
            # While file is open, attempt cleanup
            result = cleanup_planner_files(self.planner_id)
            # On Unix systems, this might still succeed since the file can be deleted
            # while open, but on Windows it might fail
            # We just verify the function doesn't crash
            self.assertIsInstance(result, bool)


if __name__ == '__main__':
    # Run the tests
    unittest.main(verbosity=2)