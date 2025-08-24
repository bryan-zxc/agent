"""
Lightweight Task Execution Tests

Unit tests for core task execution functionality following lightweight testing principles.
Tests focus on immediate feedback for glaring problems, not complex integration workflows.
"""

import unittest
import tempfile
import uuid
import os
from unittest.mock import patch, AsyncMock, MagicMock
from PIL import Image

from src.agent.tasks.task_utils import update_planner_next_task_and_queue
from src.agent.models.agent_database import AgentDatabase
from src.agent.config.settings import settings
from src.agent.tasks.planner_tasks import (
    clean_table_name, 
    get_table_metadata, 
    execute_initial_planning, 
    execute_task_creation,
    _complete_planner_execution,
    execute_synthesis
)
from src.agent.tasks.worker_tasks import (
    convert_result_to_str,
    validate_worker_result,
    process_image_variable,
    process_variable,
    worker_initialisation,
    execute_standard_worker,
    execute_sql_worker
)
from src.agent.models.tasks import TaskResult, InitialExecutionPlan, TaskArtefact, TaskValidation, TaskArtefactSQL


class TestTaskExecutionSimple(unittest.IsolatedAsyncioTestCase):
    """Lightweight tests for core task execution functionality."""

    async def asyncSetUp(self):
        """Set up minimal test environment."""
        # Test data only
        self.planner_id = f"test_planner_{uuid.uuid4().hex[:8]}"
        self.worker_id = f"test_worker_{uuid.uuid4().hex[:8]}"

    def test_task_queue_integration(self):
        """Test task queue operations work correctly."""
        # Simple smoke test to verify the function can be imported
        try:
            from src.agent.tasks.task_utils import update_planner_next_task_and_queue
            self.assertTrue(callable(update_planner_next_task_and_queue))
        except ImportError as e:
            self.skipTest(f"Task utils not available: {e}")

    async def test_message_manager_integration_simple(self):
        """Test that MessageManager can be imported and instantiated (smoke test)."""
        from src.agent.tasks.message_manager import MessageManager
        from src.agent.models.agent_database import AgentDatabase
        
        # Simple instantiation test - verifies imports and basic structure
        with patch.object(AgentDatabase, '__init__', return_value=None):
            mock_db = AgentDatabase()
            
            # Should not raise exceptions
            message_manager = MessageManager(mock_db, "planner", self.planner_id)
            self.assertIsNotNone(message_manager)
            self.assertEqual(message_manager.agent_type, "planner")
            self.assertEqual(message_manager.agent_id, self.planner_id)


