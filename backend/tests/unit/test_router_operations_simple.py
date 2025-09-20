"""
Simple unit tests for router_operations functions.
Focus on testing core functionality with proper mocking.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

from src.agent.core import router_operations
from src.agent.config.settings import settings


class TestRouterOperationsSimple(unittest.IsolatedAsyncioTestCase):
    """Simple tests for router_operations functions."""

    async def test_create_router_new(self):
        """Test creating a new router without ID."""
        with patch("src.agent.core.router_operations.AgentDatabase") as MockDB, patch(
            "src.agent.core.router_operations.LLM"
        ) as MockLLM:

            # Configure mocks
            MockDB.create = AsyncMock(return_value=AsyncMock())
            MockLLM.return_value = MagicMock()

            # Create new router
            router_state = await router_operations.create_router()

            # Verify structure
            self.assertIn("id", router_state)
            self.assertIn("agent_db", router_state)
            self.assertIn("llm", router_state)
            self.assertIn("model", router_state)
            self.assertIn("temperature", router_state)
            self.assertEqual(len(router_state["id"]), 32)
            self.assertEqual(router_state["model"], settings.router_model)
            self.assertEqual(router_state["temperature"], 0.0)

    async def test_create_router_existing(self):
        """Test loading existing router with ID."""
        router_id = f"test_{uuid.uuid4().hex[:8]}"

        with patch("src.agent.core.router_operations.AgentDatabase") as MockDB, patch(
            "src.agent.core.router_operations.LLM"
        ) as MockLLM, patch(
            "src.agent.core.router_operations.MessageManager"
        ) as MockMM:

            # Configure database mock
            mock_db = AsyncMock()
            mock_db.get_router.return_value = {
                "model": "gpt-4",
                "temperature": 0.7,
                "status": "active",
            }
            MockDB.create = AsyncMock(return_value=mock_db)

            # Configure other mocks
            MockLLM.return_value = MagicMock()
            MockMM.return_value = MagicMock()

            # Create router with existing ID
            router_state = await router_operations.create_router(router_id=router_id)

            # Verify structure
            self.assertEqual(router_state["id"], router_id)
            self.assertEqual(router_state["model"], "gpt-4")
            self.assertEqual(router_state["temperature"], 0.7)
            self.assertIn("message_manager", router_state)

    async def test_send_user_message(self):
        """Test sending user message via WebSocket."""
        mock_websocket = AsyncMock()
        router_id = "test_router_123"

        await router_operations.send_user_message(
            content="Test message", router_id=router_id, websocket=mock_websocket
        )

        # Verify WebSocket call
        mock_websocket.send_json.assert_called_once()
        call_args = mock_websocket.send_json.call_args[0][0]
        self.assertEqual(call_args["type"], "message")
        self.assertEqual(call_args["role"], "user")
        self.assertEqual(call_args["content"], "Test message")
        self.assertEqual(call_args["router_id"], router_id)

    async def test_send_status(self):
        """Test sending status update via WebSocket."""
        mock_websocket = AsyncMock()
        router_id = "test_router_456"

        await router_operations.send_status(
            status="Processing...", router_id=router_id, websocket=mock_websocket
        )

        # Verify WebSocket call
        mock_websocket.send_json.assert_called_once()
        call_args = mock_websocket.send_json.call_args[0][0]
        self.assertEqual(call_args["type"], "status")
        self.assertEqual(call_args["message"], "Processing...")
        self.assertEqual(call_args["router_id"], router_id)

    async def test_send_assistant_message(self):
        """Test sending assistant response via WebSocket."""
        mock_websocket = AsyncMock()
        router_id = "test_router_789"

        await router_operations.send_assistant_message(
            content="Here is my response",
            router_id=router_id,
            websocket=mock_websocket,
            message_id=999,
        )

        # Verify WebSocket call
        mock_websocket.send_json.assert_called_once()
        call_args = mock_websocket.send_json.call_args[0][0]
        self.assertEqual(call_args["type"], "response")
        self.assertEqual(call_args["message"], "Here is my response")
        self.assertEqual(call_args["router_id"], router_id)
        self.assertEqual(call_args["message_id"], 999)

    async def test_send_error(self):
        """Test sending error message via WebSocket."""
        mock_websocket = AsyncMock()
        router_id = "test_router_error"

        await router_operations.send_error(
            error="Something went wrong", router_id=router_id, websocket=mock_websocket
        )

        # Verify WebSocket call
        mock_websocket.send_json.assert_called_once()
        call_args = mock_websocket.send_json.call_args[0][0]
        self.assertEqual(call_args["type"], "error")
        self.assertEqual(call_args["message"], "Something went wrong")
        self.assertEqual(call_args["router_id"], router_id)

    async def test_send_input_lock(self):
        """Test locking input via WebSocket."""
        mock_websocket = AsyncMock()
        mock_db = AsyncMock()
        router_id = "test_router_lock"

        await router_operations.send_input_lock(
            router_id=router_id, agent_db=mock_db, websocket=mock_websocket
        )

        # Verify database update with keyword arguments
        mock_db.update_router.assert_called_once_with(
            router_id=router_id, status="processing"
        )

        # Verify WebSocket call
        mock_websocket.send_json.assert_called_once()
        call_args = mock_websocket.send_json.call_args[0][0]
        self.assertEqual(call_args["type"], "input_lock")
        self.assertEqual(call_args["router_id"], router_id)

    async def test_send_input_unlock(self):
        """Test unlocking input via WebSocket."""
        mock_websocket = AsyncMock()
        mock_db = AsyncMock()
        router_id = "test_router_unlock"

        await router_operations.send_input_unlock(
            router_id=router_id, agent_db=mock_db, websocket=mock_websocket
        )

        # Verify database update with keyword arguments
        mock_db.update_router.assert_called_once_with(
            router_id=router_id, status="active"
        )

        # Verify WebSocket call
        mock_websocket.send_json.assert_called_once()
        call_args = mock_websocket.send_json.call_args[0][0]
        self.assertEqual(call_args["type"], "input_unlock")
        self.assertEqual(call_args["router_id"], router_id)

    async def test_handle_simple_chat(self):
        """Test handling simple chat response."""
        with patch("src.agent.core.router_operations.MessageManager") as MockMM:
            # Configure message manager
            mock_mm = AsyncMock()
            mock_mm.get_messages.return_value = [{"role": "user", "content": "Hello"}]

            # Configure LLM
            mock_llm = AsyncMock()
            mock_response = MagicMock()
            mock_response.content = "Hello! How can I help?"
            mock_llm.a_get_response.return_value = mock_response

            # Create mock agent_db
            mock_agent_db = AsyncMock()
            mock_agent_db.get_router_system_instruction.return_value = "Default router instruction"
            
            # Create router state
            router_state = {
                "id": "test_router",
                "llm": mock_llm,
                "model": settings.router_model,
                "temperature": 0.0,
                "message_manager": mock_mm,
                "agent_db": mock_agent_db,
            }

            # Test simple chat
            response = await router_operations.handle_simple_chat(
                router_state=router_state
            )

            # Verify response
            self.assertEqual(response, "Hello! How can I help?")
            mock_llm.a_get_response.assert_called_once()

    async def test_send_message_history(self):
        """Test sending message history via WebSocket."""
        mock_websocket = AsyncMock()

        # Configure agent_db mock
        mock_db = AsyncMock()
        mock_db.get_messages_for_display.return_value = [
            {"role": "user", "content": "Message 1"},
            {"role": "assistant", "content": "Response 1"},
            {"role": "user", "content": "Message 2"},
        ]

        # Create router state with agent_db
        router_state = {
            "id": "test_router_history",
            "agent_db": mock_db,
        }

        # Send message history
        await router_operations.send_message_history(
            router_state=router_state, websocket=mock_websocket
        )

        # Verify messages were retrieved from database
        mock_db.get_messages_for_display.assert_called_once_with(
            agent_type="router", agent_id="test_router_history"
        )

        # Verify message history was sent in one call
        mock_websocket.send_json.assert_called_once()
        call_args = mock_websocket.send_json.call_args[0][0]

        # Check structure
        self.assertEqual(call_args["type"], "message_history")
        self.assertEqual(call_args["router_id"], "test_router_history")
        self.assertEqual(len(call_args["messages"]), 3)

        # Check each message in the batch
        self.assertEqual(call_args["messages"][0]["content"], "Message 1")
        self.assertEqual(call_args["messages"][1]["content"], "Response 1")
        self.assertEqual(call_args["messages"][2]["content"], "Message 2")

    def test_encode_image_content(self):
        """Test encoding image content utility function."""
        from PIL import Image
        import io
        import base64

        # Create a simple test image
        test_image = Image.new("RGB", (10, 10), color="red")

        # Test encoding
        result = router_operations.encode_image_content(
            content="Test message with image", image=test_image
        )

        # Verify structure
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)

        # Check text part
        self.assertEqual(result[0]["type"], "text")
        self.assertEqual(result[0]["text"], "Test message with image")

        # Check image part
        self.assertEqual(result[1]["type"], "image_url")
        self.assertIn("image_url", result[1])
        self.assertIn("url", result[1]["image_url"])

        # Verify it's a valid base64 image URL
        url = result[1]["image_url"]["url"]
        self.assertTrue(url.startswith("data:image/png;base64,"))

        # Verify base64 content can be decoded
        base64_content = url.replace("data:image/png;base64,", "")
        try:
            base64.b64decode(base64_content)
        except Exception as e:
            self.fail(f"Invalid base64 content: {e}")
