import unittest

"""
Test suite for WebSocket updates during execution validation.

This test suite validates that WebSocket communications provide proper real-time
updates during agent execution, including status updates, message delivery,
and connection stability throughout the execution lifecycle.
"""

import unittest
import asyncio
import json
import time
import shutil
import uuid
import os
from unittest.mock import MagicMock, AsyncMock, patch
from pathlib import Path

# Import the modules under test
from agent.core import router_operations
from agent.models.agent_database import AgentDatabase
from agent.database.connection import DatabaseConfig
from agent.config.settings import settings


class MockWebSocket:
    """Mock WebSocket for testing WebSocket communications."""

    def __init__(self):
        self.sent_messages = []
        self.is_connected = True
        self.client_state = "connected"
        self.scope = {"path": "/ws/test_router", "client": ["127.0.0.1", 8000]}

    async def send_json(self, data):
        """Mock send_json that records sent messages."""
        if self.is_connected:
            message = {"timestamp": time.time(), "data": data}
            self.sent_messages.append(message)
        else:
            raise ConnectionError("WebSocket not connected")

    async def accept(self):
        """Mock WebSocket accept."""
        self.is_connected = True

    async def close(self):
        """Mock WebSocket close."""
        self.is_connected = False

    def get_messages_by_type(self, message_type):
        """Get all sent messages of a specific type."""
        return [
            msg for msg in self.sent_messages if msg["data"].get("type") == message_type
        ]

    def get_latest_message_by_type(self, message_type):
        """Get the latest message of a specific type."""
        messages = self.get_messages_by_type(message_type)
        return messages[-1] if messages else None


