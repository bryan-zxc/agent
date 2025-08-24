"""
Comprehensive unit tests for RouterAgent methods.
Following lightweight testing philosophy - vanilla flow execution with proper mocking.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
from pathlib import Path
from PIL import Image
import json

from src.agent.core.router import RouterAgent
from src.agent.models.responses import RequireAgent
from src.agent.models.schemas import File, DocumentContext, FileGrouping


class TestRouterAgent(unittest.IsolatedAsyncioTestCase):
    """Lightweight tests for RouterAgent methods - vanilla flow only."""

    async def asyncSetUp(self):
        """Set up minimal test environment."""
        self.router_id = f"test_router_{uuid.uuid4().hex[:8]}"
        
    def test_router_initialisation_new_router(self):
        """Test RouterAgent initialisation for new router (no router_id provided)."""
        with patch('src.agent.core.router.AgentDatabase') as MockDB, \
             patch('src.agent.core.router.LLM') as MockLLM:
            
            # Configure mocks
            mock_db_instance = AsyncMock()
            MockDB.return_value = mock_db_instance
            mock_llm_instance = MagicMock()
            MockLLM.return_value = mock_llm_instance
            
            # Create router without ID
            router = RouterAgent()
            
            # Verify initialisation
            self.assertIsNotNone(router.id)
            self.assertEqual(router.agent_type, "router")
            self.assertEqual(len(router.id), 32)  # UUID hex string
            MockLLM.assert_called_once_with(caller="router")

    def test_router_initialisation_existing_router(self):
        """Test RouterAgent initialisation for existing router (router_id provided)."""
        with patch('src.agent.core.router.AgentDatabase') as MockDB, \
             patch('src.agent.core.router.LLM') as MockLLM, \
             patch.object(RouterAgent, '_load_existing_state') as mock_load_state:
            
            # Configure mocks
            mock_db_instance = AsyncMock()
            MockDB.return_value = mock_db_instance
            mock_llm_instance = MagicMock()
            MockLLM.return_value = mock_llm_instance
            mock_load_state.return_value = None  # Make it non-awaitable for sync init
            
            # Create router with ID
            router = RouterAgent(router_id=self.router_id)
            
            # Verify initialisation
            self.assertEqual(router.id, self.router_id)
            self.assertEqual(router.agent_type, "router")
            MockLLM.assert_called_once_with(caller="router")
            # Note: _load_existing_state is called but not awaited in __init__

    async def test_load_existing_state_success(self):
        """Test _load_existing_state ACTUALLY EXECUTES with successful state loading."""
        with patch('src.agent.core.router.AgentDatabase') as MockDB, \
             patch('src.agent.core.router.LLM') as MockLLM:
            
            # Configure database mock
            mock_db_instance = AsyncMock()
            MockDB.return_value = mock_db_instance
            mock_db_instance.get_router.return_value = {
                "model": "gpt-4",
                "temperature": 0.5,
                "status": "active"
            }
            
            # Configure LLM mock
            MockLLM.return_value = MagicMock()
            
            # Create router and test state loading
            router = RouterAgent()
            await router._load_existing_state()
            
            # Verify state was loaded
            self.assertEqual(router.model, "gpt-4")
            self.assertEqual(router.temperature, 0.5)
            self.assertEqual(router.status, "active")
            mock_db_instance.get_router.assert_called_once()

    async def test_load_existing_state_router_not_found(self):
        """Test _load_existing_state handles router not found error."""
        with patch('src.agent.core.router.AgentDatabase') as MockDB, \
             patch('src.agent.core.router.LLM') as MockLLM:
            
            # Configure database mock to return None (router not found)
            mock_db_instance = AsyncMock()
            MockDB.return_value = mock_db_instance
            mock_db_instance.get_router.return_value = None
            
            # Configure LLM mock
            MockLLM.return_value = MagicMock()
            
            # Create router and test error handling
            router = RouterAgent()
            
            with self.assertRaises(ValueError) as context:
                await router._load_existing_state()
            
            self.assertIn("not found in database", str(context.exception))
            mock_db_instance.get_router.assert_called_once()

    async def test_get_messages_success(self):
        """Test get_messages ACTUALLY EXECUTES and returns messages."""
        with patch('src.agent.core.router.AgentDatabase') as MockDB, \
             patch('src.agent.core.router.LLM') as MockLLM:
            
            # Configure database mock
            mock_db_instance = AsyncMock()
            MockDB.return_value = mock_db_instance
            mock_db_instance.get_messages.return_value = [
                {"role": "user", "content": "Test message"},
                {"role": "assistant", "content": "Test response"}
            ]
            
            # Configure LLM mock
            MockLLM.return_value = MagicMock()
            
            # Create router and test message retrieval
            router = RouterAgent()
            messages = await router.get_messages()
            
            # Verify messages returned
            self.assertEqual(len(messages), 2)
            self.assertEqual(messages[0]["role"], "user")
            self.assertEqual(messages[1]["role"], "assistant")
            mock_db_instance.get_messages.assert_called_once_with("router", router.id)

    async def test_add_message_text_only(self):
        """Test add_message ACTUALLY EXECUTES with text content."""
        with patch('src.agent.core.router.AgentDatabase') as MockDB, \
             patch('src.agent.core.router.LLM') as MockLLM:
            
            # Configure database mock
            mock_db_instance = AsyncMock()
            MockDB.return_value = mock_db_instance
            mock_db_instance.add_message.return_value = 123  # Mock message ID
            
            # Configure LLM mock
            MockLLM.return_value = MagicMock()
            
            # Create router and test message addition
            router = RouterAgent()
            message_id = await router.add_message(role="user", content="Test message")
            
            # Verify message was added
            self.assertEqual(message_id, 123)
            mock_db_instance.add_message.assert_called_once_with(
                agent_type="router",
                agent_id=router.id,
                role="user",
                content="Test message"
            )

    async def test_add_message_with_image(self):
        """Test add_message ACTUALLY EXECUTES with image content."""
        with patch('src.agent.core.router.AgentDatabase') as MockDB, \
             patch('src.agent.core.router.LLM') as MockLLM, \
             patch('src.agent.core.router.encode_image') as mock_encode_image, \
             patch('src.agent.core.router.decode_image') as mock_decode_image:
            
            # Configure database mock
            mock_db_instance = AsyncMock()
            MockDB.return_value = mock_db_instance
            mock_db_instance.add_message.return_value = 456  # Mock message ID
            
            # Configure LLM mock
            MockLLM.return_value = MagicMock()
            
            # Configure image encoding mock
            mock_encode_image.return_value = "encoded_image_data"
            
            # Configure image decoding mock
            mock_decode_image.return_value = MagicMock()
            
            # Create mock image instead of real PIL Image to avoid encoding issues
            test_image = MagicMock()
            test_image.__class__ = Image.Image
            
            # Create router and test message addition with image
            router = RouterAgent()
            message_id = await router.add_message(
                role="user", 
                content="Test message with image", 
                image=test_image
            )
            
            # Verify message was added
            self.assertEqual(message_id, 456)
            mock_db_instance.add_message.assert_called_once()
            # Verify content includes both text and image
            call_args = mock_db_instance.add_message.call_args
            content = call_args[1]['content']
            self.assertIsInstance(content, list)
            self.assertEqual(len(content), 2)
            self.assertEqual(content[0]['type'], 'text')
            self.assertEqual(content[1]['type'], 'image_url')

    async def test_activate_conversation_success(self):
        """Test activate_conversation ACTUALLY EXECUTES full conversation activation."""
        with patch('src.agent.core.router.AgentDatabase') as MockDB, \
             patch('src.agent.core.router.LLM') as MockLLM, \
             patch.object(RouterAgent, 'handle_message') as mock_handle_message:
            
            # Configure database mock
            mock_db_instance = AsyncMock()
            MockDB.return_value = mock_db_instance
            mock_db_instance.create_router.return_value = True
            mock_db_instance.add_message.return_value = 789
            
            # Configure LLM mock
            MockLLM.return_value = MagicMock()
            
            # Configure handle_message mock
            mock_handle_message.return_value = None
            
            # Create WebSocket mock
            mock_websocket = AsyncMock()
            
            # Create router and test conversation activation
            router = RouterAgent()
            await router.activate_conversation(
                user_message="Hello, how are you?",
                websocket=mock_websocket,
                files=None
            )
            
            # Verify router was created in database
            mock_db_instance.create_router.assert_called_once()
            # Verify system message was added
            mock_db_instance.add_message.assert_called()
            # Verify message handling was called
            mock_handle_message.assert_called_once()
            # Verify instance variables are set
            self.assertEqual(router.model, "gpt-4.1-nano")  # settings.router_model
            self.assertEqual(router.temperature, 0.0)
            self.assertEqual(router.status, "active")

    async def test_handle_simple_chat_success(self):
        """Test handle_simple_chat ACTUALLY EXECUTES and returns response."""
        with patch('src.agent.core.router.AgentDatabase') as MockDB, \
             patch('src.agent.core.router.LLM') as MockLLM:
            
            # Configure database mock
            mock_db_instance = AsyncMock()
            MockDB.return_value = mock_db_instance
            mock_db_instance.get_messages.return_value = [
                {"role": "user", "content": "Hello"}
            ]
            
            # Configure LLM mock
            mock_llm_instance = AsyncMock()
            mock_response = MagicMock()
            mock_response.content = "Hello! How can I help you today?"
            mock_llm_instance.a_get_response.return_value = mock_response
            MockLLM.return_value = mock_llm_instance
            
            # Create router with model and temperature
            router = RouterAgent()
            router._model = "gpt-4"
            router._temperature = 0.0
            
            # Test simple chat
            response = await router.handle_simple_chat()
            
            # Verify response
            self.assertEqual(response, "Hello! How can I help you today?")
            mock_llm_instance.a_get_response.assert_called_once()

    async def test_assess_agent_requirements_success(self):
        """Test assess_agent_requirements ACTUALLY EXECUTES and returns requirements."""
        with patch('src.agent.core.router.AgentDatabase') as MockDB, \
             patch('src.agent.core.router.LLM') as MockLLM:
            
            # Configure database mock
            mock_db_instance = AsyncMock()
            MockDB.return_value = mock_db_instance
            mock_db_instance.get_messages.return_value = [
                {"role": "user", "content": "I need to search for information about AI"}
            ]
            
            # Configure LLM mock
            mock_llm_instance = AsyncMock()
            mock_requirements = RequireAgent(
                calculation_required=False,
                web_search_required=True,
                complex_question=True,
                chilli_request=False,
                context_rich_agent_request="Search for information about AI"
            )
            mock_llm_instance.a_get_response.return_value = mock_requirements
            MockLLM.return_value = mock_llm_instance
            
            # Create router with model and temperature
            router = RouterAgent()
            router._model = "gpt-4"
            router._temperature = 0.0
            
            # Test agent requirements assessment
            requirements = await router.assess_agent_requirements()
            
            # Verify requirements
            self.assertIsInstance(requirements, RequireAgent)
            self.assertTrue(requirements.web_search_required)
            mock_llm_instance.a_get_response.assert_called_once()

    async def test_process_files_csv_success(self):
        """Test process_files ACTUALLY EXECUTES with CSV file processing."""
        with patch('src.agent.core.router.AgentDatabase') as MockDB, \
             patch('src.agent.core.router.LLM') as MockLLM, \
             patch('src.agent.core.router.duckdb') as mock_duckdb, \
             patch('pathlib.Path.exists') as mock_exists:
            
            # Configure database and LLM mocks
            MockDB.return_value = AsyncMock()
            MockLLM.return_value = MagicMock()
            
            # Configure CSV processing mocks
            mock_duckdb.sql.return_value = True  # Simulate successful CSV read
            mock_exists.return_value = True
            
            # Create router
            router = RouterAgent()
            
            # Test file processing with CSV
            test_files = ["/path/to/test.csv"]
            processed_files, errors, instructions = await router.process_files(test_files)
            
            # Verify processing
            self.assertEqual(len(processed_files), 1)
            self.assertEqual(len(errors), 0)
            self.assertGreater(len(instructions), 0)
            self.assertEqual(processed_files[0].file_type, "data")
            self.assertEqual(processed_files[0].data_context, "csv")

    async def test_process_files_invalid_csv(self):
        """Test process_files ACTUALLY EXECUTES with invalid CSV handling."""
        with patch('src.agent.core.router.AgentDatabase') as MockDB, \
             patch('src.agent.core.router.LLM') as MockLLM, \
             patch('src.agent.core.router.duckdb') as mock_duckdb, \
             patch('pathlib.Path.exists') as mock_exists:
            
            # Configure database and LLM mocks
            MockDB.return_value = AsyncMock()
            MockLLM.return_value = MagicMock()
            
            # Configure CSV processing to fail
            mock_duckdb.sql.side_effect = Exception("Invalid CSV format")
            mock_exists.return_value = True
            
            # Create router
            router = RouterAgent()
            
            # Test file processing with invalid CSV
            test_files = ["/path/to/invalid.csv"]
            processed_files, errors, instructions = await router.process_files(test_files)
            
            # Verify error handling
            self.assertEqual(len(processed_files), 0)
            self.assertEqual(len(errors), 1)
            self.assertIn("cannot be processed", errors[0])

    async def test_determine_file_groups_single_file(self):
        """Test determine_file_groups ACTUALLY EXECUTES with single file."""
        with patch('src.agent.core.router.AgentDatabase') as MockDB, \
             patch('src.agent.core.router.LLM') as MockLLM:
            
            # Configure mocks
            MockDB.return_value = AsyncMock()
            MockLLM.return_value = MagicMock()
            
            # Create router
            router = RouterAgent()
            
            # Test single file grouping
            files = ["/path/to/single.csv"]
            groups = await router.determine_file_groups("Analyze this file", files)
            
            # Verify single group with single file
            self.assertEqual(len(groups), 1)
            self.assertEqual(groups[0], files)

    async def test_determine_file_groups_multiple_files(self):
        """Test determine_file_groups ACTUALLY EXECUTES with multiple files."""
        with patch('src.agent.core.router.AgentDatabase') as MockDB, \
             patch('src.agent.core.router.LLM') as MockLLM:
            
            # Configure database mock
            MockDB.return_value = AsyncMock()
            
            # Configure LLM mock
            mock_llm_instance = AsyncMock()
            mock_grouping = FileGrouping(file_groups=[
                ["/path/to/file1.csv", "/path/to/file2.csv"],
                ["/path/to/file3.pdf"]
            ])
            mock_llm_instance.a_get_response.return_value = mock_grouping
            MockLLM.return_value = mock_llm_instance
            
            # Create router with model and temperature
            router = RouterAgent()
            router._model = "gpt-4"
            router._temperature = 0.0
            
            # Test multiple file grouping
            files = ["/path/to/file1.csv", "/path/to/file2.csv", "/path/to/file3.pdf"]
            groups = await router.determine_file_groups("Analyze these files", files)
            
            # Verify grouping
            self.assertEqual(len(groups), 2)
            self.assertEqual(len(groups[0]), 2)
            self.assertEqual(len(groups[1]), 1)
            mock_llm_instance.a_get_response.assert_called_once()

    async def test_send_user_message_success(self):
        """Test send_user_message ACTUALLY EXECUTES WebSocket communication."""
        with patch('src.agent.core.router.AgentDatabase') as MockDB, \
             patch('src.agent.core.router.LLM') as MockLLM:
            
            # Configure mocks
            MockDB.return_value = AsyncMock()
            MockLLM.return_value = MagicMock()
            
            # Create WebSocket mock
            mock_websocket = AsyncMock()
            
            # Create router
            router = RouterAgent()
            
            # Test WebSocket message sending
            await router.send_user_message("Test user message", mock_websocket)
            
            # Verify WebSocket was called
            mock_websocket.send_json.assert_called_once()
            call_args = mock_websocket.send_json.call_args[0][0]
            self.assertEqual(call_args["type"], "message")
            self.assertEqual(call_args["role"], "user")
            self.assertEqual(call_args["content"], "Test user message")
            self.assertEqual(call_args["router_id"], router.id)

    async def test_send_status_success(self):
        """Test send_status ACTUALLY EXECUTES WebSocket status update."""
        with patch('src.agent.core.router.AgentDatabase') as MockDB, \
             patch('src.agent.core.router.LLM') as MockLLM:
            
            # Configure mocks
            MockDB.return_value = AsyncMock()
            MockLLM.return_value = MagicMock()
            
            # Create WebSocket mock
            mock_websocket = AsyncMock()
            
            # Create router
            router = RouterAgent()
            
            # Test status sending
            await router.send_status("Processing...", mock_websocket)
            
            # Verify WebSocket was called
            mock_websocket.send_json.assert_called_once()
            call_args = mock_websocket.send_json.call_args[0][0]
            self.assertEqual(call_args["type"], "status")
            self.assertEqual(call_args["message"], "Processing...")
            self.assertEqual(call_args["router_id"], router.id)

    async def test_send_assistant_message_success(self):
        """Test send_assistant_message ACTUALLY EXECUTES WebSocket response."""
        with patch('src.agent.core.router.AgentDatabase') as MockDB, \
             patch('src.agent.core.router.LLM') as MockLLM:
            
            # Configure mocks
            MockDB.return_value = AsyncMock()
            MockLLM.return_value = MagicMock()
            
            # Create WebSocket mock
            mock_websocket = AsyncMock()
            
            # Create router
            router = RouterAgent()
            
            # Test assistant message sending with message ID
            await router.send_assistant_message("Test response", mock_websocket, message_id=123)
            
            # Verify WebSocket was called
            mock_websocket.send_json.assert_called_once()
            call_args = mock_websocket.send_json.call_args[0][0]
            self.assertEqual(call_args["type"], "response")
            self.assertEqual(call_args["message"], "Test response")
            self.assertEqual(call_args["router_id"], router.id)
            self.assertEqual(call_args["message_id"], 123)

    async def test_send_input_lock_success(self):
        """Test send_input_lock ACTUALLY EXECUTES input locking."""
        with patch('src.agent.core.router.AgentDatabase') as MockDB, \
             patch('src.agent.core.router.LLM') as MockLLM:
            
            # Configure mocks
            MockDB.return_value = AsyncMock()
            MockLLM.return_value = MagicMock()
            
            # Create WebSocket mock
            mock_websocket = AsyncMock()
            
            # Create router
            router = RouterAgent()
            router._status = "active"  # Set initial status
            
            # Test input locking
            await router.send_input_lock(mock_websocket)
            
            # Verify status changed
            self.assertEqual(router.status, "processing")
            
            # Verify WebSocket was called
            mock_websocket.send_json.assert_called_once()
            call_args = mock_websocket.send_json.call_args[0][0]
            self.assertEqual(call_args["type"], "input_lock")
            self.assertEqual(call_args["router_id"], router.id)

    async def test_send_input_unlock_success(self):
        """Test send_input_unlock ACTUALLY EXECUTES input unlocking."""
        with patch('src.agent.core.router.AgentDatabase') as MockDB, \
             patch('src.agent.core.router.LLM') as MockLLM:
            
            # Configure mocks
            MockDB.return_value = AsyncMock()
            MockLLM.return_value = MagicMock()
            
            # Create WebSocket mock
            mock_websocket = AsyncMock()
            
            # Create router
            router = RouterAgent()
            router._status = "processing"  # Set initial status
            
            # Test input unlocking
            await router.send_input_unlock(mock_websocket)
            
            # Verify status changed
            self.assertEqual(router.status, "active")
            
            # Verify WebSocket was called
            mock_websocket.send_json.assert_called_once()
            call_args = mock_websocket.send_json.call_args[0][0]
            self.assertEqual(call_args["type"], "input_unlock")
            self.assertEqual(call_args["router_id"], router.id)

    async def test_handle_planner_completion_success(self):
        """Test handle_planner_completion ACTUALLY EXECUTES completion handling."""
        with patch('src.agent.core.router.AgentDatabase') as MockDB, \
             patch('src.agent.core.router.LLM') as MockLLM, \
             patch.object(RouterAgent, 'add_message') as mock_add_message, \
             patch.object(RouterAgent, 'send_assistant_message') as mock_send_message:
            
            # Configure database mock
            mock_db_instance = AsyncMock()
            MockDB.return_value = mock_db_instance
            mock_db_instance.get_planner.return_value = {
                "user_response": "Here's the analysis result..."
            }
            
            # Configure LLM mock
            MockLLM.return_value = MagicMock()
            
            # Configure method mocks
            mock_add_message.return_value = 999
            mock_send_message.return_value = None
            
            # Create WebSocket mock
            mock_websocket = AsyncMock()
            
            # Create router
            router = RouterAgent()
            
            # Test planner completion handling
            test_planner_id = "test_planner_123"
            await router.handle_planner_completion(test_planner_id, mock_websocket)
            
            # Verify planner was retrieved
            mock_db_instance.get_planner.assert_called_once_with(test_planner_id)
            
            # Verify message was added and sent
            mock_add_message.assert_called_once_with(role="assistant", content="Here's the analysis result...")
            mock_send_message.assert_called_once_with(content="Here's the analysis result...", websocket=mock_websocket)
            
            # Verify status changed to active
            self.assertEqual(router.status, "active")

    async def test_handle_planner_completion_planner_not_found(self):
        """Test handle_planner_completion handles planner not found gracefully."""
        with patch('src.agent.core.router.AgentDatabase') as MockDB, \
             patch('src.agent.core.router.LLM') as MockLLM:
            
            # Configure database mock to return None (planner not found)
            mock_db_instance = AsyncMock()
            MockDB.return_value = mock_db_instance
            mock_db_instance.get_planner.return_value = None
            
            # Configure LLM mock
            MockLLM.return_value = MagicMock()
            
            # Create WebSocket mock
            mock_websocket = AsyncMock()
            
            # Create router
            router = RouterAgent()
            
            # Test planner completion handling with missing planner
            test_planner_id = "nonexistent_planner"
            await router.handle_planner_completion(test_planner_id, mock_websocket)
            
            # Verify planner was retrieved but nothing else happened
            mock_db_instance.get_planner.assert_called_once_with(test_planner_id)
            
            # Verify WebSocket was not called (early return)
            mock_websocket.send_json.assert_not_called()