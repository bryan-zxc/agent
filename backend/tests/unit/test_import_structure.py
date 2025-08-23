"""
Import Structure Test Suite

Tests to ensure all modules import correctly without circular dependencies.
Validates function registry imports and model exports.
"""

import unittest
import sys
import importlib
from unittest.mock import patch


class TestImportStructure(unittest.TestCase):
    """Test import structure and dependencies."""

    def test_core_module_imports(self):
        """Test core module imports work correctly."""
        try:
            from src.agent.core.router import RouterAgent
            from src.agent.core import router
            self.assertTrue(hasattr(router, 'RouterAgent'))
        except ImportError as e:
            self.fail(f"Failed to import core modules: {e}")

    def test_model_module_imports(self):
        """Test all model modules import correctly."""
        try:
            from src.agent.models.agent_database import AgentDatabase
            from src.agent.models.responses import RequestResponse, TaskResponse
            from src.agent.models.schemas import File, ImageElement, PDFContent
            from src.agent.models.tasks import Task, TaskContext, FullTask
            from src.agent.models import tasks, schemas, responses
            
            # Verify key classes are available
            self.assertTrue(hasattr(tasks, 'Task'))
            self.assertTrue(hasattr(schemas, 'File'))
            self.assertTrue(hasattr(responses, 'RequestResponse'))
            
        except ImportError as e:
            self.fail(f"Failed to import model modules: {e}")

    def test_models_init_exports(self):
        """Test models/__init__.py exports work correctly."""
        try:
            # This should work based on centralised exports pattern
            from src.agent.models import (
                AgentDatabase, 
                RequestResponse, 
                TaskResponse,
                File,
                Task,
                TaskContext
            )
            
            # Verify classes are correctly imported
            self.assertTrue(callable(AgentDatabase))
            self.assertTrue(hasattr(RequestResponse, '__annotations__'))
            self.assertTrue(hasattr(File, '__annotations__'))
            
        except ImportError as e:
            self.fail(f"Failed to import from models.__init__: {e}")

    def test_service_module_imports(self):
        """Test service layer imports work correctly."""
        try:
            from src.agent.services.llm_service import LLM
            from src.agent.services.document_service import extract_document_content
            from src.agent.services.image_service import is_image, process_image_file
            from src.agent.services.background_processor import BackgroundTaskProcessor
            
            # Verify services can be instantiated/called
            self.assertTrue(callable(LLM))
            self.assertTrue(callable(extract_document_content))
            self.assertTrue(callable(is_image))
            self.assertTrue(callable(BackgroundTaskProcessor))
            
        except ImportError as e:
            self.fail(f"Failed to import service modules: {e}")

    def test_task_module_imports(self):
        """Test task function imports work correctly."""
        try:
            from src.agent.tasks.planner_tasks import (
                execute_initial_planning,
                execute_task_creation,
                execute_synthesis
            )
            from src.agent.tasks.worker_tasks import (
                worker_initialisation,
                execute_standard_worker,
                execute_sql_worker
            )
            from src.agent.tasks.file_manager import (
                save_planner_variable,
                get_planner_variable,
                save_planner_image,
                get_planner_image
            )
            from src.agent.tasks.task_utils import update_planner_next_task_and_queue
            
            # Verify all functions are callable
            functions_to_test = [
                execute_initial_planning,
                execute_task_creation,
                execute_synthesis,
                worker_initialisation,
                execute_standard_worker,
                execute_sql_worker,
                save_planner_variable,
                get_planner_variable,
                save_planner_image,
                get_planner_image,
                update_planner_next_task_and_queue
            ]
            
            for func in functions_to_test:
                self.assertTrue(callable(func), f"{func.__name__} is not callable")
                
        except ImportError as e:
            self.fail(f"Failed to import task modules: {e}")

    def test_utils_module_imports(self):
        """Test utility module imports work correctly."""
        try:
            from src.agent.utils.file_utils import calculate_file_hash, sanitise_filename
            from src.agent.utils.async_error_utils import AsyncErrorLogger
            from src.agent.utils.image_utils import is_image_file
            from src.agent.utils.execution_plan_converter import markdown_to_execution_plan
            
            # Verify utilities are callable
            self.assertTrue(callable(calculate_file_hash))
            self.assertTrue(callable(sanitise_filename))
            self.assertTrue(callable(AsyncErrorLogger))
            self.assertTrue(callable(is_image_file))
            self.assertTrue(callable(markdown_to_execution_plan))
            
        except ImportError as e:
            self.fail(f"Failed to import utility modules: {e}")

    def test_config_module_imports(self):
        """Test configuration module imports work correctly."""
        try:
            from src.agent.config.settings import settings
            from src.agent.config.agent_names import PLANNER_NAMES, WORKER_NAMES
            from src.agent.config.constants import SUPPORTED_IMAGE_TYPES
            
            # Verify config objects exist
            self.assertTrue(hasattr(settings, 'collaterals_base_path'))
            self.assertTrue(isinstance(PLANNER_NAMES, list))
            self.assertTrue(isinstance(WORKER_NAMES, list))
            self.assertTrue(isinstance(SUPPORTED_IMAGE_TYPES, list))
            
        except ImportError as e:
            self.fail(f"Failed to import config modules: {e}")

    def test_background_processor_function_registry(self):
        """Test background processor can import all registered functions."""
        try:
            from src.agent.services.background_processor import BackgroundTaskProcessor
            
            processor = BackgroundTaskProcessor()
            
            # Check that function registry is populated
            self.assertTrue(hasattr(processor, 'function_registry'))
            self.assertIsInstance(processor.function_registry, dict)
            
            # Verify key planner functions are registered
            expected_functions = [
                'execute_initial_planning',
                'execute_task_creation', 
                'execute_synthesis',
                'worker_initialisation',
                'execute_standard_worker',
                'execute_sql_worker'
            ]
            
            for func_name in expected_functions:
                self.assertIn(func_name, processor.function_registry, 
                            f"Function {func_name} not in registry")
                self.assertTrue(callable(processor.function_registry[func_name]),
                              f"Function {func_name} is not callable")
                
        except ImportError as e:
            self.fail(f"Failed to test function registry: {e}")

    def test_no_circular_imports(self):
        """Test for circular import dependencies."""
        # Test common circular import patterns
        problematic_imports = [
            # models importing from tasks 
            ('src.agent.models.agent_database', 'src.agent.tasks.planner_tasks'),
            # core importing from models and models importing from core
            ('src.agent.core.router', 'src.agent.models.agent_database'),
            # services importing from tasks
            ('src.agent.services.background_processor', 'src.agent.tasks.planner_tasks'),
        ]
        
        for module1_name, module2_name in problematic_imports:
            with self.subTest(modules=f"{module1_name} <-> {module2_name}"):
                try:
                    # Try importing both modules
                    module1 = importlib.import_module(module1_name)
                    module2 = importlib.import_module(module2_name)
                    
                    # If we get here, no circular import occurred
                    self.assertTrue(True)
                    
                except ImportError as e:
                    if "circular import" in str(e).lower():
                        self.fail(f"Circular import detected between {module1_name} and {module2_name}: {e}")
                    else:
                        # Other import error, re-raise for debugging
                        raise

    def test_pydantic_model_imports(self):
        """Test Pydantic model imports and validation."""
        try:
            from src.agent.models.schemas import File, ImageElement
            from src.agent.models.tasks import Task, TaskContext
            from src.agent.models.responses import RequestResponse
            
            # Test that models have Pydantic features
            self.assertTrue(hasattr(File, 'model_validate'))
            self.assertTrue(hasattr(ImageElement, 'model_validate'))
            self.assertTrue(hasattr(Task, 'model_validate'))
            self.assertTrue(hasattr(TaskContext, 'model_validate'))
            self.assertTrue(hasattr(RequestResponse, 'model_validate'))
            
        except ImportError as e:
            self.fail(f"Failed to import Pydantic models: {e}")

    def test_sqlalchemy_model_imports(self):
        """Test SQLAlchemy model imports work correctly."""
        try:
            from src.agent.models.agent_database import (
                Router, 
                PlannerMessage, 
                WorkerMessage,
                RouterMessage,
                Planner,
                Worker,
                TaskQueue,
                RouterPlannerLink,
                RouterMessagePlannerLink
            )
            
            # Verify SQLAlchemy model features
            models_to_test = [
                Router, PlannerMessage, WorkerMessage, RouterMessage,
                Planner, Worker, TaskQueue, RouterPlannerLink, RouterMessagePlannerLink
            ]
            
            for model in models_to_test:
                self.assertTrue(hasattr(model, '__tablename__'))
                self.assertTrue(hasattr(model, '__table__'))
                
        except ImportError as e:
            self.fail(f"Failed to import SQLAlchemy models: {e}")

    def test_fastapi_main_imports(self):
        """Test main FastAPI application imports work correctly."""
        try:
            from main import app
            from fastapi import FastAPI
            
            self.assertIsInstance(app, FastAPI)
            
            # Verify key components can be imported alongside main
            from src.agent.core.router import RouterAgent  
            from src.agent.models.agent_database import AgentDatabase
            from src.agent.services.background_processor import start_background_processor
            
            self.assertTrue(callable(RouterAgent))
            self.assertTrue(callable(AgentDatabase))
            self.assertTrue(callable(start_background_processor))
            
        except ImportError as e:
            self.fail(f"Failed to import main application: {e}")

    def test_import_speed(self):
        """Test that imports complete within reasonable time."""
        import time
        
        modules_to_test = [
            'src.agent.core.router',
            'src.agent.models.agent_database', 
            'src.agent.services.llm_service',
            'src.agent.tasks.planner_tasks',
            'src.agent.tasks.worker_tasks'
        ]
        
        for module_name in modules_to_test:
            with self.subTest(module=module_name):
                start_time = time.time()
                
                # Remove from cache if present to test actual import time
                if module_name in sys.modules:
                    del sys.modules[module_name]
                
                importlib.import_module(module_name)
                
                import_time = time.time() - start_time
                
                # Import should complete within 1 second
                self.assertLess(import_time, 1.0, 
                              f"Import of {module_name} took {import_time:.2f}s (too slow)")

    def test_dependency_layers(self):
        """Test dependency layers follow correct hierarchy."""
        # Test that database layer doesn't import from higher layers
        try:
            import sys
            from src.agent.models.agent_database import AgentDatabase
            
            # Database should not import core or services
            prohibited_imports = [
                'src.agent.core.router',
                'src.agent.services.llm_service',
                'src.agent.tasks.planner_tasks'
            ]
            
            for prohibited in prohibited_imports:
                self.assertNotIn(prohibited, sys.modules.get('src.agent.models.agent_database', [].__dict__),
                               f"Database layer should not import {prohibited}")
                               
        except ImportError as e:
            self.fail(f"Failed dependency layer test: {e}")


if __name__ == '__main__':
    unittest.main(verbosity=2)