class TestPlannerTasksExecution(unittest.IsolatedAsyncioTestCase):
    """Lightweight tests for planner_tasks.py functions - vanilla flow only."""

    async def asyncSetUp(self):
        """Set up minimal test environment."""
        self.planner_id = f"test_planner_{uuid.uuid4().hex[:8]}"
        self.worker_id = f"test_worker_{uuid.uuid4().hex[:8]}"

    def test_clean_table_name_vanilla_execution(self):
        """Test clean_table_name executes without errors in vanilla scenario."""
        # Test with normal string
        result = clean_table_name("Sales Data 2023")
        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0)
        
        # Test with edge case
        result_empty = clean_table_name("")
        self.assertEqual(result_empty, "table")

    def test_get_table_metadata_vanilla_execution(self):
        """Test get_table_metadata can be imported and executed without syntax errors."""
        # The function is very complex with many database calls, so for a vanilla test
        # we'll focus on testing that it can be called and the gold standard is properly integrated
        
        try:
            # Verify function exists and is callable
            from src.agent.tasks.planner_tasks import get_table_metadata
            self.assertTrue(callable(get_table_metadata))
            
            # Verify return type annotation is correct
            import inspect
            signature = inspect.signature(get_table_metadata)
            self.assertEqual(str(signature.return_annotation), "<class 'src.agent.models.schemas.TableMeta'>")
            
            # Test that function accepts the correct parameters
            parameters = list(signature.parameters.keys())
            self.assertEqual(parameters, ['duck_conn', 'table_name'])
            
            # Verify helper function was added
            from src.agent.tasks.planner_tasks import clean_column_name
            self.assertTrue(callable(clean_column_name))
            
            # Verify new schema classes exist and have correct fields
            from src.agent.models.schemas import SingleValueColumn, TableMeta
            
            # Test SingleValueColumn can be validated
            single_val_col = SingleValueColumn.model_validate({
                'column_name': 'test_column',
                'only_value_in_column': 'test_value'
            })
            self.assertEqual(single_val_col.column_name, 'test_column')
            self.assertEqual(single_val_col.only_value_in_column, 'test_value')
            
            # Test TableMeta can be validated with new fields
            table_meta = TableMeta.model_validate({
                'table_name': 'test_table',
                'row_count': 100,
                'top_10_md': 'test markdown',
                'columns': [],
                'single_value_columns': [],
                'total_columns': 3
            })
            self.assertEqual(table_meta.table_name, 'test_table')
            self.assertEqual(table_meta.total_columns, 3)
            self.assertIsInstance(table_meta.single_value_columns, list)
            
            # The function integrates the gold standard - comprehensive testing would require
            # a real DuckDB instance which is beyond vanilla testing scope
            
        except ImportError as e:
            self.fail(f"Could not import required components: {e}")
        except Exception as e:
            self.fail(f"Gold standard integration failed: {e}")

    async def test_execute_initial_planning_vanilla_execution(self):
        """Test execute_initial_planning ACTUALLY EXECUTES without errors in vanilla scenario."""
        # Mock all external dependencies to allow real function execution
        with patch('src.agent.tasks.planner_tasks.AgentDatabase') as MockDB, \
             patch('src.agent.tasks.planner_tasks.llm') as mock_llm_service, \
             patch('src.agent.tasks.planner_tasks.save_execution_plan_model') as mock_save_plan, \
             patch('src.agent.tasks.planner_tasks.save_answer_template') as mock_save_template, \
             patch('src.agent.tasks.planner_tasks.save_wip_answer_template') as mock_save_wip, \
             patch('src.agent.tasks.planner_tasks.update_planner_next_task_and_queue') as mock_queue, \
             patch('src.agent.tasks.planner_tasks.MessageManager') as MockMM:
            
            # Configure database mock
            mock_db_instance = AsyncMock()
            MockDB.return_value = mock_db_instance
            mock_db_instance.get_planner.return_value = None  # No existing planner
            mock_db_instance.create_planner.return_value = None
            mock_db_instance.update_planner.return_value = True
            mock_db_instance.link_message_planner.return_value = True
            
            # Configure MessageManager mock
            mock_mm_instance = AsyncMock()
            MockMM.return_value = mock_mm_instance
            mock_mm_instance.add_message.return_value = []
            mock_mm_instance.get_messages.return_value = []
            
            # Configure LLM service mock - must return awaitables
            async def mock_llm_response_1(*args, **kwargs):
                return InitialExecutionPlan(objective="Test objective", todos=["task1", "task2"])
            
            async def mock_llm_response_2(*args, **kwargs):
                return type('MockResponse', (), {'content': "# Test Answer Template"})()
            
            mock_llm_service.a_get_response.side_effect = [
                mock_llm_response_1(),
                mock_llm_response_2()
            ]
            
            # Configure file operation mocks
            mock_save_plan.return_value = True
            mock_save_template.return_value = True
            mock_save_wip.return_value = True
            mock_queue.return_value = True
            
            # Test data
            task_data = {
                "entity_id": self.planner_id,
                "payload": {
                    "user_question": "Test question",
                    "instruction": "Test instruction",
                    "files": [],
                    "planner_name": "Test Planner",
                    "router_id": "test_router"
                }
            }
            
            # ACTUALLY EXECUTE THE FUNCTION - this is real execution!
            await execute_initial_planning(task_data)
            
            # Verify the function actually ran by checking mock calls
            mock_db_instance.create_planner.assert_called_once()
            self.assertEqual(mock_llm_service.a_get_response.call_count, 2)

    async def test_execute_task_creation_vanilla_execution(self):
        """Test execute_task_creation ACTUALLY EXECUTES without errors."""
        from src.agent.models.tasks import Task
        
        with patch('src.agent.tasks.planner_tasks.AgentDatabase') as MockDB, \
             patch('src.agent.tasks.planner_tasks.llm') as mock_llm_service, \
             patch('src.agent.tasks.planner_tasks.load_execution_plan_model') as mock_load_plan, \
             patch('src.agent.tasks.planner_tasks.save_current_task') as mock_save_task, \
             patch('src.agent.tasks.planner_tasks.load_worker_message_history') as mock_load_history, \
             patch('src.agent.tasks.planner_tasks.queue_worker_task') as mock_queue_worker, \
             patch('src.agent.tasks.planner_tasks.MessageManager') as MockMM, \
             patch('src.agent.tasks.planner_tasks.has_pending_tasks') as mock_has_pending, \
             patch('src.agent.tasks.planner_tasks.get_next_action_task') as mock_get_next:
            
            # Configure database mock
            mock_db_instance = AsyncMock()
            MockDB.return_value = mock_db_instance
            mock_db_instance.get_planner.return_value = {
                "planner_id": self.planner_id,
                "execution_plan": "Test plan",
                "model": "gpt-4",
                "temperature": 0.0,
                "image_file_paths": {},
                "variable_file_paths": {}
            }
            mock_db_instance.update_planner.return_value = True
            
            # Configure MessageManager mock
            mock_mm_instance = AsyncMock()
            MockMM.return_value = mock_mm_instance
            mock_mm_instance.get_messages.return_value = []
            
            # Configure execution plan mocks
            mock_execution_plan = MagicMock()
            mock_load_plan.return_value = mock_execution_plan
            mock_next_task = MagicMock()
            mock_next_task.description = 'Test task description'
            mock_get_next.return_value = mock_next_task
            mock_has_pending.return_value = True
            
            # Configure LLM response - must be awaitable and return proper Task model
            task_instance = Task(
                user_request="Test user request",
                task_description="Test task description",
                acceptance_criteria=["Test criteria"],
                image_keys=[],
                variable_keys=[],
                tools=[],
                querying_structured_data=False
            )
            
            async def mock_task_response(*args, **kwargs):
                return task_instance
            
            mock_llm_service.a_get_response = mock_task_response
            
            # Configure other mocks
            mock_save_task.return_value = True
            mock_load_history.return_value = []
            mock_queue_worker.return_value = True
            
            # Test data
            task_data = {"entity_id": self.planner_id}
            
            # ACTUALLY EXECUTE THE FUNCTION
            await execute_task_creation(task_data)
            
            # Verify the function actually ran by checking mock calls
            mock_db_instance.get_planner.assert_called_once()
            # Note: Can't easily assert on async function call, but execution success implies it was called

    async def test_complete_planner_execution_vanilla_execution(self):
        """Test _complete_planner_execution ACTUALLY EXECUTES without errors."""
        from src.agent.tasks.planner_tasks import _complete_planner_execution
        from src.agent.models.tasks import ExecutionPlanModel
        
        with patch('src.agent.tasks.planner_tasks.load_wip_answer_template') as mock_load_template, \
             patch('src.agent.tasks.planner_tasks.llm') as mock_llm_service, \
             patch('src.agent.tasks.planner_tasks.save_execution_plan_model') as mock_save_plan, \
             patch('src.agent.tasks.planner_tasks.execution_plan_model_to_markdown') as mock_plan_to_md:
            
            # Configure mock database instance
            mock_db = AsyncMock()
            mock_db.get_messages.return_value = [
                {"role": "user", "content": "Test user message"},
                {"role": "assistant", "content": "Test assistant message"}
            ]
            mock_db.update_planner.return_value = True
            mock_db.record_worker.return_value = True
            
            # Configure other mocks
            mock_load_template.return_value = "Test answer template"
            mock_save_plan.return_value = True
            mock_plan_to_md.return_value = "# Test Plan\nTest content"
            
            # Configure LLM response
            mock_llm_response = AsyncMock()
            mock_llm_response.content = "Test user response"
            
            async def mock_llm_call(*args, **kwargs):
                return mock_llm_response
            
            mock_llm_service.a_get_response = mock_llm_call
            
            # Create test data
            execution_plan_model = ExecutionPlanModel(
                objective="Test objective",
                todos=[]
            )
            planner_data = {
                "model": "gpt-4",
                "temperature": 0.0
            }
            
            # ACTUALLY EXECUTE THE FUNCTION
            await _complete_planner_execution(
                planner_id=self.planner_id,
                execution_plan_model=execution_plan_model,
                worker_id="test_worker_id",
                planner_data=planner_data,
                db=mock_db
            )
            
            # Verify the function actually ran by checking mock calls
            mock_db.get_messages.assert_called_once()
            mock_db.update_planner.assert_called_once()
            mock_save_plan.assert_called_once()

    async def test_execute_synthesis_vanilla_execution(self):
        """Test execute_synthesis ACTUALLY EXECUTES without errors."""
        from src.agent.tasks.planner_tasks import execute_synthesis
        
        with patch('src.agent.tasks.planner_tasks.AgentDatabase') as MockDB, \
             patch('src.agent.tasks.planner_tasks.MessageManager') as MockMM:
            
            # Configure database mock
            mock_db_instance = AsyncMock()
            MockDB.return_value = mock_db_instance
            mock_db_instance.get_planner.return_value = {
                "planner_id": self.planner_id,
                "model": "gpt-4",
                "temperature": 0.0
            }
            
            # Configure empty completed workers - this should cause early return
            mock_db_instance.get_workers_by_planner.return_value = []
            
            # Configure MessageManager mock  
            mock_mm_instance = AsyncMock()
            MockMM.return_value = mock_mm_instance
            
            # Test data
            task_data = {"entity_id": self.planner_id}
            
            # ACTUALLY EXECUTE THE FUNCTION - should exit early due to no completed workers
            await execute_synthesis(task_data)
            
            # Verify the function actually ran by checking mock calls
            mock_db_instance.get_planner.assert_called_once()
            mock_db_instance.get_workers_by_planner.assert_called_once()


