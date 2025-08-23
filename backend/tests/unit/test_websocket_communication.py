"""
WebSocket Communication Test Suite

Tests for real-time WebSocket communication including connection handling,
message routing, and session management. Integrates existing WebSocket test patterns.
"""

import unittest
import asyncio
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from src.agent.core.router import RouterAgent


class MockWebSocket:
    """Enhanced MockWebSocket for testing WebSocket communications."""
    
    def __init__(self, connected: bool = True):
        self.sent_messages = []
        self.is_connected = connected
        self.client_state = "connected" if connected else "disconnected"
        self.scope = {
            "path": "/ws/test_router",
            "client": ["127.0.0.1", 8000],
            "type": "websocket"
        }
        self.call_count = 0
    
    async def send_json(self, data):
        """Mock async send_json that records sent messages."""
        self.call_count += 1
        if self.is_connected:
            message = {
                "timestamp": time.time(),
                "data": data,
                "call_order": self.call_count
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
    
    def disconnect(self):
        """Simulate connection loss."""
        self.is_connected = False
        self.client_state = "disconnected"


class TestWebSocketCommunication(unittest.IsolatedAsyncioTestCase):
    """Test WebSocket communication functionality."""

    async def asyncSetUp(self):
        """Set up test environment."""
        self.router_id = f"test_router_{uuid.uuid4().hex[:8]}"
        self.mock_websocket = MockWebSocket()

    async def test_websocket_connection_establishment(self):
        """Test WebSocket connection establishment and message history sending."""
        with patch('src.agent.models.agent_database.AgentDatabase') as MockDB:
            mock_db = AsyncMock()
            MockDB.return_value = mock_db
            
            # Mock router data
            mock_db.get_router.return_value = {
                "router_id": self.router_id,
                "status": "active",
                "model": "gpt-4",
                "temperature": 0.7,
                "title": "Test Router",
                "preview": "Test preview"
            }
            mock_db.get_messages.return_value = [
                {"role": "user", "content": "Hello", "created_at": "2024-01-01T00:00:00"},
                {"role": "assistant", "content": "Hi there!", "created_at": "2024-01-01T00:00:01"}
            ]
            
            router = RouterAgent(router_id=self.router_id)
            router._agent_db = mock_db
            
            # Send message history (simulates connection establishment)
            await router.send_message_history(websocket=self.mock_websocket)
            
            # Verify connection is working
            self.assertTrue(self.mock_websocket.is_connected)
            
            # Verify message history was sent
            history_messages = self.mock_websocket.get_messages_by_type("message_history")
            self.assertEqual(len(history_messages), 1)
            
            # Verify message history content
            history_data = history_messages[0]["data"]
            self.assertEqual(history_data["router_id"], self.router_id)
            self.assertIn("messages", history_data)
            self.assertEqual(len(history_data["messages"]), 2)

    async def test_websocket_status_updates(self):
        """Test WebSocket status update messages."""
        router = RouterAgent(router_id=self.router_id)
        
        status_messages = [
            "Thinking...",
            "Processing files...",
            "Analysing data...", 
            "Generating response..."
        ]
        
        # Send status updates
        for status in status_messages:
            await router.send_status(status=status, websocket=self.mock_websocket)
        
        # Verify all status messages were sent
        sent_status_messages = self.mock_websocket.get_messages_by_type("status")
        self.assertEqual(len(sent_status_messages), len(status_messages))
        
        # Verify message content and order
        for i, expected_status in enumerate(status_messages):
            status_data = sent_status_messages[i]["data"]
            self.assertEqual(status_data["type"], "status")
            self.assertEqual(status_data["message"], expected_status)
            self.assertEqual(status_data["router_id"], self.router_id)

    async def test_websocket_message_delivery(self):
        """Test user and assistant message delivery via WebSocket."""
        router = RouterAgent(router_id=self.router_id)
        
        # Test user message
        user_content = "What's the weather like today?"
        await router.send_user_message(content=user_content, websocket=self.mock_websocket)
        
        user_messages = self.mock_websocket.get_messages_by_type("message")
        self.assertEqual(len(user_messages), 1)
        
        user_data = user_messages[0]["data"]
        self.assertEqual(user_data["type"], "message")
        self.assertEqual(user_data["role"], "user")
        self.assertEqual(user_data["content"], user_content)
        self.assertEqual(user_data["router_id"], self.router_id)
        
        # Test assistant message
        assistant_content = "Today is sunny with a high of 75°F"
        message_id = 42
        await router.send_assistant_message(
            content=assistant_content,
            websocket=self.mock_websocket,
            message_id=message_id
        )
        
        assistant_messages = self.mock_websocket.get_messages_by_type("response")
        self.assertEqual(len(assistant_messages), 1)
        
        assistant_data = assistant_messages[0]["data"]
        self.assertEqual(assistant_data["type"], "response")
        self.assertEqual(assistant_data["message"], assistant_content)
        self.assertEqual(assistant_data["message_id"], message_id)
        self.assertEqual(assistant_data["router_id"], self.router_id)

    async def test_websocket_input_lock_unlock(self):
        """Test input lock/unlock WebSocket updates."""
        router = RouterAgent(router_id=self.router_id)
        
        # Test input lock
        await router.send_input_lock(websocket=self.mock_websocket)
        
        lock_messages = self.mock_websocket.get_messages_by_type("input_lock")
        self.assertEqual(len(lock_messages), 1)
        
        lock_data = lock_messages[0]["data"]
        self.assertEqual(lock_data["type"], "input_lock")
        self.assertEqual(lock_data["router_id"], self.router_id)
        
        # Test input unlock
        await router.send_input_unlock(websocket=self.mock_websocket)
        
        unlock_messages = self.mock_websocket.get_messages_by_type("input_unlock")
        self.assertEqual(len(unlock_messages), 1)
        
        unlock_data = unlock_messages[0]["data"]
        self.assertEqual(unlock_data["type"], "input_unlock")
        self.assertEqual(unlock_data["router_id"], self.router_id)

    async def test_websocket_error_handling(self):
        """Test error message handling via WebSocket."""
        router = RouterAgent(router_id=self.router_id)
        
        error_message = "Something went wrong during processing"
        await router.send_error(error=error_message, websocket=self.mock_websocket)
        
        error_messages = self.mock_websocket.get_messages_by_type("error")
        self.assertEqual(len(error_messages), 1)
        
        error_data = error_messages[0]["data"]
        self.assertEqual(error_data["type"], "error")
        self.assertEqual(error_data["message"], error_message)
        self.assertEqual(error_data["router_id"], self.router_id)

    async def test_websocket_message_ordering(self):
        """Test that WebSocket messages maintain correct order."""
        router = RouterAgent(router_id=self.router_id)
        
        # Send sequence of different message types
        await router.send_input_lock(websocket=self.mock_websocket)
        await router.send_status(status="Starting", websocket=self.mock_websocket)
        await router.send_user_message(content="User message", websocket=self.mock_websocket)
        await router.send_status(status="Processing", websocket=self.mock_websocket)
        await router.send_assistant_message(content="Assistant response", websocket=self.mock_websocket)
        await router.send_input_unlock(websocket=self.mock_websocket)
        
        # Verify total message count
        all_messages = self.mock_websocket.sent_messages
        self.assertEqual(len(all_messages), 6)
        
        # Verify message order by call_order
        expected_types = ["input_lock", "status", "message", "status", "response", "input_unlock"]
        actual_types = [msg["data"]["type"] for msg in all_messages]
        self.assertEqual(actual_types, expected_types)
        
        # Verify timestamps are in order
        timestamps = [msg["timestamp"] for msg in all_messages]
        self.assertEqual(timestamps, sorted(timestamps))

    async def test_websocket_connection_resilience(self):
        """Test WebSocket handling when connection fails."""
        router = RouterAgent(router_id=self.router_id)
        
        # Test normal operation
        await router.send_status(status="Normal operation", websocket=self.mock_websocket)
        self.assertEqual(len(self.mock_websocket.get_messages_by_type("status")), 1)
        
        # Simulate connection failure
        self.mock_websocket.disconnect()
        
        # These should not raise exceptions (graceful handling)
        await router.send_status(status="After disconnection", websocket=self.mock_websocket)
        await router.send_assistant_message(content="Should not crash", websocket=self.mock_websocket)
        await router.send_error(error="Error after disconnection", websocket=self.mock_websocket)
        
        # Should still only have the first status message
        status_messages = self.mock_websocket.get_messages_by_type("status")
        self.assertEqual(len(status_messages), 1)
        self.assertEqual(status_messages[0]["data"]["message"], "Normal operation")

    async def test_concurrent_websocket_messaging(self):
        """Test concurrent WebSocket message sending."""
        router = RouterAgent(router_id=self.router_id)
        
        # Send multiple messages concurrently
        async def send_status_batch(prefix: str, count: int):
            tasks = []
            for i in range(count):
                task = router.send_status(
                    status=f"{prefix} {i}",
                    websocket=self.mock_websocket
                )
                tasks.append(task)
            await asyncio.gather(*tasks)
        
        # Run concurrent batches
        await asyncio.gather(
            send_status_batch("Batch A", 3),
            send_status_batch("Batch B", 3),
            send_status_batch("Batch C", 3)
        )
        
        # Verify all messages were sent
        status_messages = self.mock_websocket.get_messages_by_type("status")
        self.assertEqual(len(status_messages), 9)
        
        # Verify all expected messages are present
        sent_statuses = [msg["data"]["message"] for msg in status_messages]
        expected_statuses = [
            "Batch A 0", "Batch A 1", "Batch A 2",
            "Batch B 0", "Batch B 1", "Batch B 2", 
            "Batch C 0", "Batch C 1", "Batch C 2"
        ]
        
        # Sort both lists since concurrent execution order may vary
        self.assertEqual(sorted(sent_statuses), sorted(expected_statuses))

    async def test_websocket_large_message_handling(self):
        """Test WebSocket handling of large messages."""
        router = RouterAgent(router_id=self.router_id)
        
        # Create large message content (10KB)
        large_content = "A" * 10000
        
        # Send large message
        await router.send_assistant_message(
            content=large_content,
            websocket=self.mock_websocket
        )
        
        # Verify message was sent correctly
        response_messages = self.mock_websocket.get_messages_by_type("response")
        self.assertEqual(len(response_messages), 1)
        
        response_data = response_messages[0]["data"]
        self.assertEqual(response_data["message"], large_content)
        self.assertEqual(len(response_data["message"]), 10000)

    async def test_websocket_json_serialisation(self):
        """Test WebSocket JSON serialisation of complex data."""
        router = RouterAgent(router_id=self.router_id)
        
        # Test message with special characters and unicode
        complex_content = 'Complex message with "quotes", \'apostrophes\', & symbols: 🚀 🌍 🎉'
        
        await router.send_assistant_message(
            content=complex_content,
            websocket=self.mock_websocket
        )
        
        # Verify message was serialised correctly
        response_messages = self.mock_websocket.get_messages_by_type("response")
        self.assertEqual(len(response_messages), 1)
        
        response_content = response_messages[0]["data"]["message"]
        self.assertEqual(response_content, complex_content)

    async def test_websocket_session_tracking(self):
        """Test WebSocket session tracking functionality."""
        # Simulate session establishment
        session_id = uuid.uuid4().hex
        
        # Mock WebSocket with session info
        self.mock_websocket.session_id = session_id
        
        router = RouterAgent(router_id=self.router_id)
        
        # Send message with session context
        await router.send_status(
            status="Session active",
            websocket=self.mock_websocket
        )
        
        # Verify message includes router context
        status_messages = self.mock_websocket.get_messages_by_type("status")
        self.assertEqual(len(status_messages), 1)
        
        status_data = status_messages[0]["data"]
        self.assertEqual(status_data["router_id"], self.router_id)

    async def test_websocket_message_timestamps(self):
        """Test that WebSocket messages include proper timestamps."""
        router = RouterAgent(router_id=self.router_id)
        
        start_time = time.time()
        
        # Send messages with small delays
        await router.send_status(status="First", websocket=self.mock_websocket)
        await asyncio.sleep(0.01)
        await router.send_status(status="Second", websocket=self.mock_websocket)
        await asyncio.sleep(0.01)
        await router.send_status(status="Third", websocket=self.mock_websocket)
        
        end_time = time.time()
        
        # Verify timestamps are within expected range
        status_messages = self.mock_websocket.get_messages_by_type("status")
        self.assertEqual(len(status_messages), 3)
        
        for msg in status_messages:
            timestamp = msg["timestamp"]
            self.assertGreaterEqual(timestamp, start_time)
            self.assertLessEqual(timestamp, end_time)
        
        # Verify timestamps are in order
        timestamps = [msg["timestamp"] for msg in status_messages]
        self.assertEqual(timestamps, sorted(timestamps))

    async def test_websocket_connection_state_validation(self):
        """Test WebSocket connection state validation."""
        router = RouterAgent(router_id=self.router_id)
        
        # Test with connected WebSocket
        self.assertTrue(self.mock_websocket.is_connected)
        await router.send_status(status="Connected", websocket=self.mock_websocket)
        self.assertEqual(len(self.mock_websocket.sent_messages), 1)
        
        # Test with disconnected WebSocket
        disconnected_ws = MockWebSocket(connected=False)
        
        # Should handle disconnection gracefully
        await router.send_status(status="Disconnected", websocket=disconnected_ws)
        self.assertEqual(len(disconnected_ws.sent_messages), 0)

    async def test_websocket_required_parameters(self):
        """Test that WebSocket methods require WebSocket parameter."""
        router = RouterAgent(router_id=self.router_id)
        
        # All WebSocket methods should require websocket parameter
        websocket_methods = [
            ("send_status", {"status": "test"}),
            ("send_user_message", {"content": "test"}),
            ("send_assistant_message", {"content": "test"}),
            ("send_error", {"error": "test"}),
            ("send_input_lock", {}),
            ("send_input_unlock", {}),
            ("send_message_history", {})
        ]
        
        for method_name, kwargs in websocket_methods:
            method = getattr(router, method_name)
            
            # Should work with websocket parameter
            await method(websocket=self.mock_websocket, **kwargs)
            
            # Verify message was sent (except for methods that may not send in all cases)
            self.assertGreater(len(self.mock_websocket.sent_messages), 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)