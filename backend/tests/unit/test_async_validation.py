"""
Async/Await Validation Test Suite

Tests to catch missing await keywords that would break coroutines.
Focuses on RouterAgent, AgentDatabase, Background Processor, and LLM Service async methods.
"""

import unittest
import asyncio
import tempfile
import shutil
import uuid
from unittest.mock import patch, AsyncMock, MagicMock
from pathlib import Path

# Import modules under test
from src.agent.core.router import RouterAgent
from src.agent.models.agent_database import AgentDatabase
from src.agent.services.llm_service import LLM
from src.agent.services.background_processor import BackgroundTaskProcessor
from src.agent.config.settings import settings


class MockWebSocket:
    """Mock WebSocket for testing async operations."""
    
    def __init__(self):
        self.sent_messages = []
        self.is_connected = True
        
    async def send_json(self, data):
        """Mock async send_json."""
        if self.is_connected:
            self.sent_messages.append(data)


class TestAsyncValidation(unittest.IsolatedAsyncioTestCase):
    """Test async/await compliance across all components."""

    async def asyncSetUp(self):
        """Set up test environment with temporary directories."""
        self.test_dir = tempfile.mkdtemp()
        self.original_base_path = settings.collaterals_base_path
        settings.collaterals_base_path = self.test_dir
        
        # Create temporary database
        self.db_fd, self.test_db_path = tempfile.mkstemp(suffix='.db')
        self.db = AgentDatabase(database_path=self.test_db_path)
        
        self.router_id = f"test_router_{uuid.uuid4().hex[:8]}"

    async def asyncTearDown(self):
        """Clean up test environment."""
        settings.collaterals_base_path = self.original_base_path
        shutil.rmtree(self.test_dir, ignore_errors=True)
        
        # Clean up database file
        import os
        try:
            os.close(self.db_fd)
            os.unlink(self.test_db_path)
        except (OSError, AttributeError):
            pass

    async def test_router_agent_async_methods(self):
        """Verify RouterAgent async methods properly await operations."""
        mock_websocket = MockWebSocket()
        
        with patch.object(self.db, 'add_message', new_callable=AsyncMock) as mock_add_message, \
             patch.object(self.db, 'create_router', new_callable=AsyncMock) as mock_create_router, \
             patch.object(self.db, 'update_router', new_callable=AsyncMock) as mock_update_router, \
             patch('src.agent.services.llm_service.LLM.a_get_response', new_callable=AsyncMock) as mock_llm:
            
            mock_add_message.return_value = 1
            mock_create_router.return_value = True  
            mock_update_router.return_value = True
            mock_llm.return_value = "Test response"
            
            # Test activate_conversation awaits database operations
            router = RouterAgent()
            await router.activate_conversation(
                user_message="Test message",
                websocket=mock_websocket
            )
            
            # Verify async methods were awaited
            mock_create_router.assert_awaited_once()
            mock_add_message.assert_awaited()

    async def test_router_agent_handle_message_await(self):
        """Test RouterAgent.handle_message properly awaits async operations."""
        mock_websocket = MockWebSocket()
        
        with patch.object(self.db, 'add_message', new_callable=AsyncMock) as mock_add_message, \
             patch.object(self.db, 'get_messages', new_callable=AsyncMock) as mock_get_messages, \
             patch('src.agent.core.router.RouterAgent.assess_agent_requirements', new_callable=AsyncMock) as mock_assess, \
             patch('src.agent.core.router.RouterAgent.handle_simple_chat', new_callable=AsyncMock) as mock_simple_chat:
            
            mock_add_message.return_value = 1
            mock_get_messages.return_value = []
            
            # Mock agent requirements (no agent needed)
            from src.agent.models.responses import RequireAgent
            mock_assess.return_value = RequireAgent(
                web_search_required=False,
                chilli_request=False,
                context_rich_agent_request=""
            )
            mock_simple_chat.return_value = "Simple response"
            
            router = RouterAgent(router_id=self.router_id)
            router._agent_db = self.db
            
            message_data = {"message": "Hello"}
            await router.handle_message(message_data, mock_websocket)
            
            # Verify all async methods were awaited
            mock_assess.assert_awaited_once()
            mock_simple_chat.assert_awaited_once()
            mock_add_message.assert_awaited()

    async def test_router_agent_load_existing_state_await(self):
        """Test RouterAgent._load_existing_state awaits database operations."""
        with patch.object(self.db, 'get_router', new_callable=AsyncMock) as mock_get_router, \
             patch.object(self.db, 'get_messages', new_callable=AsyncMock) as mock_get_messages:
            
            mock_get_router.return_value = {
                "router_id": self.router_id,
                "status": "active",
                "model": "gpt-4",
                "temperature": 0.7,
                "title": "Test",
                "preview": "Test preview"
            }
            mock_get_messages.return_value = []
            
            router = RouterAgent(router_id=self.router_id)
            router._agent_db = self.db
            await router._load_existing_state()
            
            # Verify database methods were awaited
            mock_get_router.assert_awaited_once_with(self.router_id)
            mock_get_messages.assert_awaited_once_with("router", self.router_id)

    async def test_agent_database_async_operations(self):
        """Test AgentDatabase async methods are properly awaited."""
        db = AgentDatabase(database_path=":memory:")
        
        # Test async database operations
        router_id = "test_router_123"
        
        # Test create_router awaits
        result = await db.create_router(
            router_id=router_id,
            status="active",
            model="gpt-4",
            temperature=0.7,
            title="Test Router",
            preview="Test preview"
        )
        self.assertTrue(result)
        
        # Test get_router awaits
        router_data = await db.get_router(router_id)
        self.assertEqual(router_data["router_id"], router_id)
        
        # Test add_message awaits
        message_id = await db.add_message("router", router_id, "user", "Test message")
        self.assertIsInstance(message_id, int)
        
        # Test get_messages awaits  
        messages = await db.get_messages("router", router_id)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["content"], "Test message")

    async def test_agent_database_planner_operations_await(self):
        """Test AgentDatabase planner operations properly await."""
        db = AgentDatabase(database_path=":memory:")
        
        planner_id = "test_planner_123"
        
        # Test create_planner awaits
        result = await db.create_planner(
            planner_id=planner_id,
            planner_name="Test Planner",
            user_question="Test question",
            instruction="Test instruction",
            status="planning"
        )
        self.assertTrue(result)
        
        # Test update_planner awaits
        result = await db.update_planner(
            planner_id,
            status="executing",
            execution_plan="Test plan"
        )
        self.assertTrue(result)
        
        # Test get_planner awaits
        planner_data = await db.get_planner(planner_id)
        self.assertEqual(planner_data["planner_id"], planner_id)
        self.assertEqual(planner_data["status"], "executing")

    async def test_agent_database_task_queue_operations_await(self):
        """Test AgentDatabase task queue operations properly await."""
        db = AgentDatabase(database_path=":memory:")
        
        task_id = "test_task_123"
        
        # Test enqueue_task awaits
        result = await db.enqueue_task(
            task_id=task_id,
            entity_type="planner",
            entity_id="test_planner",
            function_name="test_function"
        )
        self.assertTrue(result)
        
        # Test get_pending_tasks awaits
        pending_tasks = await db.get_pending_tasks()
        self.assertEqual(len(pending_tasks), 1)
        self.assertEqual(pending_tasks[0]["task_id"], task_id)
        
        # Test update_task_status awaits
        result = await db.update_task_status(task_id, "COMPLETED")
        self.assertTrue(result)

    async def test_llm_service_async_response_await(self):
        """Test LLM service async response methods properly await."""
        with patch('openai.AsyncOpenAI') as MockOpenAI, \
             patch('anthropic.AsyncAnthropic') as MockAnthropic:
            
            # Mock OpenAI async response
            mock_openai_client = AsyncMock()
            mock_response = AsyncMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "Test response"
            mock_response.usage.prompt_tokens = 10
            mock_response.usage.completion_tokens = 5
            mock_openai_client.chat.completions.create.return_value = mock_response
            MockOpenAI.return_value = mock_openai_client
            
            llm = LLM()
            messages = [{"role": "user", "content": "Test"}]
            
            # Test a_get_response awaits OpenAI API call
            response = await llm.a_get_response(
                messages=messages,
                model="gpt-4.1-nano",
                temperature=0.7
            )
            
            self.assertEqual(response, "Test response")
            mock_openai_client.chat.completions.create.assert_awaited_once()

    async def test_background_processor_async_execution(self):
        """Test BackgroundTaskProcessor async methods properly await."""
        with patch('src.agent.models.agent_database.AgentDatabase') as MockDB:
            mock_db = AsyncMock()
            MockDB.return_value = mock_db
            
            # Mock pending tasks
            mock_db.get_pending_tasks.return_value = [
                {
                    "task_id": "test_task",
                    "entity_type": "planner",
                    "entity_id": "test_planner",
                    "function_name": "test_function",
                    "payload": {}
                }
            ]
            
            processor = BackgroundTaskProcessor()
            processor.db = mock_db
            
            # Mock task function
            async def mock_test_function(task_data):
                return "Task completed"
            
            processor.function_registry["test_function"] = mock_test_function
            
            # Test execute_task awaits the task function
            task_data = {
                "task_id": "test_task",
                "function_name": "test_function",
                "payload": {}
            }
            
            await processor.execute_task(task_data)
            
            # Verify database update was awaited
            mock_db.update_task_status.assert_awaited()

    async def test_websocket_send_methods_are_async(self):
        """Test that RouterAgent WebSocket send methods are properly async."""
        mock_websocket = AsyncMock()
        
        with patch.object(self.db, 'get_router', new_callable=AsyncMock) as mock_get_router:
            mock_get_router.return_value = {
                "router_id": self.router_id,
                "status": "active",
                "model": "gpt-4",
                "temperature": 0.7,
                "title": "Test",
                "preview": "Test preview"
            }
            
            router = RouterAgent(router_id=self.router_id)
            router._agent_db = self.db
            
            # Test all WebSocket send methods are async
            await router.send_status("Test status", mock_websocket)
            await router.send_user_message("Test message", mock_websocket)
            await router.send_assistant_message("Test response", mock_websocket)
            await router.send_error("Test error", mock_websocket)
            await router.send_input_lock(mock_websocket)
            await router.send_input_unlock(mock_websocket)
            await router.send_message_history(mock_websocket)
            
            # Verify WebSocket methods were awaited
            self.assertEqual(mock_websocket.send_json.await_count, 7)

    async def test_concurrent_async_operations(self):
        """Test that concurrent async operations work correctly."""
        db = AgentDatabase(database_path=":memory:")
        
        # Create multiple concurrent database operations
        async def create_test_router(router_id):
            return await db.create_router(
                router_id=router_id,
                status="active",
                model="gpt-4",
                temperature=0.7,
                title=f"Router {router_id}",
                preview=f"Preview {router_id}"
            )
        
        # Run concurrent operations
        router_ids = [f"router_{i}" for i in range(5)]
        results = await asyncio.gather(
            *[create_test_router(router_id) for router_id in router_ids]
        )
        
        # Verify all operations succeeded
        self.assertTrue(all(results))
        
        # Verify all routers were created
        for router_id in router_ids:
            router_data = await db.get_router(router_id)
            self.assertEqual(router_data["router_id"], router_id)

    async def test_error_handling_in_async_context(self):
        """Test error handling in async context doesn't break await chains."""
        mock_websocket = AsyncMock()
        
        with patch('src.agent.services.llm_service.LLM.a_get_response', new_callable=AsyncMock) as mock_llm:
            # Simulate LLM service error
            mock_llm.side_effect = Exception("LLM API Error")
            
            router = RouterAgent()
            
            # Should handle error gracefully without breaking async chain
            try:
                await router.activate_conversation(
                    user_message="Test",
                    websocket=mock_websocket
                )
            except Exception as e:
                # Verify error was properly propagated
                self.assertIn("LLM API Error", str(e))
            
            # Verify LLM was awaited even in error case
            mock_llm.assert_awaited()


if __name__ == '__main__':
    unittest.main(verbosity=2)