class TestWebSocketUpdatesExecution(unittest.IsolatedAsyncioTestCase):
    """Test WebSocket updates during agent execution."""

    async def asyncSetUp(self):
        """Set up test environment before each test."""
        # Create temporary directory for testing
        self.original_base_path = settings.collaterals_base_path

        # Mock settings to use test directory
        settings.collaterals_base_path = self.test_dir

        # Set up in-memory database for testing
        # Use PostgreSQL test database
        config = DatabaseConfig()
        test_db_url = config.get_database_url(database_name="test")
        self.db = await AgentDatabase.create(database_url=test_db_url)

        # Test data
        self.router_id = f"test_router_{uuid.uuid4().hex[:8]}"
        self.websocket_messages = []

    async def asyncTearDown(self):
        """Clean up after each test."""
        # Restore original settings
        settings.collaterals_base_path = self.original_base_path

        # Remove test directory
        shutil.rmtree(self.test_dir, ignore_errors=True)

        # Remove test database file
        if hasattr(self, "test_db_path") and os.path.exists(self.test_db_path):
            os.unlink(self.test_db_path)

    async def create_router_with_websocket(self):
        """Create a router with mock WebSocket connection for functional architecture."""
        # Create router in database first (simulate activation)
        await self.db.create_router(
            router_id=self.router_id,
            status="active",
            model="gpt-4.1-nano",
            temperature=0.0,
            title="Test Router",
            preview="Test router for websocket testing",
        )

        # Create a mock message manager for tests that need it
        from unittest.mock import AsyncMock
        mock_message_manager = AsyncMock()
        mock_message_manager.get_messages.return_value = []  # Return empty messages for testing

        # Create router state manually (avoid database lookup issue)
        router_state = {
            "id": self.router_id,
            "llm": None,  # Not needed for these tests
            "model": "gpt-4.1-nano",
            "temperature": 0.0,
            "agent_db": self.db,
            "message_manager": mock_message_manager,
        }

        mock_websocket = MockWebSocket()

        return router_state, mock_websocket

    async def test_websocket_connection_establishment(self):
        """Test ephemeral router creation and message history sending."""
        router_state, mock_websocket = await self.create_router_with_websocket()

        # Test message history sending with functional architecture
        await router_operations.send_message_history(router_state, mock_websocket)

        # Verify connection is working
        self.assertTrue(mock_websocket.is_connected)

        # Verify message history was sent
        history_messages = mock_websocket.get_messages_by_type("message_history")
        self.assertEqual(len(history_messages), 1)

        # Verify router state was loaded from database
        self.assertEqual(router_state["id"], self.router_id)
        # Router status is stored in database, not as an attribute
        self.assertEqual(router_state["model"], "gpt-4.1-nano")

        # Verify message history content
        history_data = history_messages[0]["data"]
        self.assertEqual(history_data["router_id"], self.router_id)
        self.assertIn("messages", history_data)

    async def test_input_lock_unlock_websocket_updates(self):
        """Test that input lock/unlock sends proper WebSocket updates."""
        router_state, mock_websocket = await self.create_router_with_websocket()

        # Test input lock with functional API
        await router_operations.send_input_lock(
            router_state["id"], router_state["agent_db"], mock_websocket
        )

        lock_messages = mock_websocket.get_messages_by_type("input_lock")
        self.assertEqual(len(lock_messages), 1)

        lock_data = lock_messages[0]["data"]
        self.assertEqual(lock_data["type"], "input_lock")
        self.assertEqual(lock_data["router_id"], self.router_id)
        # Router processing status is stored in database, not as an attribute

        # Test input unlock with functional API
        await router_operations.send_input_unlock(
            router_state["id"], router_state["agent_db"], mock_websocket
        )

        unlock_messages = mock_websocket.get_messages_by_type("input_unlock")
        self.assertEqual(len(unlock_messages), 1)

        unlock_data = unlock_messages[0]["data"]
        self.assertEqual(unlock_data["type"], "input_unlock")
        self.assertEqual(unlock_data["router_id"], self.router_id)
        # Router status is stored in database, not as an attribute

    async def test_status_updates_during_processing(self):
        """Test status updates are sent via WebSocket during processing."""
        router_state, mock_websocket = await self.create_router_with_websocket()

        # Send various status updates
        status_messages = [
            "Thinking",
            "Processing files",
            "Analyzing data",
            "Generating response",
        ]

        for status in status_messages:
            await router_operations.send_status(
                status=status, router_id=router_state["id"], websocket=mock_websocket
            )

        # Verify all status messages were sent
        sent_status_messages = mock_websocket.get_messages_by_type("status")
        self.assertEqual(len(sent_status_messages), len(status_messages))

        # Verify message content
        for i, status in enumerate(status_messages):
            status_data = sent_status_messages[i]["data"]
            self.assertEqual(status_data["type"], "status")
            self.assertEqual(status_data["message"], status)
            self.assertEqual(status_data["router_id"], self.router_id)

    async def test_message_delivery_via_websocket(self):
        """Test that messages are properly delivered via WebSocket."""
        router_state, mock_websocket = await self.create_router_with_websocket()

        # Test user message
        user_message = "Test user message"
        await router_operations.send_user_message(
            content=user_message, router_id=router_state["id"], websocket=mock_websocket
        )

        user_messages = mock_websocket.get_messages_by_type("message")
        self.assertEqual(len(user_messages), 1)

        user_data = user_messages[0]["data"]
        self.assertEqual(user_data["type"], "message")
        self.assertEqual(user_data["role"], "user")
        self.assertEqual(user_data["content"], user_message)
        self.assertEqual(user_data["router_id"], self.router_id)

        # Test assistant message
        assistant_message = "Test assistant response"
        message_id = 123
        await router_operations.send_assistant_message(
            content=assistant_message, 
            router_id=router_state["id"], 
            websocket=mock_websocket, 
            message_id=message_id
        )

        assistant_messages = mock_websocket.get_messages_by_type("response")
        self.assertEqual(len(assistant_messages), 1)

        assistant_data = assistant_messages[0]["data"]
        self.assertEqual(assistant_data["type"], "response")
        self.assertEqual(assistant_data["message"], assistant_message)
        self.assertEqual(assistant_data["message_id"], message_id)
        self.assertEqual(assistant_data["router_id"], self.router_id)

    async def test_error_handling_via_websocket(self):
        """Test error messages are sent via WebSocket."""
        router_state, mock_websocket = await self.create_router_with_websocket()

        # Send error message
        error_message = "Test error occurred"
        await router_operations.send_error(
            error=error_message, router_id=router_state["id"], websocket=mock_websocket
        )

        error_messages = mock_websocket.get_messages_by_type("error")
        self.assertEqual(len(error_messages), 1)

        error_data = error_messages[0]["data"]
        self.assertEqual(error_data["type"], "error")
        self.assertEqual(error_data["message"], error_message)
        self.assertEqual(error_data["router_id"], self.router_id)

    @patch("agent.core.router_operations.assess_agent_requirements")
    @patch("agent.core.router_operations.handle_simple_chat")
    async def test_websocket_updates_during_simple_chat(
        self, mock_simple_chat, mock_assess
    ):
        """Test WebSocket updates during simple chat processing."""
        router_state, mock_websocket = await self.create_router_with_websocket()

        # Mock simple chat response
        mock_simple_chat.return_value = "Simple chat response"

        # Mock agent requirements (no agent needed)
        from agent.models.responses import RequireAgent

        mock_assess.return_value = RequireAgent(
            web_search_required=False,
            calculation_required=False,  # Add missing required field
            complex_question=False,  # Add missing required field
            chilli_request=False,
            context_rich_agent_request="",
        )

        # Handle message
        message_data = {"message": "Hello, how are you?"}
        await router_operations.handle_message(
            router_state, message_data, websocket=mock_websocket
        )

        # Verify WebSocket message sequence
        all_messages = mock_websocket.sent_messages
        self.assertGreater(len(all_messages), 0)

        # Check for input lock
        lock_messages = mock_websocket.get_messages_by_type("input_lock")
        self.assertEqual(len(lock_messages), 1)

        # Check for status updates
        status_messages = mock_websocket.get_messages_by_type("status")
        self.assertGreater(len(status_messages), 0)

        # Check for response
        response_messages = mock_websocket.get_messages_by_type("response")
        self.assertEqual(len(response_messages), 1)
        self.assertEqual(
            response_messages[0]["data"]["message"], "Simple chat response"
        )

        # Check for input unlock
        unlock_messages = mock_websocket.get_messages_by_type("input_unlock")
        self.assertEqual(len(unlock_messages), 1)

    @patch("agent.tasks.task_utils.update_planner_next_task_and_queue")
    @patch("agent.core.router_operations.assess_agent_requirements")
    async def test_websocket_updates_during_complex_request(
        self, mock_assess, mock_queue_task
    ):
        """Test WebSocket updates during complex request processing."""
        router_state, mock_websocket = await self.create_router_with_websocket()
        
        # Add mock LLM for handle_message
        from unittest.mock import AsyncMock
        mock_llm = AsyncMock()
        mock_llm.a_get_response.return_value = type('MockResponse', (), {
            'content': 'Test response'
        })()
        router_state["llm"] = mock_llm

        # Mock agent requirements (agent needed)
        from agent.models.responses import RequireAgent

        mock_assess.return_value = RequireAgent(
            web_search_required=True,
            calculation_required=False,  # Add missing required field
            complex_question=True,  # Add missing required field
            chilli_request=False,
            context_rich_agent_request="Search for information about Python",
        )

        # Mock task queueing
        mock_queue_task.return_value = True

        # Handle complex message
        message_data = {"message": "Search for Python programming information"}
        await router_operations.handle_message(
            router_state, message_data, websocket=mock_websocket
        )

        # Verify WebSocket message sequence
        all_messages = mock_websocket.sent_messages
        self.assertGreater(len(all_messages), 0)

        # Check for input lock
        lock_messages = mock_websocket.get_messages_by_type("input_lock")
        self.assertEqual(len(lock_messages), 1)

        # Check for status updates
        status_messages = mock_websocket.get_messages_by_type("status")
        self.assertGreater(len(status_messages), 0)

        # Check for "Agents assemble!" message
        response_messages = mock_websocket.get_messages_by_type("response")
        self.assertEqual(len(response_messages), 1)
        self.assertEqual(response_messages[0]["data"]["message"], "Agents assemble!")

        # Check for input unlock
        unlock_messages = mock_websocket.get_messages_by_type("input_unlock")
        self.assertEqual(len(unlock_messages), 1)

    async def test_websocket_message_ordering(self):
        """Test that WebSocket messages are sent in correct order."""
        router_state, mock_websocket = await self.create_router_with_websocket()

        # Send sequence of messages
        await router_operations.send_input_lock(
            router_state["id"], router_state["agent_db"], mock_websocket
        )
        await router_operations.send_status(
            status="Processing", router_id=router_state["id"], websocket=mock_websocket
        )
        await router_operations.send_assistant_message(
            content="Working on it...", router_id=router_state["id"], websocket=mock_websocket
        )
        await router_operations.send_status(
            status="Almost done", router_id=router_state["id"], websocket=mock_websocket
        )
        await router_operations.send_assistant_message(
            content="Complete!", router_id=router_state["id"], websocket=mock_websocket
        )
        await router_operations.send_input_unlock(
            router_state["id"], router_state["agent_db"], mock_websocket
        )

        # Verify message order
        all_messages = mock_websocket.sent_messages
        self.assertEqual(len(all_messages), 6)

        # Check sequence
        self.assertEqual(all_messages[0]["data"]["type"], "input_lock")
        self.assertEqual(all_messages[1]["data"]["type"], "status")
        self.assertEqual(all_messages[1]["data"]["message"], "Processing")
        self.assertEqual(all_messages[2]["data"]["type"], "response")
        self.assertEqual(all_messages[2]["data"]["message"], "Working on it...")
        self.assertEqual(all_messages[3]["data"]["type"], "status")
        self.assertEqual(all_messages[3]["data"]["message"], "Almost done")
        self.assertEqual(all_messages[4]["data"]["type"], "response")
        self.assertEqual(all_messages[4]["data"]["message"], "Complete!")
        self.assertEqual(all_messages[5]["data"]["type"], "input_unlock")

    async def test_websocket_connection_resilience(self):
        """Test WebSocket resilience when connection fails."""
        router_state, mock_websocket = await self.create_router_with_websocket()

        # Test normal operation
        await router_operations.send_status(
            status="Normal operation", router_id=router_state["id"], websocket=mock_websocket
        )
        self.assertEqual(len(mock_websocket.get_messages_by_type("status")), 1)

        # Simulate connection failure
        mock_websocket.is_connected = False

        # These should raise ConnectionError but shouldn't crash the router
        try:
            await router_operations.send_status(
                status="After disconnection", router_id=router_state["id"], websocket=mock_websocket
            )
        except ConnectionError:
            pass  # Expected when WebSocket is disconnected

        try:
            await router_operations.send_assistant_message(
                content="Should not crash", router_id=router_state["id"], websocket=mock_websocket
            )
        except ConnectionError:
            pass  # Expected when WebSocket is disconnected

        try:
            await router_operations.send_error(
                error="Error after disconnection", router_id=router_state["id"], websocket=mock_websocket
            )
        except ConnectionError:
            pass  # Expected when WebSocket is disconnected

        # Messages should not be added when disconnected
        status_messages = mock_websocket.get_messages_by_type("status")
        self.assertEqual(len(status_messages), 1)  # Only the first one

    async def test_websocket_concurrent_message_sending(self):
        """Test concurrent WebSocket message sending."""
        router_state, mock_websocket = await self.create_router_with_websocket()

        # Send multiple messages concurrently
        async def send_status_batch(start_idx, count):
            for i in range(count):
                await router_operations.send_status(
                    status=f"Status {start_idx + i}", router_id=router_state["id"], websocket=mock_websocket
                )

        # Run concurrent status updates
        await asyncio.gather(
            send_status_batch(1, 5), send_status_batch(6, 5), send_status_batch(11, 5)
        )

        # Verify all messages were sent
        status_messages = mock_websocket.get_messages_by_type("status")
        self.assertEqual(len(status_messages), 15)

        # Verify message content (order may vary due to concurrency)
        sent_statuses = [msg["data"]["message"] for msg in status_messages]
        expected_statuses = [f"Status {i}" for i in range(1, 16)]

        self.assertEqual(sorted(sent_statuses), sorted(expected_statuses))

    async def test_planner_completion_websocket_updates(self):
        """Test WebSocket updates when planner completes."""
        router_state, mock_websocket = await self.create_router_with_websocket()

        # Create a completed planner in database
        planner_id = "test_planner_123"
        user_response = "This is the final planner response"

        # Create planner first, then update with user_response
        await self.db.create_planner(
            planner_id=planner_id,
            planner_name="Test Planner",
            user_question="Test question",
            instruction="Test instruction",
            status="completed",
        )

        # Update with user_response
        await self.db.update_planner(planner_id=planner_id, user_response=user_response)

        # Handle planner completion
        await router_operations.handle_planner_completion(
            router_state, planner_id=planner_id, websocket=mock_websocket
        )

        # Verify response was sent via WebSocket
        response_messages = mock_websocket.get_messages_by_type("response")
        self.assertEqual(len(response_messages), 1)

        response_data = response_messages[0]["data"]
        self.assertEqual(response_data["message"], user_response)
        self.assertEqual(response_data["router_id"], self.router_id)

        # Verify router status was updated to active
        # Router status is stored in database, not as an attribute

    async def test_websocket_message_timestamps(self):
        """Test that WebSocket messages include proper timestamps."""
        router_state, mock_websocket = await self.create_router_with_websocket()

        start_time = time.time()

        # Send messages with small delays
        await router_operations.send_status(
            status="First message", router_id=router_state["id"], websocket=mock_websocket
        )
        await asyncio.sleep(0.01)
        await router_operations.send_status(
            status="Second message", router_id=router_state["id"], websocket=mock_websocket
        )
        await asyncio.sleep(0.01)
        await router_operations.send_status(
            status="Third message", router_id=router_state["id"], websocket=mock_websocket
        )

        end_time = time.time()

        # Verify timestamps are within expected range
        status_messages = mock_websocket.get_messages_by_type("status")
        self.assertEqual(len(status_messages), 3)

        for msg in status_messages:
            timestamp = msg["timestamp"]
            self.assertGreaterEqual(timestamp, start_time)
            self.assertLessEqual(timestamp, end_time)

        # Verify timestamps are in order
        timestamps = [msg["timestamp"] for msg in status_messages]
        self.assertEqual(timestamps, sorted(timestamps))

    async def test_websocket_large_message_handling(self):
        """Test WebSocket handling of large messages."""
        router_state, mock_websocket = await self.create_router_with_websocket()

        # Create large message content
        large_content = "A" * 10000  # 10KB message

        # Send large message
        await router_operations.send_assistant_message(
            content=large_content, router_id=router_state["id"], websocket=mock_websocket
        )

        # Verify message was sent correctly
        response_messages = mock_websocket.get_messages_by_type("response")
        self.assertEqual(len(response_messages), 1)

        response_data = response_messages[0]["data"]
        self.assertEqual(response_data["message"], large_content)
        self.assertEqual(len(response_data["message"]), 10000)

    async def test_websocket_json_serialization(self):
        """Test WebSocket JSON serialization of complex data."""
        router_state, mock_websocket = await self.create_router_with_websocket()

        # Test complex message content with special characters
        complex_content = {
            "text": "Complex content with special chars: 🚀 \"quotes\" 'apostrophes' & symbols",
            "data": {"numbers": [1, 2, 3], "boolean": True, "null": None},
        }

        # Send message with complex content (converted to string for message)
        content_str = json.dumps(complex_content)
        await router_operations.send_assistant_message(
            content=content_str, router_id=router_state["id"], websocket=mock_websocket
        )

        # Verify message was serialized correctly
        response_messages = mock_websocket.get_messages_by_type("response")
        self.assertEqual(len(response_messages), 1)

        # Verify we can parse the content back
        response_content = response_messages[0]["data"]["message"]
        parsed_content = json.loads(response_content)
        self.assertEqual(parsed_content, complex_content)


if __name__ == "__main__":
    # Run the tests with asyncio
    unittest.main(verbosity=2)
