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
import tempfile
import shutil
import uuid
import os
from unittest.mock import MagicMock, AsyncMock, patch
from pathlib import Path

# Import the modules under test
from agent.core.router import RouterAgent
from agent.models.agent_database import AgentDatabase
from agent.config.settings import settings


class MockWebSocket:
    """Mock WebSocket for testing WebSocket communications."""
    
    def __init__(self):
        self.sent_messages = []
        self.is_connected = True
        self.client_state = "connected"
        self.scope = {
            "path": "/ws/test_router",
            "client": ["127.0.0.1", 8000]
        }
    
    async def send_json(self, data):
        """Mock send_json that records sent messages."""
        if self.is_connected:
            message = {
                "timestamp": time.time(),
                "data": data
            }
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
        return [msg for msg in self.sent_messages if msg["data"].get("type") == message_type]
    
    def get_latest_message_by_type(self, message_type):
        """Get the latest message of a specific type."""
        messages = self.get_messages_by_type(message_type)
        return messages[-1] if messages else None


class TestWebSocketUpdatesExecution(unittest.TestCase):
    """Test WebSocket updates during agent execution."""
    
    def setUp(self):
        """Set up test environment before each test."""
        # Create temporary directory for testing
        self.test_dir = tempfile.mkdtemp()
        self.original_base_path = settings.collaterals_base_path
        
        # Mock settings to use test directory
        settings.collaterals_base_path = self.test_dir
        
        # Set up in-memory database for testing
        # Create temporary database file for testing
        db_fd, self.test_db_path = tempfile.mkstemp(suffix='.db')
        os.close(db_fd)  # Close file descriptor, AgentDatabase will open it
        
        # Create AgentDatabase with test database path
        self.db = AgentDatabase(database_path=self.test_db_path)
        
        # Test data
        self.router_id = f"test_router_{uuid.uuid4().hex[:8]}"
        self.websocket_messages = []
        
    def tearDown(self):
        """Clean up after each test."""
        # Restore original settings
        settings.collaterals_base_path = self.original_base_path
        
        # Remove test directory
        shutil.rmtree(self.test_dir, ignore_errors=True)
        
        # Remove test database file
        if hasattr(self, 'test_db_path') and os.path.exists(self.test_db_path):
            os.unlink(self.test_db_path)

    def create_router_with_websocket(self):
        """Create a router with mock WebSocket connection for ephemeral architecture."""
        # Create router in database first (simulate activation)
        self.db.create_router(
            router_id=self.router_id,
            status="active",
            model="gpt-4.1-nano",
            temperature=0.0,
            title="Test Router",
            preview="Test router for websocket testing"
        )
        
        # Create ephemeral router instance that loads from database
        router = RouterAgent(self.router_id)
        router._agent_db = self.db  # Use test database
        
        mock_websocket = MockWebSocket()
        
        return router, mock_websocket

    async def test_websocket_connection_establishment(self):
        """Test ephemeral router creation and message history sending."""
        router, mock_websocket = self.create_router_with_websocket()
        
        # Test message history sending with ephemeral architecture
        await router.send_message_history(websocket=mock_websocket)
        
        # Verify connection is working
        self.assertTrue(mock_websocket.is_connected)
        
        # Verify message history was sent
        history_messages = mock_websocket.get_messages_by_type("message_history")
        self.assertEqual(len(history_messages), 1)
        
        # Verify router state was loaded from database
        self.assertEqual(router.id, self.router_id)
        self.assertEqual(router.status, "active")
        self.assertEqual(router.model, "gpt-4.1-nano")
        
        # Verify message history content
        history_data = history_messages[0]["data"]
        self.assertEqual(history_data["router_id"], self.router_id)
        self.assertIn("messages", history_data)

    async def test_input_lock_unlock_websocket_updates(self):
        """Test that input lock/unlock sends proper WebSocket updates."""
        router, mock_websocket = self.create_router_with_websocket()
        
        # Test input lock with websocket parameter
        await router.send_input_lock(websocket=mock_websocket)
        
        lock_messages = mock_websocket.get_messages_by_type("input_lock")
        self.assertEqual(len(lock_messages), 1)
        
        lock_data = lock_messages[0]["data"]
        self.assertEqual(lock_data["type"], "input_lock")
        self.assertEqual(lock_data["router_id"], self.router_id)
        self.assertEqual(router.status, "processing")
        
        # Test input unlock with websocket parameter
        await router.send_input_unlock(websocket=mock_websocket)
        
        unlock_messages = mock_websocket.get_messages_by_type("input_unlock")
        self.assertEqual(len(unlock_messages), 1)
        
        unlock_data = unlock_messages[0]["data"]
        self.assertEqual(unlock_data["type"], "input_unlock")
        self.assertEqual(unlock_data["router_id"], self.router_id)
        self.assertEqual(router.status, "active")

    async def test_status_updates_during_processing(self):
        """Test status updates are sent via WebSocket during processing."""
        router, mock_websocket = self.create_router_with_websocket()
        
        # Send various status updates
        status_messages = [
            "Thinking",
            "Processing files",
            "Analyzing data",
            "Generating response"
        ]
        
        for status in status_messages:
            await router.send_status(status=status, websocket=mock_websocket)
        
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
        router, mock_websocket = self.create_router_with_websocket()
        
        # Test user message
        user_message = "Test user message"
        await router.send_user_message(content=user_message, websocket=mock_websocket)
        
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
        await router.send_assistant_message(content=assistant_message, websocket=mock_websocket, message_id=message_id)
        
        assistant_messages = mock_websocket.get_messages_by_type("response")
        self.assertEqual(len(assistant_messages), 1)
        
        assistant_data = assistant_messages[0]["data"]
        self.assertEqual(assistant_data["type"], "response")
        self.assertEqual(assistant_data["message"], assistant_message)
        self.assertEqual(assistant_data["message_id"], message_id)
        self.assertEqual(assistant_data["router_id"], self.router_id)

    async def test_error_handling_via_websocket(self):
        """Test error messages are sent via WebSocket."""
        router, mock_websocket = self.create_router_with_websocket()
        
        # Send error message
        error_message = "Test error occurred"
        await router.send_error(error=error_message, websocket=mock_websocket)
        
        error_messages = mock_websocket.get_messages_by_type("error")
        self.assertEqual(len(error_messages), 1)
        
        error_data = error_messages[0]["data"]
        self.assertEqual(error_data["type"], "error")
        self.assertEqual(error_data["message"], error_message)
        self.assertEqual(error_data["router_id"], self.router_id)

    @patch('agent.core.router.RouterAgent.assess_agent_requirements')
    @patch('agent.core.router.RouterAgent.handle_simple_chat')
    async def test_websocket_updates_during_simple_chat(self, mock_simple_chat, mock_assess):
        """Test WebSocket updates during simple chat processing."""
        router, mock_websocket = self.create_router_with_websocket()
        
        # Mock simple chat response
        mock_simple_chat.return_value = "Simple chat response"
        
        # Mock agent requirements (no agent needed)
        from agent.models.responses import RequireAgent
        mock_assess.return_value = RequireAgent(
            web_search_required=False,
            chilli_request=False,
            context_rich_agent_request=""
        )
        
        # Handle message
        message_data = {"message": "Hello, how are you?"}
        await router.handle_message(message_data)
        
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
        self.assertEqual(response_messages[0]["data"]["message"], "Simple chat response")
        
        # Check for input unlock
        unlock_messages = mock_websocket.get_messages_by_type("input_unlock")
        self.assertEqual(len(unlock_messages), 1)

    @patch('agent.tasks.task_utils.update_planner_next_task_and_queue')
    @patch('agent.core.router.RouterAgent.assess_agent_requirements')
    async def test_websocket_updates_during_complex_request(self, mock_assess, mock_queue_task):
        """Test WebSocket updates during complex request processing."""
        router, mock_websocket = self.create_router_with_websocket()
        
        # Mock agent requirements (agent needed)
        from agent.models.responses import RequireAgent
        mock_assess.return_value = RequireAgent(
            web_search_required=True,
            chilli_request=False,
            context_rich_agent_request="Search for information about Python"
        )
        
        # Mock task queueing
        mock_queue_task.return_value = True
        
        # Handle complex message
        message_data = {"message": "Search for Python programming information"}
        await router.handle_message(message_data)
        
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
        router, mock_websocket = self.create_router_with_websocket()
        
        # Send sequence of messages
        await router.send_input_lock(websocket=mock_websocket)
        await router.send_status(status="Processing", websocket=mock_websocket)
        await router.send_assistant_message(content="Working on it...", websocket=mock_websocket)
        await router.send_status(status="Almost done", websocket=mock_websocket)
        await router.send_assistant_message(content="Complete!", websocket=mock_websocket)
        await router.send_input_unlock(websocket=mock_websocket)
        
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
        router, mock_websocket = self.create_router_with_websocket()
        
        # Test normal operation
        await router.send_status(status="Normal operation", websocket=mock_websocket)
        self.assertEqual(len(mock_websocket.get_messages_by_type("status")), 1)
        
        # Simulate connection failure
        mock_websocket.is_connected = False
        
        # These should not raise exceptions
        await router.send_status(status="After disconnection", websocket=mock_websocket)
        await router.send_assistant_message(content="Should not crash", websocket=mock_websocket)
        await router.send_error(error="Error after disconnection", websocket=mock_websocket)
        
        # Messages should not be added when disconnected
        status_messages = mock_websocket.get_messages_by_type("status")
        self.assertEqual(len(status_messages), 1)  # Only the first one

    async def test_websocket_concurrent_message_sending(self):
        """Test concurrent WebSocket message sending."""
        router, mock_websocket = self.create_router_with_websocket()
        
        # Send multiple messages concurrently
        async def send_status_batch(start_idx, count):
            for i in range(count):
                await router.send_status(status=f"Status {start_idx + i}", websocket=mock_websocket)
        
        # Run concurrent status updates
        await asyncio.gather(
            send_status_batch(1, 5),
            send_status_batch(6, 5),
            send_status_batch(11, 5)
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
        router, mock_websocket = self.create_router_with_websocket()
        
        # Create a completed planner in database
        planner_id = "test_planner_123"
        user_response = "This is the final planner response"
        
        self.db.create_planner(
            planner_id=planner_id,
            planner_name="Test Planner",
            user_question="Test question",
            instruction="Test instruction",
            status="completed",
            user_response=user_response
        )
        
        # Handle planner completion
        await router.handle_planner_completion(planner_id=planner_id, websocket=None)
        
        # Verify response was sent via WebSocket
        response_messages = mock_websocket.get_messages_by_type("response")
        self.assertEqual(len(response_messages), 1)
        
        response_data = response_messages[0]["data"]
        self.assertEqual(response_data["message"], user_response)
        self.assertEqual(response_data["router_id"], self.router_id)
        
        # Verify router status was updated to active
        self.assertEqual(router.status, "active")

    async def test_websocket_message_timestamps(self):
        """Test that WebSocket messages include proper timestamps."""
        router, mock_websocket = self.create_router_with_websocket()
        
        start_time = time.time()
        
        # Send messages with small delays
        await router.send_status(status="First message", websocket=mock_websocket)
        await asyncio.sleep(0.01)
        await router.send_status(status="Second message", websocket=mock_websocket)
        await asyncio.sleep(0.01)
        await router.send_status(status="Third message", websocket=mock_websocket)
        
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
        router, mock_websocket = self.create_router_with_websocket()
        
        # Create large message content
        large_content = "A" * 10000  # 10KB message
        
        # Send large message
        await router.send_assistant_message(content=large_content, websocket=mock_websocket)
        
        # Verify message was sent correctly
        response_messages = mock_websocket.get_messages_by_type("response")
        self.assertEqual(len(response_messages), 1)
        
        response_data = response_messages[0]["data"]
        self.assertEqual(response_data["message"], large_content)
        self.assertEqual(len(response_data["message"]), 10000)

    async def test_websocket_json_serialization(self):
        """Test WebSocket JSON serialization of complex data."""
        router, mock_websocket = self.create_router_with_websocket()
        
        # Test complex message content with special characters
        complex_content = {
            "text": "Complex content with special chars: 🚀 \"quotes\" 'apostrophes' & symbols",
            "data": {"numbers": [1, 2, 3], "boolean": True, "null": None}
        }
        
        # Send message with complex content (converted to string for message)
        content_str = json.dumps(complex_content)
        await router.send_assistant_message(content=content_str, websocket=mock_websocket)
        
        # Verify message was serialized correctly
        response_messages = mock_websocket.get_messages_by_type("response")
        self.assertEqual(len(response_messages), 1)
        
        # Verify we can parse the content back
        response_content = response_messages[0]["data"]["message"]
        parsed_content = json.loads(response_content)
        self.assertEqual(parsed_content, complex_content)


if __name__ == '__main__':
    # Run the tests with asyncio
    unittest.main(verbosity=2)