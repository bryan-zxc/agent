"""
RouterAgent Test Suite

Tests for ephemeral RouterAgent lifecycle, message routing,
WebSocket communication, and database persistence.
"""

import unittest
import asyncio
import tempfile
import shutil
import uuid
import os
from unittest.mock import patch, AsyncMock, MagicMock
from pathlib import Path

from src.agent.core.router import RouterAgent
from src.agent.models.agent_database import AgentDatabase
from src.agent.config.settings import settings


class MockWebSocket:
    """Mock WebSocket for testing RouterAgent communications."""
    
    def __init__(self):
        self.sent_messages = []
        self.is_connected = True
        self.scope = {
            "path": "/ws/test",
            "client": ["127.0.0.1", 8000]
        }
    
    async def send_json(self, data):
        """Mock async send_json method."""
        if self.is_connected:
            self.sent_messages.append(data)
    
    def get_messages_by_type(self, message_type):
        """Get messages of specific type."""
        return [msg for msg in self.sent_messages if msg.get("type") == message_type]


class TestRouterAgent(unittest.IsolatedAsyncioTestCase):
    """Test RouterAgent ephemeral architecture and operations."""

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
        self.router_id = f"test_router_{uuid.uuid4().hex[:8]}"
        self.mock_websocket = MockWebSocket()

    async def asyncTearDown(self):
        """Clean up test environment."""
        settings.collaterals_base_path = self.original_base_path
        shutil.rmtree(self.test_dir, ignore_errors=True)
        
        try:
            os.unlink(self.test_db_path)
        except (OSError, FileNotFoundError):
            pass

    async def test_ephemeral_router_creation(self):
        """Test ephemeral router creation without memory persistence."""
        # Create new router (ephemeral)
        router = RouterAgent()
        
        # Should have generated unique ID
        self.assertIsNotNone(router.id)
        self.assertTrue(router.id.startswith("router_"))
        
        # Should not be persisted in memory or database yet
        router_data = await self.db.get_router(router.id)
        self.assertIsNone(router_data)
        
        # Router should be in initial state
        self.assertEqual(router.status, "active")
        self.assertEqual(router.model, "gpt-4.1-nano")

    async def test_ephemeral_router_state_loading(self):
        """Test ephemeral router loading state from database."""
        # Create router in database first
        await self.db.create_router(
            router_id=self.router_id,
            status="processing",
            model="sonnet-4",
            temperature=0.8,
            title="Existing Router",
            preview="Existing router preview"
        )
        
        # Add some messages
        await self.db.add_message("router", self.router_id, "user", "Hello")
        await self.db.add_message("router", self.router_id, "assistant", "Hi there!")
        
        # Create ephemeral router that loads from database
        router = RouterAgent(router_id=self.router_id)
        router._agent_db = self.db
        
        # Load state
        await router._load_existing_state()
        
        # Verify state was loaded correctly
        self.assertEqual(router.id, self.router_id)
        self.assertEqual(router.status, "processing")
        self.assertEqual(router.model, "sonnet-4")
        self.assertEqual(router.temperature, 0.8)
        self.assertEqual(router.title, "Existing Router")
        self.assertEqual(len(router.messages), 2)

    async def test_router_activation_conversation(self):
        """Test router activation with first user message."""
        with patch('src.agent.services.llm_service.LLM.a_get_response', new_callable=AsyncMock) as mock_llm, \
             patch('src.agent.core.router.RouterAgent.assess_agent_requirements', new_callable=AsyncMock) as mock_assess:
            
            mock_llm.return_value = "Hello! How can I help you today?"
            
            # Mock agent requirements (simple chat)
            from src.agent.models.responses import RequireAgent
            mock_assess.return_value = RequireAgent(
                web_search_required=False,
                chilli_request=False,
                context_rich_agent_request=""
            )
            
            router = RouterAgent()
            router._agent_db = self.db
            
            # Activate conversation
            await router.activate_conversation(
                user_message="Hello, I need help",
                websocket=self.mock_websocket
            )
            
            # Verify router was created in database
            router_data = await self.db.get_router(router.id)
            self.assertIsNotNone(router_data)
            self.assertEqual(router_data["status"], "active")
            
            # Verify messages were sent via WebSocket
            messages = self.mock_websocket.get_messages_by_type("message")
            self.assertGreater(len(messages), 0)
            
            # Verify messages were stored in database
            stored_messages = await self.db.get_messages("router", router.id)
            self.assertGreater(len(stored_messages), 0)

    async def test_message_routing_simple_chat(self):
        """Test message routing to simple chat."""
        with patch('src.agent.services.llm_service.LLM.a_get_response', new_callable=AsyncMock) as mock_llm, \
             patch('src.agent.core.router.RouterAgent.assess_agent_requirements', new_callable=AsyncMock) as mock_assess:
            
            mock_llm.return_value = "This is a simple chat response."
            
            # Mock agent requirements (no agent needed)
            from src.agent.models.responses import RequireAgent
            mock_assess.return_value = RequireAgent(
                web_search_required=False,
                chilli_request=False,
                context_rich_agent_request=""
            )
            
            # Create router with existing state
            await self.db.create_router(
                router_id=self.router_id,
                status="active",
                model="gpt-4",
                temperature=0.7,
                title="Test Router",
                preview="Test preview"
            )
            
            router = RouterAgent(router_id=self.router_id)
            router._agent_db = self.db
            await router._load_existing_state()
            
            # Handle simple chat message
            message_data = {"message": "What's the weather like?"}
            await router.handle_message(message_data, self.mock_websocket)
            
            # Verify simple chat was called
            mock_assess.assert_awaited_once()
            mock_llm.assert_awaited_once()
            
            # Verify response was sent via WebSocket
            response_messages = self.mock_websocket.get_messages_by_type("response")
            self.assertEqual(len(response_messages), 1)
            self.assertEqual(response_messages[0]["message"], "This is a simple chat response.")

    async def test_message_routing_complex_request(self):
        """Test message routing to complex agent request."""
        with patch('src.agent.core.router.RouterAgent.assess_agent_requirements', new_callable=AsyncMock) as mock_assess, \
             patch('src.agent.tasks.task_utils.update_planner_next_task_and_queue', return_value=True) as mock_queue:
            
            # Mock agent requirements (agent needed)
            from src.agent.models.responses import RequireAgent
            mock_assess.return_value = RequireAgent(
                web_search_required=True,
                chilli_request=False,
                context_rich_agent_request="Search for Python programming tutorials"
            )
            
            # Create router
            await self.db.create_router(
                router_id=self.router_id,
                status="active", 
                model="gpt-4",
                temperature=0.7,
                title="Test Router",
                preview="Test preview"
            )
            
            router = RouterAgent(router_id=self.router_id)
            router._agent_db = self.db
            await router._load_existing_state()
            
            # Handle complex request
            message_data = {"message": "Find me tutorials for learning Python programming"}
            await router.handle_message(message_data, self.mock_websocket)
            
            # Verify agent requirements were assessed
            mock_assess.assert_awaited_once()
            
            # Verify task was queued
            mock_queue.assert_called_once()
            
            # Verify "Agents assemble!" message was sent
            response_messages = self.mock_websocket.get_messages_by_type("response")
            self.assertEqual(len(response_messages), 1)
            self.assertEqual(response_messages[0]["message"], "Agents assemble!")

    async def test_websocket_communication_methods(self):
        """Test all WebSocket communication methods require WebSocket parameter."""
        router = RouterAgent(router_id=self.router_id)
        router._agent_db = self.db
        
        # Test send_status
        await router.send_status("Processing...", self.mock_websocket)
        status_messages = self.mock_websocket.get_messages_by_type("status")
        self.assertEqual(len(status_messages), 1)
        self.assertEqual(status_messages[0]["message"], "Processing...")
        
        # Test send_user_message
        await router.send_user_message("Hello", self.mock_websocket)
        user_messages = self.mock_websocket.get_messages_by_type("message")
        self.assertEqual(len(user_messages), 1)
        self.assertEqual(user_messages[0]["content"], "Hello")
        self.assertEqual(user_messages[0]["role"], "user")
        
        # Test send_assistant_message
        await router.send_assistant_message("Hi there", self.mock_websocket, message_id=123)
        assistant_messages = self.mock_websocket.get_messages_by_type("response")
        self.assertEqual(len(assistant_messages), 1)
        self.assertEqual(assistant_messages[0]["message"], "Hi there")
        self.assertEqual(assistant_messages[0]["message_id"], 123)
        
        # Test send_error
        await router.send_error("Something went wrong", self.mock_websocket)
        error_messages = self.mock_websocket.get_messages_by_type("error")
        self.assertEqual(len(error_messages), 1)
        self.assertEqual(error_messages[0]["message"], "Something went wrong")
        
        # Test input lock/unlock
        await router.send_input_lock(self.mock_websocket)
        await router.send_input_unlock(self.mock_websocket)
        
        lock_messages = self.mock_websocket.get_messages_by_type("input_lock")
        unlock_messages = self.mock_websocket.get_messages_by_type("input_unlock")
        self.assertEqual(len(lock_messages), 1)
        self.assertEqual(len(unlock_messages), 1)

    async def test_message_history_sending(self):
        """Test message history sending on WebSocket connection."""
        # Create router with message history
        await self.db.create_router(
            router_id=self.router_id,
            status="active",
            model="gpt-4",
            temperature=0.7,
            title="History Test Router",
            preview="Router with history"
        )
        
        # Add some message history
        await self.db.add_message("router", self.router_id, "user", "Previous question")
        await self.db.add_message("router", self.router_id, "assistant", "Previous answer")
        await self.db.add_message("router", self.router_id, "user", "Another question")
        
        router = RouterAgent(router_id=self.router_id)
        router._agent_db = self.db
        await router._load_existing_state()
        
        # Send message history
        await router.send_message_history(self.mock_websocket)
        
        # Verify message history was sent
        history_messages = self.mock_websocket.get_messages_by_type("message_history")
        self.assertEqual(len(history_messages), 1)
        
        history_data = history_messages[0]
        self.assertEqual(history_data["router_id"], self.router_id)
        self.assertIn("messages", history_data)
        self.assertEqual(len(history_data["messages"]), 3)

    async def test_database_persistence(self):
        """Test router operations persist correctly to database."""
        router = RouterAgent()
        router._agent_db = self.db
        
        # Activate conversation (should create router in database)
        with patch('src.agent.services.llm_service.LLM.a_get_response', new_callable=AsyncMock) as mock_llm, \
             patch('src.agent.core.router.RouterAgent.assess_agent_requirements', new_callable=AsyncMock) as mock_assess:
            
            mock_llm.return_value = "Response"
            from src.agent.models.responses import RequireAgent
            mock_assess.return_value = RequireAgent(
                web_search_required=False,
                chilli_request=False,
                context_rich_agent_request=""
            )
            
            await router.activate_conversation(
                user_message="Test message",
                websocket=self.mock_websocket
            )
        
        # Verify router exists in database
        router_data = await self.db.get_router(router.id)
        self.assertIsNotNone(router_data)
        self.assertEqual(router_data["status"], "active")
        
        # Verify messages were persisted
        messages = await self.db.get_messages("router", router.id)
        self.assertGreater(len(messages), 0)
        
        # Find user message
        user_messages = [msg for msg in messages if msg["role"] == "user"]
        self.assertEqual(len(user_messages), 1)
        self.assertEqual(user_messages[0]["content"], "Test message")

    async def test_title_generation(self):
        """Test router title generation."""
        with patch('src.agent.services.llm_service.LLM.a_get_response', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "Python Programming Help"
            
            # Create router with message history
            await self.db.create_router(
                router_id=self.router_id,
                status="active",
                model="gpt-4",
                temperature=0.7,
                title="New Conversation",  # Default title
                preview="Preview"
            )
            
            await self.db.add_message("router", self.router_id, "user", "Help me learn Python programming")
            await self.db.add_message("router", self.router_id, "assistant", "I'd be happy to help you learn Python!")
            
            router = RouterAgent(router_id=self.router_id)
            router._agent_db = self.db
            await router._load_existing_state()
            
            # Generate and update title
            await router.generate_and_update_title()
            
            # Verify LLM was called for title generation
            mock_llm.assert_awaited_once()
            
            # Verify title was updated in database
            updated_router_data = await self.db.get_router(self.router_id)
            self.assertEqual(updated_router_data["title"], "Python Programming Help")

    async def test_file_processing_integration(self):
        """Test router file processing integration."""
        with patch('src.agent.core.router.RouterAgent.process_files', new_callable=AsyncMock) as mock_process_files, \
             patch('src.agent.core.router.RouterAgent.assess_agent_requirements', new_callable=AsyncMock) as mock_assess, \
             patch('src.agent.tasks.task_utils.update_planner_next_task_and_queue', return_value=True) as mock_queue:
            
            # Mock file processing
            from src.agent.models.schemas import File
            mock_process_files.return_value = [
                File(filepath="/test/image.png", file_type="image", image_context=[], data_context="", document_context=None)
            ]
            
            # Mock agent requirements (complex request with files)
            from src.agent.models.responses import RequireAgent
            mock_assess.return_value = RequireAgent(
                web_search_required=False,
                chilli_request=False,
                context_rich_agent_request="Analyze the uploaded image"
            )
            
            router = RouterAgent()
            router._agent_db = self.db
            
            # Activate conversation with files
            await router.activate_conversation(
                user_message="Analyze this image",
                files=["/test/image.png"],
                websocket=self.mock_websocket
            )
            
            # Verify file processing was called
            mock_process_files.assert_awaited_once_with(["/test/image.png"])
            
            # Verify complex request handling was triggered
            mock_assess.assert_awaited_once()
            mock_queue.assert_called_once()

    async def test_agent_requirement_assessment(self):
        """Test agent requirement assessment logic."""
        with patch('src.agent.services.llm_service.LLM.a_get_response', new_callable=AsyncMock) as mock_llm:
            # Mock LLM response for agent assessment
            from src.agent.models.responses import RequireAgent
            mock_response = RequireAgent(
                web_search_required=True,
                chilli_request=False,
                context_rich_agent_request="Search for recent AI developments"
            )
            mock_llm.return_value = mock_response
            
            router = RouterAgent(router_id=self.router_id)
            router._agent_db = self.db
            
            # Set up router with message context
            router.messages = [
                {"role": "user", "content": "What are the latest developments in AI?"}
            ]
            
            # Assess agent requirements
            requirements = await router.assess_agent_requirements()
            
            # Verify LLM was called with correct parameters
            mock_llm.assert_awaited_once()
            call_args = mock_llm.call_args
            
            # Verify structured output was requested
            self.assertEqual(call_args.kwargs["response_format"], RequireAgent)
            
            # Verify requirements were returned correctly
            self.assertTrue(requirements.web_search_required)
            self.assertFalse(requirements.chilli_request)
            self.assertEqual(requirements.context_rich_agent_request, "Search for recent AI developments")

    async def test_router_cleanup_no_memory_leaks(self):
        """Test that ephemeral router instances don't cause memory leaks."""
        initial_router_count = 0
        
        # Create multiple ephemeral routers
        for i in range(10):
            router = RouterAgent()
            router._agent_db = self.db
            
            # Use router briefly
            with patch('src.agent.services.llm_service.LLM.a_get_response', new_callable=AsyncMock) as mock_llm, \
                 patch('src.agent.core.router.RouterAgent.assess_agent_requirements', new_callable=AsyncMock) as mock_assess:
                
                mock_llm.return_value = "Response"
                from src.agent.models.responses import RequireAgent
                mock_assess.return_value = RequireAgent(
                    web_search_required=False,
                    chilli_request=False,
                    context_rich_agent_request=""
                )
                
                await router.activate_conversation(
                    user_message=f"Message {i}",
                    websocket=MockWebSocket()
                )
            
            # Router instance should be discarded after use
            # (In real usage, this happens when the function/handler completes)
            del router
        
        # Verify all routers were persisted to database but not kept in memory
        all_routers = await self.db.get_all_routers()
        self.assertEqual(len(all_routers), 10)

    async def test_concurrent_router_operations(self):
        """Test concurrent operations with multiple router instances."""
        async def create_and_use_router(index):
            router = RouterAgent()
            router._agent_db = self.db
            
            with patch('src.agent.services.llm_service.LLM.a_get_response', new_callable=AsyncMock) as mock_llm, \
                 patch('src.agent.core.router.RouterAgent.assess_agent_requirements', new_callable=AsyncMock) as mock_assess:
                
                mock_llm.return_value = f"Response {index}"
                from src.agent.models.responses import RequireAgent
                mock_assess.return_value = RequireAgent(
                    web_search_required=False,
                    chilli_request=False,
                    context_rich_agent_request=""
                )
                
                await router.activate_conversation(
                    user_message=f"Concurrent message {index}",
                    websocket=MockWebSocket()
                )
                
                return router.id
        
        # Run multiple routers concurrently
        router_ids = await asyncio.gather(
            *[create_and_use_router(i) for i in range(5)]
        )
        
        # Verify all routers were created successfully
        self.assertEqual(len(router_ids), 5)
        self.assertEqual(len(set(router_ids)), 5)  # All unique
        
        # Verify all routers exist in database
        for router_id in router_ids:
            router_data = await self.db.get_router(router_id)
            self.assertIsNotNone(router_data)


if __name__ == '__main__':
    unittest.main(verbosity=2)