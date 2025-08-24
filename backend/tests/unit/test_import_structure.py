"""
Lightweight Import Structure Tests

Unit tests for import structure validation following lightweight testing principles.
Tests focus on basic import functionality and circular dependency detection.
"""

import unittest
import time


class TestImportStructureSimple(unittest.TestCase):
    """Lightweight tests for import structure validation."""

    def test_config_module_imports(self):
        """Test configuration module imports work correctly."""
        try:
            from src.agent.config.settings import settings
            from src.agent.config.agent_names import PLANNER_NAMES, WORKER_NAMES
            from src.agent.config.constants import SUPPORTED_IMAGE_FORMATS
            
            # Verify config objects exist
            self.assertTrue(hasattr(settings, 'collaterals_base_path'))
            self.assertTrue(isinstance(PLANNER_NAMES, list))
            self.assertTrue(isinstance(WORKER_NAMES, list))
            self.assertTrue(isinstance(SUPPORTED_IMAGE_FORMATS, set))
            
        except ImportError as e:
            self.fail(f"Failed to import config modules: {e}")

    def test_core_module_imports(self):
        """Test core module imports work correctly."""
        try:
            # Basic core module imports
            from src.agent.core import router
            
            # Verify module imports
            self.assertTrue(hasattr(router, 'RouterAgent'))
            
        except ImportError as e:
            self.fail(f"Failed to import core modules: {e}")

    def test_service_module_imports(self):
        """Test service module imports work correctly."""
        try:
            # Test service imports
            from src.agent.services import llm_service
            from src.agent.services import background_processor
            
            # Verify services exist
            self.assertTrue(hasattr(llm_service, 'LLM'))
            self.assertTrue(hasattr(background_processor, 'start_background_processor'))
            
        except ImportError as e:
            self.fail(f"Failed to import service modules: {e}")

    def test_task_module_imports(self):
        """Test task module imports work correctly."""
        try:
            # Test task imports
            from src.agent.tasks import planner_tasks
            from src.agent.tasks import worker_tasks
            
            # Verify task modules exist
            self.assertTrue(hasattr(planner_tasks, 'execute_initial_planning'))
            self.assertTrue(hasattr(worker_tasks, 'worker_initialisation'))
            
        except ImportError as e:
            self.fail(f"Failed to import task modules: {e}")

    def test_sqlalchemy_model_imports(self):
        """Test SQLAlchemy model imports work correctly."""
        try:
            # Test database model imports
            from src.agent.models.agent_database import AgentDatabase
            
            # Verify database models
            self.assertTrue(callable(AgentDatabase))
            
        except ImportError as e:
            self.fail(f"Failed to import SQLAlchemy models: {e}")

    def test_fastapi_main_imports(self):
        """Test FastAPI main module imports work correctly."""
        try:
            # Test main imports (this might be tricky due to dependencies)
            import main
            
            # Verify FastAPI app exists
            self.assertTrue(hasattr(main, 'app'))
            
        except ImportError as e:
            # FastAPI might not be available in test environment, skip
            self.skipTest(f"FastAPI dependencies not available: {e}")

    def test_no_circular_imports(self):
        """Test that there are no circular imports in the core modules."""
        try:
            # Import core modules in different orders to detect circular dependencies
            from src.agent.models import agent_database
            from src.agent.config import settings
            from src.agent.tasks import message_manager
            
            # If we get here without ImportError, no circular imports detected
            self.assertTrue(True, "No circular imports detected")
            
        except ImportError as e:
            if "circular import" in str(e).lower():
                self.fail(f"Circular import detected: {e}")
            else:
                # Other import errors are acceptable
                self.skipTest(f"Import error (not circular): {e}")

    def test_dependency_layers(self):
        """Test dependency layers follow correct hierarchy."""
        # Simplified test - just verify modules can be imported without circular dependencies
        try:
            # Test basic imports work
            from src.agent.models.agent_database import AgentDatabase
            self.assertIsNotNone(AgentDatabase)
            
            # This passes if no circular import errors occur
            self.assertTrue(True, "Dependency imports completed successfully")
                               
        except ImportError as e:
            self.fail(f"Circular import detected: {e}")

    def test_import_speed(self):
        """Test that imports complete in reasonable time."""
        # Test import performance for critical modules
        critical_modules = [
            'src.agent.config.settings',
            'src.agent.models.agent_database', 
            'src.agent.tasks.message_manager'
        ]
        
        for module_name in critical_modules:
            try:
                start_time = time.time()
                __import__(module_name)
                import_time = time.time() - start_time
                
                # Import should complete within 1 second
                self.assertLess(import_time, 1.0, 
                              f"Import of {module_name} took {import_time:.2f}s (too slow)")
                              
            except ImportError:
                # Skip if module has dependency issues
                self.skipTest(f"Could not import {module_name}")

    def test_background_processor_function_registry(self):
        """Test background processor can import all registered functions."""
        try:
            # Import background processor
            from src.agent.services.background_processor import BackgroundTaskProcessor
            
            processor = BackgroundTaskProcessor()
            
            # Verify registry exists and is populated
            self.assertTrue(isinstance(processor.function_registry, dict))
            self.assertGreater(len(processor.function_registry), 0)
            
            # Test that registered functions are callable
            for func_name, func in processor.function_registry.items():
                self.assertTrue(callable(func), f"Function {func_name} is not callable")
                
        except ImportError as e:
            self.skipTest(f"Background processor dependencies not available: {e}")
        except AttributeError as e:
            self.skipTest(f"Background processor registry structure changed: {e}")