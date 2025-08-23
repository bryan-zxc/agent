"""
Task Execution Pipeline Test Suite

Tests for function-based task system including planner tasks, worker tasks,
and task queue integration. Integrates patterns from existing concurrent tests.
"""

import unittest
import asyncio
import tempfile
import shutil
import uuid
import os
from unittest.mock import patch, AsyncMock, MagicMock
from pathlib import Path

from src.agent.tasks.planner_tasks import execute_initial_planning, execute_task_creation, execute_synthesis
from src.agent.tasks.worker_tasks import worker_initialisation, execute_standard_worker, execute_sql_worker
from src.agent.tasks.task_utils import update_planner_next_task_and_queue
from src.agent.models.agent_database import AgentDatabase
from src.agent.config.settings import settings


class TestTaskExecution(unittest.IsolatedAsyncioTestCase):
    """Test function-based task execution pipeline."""

    async def asyncSetUp(self):
        """Set up test environment with temporary database and directories."""
        # Set up temporary directories
        self.test_dir = tempfile.mkdtemp()
        self.original_base_path = settings.collaterals_base_path
        settings.collaterals_base_path = self.test_dir
        
        # Set up temporary database
        self.db_fd, self.test_db_path = tempfile.mkstemp(suffix='.db')
        os.close(self.db_fd)
        self.db = AgentDatabase(database_path=self.test_db_path)
        
        # Test data
        self.planner_id = f"test_planner_{uuid.uuid4().hex[:8]}"
        self.worker_id = f"test_worker_{uuid.uuid4().hex[:8]}"

    async def asyncTearDown(self):
        """Clean up test environment."""
        settings.collaterals_base_path = self.original_base_path
        shutil.rmtree(self.test_dir, ignore_errors=True)
        
        try:
            os.unlink(self.test_db_path)
        except (OSError, FileNotFoundError):
            pass

    async def test_execute_initial_planning_awaits(self):
        """Test execute_initial_planning properly awaits async operations."""
        with patch('src.agent.models.agent_database.AgentDatabase') as MockDB, \
             patch('src.agent.services.llm_service.LLM.a_get_response', new_callable=AsyncMock) as mock_llm, \
             patch('src.agent.tasks.file_manager.save_answer_template', return_value=True) as mock_save_template, \
             patch('src.agent.tasks.task_utils.update_planner_next_task_and_queue', return_value=True) as mock_queue:
            
            # Mock database
            mock_db = AsyncMock()
            MockDB.return_value = mock_db
            mock_db.create_planner.return_value = True
            mock_db.update_planner.return_value = True
            
            # Mock LLM response
            mock_llm.return_value = "## Execution Plan\n1. Analyse data\n2. Generate report"
            
            # Test task data
            task_data = {
                "task_id": "test_task_123",
                "entity_id": self.planner_id,
                "payload": {
                    "user_question": "Analyse sales data", 
                    "instruction": "Create comprehensive analysis",
                    "files": [],
                    "planner_name": "Test Planner",
                    "router_id": "test_router_123"
                }
            }
            
            # Execute initial planning
            await execute_initial_planning(task_data)
            
            # Verify database operations were awaited
            mock_db.create_planner.assert_awaited_once()
            mock_db.update_planner.assert_awaited()
            
            # Verify LLM was awaited
            mock_llm.assert_awaited_once()
            
            # Verify next task was queued
            mock_queue.assert_called_once()

    async def test_execute_task_creation_awaits(self):
        """Test execute_task_creation properly awaits async operations."""
        with patch('src.agent.models.agent_database.AgentDatabase') as MockDB, \
             patch('src.agent.services.llm_service.LLM.a_get_response', new_callable=AsyncMock) as mock_llm, \
             patch('src.agent.tasks.file_manager.load_execution_plan_model', return_value=MagicMock()) as mock_load_plan, \
             patch('src.agent.tasks.task_utils.update_planner_next_task_and_queue', return_value=True) as mock_queue:
            
            # Mock database
            mock_db = AsyncMock()
            MockDB.return_value = mock_db
            mock_db.get_planner.return_value = {
                "planner_id": self.planner_id,
                "user_question": "Test question",
                "instruction": "Test instruction"
            }
            mock_db.create_worker.return_value = True
            
            # Mock LLM response with worker tasks
            mock_llm.return_value = [
                {
                    "task_description": "Load and analyse data",
                    "acceptance_criteria": ["Data loaded successfully", "Analysis completed"],
                    "querying_structured_data": True,
                    "image_keys": [],
                    "variable_keys": ["data"],
                    "tools": ["data_loader"]
                }
            ]
            
            # Test task data
            task_data = {
                "task_id": "test_task_123",
                "entity_id": self.planner_id
            }
            
            # Execute task creation
            await execute_task_creation(task_data)
            
            # Verify database operations were awaited
            mock_db.get_planner.assert_awaited_once()
            mock_db.create_worker.assert_awaited()
            
            # Verify LLM was awaited
            mock_llm.assert_awaited_once()
            
            # Verify next task was queued
            mock_queue.assert_called()

    async def test_execute_synthesis_awaits(self):
        """Test execute_synthesis properly awaits async operations."""
        with patch('src.agent.models.agent_database.AgentDatabase') as MockDB, \
             patch('src.agent.services.llm_service.LLM.a_get_response', new_callable=AsyncMock) as mock_llm, \
             patch('src.agent.tasks.file_manager.load_execution_plan_model', return_value=MagicMock()) as mock_load_plan, \
             patch('src.agent.tasks.file_manager.save_execution_plan_model', return_value=True) as mock_save_plan, \
             patch('src.agent.tasks.file_manager.append_to_worker_message_history', return_value=True) as mock_append_history:
            
            # Mock database
            mock_db = AsyncMock()
            MockDB.return_value = mock_db
            mock_db.get_planner.return_value = {
                "planner_id": self.planner_id,
                "status": "executing",
                "user_question": "Test question"
            }
            mock_db.get_workers_by_planner.return_value = [
                {
                    "worker_id": self.worker_id,
                    "task_status": "completed",
                    "task_result": "Analysis completed successfully"
                }
            ]
            mock_db.update_planner.return_value = True
            mock_db.mark_worker_as_recorded.return_value = True
            
            # Mock LLM responses
            mock_llm.return_value = "Updated execution plan with completed tasks"
            
            # Test task data
            task_data = {
                "task_id": "test_task_123",
                "entity_id": self.planner_id
            }
            
            # Execute synthesis
            await execute_synthesis(task_data)
            
            # Verify database operations were awaited
            mock_db.get_planner.assert_awaited_once()
            mock_db.get_workers_by_planner.assert_awaited_once()
            mock_db.update_planner.assert_awaited()

    async def test_worker_initialisation_awaits(self):
        """Test worker_initialisation properly awaits async operations."""
        with patch('src.agent.models.agent_database.AgentDatabase') as MockDB, \
             patch('src.agent.tasks.task_utils.queue_worker_task', return_value=True) as mock_queue_worker:
            
            # Mock database
            mock_db = AsyncMock()
            MockDB.return_value = mock_db
            mock_db.get_worker.return_value = {
                "worker_id": self.worker_id,
                "planner_id": self.planner_id,
                "task_status": "created",
                "task_description": "Test task",
                "querying_structured_data": False
            }
            mock_db.get_planner.return_value = {
                "planner_id": self.planner_id,
                "variable_file_paths": {},
                "image_file_paths": {}
            }
            mock_db.update_worker.return_value = True
            
            # Test task data
            task_data = {
                "task_id": "test_task_123",
                "entity_id": self.worker_id
            }
            
            # Execute worker initialisation
            await worker_initialisation(task_data)
            
            # Verify database operations were awaited
            mock_db.get_worker.assert_awaited_once()
            mock_db.get_planner.assert_awaited_once()
            mock_db.update_worker.assert_awaited_once()
            
            # Verify next worker task was queued
            mock_queue_worker.assert_called_once()

    async def test_execute_standard_worker_awaits(self):
        """Test execute_standard_worker properly awaits async operations."""
        with patch('src.agent.models.agent_database.AgentDatabase') as MockDB, \
             patch('src.agent.services.llm_service.LLM.a_get_response', new_callable=AsyncMock) as mock_llm, \
             patch('src.agent.utils.sandbox.execute_code', return_value=("Success", None, {})) as mock_execute, \
             patch('src.agent.tasks.task_utils.update_planner_next_task_and_queue', return_value=True) as mock_queue:
            
            # Mock database
            mock_db = AsyncMock()
            MockDB.return_value = mock_db
            mock_db.get_worker.return_value = {
                "worker_id": self.worker_id,
                "planner_id": self.planner_id,
                "task_status": "ready",
                "task_description": "Generate analysis chart",
                "acceptance_criteria": ["Chart generated", "Data visualised"],
                "user_request": "Create visualisation"
            }
            mock_db.update_worker.return_value = True
            
            # Mock LLM response with code
            from src.agent.models.tasks import TaskArtefact
            mock_llm.return_value = TaskArtefact(
                summary_of_previous_failures="",
                thought="I need to create a chart",
                result="Chart generation task",
                python_code="import matplotlib.pyplot as plt\nplt.plot([1,2,3])\nplt.savefig('chart.png')",
                output_variables=["chart_path"],
                is_malicious=False
            )
            
            # Test task data
            task_data = {
                "task_id": "test_task_123",
                "entity_id": self.worker_id
            }
            
            # Execute standard worker
            await execute_standard_worker(task_data)
            
            # Verify database operations were awaited
            mock_db.get_worker.assert_awaited_once()
            mock_db.update_worker.assert_awaited()
            
            # Verify LLM was awaited
            mock_llm.assert_awaited_once()

    async def test_execute_sql_worker_awaits(self):
        """Test execute_sql_worker properly awaits async operations."""
        with patch('src.agent.models.agent_database.AgentDatabase') as MockDB, \
             patch('src.agent.services.llm_service.LLM.a_get_response', new_callable=AsyncMock) as mock_llm, \
             patch('duckdb.connect') as mock_duckdb:
            
            # Mock database
            mock_db = AsyncMock()
            MockDB.return_value = mock_db
            mock_db.get_worker.return_value = {
                "worker_id": self.worker_id,
                "planner_id": self.planner_id,
                "task_status": "ready",
                "task_description": "Query sales data",
                "tables": [{"name": "sales", "schema": "id, amount, date"}],
                "user_request": "Find total sales"
            }
            mock_db.update_worker.return_value = True
            
            # Mock LLM SQL response
            from src.agent.models.tasks import TaskArtefactSQL
            mock_llm.return_value = TaskArtefactSQL(
                summary_of_previous_failures="",
                thought="I need to calculate total sales",
                sql_code="SELECT SUM(amount) as total_sales FROM sales",
                reason_code_not_created=""
            )
            
            # Mock DuckDB
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchall.return_value = [(50000,)]
            mock_duckdb.return_value = mock_conn
            
            # Test task data
            task_data = {
                "task_id": "test_task_123",
                "entity_id": self.worker_id
            }
            
            # Execute SQL worker
            await execute_sql_worker(task_data)
            
            # Verify database operations were awaited
            mock_db.get_worker.assert_awaited_once()
            mock_db.update_worker.assert_awaited()
            
            # Verify LLM was awaited
            mock_llm.assert_awaited_once()

    async def test_task_queue_integration(self):
        """Test task queue operations work correctly."""
        task_id = f"test_task_{uuid.uuid4().hex[:8]}"
        
        # Test update_planner_next_task_and_queue
        with patch('src.agent.models.agent_database.AgentDatabase') as MockDB:
            mock_db = AsyncMock()
            MockDB.return_value = mock_db
            mock_db.update_planner.return_value = True
            mock_db.enqueue_task.return_value = True
            
            result = update_planner_next_task_and_queue(
                self.planner_id, 
                "execute_task_creation"
            )
            
            # Should be synchronous function that internally handles async
            self.assertTrue(result)

    async def test_task_status_transitions(self):
        """Test task status transitions through pipeline."""
        # Test the complete task lifecycle
        with patch('src.agent.models.agent_database.AgentDatabase') as MockDB, \
             patch('src.agent.services.llm_service.LLM.a_get_response', new_callable=AsyncMock) as mock_llm:
            
            mock_db = AsyncMock()
            MockDB.return_value = mock_db
            
            # Mock planner creation and task queueing
            mock_db.create_planner.return_value = True
            mock_db.update_planner.return_value = True
            mock_db.enqueue_task.return_value = True
            mock_llm.return_value = "## Plan\n1. Step one\n2. Step two"
            
            # Test initial planning (PENDING → IN_PROGRESS → COMPLETED)
            task_data = {
                "task_id": "planning_task",
                "entity_id": self.planner_id,
                "payload": {
                    "user_question": "Test question",
                    "instruction": "Test instruction",
                    "files": [],
                    "planner_name": "Test Planner",
                    "router_id": "test_router"
                }
            }
            
            # Execute initial planning
            await execute_initial_planning(task_data)
            
            # Verify planner was created and updated
            mock_db.create_planner.assert_awaited_once()
            mock_db.update_planner.assert_awaited()
            
            # Verify next task was queued
            mock_db.enqueue_task.assert_awaited()

    async def test_concurrent_task_execution(self):
        """Test concurrent execution of multiple tasks (adapted from existing test)."""
        # Based on test_concurrent_planner_execution.py patterns
        with patch('src.agent.models.agent_database.AgentDatabase') as MockDB, \
             patch('src.agent.services.llm_service.LLM.a_get_response', new_callable=AsyncMock) as mock_llm:
            
            mock_db = AsyncMock()
            MockDB.return_value = mock_db
            mock_db.create_planner.return_value = True
            mock_db.update_planner.return_value = True
            mock_llm.return_value = "## Concurrent Plan\n1. Process data\n2. Generate results"
            
            # Create multiple concurrent planning tasks
            planner_ids = [f"concurrent_planner_{i}" for i in range(3)]
            
            async def run_planning_task(planner_id):
                task_data = {
                    "task_id": f"task_{planner_id}",
                    "entity_id": planner_id,
                    "payload": {
                        "user_question": f"Question for {planner_id}",
                        "instruction": f"Instruction for {planner_id}",
                        "files": [],
                        "planner_name": f"Planner {planner_id}",
                        "router_id": f"router_{planner_id}"
                    }
                }
                
                await execute_initial_planning(task_data)
                return planner_id
            
            # Execute concurrent planning tasks
            results = await asyncio.gather(
                *[run_planning_task(planner_id) for planner_id in planner_ids]
            )
            
            # Verify all tasks completed successfully
            self.assertEqual(len(results), 3)
            self.assertEqual(set(results), set(planner_ids))
            
            # Verify database operations were called for each planner
            self.assertEqual(mock_db.create_planner.await_count, 3)

    async def test_error_handling_in_task_execution(self):
        """Test error handling doesn't break async chains."""
        with patch('src.agent.models.agent_database.AgentDatabase') as MockDB, \
             patch('src.agent.services.llm_service.LLM.a_get_response', new_callable=AsyncMock) as mock_llm:
            
            mock_db = AsyncMock()
            MockDB.return_value = mock_db
            
            # Simulate database error
            mock_db.create_planner.side_effect = Exception("Database connection failed")
            mock_llm.return_value = "Test plan"
            
            task_data = {
                "task_id": "error_test",
                "entity_id": self.planner_id,
                "payload": {
                    "user_question": "Test question",
                    "instruction": "Test instruction", 
                    "files": [],
                    "planner_name": "Error Test Planner",
                    "router_id": "test_router"
                }
            }
            
            # Should handle error gracefully
            with self.assertRaises(Exception) as context:
                await execute_initial_planning(task_data)
            
            self.assertIn("Database connection failed", str(context.exception))
            
            # Verify database operation was attempted
            mock_db.create_planner.assert_awaited_once()

    async def test_early_completion_optimisation(self):
        """Test early completion optimisation in execute_synthesis."""
        with patch('src.agent.models.agent_database.AgentDatabase') as MockDB, \
             patch('src.agent.tasks.file_manager.load_execution_plan_model') as mock_load_plan, \
             patch('src.agent.tasks.file_manager.save_execution_plan_model', return_value=True) as mock_save_plan, \
             patch('src.agent.tasks.planner_tasks._complete_planner_execution', new_callable=AsyncMock) as mock_complete:
            
            # Mock database
            mock_db = AsyncMock()
            MockDB.return_value = mock_db
            mock_db.get_planner.return_value = {
                "planner_id": self.planner_id,
                "status": "executing"
            }
            mock_db.get_workers_by_planner.return_value = [
                {
                    "worker_id": self.worker_id,
                    "task_status": "completed",
                    "task_result": "Task completed successfully"
                }
            ]
            
            # Mock execution plan with no open todos (triggers early completion)
            mock_execution_plan = MagicMock()
            mock_execution_plan.open_todos = []  # No open todos
            mock_load_plan.return_value = mock_execution_plan
            
            task_data = {
                "task_id": "early_completion_test",
                "entity_id": self.planner_id
            }
            
            # Execute synthesis
            await execute_synthesis(task_data)
            
            # Verify early completion was triggered
            mock_complete.assert_awaited_once()


if __name__ == '__main__':
    unittest.main(verbosity=2)