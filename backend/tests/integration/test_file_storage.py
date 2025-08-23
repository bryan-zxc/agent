"""
Test suite for file storage operations (variables and images).

This test suite validates the file storage system for planner variables and images,
including save/load operations, collision avoidance, and cleanup functionality.
"""

import unittest
import tempfile
import uuid
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
import pickle

# Import the modules under test
from agent.tasks.file_manager import (
    get_planner_path,
    generate_variable_path,
    generate_image_path,
    save_variable_to_file,
    load_variable_from_file,
    save_image_to_file,
    load_image_from_file,
    save_planner_variable,
    save_planner_image,
    get_planner_variable,
    get_planner_image,
    get_planner_variables,
    get_planner_images,
    cleanup_planner_files,
    clean_image_name
)
from agent.config.settings import settings


class TestFileStorage(unittest.TestCase):
    """Test file storage operations for variables and images."""
    
    def setUp(self):
        """Set up test environment before each test."""
        # Create temporary directory for testing
        self.test_dir = tempfile.mkdtemp()
        self.original_base_path = settings.collaterals_base_path
        
        # Mock settings to use test directory
        settings.collaterals_base_path = self.test_dir
        
        # Test data
        self.planner_id = "test_planner_" + uuid.uuid4().hex[:8]
        self.test_variable_data = {"test_key": "test_value", "number": 42}
        self.test_image_data = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        
    def tearDown(self):
        """Clean up after each test."""
        # Restore original settings
        settings.collaterals_base_path = self.original_base_path
        
        # Remove test directory
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_get_planner_path(self):
        """Test planner directory path generation."""
        path = get_planner_path(self.planner_id)
        expected = Path(self.test_dir) / self.planner_id
        self.assertEqual(path, expected)

    def test_generate_variable_path_basic(self):
        """Test basic variable path generation without collision checking."""
        file_path, final_key = generate_variable_path(self.planner_id, "test_var")
        
        expected_path = str(Path(self.test_dir) / self.planner_id / "variables" / "test_var.pkl")
        self.assertEqual(file_path, expected_path)
        self.assertEqual(final_key, "test_var")

    def test_generate_variable_path_with_collision(self):
        """Test variable path generation with collision avoidance."""
        # Create existing file to simulate collision
        base_path = Path(self.test_dir) / self.planner_id / "variables"
        base_path.mkdir(parents=True, exist_ok=True)
        existing_file = base_path / "test_var.pkl"
        existing_file.write_text("existing")
        
        file_path, final_key = generate_variable_path(self.planner_id, "test_var", check_existing=True)
        
        # Should generate new name with hex suffix
        self.assertNotEqual(final_key, "test_var")
        self.assertTrue(final_key.startswith("test_var_"))
        self.assertEqual(len(final_key), len("test_var_") + 3)  # 3-char hex suffix

    def test_generate_image_path_basic(self):
        """Test basic image path generation without collision checking."""
        file_path, final_key = generate_image_path(self.planner_id, "test_img")
        
        expected_path = str(Path(self.test_dir) / self.planner_id / "images" / "test_img.b64")
        self.assertEqual(file_path, expected_path)
        self.assertEqual(final_key, "test_img")

    def test_generate_image_path_with_collision(self):
        """Test image path generation with collision avoidance."""
        # Create existing file to simulate collision
        base_path = Path(self.test_dir) / self.planner_id / "images"
        base_path.mkdir(parents=True, exist_ok=True)
        existing_file = base_path / "test_img.b64"
        existing_file.write_text("existing")
        
        file_path, final_key = generate_image_path(self.planner_id, "test_img", check_existing=True)
        
        # Should generate new name with hex suffix
        self.assertNotEqual(final_key, "test_img")
        self.assertTrue(final_key.startswith("test_img_"))
        self.assertEqual(len(final_key), len("test_img_") + 3)  # 3-char hex suffix

    def test_save_and_load_variable_to_file(self):
        """Test basic variable save and load operations."""
        file_path = str(Path(self.test_dir) / "test_var.pkl")
        
        # Test save
        success = save_variable_to_file(file_path, self.test_variable_data)
        self.assertTrue(success)
        self.assertTrue(Path(file_path).exists())
        
        # Test load
        loaded_data = load_variable_from_file(file_path)
        self.assertEqual(loaded_data, self.test_variable_data)

    def test_load_variable_nonexistent_file(self):
        """Test loading variable from non-existent file."""
        file_path = str(Path(self.test_dir) / "nonexistent.pkl")
        loaded_data = load_variable_from_file(file_path)
        self.assertIsNone(loaded_data)

    def test_save_and_load_image_to_file(self):
        """Test basic image save and load operations."""
        file_path = str(Path(self.test_dir) / "test_img.b64")
        
        # Test save
        success = save_image_to_file(file_path, self.test_image_data)
        self.assertTrue(success)
        self.assertTrue(Path(file_path).exists())
        
        # Test load
        loaded_data = load_image_from_file(file_path)
        self.assertEqual(loaded_data, self.test_image_data)

    def test_load_image_nonexistent_file(self):
        """Test loading image from non-existent file."""
        file_path = str(Path(self.test_dir) / "nonexistent.b64")
        loaded_data = load_image_from_file(file_path)
        self.assertIsNone(loaded_data)

    @patch('agent.tasks.file_manager.AgentDatabase')
    def test_save_planner_variable(self, mock_db_class):
        """Test saving planner variable with database integration."""
        # Mock database
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_db.get_planner.return_value = {"variable_file_paths": {}}
        
        # Test save
        file_path, final_key = save_planner_variable(self.planner_id, "test_var", self.test_variable_data)
        
        # Verify file was created
        self.assertTrue(Path(file_path).exists())
        self.assertEqual(final_key, "test_var")
        
        # Verify database was updated
        mock_db.update_planner_file_paths.assert_called_once()
        call_args = mock_db.update_planner_file_paths.call_args
        self.assertEqual(call_args[0][0], self.planner_id)  # planner_id
        self.assertIn("variable_paths", call_args[1])  # variable_paths in kwargs

    @patch('agent.tasks.file_manager.AgentDatabase')
    def test_save_planner_image(self, mock_db_class):
        """Test saving planner image with database integration."""
        # Mock database
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_db.get_planner.return_value = {"image_file_paths": {}}
        
        # Test save
        file_path, final_key = save_planner_image(self.planner_id, "test_img", self.test_image_data)
        
        # Verify file was created
        self.assertTrue(Path(file_path).exists())
        self.assertEqual(final_key, "test_img")
        
        # Verify database was updated
        mock_db.update_planner_file_paths.assert_called_once()
        call_args = mock_db.update_planner_file_paths.call_args
        self.assertEqual(call_args[0][0], self.planner_id)  # planner_id
        self.assertIn("image_paths", call_args[1])  # image_paths in kwargs

    @patch('agent.tasks.file_manager.AgentDatabase')
    def test_get_planner_variable(self, mock_db_class):
        """Test retrieving planner variable."""
        # Create test file
        test_file = Path(self.test_dir) / "test_var.pkl"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        with open(test_file, 'wb') as f:
            pickle.dump(self.test_variable_data, f)
        
        # Mock database
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_db.get_planner.return_value = {
            "variable_file_paths": {"test_var": str(test_file)}
        }
        
        # Test retrieval
        result = get_planner_variable(self.planner_id, "test_var")
        self.assertEqual(result, self.test_variable_data)

    @patch('agent.tasks.file_manager.AgentDatabase')
    def test_get_planner_image(self, mock_db_class):
        """Test retrieving planner image."""
        # Create test file
        test_file = Path(self.test_dir) / "test_img.b64"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(self.test_image_data)
        
        # Mock database
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_db.get_planner.return_value = {
            "image_file_paths": {"test_img": str(test_file)}
        }
        
        # Test retrieval
        result = get_planner_image(self.planner_id, "test_img")
        self.assertEqual(result, self.test_image_data)

    def test_cleanup_planner_files(self):
        """Test cleanup of planner files."""
        # Create planner directory with files
        planner_dir = Path(self.test_dir) / self.planner_id
        planner_dir.mkdir(parents=True)
        
        # Create some test files
        (planner_dir / "variables").mkdir()
        (planner_dir / "images").mkdir()
        (planner_dir / "variables" / "test.pkl").write_text("test")
        (planner_dir / "images" / "test.b64").write_text("test")
        
        # Verify files exist
        self.assertTrue(planner_dir.exists())
        self.assertTrue((planner_dir / "variables" / "test.pkl").exists())
        
        # Test cleanup
        success = cleanup_planner_files(self.planner_id)
        self.assertTrue(success)
        self.assertFalse(planner_dir.exists())

    def test_clean_image_name(self):
        """Test image name cleaning functionality."""
        existing_names = {"existing_image", "test_img_1"}
        
        # Test basic cleaning
        self.assertEqual(clean_image_name("test-image.jpg", existing_names), "test_image_jpg")
        
        # Test special characters
        self.assertEqual(clean_image_name("test@#$%image", existing_names), "test_image")
        
        # Test repeated underscores
        self.assertEqual(clean_image_name("test___image", existing_names), "test_image")
        
        # Test leading/trailing underscores
        self.assertEqual(clean_image_name("_test_image_", existing_names), "test_image")
        
        # Test empty name fallback
        self.assertEqual(clean_image_name("", existing_names), "image")
        self.assertEqual(clean_image_name("@#$%", existing_names), "image")
        
        # Test duplicate handling
        self.assertEqual(clean_image_name("existing_image", existing_names), "existing_image_1")

    @patch('agent.tasks.file_manager.AgentDatabase')
    def test_collision_avoidance_variables(self, mock_db_class):
        """Test collision avoidance for variables."""
        # Mock database
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_db.get_planner.return_value = {"variable_file_paths": {}}
        
        # Save first variable
        file_path1, key1 = save_planner_variable(self.planner_id, "test_var", {"data": 1})
        self.assertEqual(key1, "test_var")
        
        # Save second variable with same name but collision checking
        file_path2, key2 = save_planner_variable(self.planner_id, "test_var", {"data": 2}, check_existing=True)
        self.assertNotEqual(key2, "test_var")
        self.assertTrue(key2.startswith("test_var_"))
        
        # Verify both files exist and contain different data
        self.assertTrue(Path(file_path1).exists())
        self.assertTrue(Path(file_path2).exists())
        self.assertNotEqual(file_path1, file_path2)

    @patch('agent.tasks.file_manager.AgentDatabase')
    def test_collision_avoidance_images(self, mock_db_class):
        """Test collision avoidance for images."""
        # Mock database
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_db.get_planner.return_value = {"image_file_paths": {}}
        
        # Save first image
        file_path1, key1 = save_planner_image(self.planner_id, "test_img", "image_data_1")
        self.assertEqual(key1, "test_img")
        
        # Save second image with same name but collision checking
        file_path2, key2 = save_planner_image(self.planner_id, "test_img", "image_data_2", check_existing=True)
        self.assertNotEqual(key2, "test_img")
        self.assertTrue(key2.startswith("test_img_"))
        
        # Verify both files exist and contain different data
        self.assertTrue(Path(file_path1).exists())
        self.assertTrue(Path(file_path2).exists())
        self.assertNotEqual(file_path1, file_path2)

    @patch('agent.tasks.file_manager.AgentDatabase')
    def test_get_planner_variables_multiple(self, mock_db_class):
        """Test retrieving multiple planner variables."""
        # Create multiple test files
        var_dir = Path(self.test_dir) / "variables"
        var_dir.mkdir(parents=True)
        
        test_data = {
            "var1": {"data": "value1"},
            "var2": {"data": "value2"},
            "var3": {"data": "value3"}
        }
        
        file_paths = {}
        for var_name, data in test_data.items():
            file_path = var_dir / f"{var_name}.pkl"
            with open(file_path, 'wb') as f:
                pickle.dump(data, f)
            file_paths[var_name] = str(file_path)
        
        # Mock database
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_db.get_planner.return_value = {"variable_file_paths": file_paths}
        
        # Test retrieval
        result = get_planner_variables(self.planner_id)
        self.assertEqual(len(result), 3)
        for var_name, expected_data in test_data.items():
            self.assertIn(var_name, result)
            self.assertEqual(result[var_name], expected_data)

    @patch('agent.tasks.file_manager.AgentDatabase')
    def test_get_planner_images_multiple(self, mock_db_class):
        """Test retrieving multiple planner images."""
        # Create multiple test files
        img_dir = Path(self.test_dir) / "images"
        img_dir.mkdir(parents=True)
        
        test_data = {
            "img1": "encoded_image_data_1",
            "img2": "encoded_image_data_2",
            "img3": "encoded_image_data_3"
        }
        
        file_paths = {}
        for img_name, data in test_data.items():
            file_path = img_dir / f"{img_name}.b64"
            file_path.write_text(data)
            file_paths[img_name] = str(file_path)
        
        # Mock database
        mock_db = MagicMock()
        mock_db_class.return_value = mock_db
        mock_db.get_planner.return_value = {"image_file_paths": file_paths}
        
        # Test retrieval
        result = get_planner_images(self.planner_id)
        self.assertEqual(len(result), 3)
        for img_name, expected_data in test_data.items():
            self.assertIn(img_name, result)
            self.assertEqual(result[img_name], expected_data)


if __name__ == '__main__':
    # Run the tests
    unittest.main(verbosity=2)