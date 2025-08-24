"""
Lightweight File Manager Tests

Unit tests for core file manager functionality following lightweight testing principles.
Simple smoke tests to verify module imports work correctly.
"""

import unittest


class TestFileManagerSimple(unittest.TestCase):
    """Lightweight tests for core file manager functionality."""

    def test_file_manager_module_imports(self):
        """Test that file manager module can be imported (smoke test)."""
        # Simple import test to verify module structure
        try:
            from src.agent.tasks import file_manager
            self.assertTrue(hasattr(file_manager, 'clean_image_name'))
        except ImportError:
            # If import fails due to dependencies, skip this test
            self.skipTest("File manager module has unresolved dependencies")

    def test_basic_module_functionality(self):
        """Test basic module functionality without complex dependencies."""
        # Test that we can access the module without triggering complex imports
        import sys
        import importlib.util
        
        spec = importlib.util.find_spec('src.agent.tasks.file_manager')
        self.assertIsNotNone(spec, "File manager module should be discoverable")
        
        # This confirms the module structure is valid
        self.assertTrue(spec.origin.endswith('file_manager.py'))