"""
Test suite for file path database validation.

This test suite validates that file paths are correctly stored and retrieved
from the database, ensuring data integrity and proper JSON serialisation.
"""

import unittest
import tempfile
import uuid
import shutil
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

# Import the modules under test
from agent.models.agent_database import AgentDatabase, Planner
from agent.tasks.file_manager import save_planner_variable, save_planner_image
from agent.config.settings import settings


class TestFilePathDatabase(unittest.TestCase):
    """Test file path storage and retrieval in database."""
    
    def setUp(self):
        """Set up test environment before each test."""
        # Create temporary directory for testing
        self.test_dir = tempfile.mkdtemp()
        self.original_base_path = settings.collaterals_base_path
        
        # Mock settings to use test directory
        settings.collaterals_base_path = self.test_dir
        
        # Set up in-memory database for testing
        self.db = AgentDatabase()
        # Use in-memory SQLite database for testing
        self.db.engine = self.db.create_engine("sqlite:///:memory:")
        self.db.Base.metadata.create_all(self.db.engine)
        self.db.SessionLocal = self.db.sessionmaker(bind=self.db.engine)
        
        # Test data
        self.planner_id = "test_planner_" + uuid.uuid4().hex[:8]
        self.test_variable_data = {"test_key": "test_value", "number": 42}
        self.test_image_data = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        
        # Create test planner in database
        self.db.create_planner(
            planner_id=self.planner_id,
            user_question="Test question",
            instruction="Test instruction",
            status="executing"
        )
        
    def tearDown(self):
        """Clean up after each test."""
        # Restore original settings
        settings.collaterals_base_path = self.original_base_path
        
        # Remove test directory
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_update_planner_file_paths_variables_only(self):
        """Test updating only variable file paths."""
        variable_paths = {
            "var1": "/path/to/var1.pkl",
            "var2": "/path/to/var2.pkl",
            "special_var": "/path/with spaces/special.pkl"
        }
        
        # Update variable paths
        success = self.db.update_planner_file_paths(
            self.planner_id, 
            variable_paths=variable_paths
        )
        self.assertTrue(success)
        
        # Verify paths were stored correctly
        planner_data = self.db.get_planner(self.planner_id)
        self.assertEqual(planner_data["variable_file_paths"], variable_paths)
        self.assertEqual(planner_data["image_file_paths"], {})  # Should remain empty

    def test_update_planner_file_paths_images_only(self):
        """Test updating only image file paths."""
        image_paths = {
            "img1": "/path/to/img1.b64",
            "img2": "/path/to/img2.b64",
            "special-img": "/path/with-dashes/special.b64"
        }
        
        # Update image paths
        success = self.db.update_planner_file_paths(
            self.planner_id, 
            image_paths=image_paths
        )
        self.assertTrue(success)
        
        # Verify paths were stored correctly
        planner_data = self.db.get_planner(self.planner_id)
        self.assertEqual(planner_data["image_file_paths"], image_paths)
        self.assertEqual(planner_data["variable_file_paths"], {})  # Should remain empty

    def test_update_planner_file_paths_both(self):
        """Test updating both variable and image file paths."""
        variable_paths = {
            "var1": "/path/to/var1.pkl",
            "var2": "/path/to/var2.pkl"
        }
        image_paths = {
            "img1": "/path/to/img1.b64",
            "img2": "/path/to/img2.b64"
        }
        
        # Update both types of paths
        success = self.db.update_planner_file_paths(
            self.planner_id, 
            variable_paths=variable_paths,
            image_paths=image_paths
        )
        self.assertTrue(success)
        
        # Verify both types were stored correctly
        planner_data = self.db.get_planner(self.planner_id)
        self.assertEqual(planner_data["variable_file_paths"], variable_paths)
        self.assertEqual(planner_data["image_file_paths"], image_paths)

    def test_update_planner_file_paths_incremental(self):
        """Test incremental updates to file paths."""
        # First update - add some variables
        variable_paths_1 = {"var1": "/path/to/var1.pkl"}
        success = self.db.update_planner_file_paths(
            self.planner_id, 
            variable_paths=variable_paths_1
        )
        self.assertTrue(success)
        
        # Second update - add images (should not affect variables)
        image_paths = {"img1": "/path/to/img1.b64"}
        success = self.db.update_planner_file_paths(
            self.planner_id, 
            image_paths=image_paths
        )
        self.assertTrue(success)
        
        # Third update - add more variables (should replace all variables)
        variable_paths_2 = {
            "var1": "/path/to/var1.pkl",
            "var2": "/path/to/var2.pkl"
        }
        success = self.db.update_planner_file_paths(
            self.planner_id, 
            variable_paths=variable_paths_2
        )
        self.assertTrue(success)
        
        # Verify final state
        planner_data = self.db.get_planner(self.planner_id)
        self.assertEqual(planner_data["variable_file_paths"], variable_paths_2)
        self.assertEqual(planner_data["image_file_paths"], image_paths)

    def test_update_planner_file_paths_nonexistent_planner(self):
        """Test updating file paths for non-existent planner."""
        non_existent_planner = "non_existent_" + uuid.uuid4().hex[:8]
        
        success = self.db.update_planner_file_paths(
            non_existent_planner,
            variable_paths={"var1": "/path/to/var1.pkl"}
        )
        self.assertFalse(success)

    def test_file_path_json_serialisation(self):
        """Test that file paths with special characters are properly serialised."""
        special_paths = {
            "unicode_var": "/path/with/üñíçødé/file.pkl",
            "spaces_var": "/path with spaces/file.pkl",
            "symbols_var": "/path/with/@#$%/file.pkl",
            "quotes_var": "/path/with\"quotes\"/file.pkl",
            "backslash_var": "/path\\with\\backslashes\\file.pkl"
        }
        
        # Update with special characters
        success = self.db.update_planner_file_paths(
            self.planner_id,
            variable_paths=special_paths
        )
        self.assertTrue(success)
        
        # Verify special characters are preserved
        planner_data = self.db.get_planner(self.planner_id)
        self.assertEqual(planner_data["variable_file_paths"], special_paths)
        
        # Verify the data can be JSON serialised and deserialised
        json_str = json.dumps(planner_data["variable_file_paths"])
        deserialised = json.loads(json_str)
        self.assertEqual(deserialised, special_paths)

    def test_empty_file_paths_update(self):
        """Test updating with empty dictionaries."""
        # First, add some paths
        initial_vars = {"var1": "/path/to/var1.pkl"}
        initial_imgs = {"img1": "/path/to/img1.b64"}
        
        self.db.update_planner_file_paths(
            self.planner_id,
            variable_paths=initial_vars,
            image_paths=initial_imgs
        )
        
        # Clear variables with empty dict
        success = self.db.update_planner_file_paths(
            self.planner_id,
            variable_paths={}
        )
        self.assertTrue(success)
        
        # Verify variables cleared but images remain
        planner_data = self.db.get_planner(self.planner_id)
        self.assertEqual(planner_data["variable_file_paths"], {})
        self.assertEqual(planner_data["image_file_paths"], initial_imgs)

    def test_large_file_path_dictionary(self):
        """Test handling large dictionaries of file paths."""
        # Create large dictionary
        large_variable_paths = {}
        large_image_paths = {}
        
        for i in range(100):
            large_variable_paths[f"var_{i}"] = f"/path/to/variables/var_{i}.pkl"
            large_image_paths[f"img_{i}"] = f"/path/to/images/img_{i}.b64"
        
        # Update with large dictionaries
        success = self.db.update_planner_file_paths(
            self.planner_id,
            variable_paths=large_variable_paths,
            image_paths=large_image_paths
        )
        self.assertTrue(success)
        
        # Verify all paths stored correctly
        planner_data = self.db.get_planner(self.planner_id)
        self.assertEqual(len(planner_data["variable_file_paths"]), 100)
        self.assertEqual(len(planner_data["image_file_paths"]), 100)
        self.assertEqual(planner_data["variable_file_paths"], large_variable_paths)
        self.assertEqual(planner_data["image_file_paths"], large_image_paths)

    def test_file_path_database_consistency_with_file_manager(self):
        """Test that file manager operations correctly update database paths."""
        # Create actual files and use file manager to save
        test_variable = {"data": "test_value"}
        test_image = "test_image_data"
        
        # Use file manager to save variable
        file_path_var, final_key_var = save_planner_variable(
            self.planner_id, 
            "test_var", 
            test_variable
        )
        
        # Use file manager to save image  
        file_path_img, final_key_img = save_planner_image(
            self.planner_id,
            "test_img",
            test_image
        )
        
        # Verify database was updated with correct paths
        planner_data = self.db.get_planner(self.planner_id)
        
        self.assertIn(final_key_var, planner_data["variable_file_paths"])
        self.assertIn(final_key_img, planner_data["image_file_paths"])
        
        self.assertEqual(planner_data["variable_file_paths"][final_key_var], file_path_var)
        self.assertEqual(planner_data["image_file_paths"][final_key_img], file_path_img)
        
        # Verify files actually exist at the stored paths
        self.assertTrue(Path(file_path_var).exists())
        self.assertTrue(Path(file_path_img).exists())

    def test_file_path_database_validation_after_collision_avoidance(self):
        """Test database paths are correct after collision avoidance."""
        # Create existing file to trigger collision avoidance
        existing_var_path = Path(self.test_dir) / self.planner_id / "variables"
        existing_var_path.mkdir(parents=True, exist_ok=True)
        existing_file = existing_var_path / "collision_var.pkl"
        existing_file.write_text("existing")
        
        # Save variable with collision checking (should get new name)
        file_path, final_key = save_planner_variable(
            self.planner_id,
            "collision_var",
            {"data": "new_value"},
            check_existing=True
        )
        
        # Verify database has the collision-avoided key and path
        planner_data = self.db.get_planner(self.planner_id)
        
        self.assertNotEqual(final_key, "collision_var")
        self.assertTrue(final_key.startswith("collision_var_"))
        self.assertIn(final_key, planner_data["variable_file_paths"])
        self.assertEqual(planner_data["variable_file_paths"][final_key], file_path)
        
        # Verify the file exists at the stored path
        self.assertTrue(Path(file_path).exists())

    def test_database_file_path_retrieval_performance(self):
        """Test that file path retrieval from database is efficient."""
        # Add multiple variables and images
        variable_paths = {f"var_{i}": f"/path/to/var_{i}.pkl" for i in range(50)}
        image_paths = {f"img_{i}": f"/path/to/img_{i}.b64" for i in range(50)}
        
        self.db.update_planner_file_paths(
            self.planner_id,
            variable_paths=variable_paths,
            image_paths=image_paths
        )
        
        # Test retrieval multiple times to check consistency
        for _ in range(10):
            planner_data = self.db.get_planner(self.planner_id)
            self.assertEqual(len(planner_data["variable_file_paths"]), 50)
            self.assertEqual(len(planner_data["image_file_paths"]), 50)
            
            # Verify specific entries
            self.assertEqual(planner_data["variable_file_paths"]["var_25"], "/path/to/var_25.pkl")
            self.assertEqual(planner_data["image_file_paths"]["img_25"], "/path/to/img_25.b64")

    def test_null_and_none_file_path_handling(self):
        """Test handling of None values in file path updates."""
        # Add initial paths
        initial_vars = {"var1": "/path/to/var1.pkl"}
        initial_imgs = {"img1": "/path/to/img1.b64"}
        
        self.db.update_planner_file_paths(
            self.planner_id,
            variable_paths=initial_vars,
            image_paths=initial_imgs
        )
        
        # Update with None (should not change existing values)
        success = self.db.update_planner_file_paths(
            self.planner_id,
            variable_paths=None,
            image_paths=None
        )
        self.assertTrue(success)
        
        # Verify values unchanged
        planner_data = self.db.get_planner(self.planner_id)
        self.assertEqual(planner_data["variable_file_paths"], initial_vars)
        self.assertEqual(planner_data["image_file_paths"], initial_imgs)


if __name__ == '__main__':
    # Run the tests
    unittest.main(verbosity=2)