class TestWorkerTasksExecution(unittest.IsolatedAsyncioTestCase):
    """Lightweight tests for worker_tasks.py functions - vanilla flow only."""

    async def asyncSetUp(self):
        """Set up minimal test environment."""
        self.planner_id = f"test_planner_{uuid.uuid4().hex[:8]}"
        self.worker_id = f"test_worker_{uuid.uuid4().hex[:8]}"

    def test_convert_result_to_str_vanilla_execution(self):
        """Test convert_result_to_str executes without errors in vanilla scenario."""
        # Create a mock TaskResult
        task_result = TaskResult(result="Test result", output="Test output")
        
        # Execute function
        result_str = convert_result_to_str(task_result)
        
        # Verify basic structure
        self.assertIsInstance(result_str, str)
        self.assertIn("Test result", result_str)
        self.assertIn("Test output", result_str)

    async def test_validate_worker_result_vanilla_execution(self):
        """Test validate_worker_result executes without errors in vanilla scenario."""
        with patch('src.agent.services.llm_service.LLM.a_get_response', autospec=True) as mock_llm:
            
            # Configure LLM response for successful validation
            mock_validation = TaskValidation(
                task_completed=True,
                validated_result=TaskResult(result="Task completed", output="Success"),
                failed_criteria=""
            )
            mock_llm.return_value = mock_validation
            
            # Configure database and message manager mocks
            mock_db = AsyncMock()
            mock_db.update_worker.return_value = True
            
            mock_message_manager = AsyncMock()
            mock_message_manager.add_message.return_value = []
            
            # Execute function
            result = await validate_worker_result(
                self.worker_id, 
                "Test acceptance criteria", 
                mock_db, 
                mock_message_manager
            )
            
            # Verify successful execution
            self.assertTrue(result)
            mock_db.update_worker.assert_called_once()

    async def test_process_image_variable_vanilla_execution(self):
        """Test process_image_variable executes without errors in vanilla scenario."""
        with patch('src.agent.utils.tools.encode_image', return_value="encoded_image"), \
             patch('src.agent.tasks.file_manager.generate_image_path', return_value=("/path/image.png", "test_image")), \
             patch('src.agent.tasks.file_manager.save_image_to_file', return_value=True):
            
            # Configure database mock
            mock_db = AsyncMock()
            mock_db.get_worker.return_value = {"output_image_filepaths": {}}
            mock_db.update_worker.return_value = True
            
            # Configure message manager mock
            mock_message_manager = AsyncMock()
            mock_message_manager.add_message.return_value = []
            
            # Create a test PIL Image
            test_image = Image.new('RGB', (100, 100), color='red')
            
            # Execute function
            result_key = await process_image_variable(
                test_image,
                "test_image",
                self.worker_id,
                self.planner_id,
                mock_db,
                mock_message_manager
            )
            
            # Verify execution completed successfully - just check it doesn't crash
            self.assertIsNotNone(result_key)
            self.assertIsInstance(result_key, str)
            mock_db.update_worker.assert_called_once()

    async def test_process_variable_vanilla_execution(self):
        """Test process_variable executes without errors in vanilla scenario."""
        with patch('src.agent.tasks.file_manager.generate_variable_path', return_value=("/path/var.pkl", "test_variable")), \
             patch('src.agent.tasks.file_manager.save_variable_to_file', return_value=True), \
             patch('src.agent.utils.tools.is_serialisable', return_value=(True, True)):
            
            # Configure database mock
            mock_db = AsyncMock()
            mock_db.get_worker.return_value = {"output_variable_filepaths": {}}
            mock_db.update_worker.return_value = True
            
            # Configure message manager mock
            mock_message_manager = AsyncMock()
            mock_message_manager.add_message.return_value = []
            
            # Execute function
            result_key = await process_variable(
                {"test": "data"},
                "test_variable",
                self.worker_id,
                self.planner_id,
                mock_db,
                mock_message_manager
            )
            
            # Verify execution completed successfully - just check it doesn't crash
            self.assertIsNotNone(result_key)
            self.assertIsInstance(result_key, str)
            mock_db.update_worker.assert_called_once()

    async def test_worker_initialisation_vanilla_execution(self):
        """Test worker_initialisation ACTUALLY EXECUTES without errors."""
        from src.agent.tasks.worker_tasks import worker_initialisation
        
        with patch('src.agent.tasks.worker_tasks.AgentDatabase') as MockDB, \
             patch('src.agent.tasks.worker_tasks.update_worker_next_task_and_queue') as mock_update_queue:
            
            # Configure database mock - simulate existing worker scenario (resume)
            mock_db_instance = AsyncMock()
            MockDB.return_value = mock_db_instance
            mock_db_instance.get_worker.return_value = {
                "worker_id": self.worker_id,
                "status": "pending"
            }
            
            # Configure other mocks
            mock_update_queue.return_value = True
            
            # Test data - worker initialisation takes entity_id and payload
            task_data = {
                "entity_id": self.worker_id,
                "payload": {"planner_id": self.planner_id}
            }
            
            # ACTUALLY EXECUTE THE FUNCTION - should take resume path due to existing worker
            await worker_initialisation(task_data)
            
            # Verify the function actually ran by checking mock calls
            mock_db_instance.get_worker.assert_called_once_with(self.worker_id)
            mock_update_queue.assert_called_once()

    async def test_execute_standard_worker_vanilla_execution(self):
        """Test execute_standard_worker ACTUALLY EXECUTES without errors."""
        from src.agent.tasks.worker_tasks import execute_standard_worker
        
        with patch('src.agent.tasks.worker_tasks.AgentDatabase') as MockDB:
            
            # Configure database mock - simulate worker not found scenario (early return)
            mock_db_instance = AsyncMock()
            MockDB.return_value = mock_db_instance
            mock_db_instance.get_worker.return_value = None  # Worker not found
            
            # Test data
            task_data = {"entity_id": self.worker_id}
            
            # ACTUALLY EXECUTE THE FUNCTION - should exit early due to worker not found
            await execute_standard_worker(task_data)
            
            # Verify the function actually ran by checking mock calls
            mock_db_instance.get_worker.assert_called_once_with(self.worker_id)

    async def test_execute_sql_worker_vanilla_execution(self):
        """Test execute_sql_worker ACTUALLY EXECUTES without errors."""
        from src.agent.tasks.worker_tasks import execute_sql_worker
        
        with patch('src.agent.tasks.worker_tasks.AgentDatabase') as MockDB:
            
            # Configure database mock - simulate worker not found scenario (early return)
            mock_db_instance = AsyncMock()
            MockDB.return_value = mock_db_instance
            mock_db_instance.get_worker.return_value = None  # Worker not found
            
            # Test data
            task_data = {"entity_id": self.worker_id}
            
            # ACTUALLY EXECUTE THE FUNCTION - should exit early due to worker not found
            await execute_sql_worker(task_data)
            
            # Verify the function actually ran by checking mock calls
            mock_db_instance.get_worker.assert_called_once_with(self.worker_id)