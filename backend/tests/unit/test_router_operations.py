"""
Comprehensive unit tests for router_operations functions.
Following lightweight testing philosophy - vanilla flow execution with proper mocking.
Tests the function-based architecture refactored from RouterAgent class.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch, call
import uuid
from pathlib import Path
from PIL import Image
import json
from typing import Dict, Any, List

from src.agent.core import router_operations
from src.agent.models.responses import RequireAgent
from src.agent.models.schemas import File, DocumentContext, FileGrouping
from src.agent.config.settings import settings


class TestRouterOperations(unittest.IsolatedAsyncioTestCase):
    """Lightweight tests for router_operations functions - vanilla flow only."""

    async def asyncSetUp(self):
        """Set up minimal test environment."""
        self.router_id = f"test_router_{uuid.uuid4().hex[:8]}"

    async def test_create_router_new_without_id(self):
        """Test create_router for new router without providing router_id."""
        with patch("src.agent.core.router_operations.AgentDatabase") as MockDB, patch(
            "src.agent.core.router_operations.LLM"
        ) as MockLLM:

            # Configure mocks
            mock_db_instance = AsyncMock()
            MockDB.create = AsyncMock(return_value=mock_db_instance)
            mock_llm_instance = MagicMock()
            MockLLM.return_value = mock_llm_instance

            # Create router without ID
            router_state = await router_operations.create_router()

            # Verify router_state structure
            self.assertIn("id", router_state)
            self.assertIn("agent_db", router_state)
            self.assertIn("llm", router_state)
            self.assertNotIn("agent_type", router_state)  # Not included in new router
            self.assertEqual(len(router_state["id"]), 32)  # UUID hex string
            MockLLM.assert_called_once_with(caller="router")

    async def test_create_router_existing_with_id(self):
        """Test create_router for existing router with router_id provided."""
        with patch("src.agent.core.router_operations.AgentDatabase") as MockDB, patch(
            "src.agent.core.router_operations.LLM"
        ) as MockLLM, patch(
            "src.agent.core.router_operations.load_existing_router_state"
        ) as mock_load_state:

            # Configure mocks
            mock_db_instance = AsyncMock()
            MockDB.create = AsyncMock(return_value=mock_db_instance)
            mock_llm_instance = MagicMock()
            MockLLM.return_value = mock_llm_instance
            mock_load_state.return_value = {
                "model": "gpt-4",
                "temperature": 0.5,
                "status": "active",
            }

            # Create router with ID
            router_state = await router_operations.create_router(
                router_id=self.router_id
            )

            # Verify router_state
            self.assertEqual(router_state["id"], self.router_id)
            self.assertEqual(router_state["model"], "gpt-4")
            self.assertEqual(router_state["temperature"], 0.5)
            mock_load_state.assert_called_once_with(
                router_id=self.router_id, agent_db=mock_db_instance
            )

    async def test_load_existing_router_state_success(self):
        """Test load_existing_router_state with successful state loading."""
        with patch(
            "src.agent.core.router_operations.MessageManager"
        ) as MockMessageManager:

            # Configure database mock
            mock_db = AsyncMock()
            mock_db.get_router.return_value = {
                "model": "gpt-4",
                "temperature": 0.5,
                "status": "active",
            }

            # Configure MessageManager mock
            mock_message_manager = AsyncMock()
            MockMessageManager.return_value = mock_message_manager

            # Test state loading
            state_update = await router_operations.load_existing_router_state(
                router_id=self.router_id, agent_db=mock_db
            )

            # Verify state was loaded
            self.assertEqual(state_update["model"], "gpt-4")
            self.assertEqual(state_update["temperature"], 0.5)
            self.assertEqual(state_update["status"], "active")
            mock_db.get_router.assert_called_once_with(router_id=self.router_id)

    async def test_load_existing_router_state_not_found(self):
        """Test load_existing_router_state handles router not found error."""
        # Configure database mock to return None
        mock_db = AsyncMock()
        mock_db.get_router.return_value = None

        # Test error handling
        with self.assertRaises(ValueError) as context:
            await router_operations.load_existing_router_state(
                router_id=self.router_id, agent_db=mock_db
            )

        self.assertIn("not found in database", str(context.exception))
        mock_db.get_router.assert_called_once_with(router_id=self.router_id)

    async def test_activate_conversation_success(self):
        """Test activate_conversation for full conversation activation."""
        with patch(
            "src.agent.core.router_operations.create_router"
        ) as mock_create_router, patch(
            "src.agent.core.router_operations.handle_message"
        ) as mock_handle_message, patch(
            "src.agent.core.router_operations.MessageManager"
        ) as MockMessageManager:

            # Configure router creation mock
            mock_router_state = {
                "id": self.router_id,
                "agent_db": AsyncMock(),
                "llm": MagicMock(),
                "model": settings.router_model,
                "temperature": 0.0,
                "agent_type": "router",
            }
            mock_create_router.return_value = mock_router_state

            # Configure database operations
            mock_router_state["agent_db"].create_router.return_value = True
            mock_router_state["agent_db"].add_message.return_value = 789

            # Configure MessageManager mock properly
            mock_message_manager = AsyncMock()
            # Important: Make _messages a real list, not an AsyncMock
            mock_message_manager._messages = []
            mock_message_manager.add_message = AsyncMock()
            MockMessageManager.return_value = mock_message_manager

            # Configure handle_message mock
            mock_handle_message.return_value = None

            # Create WebSocket mock
            mock_websocket = AsyncMock()

            # Test conversation activation
            await router_operations.activate_conversation(
                user_message="Hello, how are you?", websocket=mock_websocket, files=None
            )

            # Verify router was created
            mock_create_router.assert_called_once()
            # Verify database operations
            mock_router_state["agent_db"].create_router.assert_called_once()
            # Verify MessageManager was created
            MockMessageManager.assert_called_once_with(
                db=mock_router_state["agent_db"], agent_type="router", agent_id=self.router_id
            )
            # Verify message handling with fully qualified parameters
            mock_handle_message.assert_called_once_with(
                router_state=mock_router_state,
                message_data={"message": "Hello, how are you?", "files": []},
                websocket=mock_websocket,
            )

    async def test_handle_message_simple_chat(self):
        """Test handle_message for simple chat flow."""
        with patch(
            "src.agent.core.router_operations.send_status"
        ) as mock_send_status, patch(
            "src.agent.core.router_operations.send_input_lock"
        ) as mock_lock, patch(
            "src.agent.core.router_operations.assess_agent_requirements"
        ) as mock_assess, patch(
            "src.agent.core.router_operations.handle_simple_chat"
        ) as mock_simple_chat, patch(
            "src.agent.core.router_operations.send_assistant_message"
        ) as mock_send_assistant, patch(
            "src.agent.core.router_operations.send_input_unlock"
        ) as mock_unlock:

            # Configure router state
            mock_db = AsyncMock()
            mock_db.add_message.return_value = {"message_id": "123", "display_texts": []}
            mock_db.get_router.return_value = {"status": "active", "mode": "auto"}
            # Configure message manager mock
            mock_message_manager = AsyncMock()

            router_state = {
                "id": self.router_id,
                "agent_db": mock_db,
                "llm": MagicMock(),
                "model": settings.router_model,
                "temperature": 0.0,
                "message_manager": mock_message_manager,
            }

            # Configure assessment to indicate simple chat
            mock_requirements = RequireAgent(
                calculation_required=False,
                web_search_required=False,
                complex_question=False,
                chilli_request=False,
                context_rich_agent_request="",
            )
            mock_assess.return_value = mock_requirements

            # Configure simple chat response
            mock_simple_chat.return_value = "Hello! How can I help you today?"

            # Create WebSocket mock
            mock_websocket = AsyncMock()

            # Test message handling
            await router_operations.handle_message(
                router_state=router_state,
                message_data={"message": "Hello"},
                websocket=mock_websocket,
            )

            # Verify flow with fully qualified parameters
            # Note: handle_message doesn't send user messages, it stores them in message_manager
            mock_message_manager.add_message.assert_any_call(
                role="user", content="Hello"
            )
            # Input locking is disabled - tracked in separate ticket
            # mock_lock.assert_called_once_with(
            #     router_id=self.router_id, agent_db=mock_db, websocket=mock_websocket
            # )
            mock_assess.assert_called_once_with(router_state=router_state)
            mock_simple_chat.assert_called_once_with(router_state=router_state)
            mock_send_assistant.assert_called_once_with(
                content="Hello! How can I help you today?",
                router_id=self.router_id,
                websocket=mock_websocket,
            )
            # Input unlock is also disabled
            # mock_unlock.assert_called_once_with(
            #     router_id=self.router_id, agent_db=mock_db, websocket=mock_websocket
            # )

    async def test_handle_message_complex_request(self):
        """Test handle_message for complex request flow."""
        with patch(
            "src.agent.core.router_operations.send_status"
        ) as mock_send_status, patch(
            "src.agent.core.router_operations.send_input_lock"
        ) as mock_lock, patch(
            "src.agent.core.router_operations.assess_agent_requirements"
        ) as mock_assess, patch(
            "src.agent.core.router_operations.handle_complex_request"
        ) as mock_complex, patch(
            "src.agent.core.router_operations.send_input_unlock"
        ) as mock_unlock:

            # Configure router state
            mock_db = AsyncMock()
            mock_db.get_router.return_value = {"status": "active", "mode": "auto"}
            # Configure message manager mock
            mock_message_manager = AsyncMock()

            router_state = {
                "id": self.router_id,
                "agent_db": mock_db,
                "llm": MagicMock(),
                "model": settings.router_model,
                "temperature": 0.0,
                "message_manager": mock_message_manager,
            }

            # Configure assessment to indicate complex request
            mock_requirements = RequireAgent(
                calculation_required=True,
                web_search_required=True,
                complex_question=True,
                chilli_request=False,
                context_rich_agent_request="Analyse this complex data",
            )
            mock_assess.return_value = mock_requirements

            # Create WebSocket mock
            mock_websocket = AsyncMock()

            # Test message handling
            await router_operations.handle_message(
                router_state=router_state,
                message_data={
                    "message": "Analyse this data",
                    "files": ["/path/to/data.csv"],
                },
                websocket=mock_websocket,
            )

            # Verify complex request was called with fully qualified parameters
            mock_complex.assert_called_once_with(
                router_state=router_state,
                files=["/path/to/data.csv"],
                websocket=mock_websocket,
            )

    async def test_handle_simple_chat_success(self):
        """Test handle_simple_chat returns response successfully."""
        with patch(
            "src.agent.core.router_operations.MessageManager"
        ) as MockMessageManager:

            # Configure MessageManager mock
            mock_message_manager = AsyncMock()
            mock_message_manager.get_messages.return_value = [
                {"role": "user", "content": "Hello"}
            ]

            # Configure LLM mock
            mock_llm = AsyncMock()
            mock_response = MagicMock()
            mock_response.content = "Hello! How can I help you today?"
            mock_llm.a_get_response.return_value = mock_response

            # Configure router state
            router_state = {
                "id": self.router_id,
                "agent_db": AsyncMock(),
                "llm": mock_llm,
                "model": settings.router_model,
                "temperature": 0.0,
                "message_manager": mock_message_manager,
            }

            # Test simple chat
            response = await router_operations.handle_simple_chat(
                router_state=router_state
            )

            # Verify response
            self.assertEqual(response, "Hello! How can I help you today?")
            mock_llm.a_get_response.assert_called_once()

    async def test_assess_agent_requirements_success(self):
        """Test assess_agent_requirements returns requirements."""
        with patch(
            "src.agent.core.router_operations.MessageManager"
        ) as MockMessageManager:

            # Configure MessageManager mock
            mock_message_manager = AsyncMock()
            mock_message_manager.get_messages.return_value = [
                {"role": "user", "content": "I need to search for information about AI"}
            ]

            # Configure LLM mock
            mock_llm = AsyncMock()
            mock_requirements = RequireAgent(
                calculation_required=False,
                web_search_required=True,
                complex_question=True,
                chilli_request=False,
                context_rich_agent_request="Search for information about AI",
            )
            mock_llm.a_get_response.return_value = mock_requirements

            # Configure router state
            router_state = {
                "id": self.router_id,
                "agent_db": AsyncMock(),
                "llm": mock_llm,
                "model": settings.router_model,
                "temperature": 0.0,
                "message_manager": mock_message_manager,
            }

            # Test agent requirements assessment
            requirements = await router_operations.assess_agent_requirements(
                router_state=router_state
            )

            # Verify requirements
            self.assertIsInstance(requirements, RequireAgent)
            self.assertTrue(requirements.web_search_required)
            mock_llm.a_get_response.assert_called_once()

    async def test_send_user_message_success(self):
        """Test send_user_message WebSocket communication."""
        # Create WebSocket mock
        mock_websocket = AsyncMock()

        # Test WebSocket message sending
        await router_operations.send_user_message(
            content="Test user message",
            router_id=self.router_id,
            websocket=mock_websocket,
        )

        # Verify WebSocket was called with fully qualified parameters
        mock_websocket.send_json.assert_called_once()
        call_args = mock_websocket.send_json.call_args[0][0]
        self.assertEqual(call_args["type"], "message")
        self.assertEqual(call_args["role"], "user")
        self.assertEqual(call_args["content"], "Test user message")
        self.assertEqual(call_args["router_id"], self.router_id)

    async def test_send_status_success(self):
        """Test send_status WebSocket status update."""
        # Create WebSocket mock
        mock_websocket = AsyncMock()

        # Test status sending
        await router_operations.send_status(
            status="Processing...", router_id=self.router_id, websocket=mock_websocket
        )

        # Verify WebSocket was called
        mock_websocket.send_json.assert_called_once()
        call_args = mock_websocket.send_json.call_args[0][0]
        self.assertEqual(call_args["type"], "status")
        self.assertEqual(call_args["message"], "Processing...")
        self.assertEqual(call_args["router_id"], self.router_id)

    async def test_send_assistant_message_success(self):
        """Test send_assistant_message WebSocket response."""
        # Create WebSocket mock
        mock_websocket = AsyncMock()

        # Test assistant message sending with message ID
        await router_operations.send_assistant_message(
            content="Test response",
            router_id=self.router_id,
            websocket=mock_websocket,
            message_id=123,
        )

        # Verify WebSocket was called
        mock_websocket.send_json.assert_called_once()
        call_args = mock_websocket.send_json.call_args[0][0]
        self.assertEqual(call_args["type"], "response")
        self.assertEqual(call_args["message"], "Test response")
        self.assertEqual(call_args["router_id"], self.router_id)
        self.assertEqual(call_args["message_id"], 123)

    async def test_send_error_success(self):
        """Test send_error WebSocket error message."""
        # Create WebSocket mock
        mock_websocket = AsyncMock()

        # Test error message sending
        await router_operations.send_error(
            error="Something went wrong",
            router_id=self.router_id,
            websocket=mock_websocket,
        )

        # Verify WebSocket was called
        mock_websocket.send_json.assert_called_once()
        call_args = mock_websocket.send_json.call_args[0][0]
        self.assertEqual(call_args["type"], "error")
        self.assertEqual(call_args["message"], "Something went wrong")
        self.assertEqual(call_args["router_id"], self.router_id)

    async def test_send_message_history_success(self):
        """Test send_message_history sends all messages via WebSocket."""
        # Configure agent_db mock
        mock_db = AsyncMock()
        mock_db.get_messages_for_display.return_value = [
            {"role": "user", "content": "First message"},
            {"role": "assistant", "content": "First response"},
            {"role": "user", "content": "Second message"},
        ]

        # Configure router state
        router_state = {"id": self.router_id, "agent_db": mock_db}

        # Create WebSocket mock
        mock_websocket = AsyncMock()

        # Test message history sending
        await router_operations.send_message_history(
            router_state=router_state, websocket=mock_websocket
        )

        # Verify message history was sent in one batch
        mock_websocket.send_json.assert_called_once()

        # Verify the batch contains all messages
        call_args = mock_websocket.send_json.call_args[0][0]
        self.assertEqual(call_args["type"], "message_history")
        self.assertEqual(call_args["router_id"], self.router_id)
        self.assertEqual(len(call_args["messages"]), 3)
        self.assertEqual(call_args["messages"][0]["content"], "First message")
        self.assertEqual(call_args["messages"][1]["content"], "First response")
        self.assertEqual(call_args["messages"][2]["content"], "Second message")

    async def test_send_input_lock_success(self):
        """Test send_input_lock updates status and locks input."""
        # Configure database mock
        mock_db = AsyncMock()

        # Create WebSocket mock
        mock_websocket = AsyncMock()

        # Test input locking
        await router_operations.send_input_lock(
            router_id=self.router_id, agent_db=mock_db, websocket=mock_websocket
        )

        # Verify database update with fully qualified parameters
        mock_db.update_router.assert_called_once_with(
            router_id=self.router_id, status="processing"
        )

        # Verify WebSocket was called
        mock_websocket.send_json.assert_called_once()
        call_args = mock_websocket.send_json.call_args[0][0]
        self.assertEqual(call_args["type"], "input_lock")
        self.assertEqual(call_args["router_id"], self.router_id)

    async def test_send_input_unlock_success(self):
        """Test send_input_unlock updates status and unlocks input."""
        # Configure database mock
        mock_db = AsyncMock()

        # Create WebSocket mock
        mock_websocket = AsyncMock()

        # Test input unlocking
        await router_operations.send_input_unlock(
            router_id=self.router_id, agent_db=mock_db, websocket=mock_websocket
        )

        # Verify database update with fully qualified parameters
        mock_db.update_router.assert_called_once_with(
            router_id=self.router_id, status="active"
        )

        # Verify WebSocket was called
        mock_websocket.send_json.assert_called_once()
        call_args = mock_websocket.send_json.call_args[0][0]
        self.assertEqual(call_args["type"], "input_unlock")
        self.assertEqual(call_args["router_id"], self.router_id)

    async def test_process_files_csv_success(self):
        """Test process_files with CSV file processing."""
        with patch("src.agent.core.router_operations.duckdb") as mock_duckdb, patch(
            "pathlib.Path.exists"
        ) as mock_exists:

            # Configure CSV processing mocks
            mock_duckdb.sql.return_value = True  # Simulate successful CSV read
            mock_exists.return_value = True

            # Test file processing with CSV
            test_files = ["/path/to/test.csv"]
            processed_files, errors, instructions = (
                await router_operations.process_files(test_files)
            )

            # Verify processing
            self.assertEqual(len(processed_files), 1)
            self.assertEqual(len(errors), 0)
            self.assertGreater(len(instructions), 0)
            self.assertEqual(processed_files[0].file_type, "data")
            self.assertEqual(processed_files[0].data_context, "csv")

    async def test_process_files_invalid_csv(self):
        """Test process_files with invalid CSV handling."""
        with patch("src.agent.core.router_operations.duckdb") as mock_duckdb, patch(
            "pathlib.Path.exists"
        ) as mock_exists:

            # Configure CSV processing to fail
            mock_duckdb.sql.side_effect = Exception("Invalid CSV format")
            mock_exists.return_value = True

            # Test file processing with invalid CSV
            test_files = ["/path/to/invalid.csv"]
            processed_files, errors, instructions = (
                await router_operations.process_files(test_files)
            )

            # Verify error handling
            self.assertEqual(len(processed_files), 0)
            self.assertEqual(len(errors), 1)
            self.assertIn("cannot be processed", errors[0])

    async def test_determine_file_groups_single_file(self):
        """Test determine_file_groups with single file."""
        # Test single file grouping
        files = ["/path/to/single.csv"]

        # Create router state
        router_state = {
            "id": self.router_id,
            "llm": MagicMock(),
            "model": settings.router_model,
            "temperature": 0.0,
        }

        groups = await router_operations.determine_file_groups(
            router_state=router_state, user_question="Analyze this file", files=files
        )

        # Verify single group with single file
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0], files)

    async def test_determine_file_groups_multiple_files(self):
        """Test determine_file_groups with multiple files."""
        # Configure LLM mock
        mock_llm = AsyncMock()
        mock_grouping = FileGrouping(
            file_groups=[
                ["/path/to/file1.csv", "/path/to/file2.csv"],
                ["/path/to/file3.pdf"],
            ]
        )
        mock_llm.a_get_response.return_value = mock_grouping

        # Create mock agent_db
        mock_agent_db = AsyncMock()
        mock_agent_db.get_router_system_instruction.return_value = "Default router instruction"
        
        # Create router state
        router_state = {
            "id": self.router_id,
            "llm": mock_llm,
            "model": settings.router_model,
            "temperature": 0.0,
            "agent_db": mock_agent_db,
        }

        # Test multiple file grouping
        files = ["/path/to/file1.csv", "/path/to/file2.csv", "/path/to/file3.pdf"]
        groups = await router_operations.determine_file_groups(
            router_state=router_state, user_question="Analyze these files", files=files
        )

        # Verify grouping
        self.assertEqual(len(groups), 2)
        self.assertEqual(len(groups[0]), 2)
        self.assertEqual(len(groups[1]), 1)
        mock_llm.a_get_response.assert_called_once()

    async def test_handle_planner_completion_success(self):
        """Test handle_planner_completion handles completion properly."""
        with patch(
            "src.agent.core.router_operations.MessageManager"
        ) as MockMessageManager, patch(
            "src.agent.core.router_operations.send_assistant_message"
        ) as mock_send_message:

            # Configure database mock
            mock_db = AsyncMock()
            mock_db.get_planner.return_value = {
                "user_response": "Here's the analysis result..."
            }

            # Configure MessageManager mock
            mock_message_manager = AsyncMock()
            mock_message_manager.add_message.return_value = [
                {"role": "assistant", "content": "Here's the analysis result..."}
            ]

            # Configure method mocks
            mock_send_message.return_value = None

            # Create WebSocket mock
            mock_websocket = AsyncMock()

            # Configure router state
            router_state = {
                "id": self.router_id,
                "agent_db": mock_db,
                "message_manager": mock_message_manager,
            }

            # Test planner completion handling
            test_planner_id = "test_planner_123"
            await router_operations.handle_planner_completion(
                router_state=router_state,
                planner_id=test_planner_id,
                websocket=mock_websocket,
            )

            # Verify planner was retrieved
            mock_db.get_planner.assert_called_once_with(planner_id=test_planner_id)

            # Verify message was added and sent with fully qualified parameters
            mock_message_manager.add_message.assert_called_once_with(
                role="assistant", content="Here's the analysis result..."
            )
            mock_send_message.assert_called_once_with(
                content="Here's the analysis result...",
                router_id=self.router_id,
                websocket=mock_websocket,
            )

            # Verify database update for status change
            mock_db.update_router.assert_called_with(
                router_id=self.router_id, status="active"
            )

    async def test_handle_planner_completion_not_found(self):
        """Test handle_planner_completion handles missing planner gracefully."""
        # Configure database mock to return None
        mock_db = AsyncMock()
        mock_db.get_planner.return_value = None

        # Configure message manager mock
        mock_message_manager = AsyncMock()

        # Create WebSocket mock
        mock_websocket = AsyncMock()

        # Configure router state
        router_state = {
            "id": self.router_id,
            "agent_db": mock_db,
            "message_manager": mock_message_manager,
        }

        # Test planner completion handling with missing planner
        test_planner_id = "nonexistent_planner"
        await router_operations.handle_planner_completion(
            router_state=router_state,
            planner_id=test_planner_id,
            websocket=mock_websocket,
        )

        # Verify planner was retrieved but nothing else happened
        mock_db.get_planner.assert_called_once_with(planner_id=test_planner_id)

        # Verify WebSocket was not called (early return)
        mock_websocket.send_json.assert_not_called()

    async def test_invoke_single_success(self):
        """Test invoke_single creates planner and queues task successfully."""
        with patch(
            "src.agent.core.router_operations.process_files"
        ) as mock_process_files, patch(
            "src.agent.core.router_operations.send_assistant_message"
        ) as mock_send_assistant:

            # Configure file processing mock
            test_file = File(
                filepath="/path/to/data.csv", file_type="data", data_context="csv"
            )
            mock_process_files.return_value = (
                [test_file],
                [],
                ["Processing instructions"],
            )

            # Configure database mock
            mock_db = AsyncMock()
            mock_db.create_planner.return_value = "planner_123"
            mock_db.enqueue_task.return_value = True

            # Configure message manager mock
            mock_message_manager = AsyncMock()
            mock_message_manager.get_messages.return_value = []

            # Create WebSocket mock
            mock_websocket = AsyncMock()

            # Configure router state
            router_state = {
                "id": self.router_id,
                "agent_db": mock_db,
                "model": settings.router_model,
                "temperature": 0.0,
                "message_manager": mock_message_manager,
            }

            # Test invoke_single
            await router_operations.invoke_single(
                router_state=router_state,
                files=["/path/to/data.csv"],
                user_question="Analyse this data",
                instructions=["Analyse this data"],
                websocket=mock_websocket,
            )

            # Verify task was queued (planner is not directly created, just queued)
            mock_db.enqueue_task.assert_called_once()
            call_args = mock_db.enqueue_task.call_args
            # Verify it's queuing a planner task
            self.assertEqual(call_args.kwargs["entity_type"], "planner")
            self.assertEqual(
                call_args.kwargs["function_name"], "execute_initial_planning"
            )

    async def test_generate_and_update_title_success(self):
        """Test generate_and_update_title updates router title."""
        with patch(
            "src.agent.core.router_operations.MessageManager"
        ) as MockMessageManager:

            # Configure MessageManager mock
            mock_message_manager = AsyncMock()
            mock_message_manager.get_messages.return_value = [
                {"role": "user", "content": "Help me with Python programming"}
            ]

            # Configure LLM mock
            mock_llm = AsyncMock()
            mock_response = MagicMock()
            mock_response.content = "Python Programming Help"
            mock_llm.a_get_response.return_value = mock_response

            # Configure database mock
            mock_db = AsyncMock()

            # Configure router state
            router_state = {
                "id": self.router_id,
                "agent_db": mock_db,
                "llm": mock_llm,
                "model": settings.router_model,
                "temperature": 0.0,
                "message_manager": mock_message_manager,
            }

            # Test title generation
            await router_operations.generate_and_update_title(router_state=router_state)

            # Verify database was updated with new title
            mock_db.update_router.assert_called_once_with(
                router_id=self.router_id, title="Python Programming Help"
            )

    async def test_handle_complex_request_with_files(self):
        """Test handle_complex_request with file processing."""
        with patch(
            "src.agent.core.router_operations.determine_file_groups"
        ) as mock_determine_groups, patch(
            "src.agent.core.router_operations.invoke_single"
        ) as mock_invoke, patch(
            "src.agent.core.router_operations.send_status"
        ) as mock_send_status:

            # No need to mock process_files as it's called inside invoke_single

            # Configure file grouping mock
            mock_determine_groups.return_value = [["/path/to/data.csv"]]

            # Configure database mock
            mock_db = AsyncMock()

            # Configure router state
            # Configure message manager mock
            mock_message_manager = AsyncMock()

            router_state = {
                "id": self.router_id,
                "agent_db": mock_db,
                "llm": MagicMock(),
                "model": settings.router_model,
                "temperature": 0.0,
                "message_manager": mock_message_manager,
            }

            # Configure requirements
            requirements = RequireAgent(
                calculation_required=True,
                web_search_required=False,
                complex_question=True,
                chilli_request=False,
                context_rich_agent_request="Analyse CSV data",
            )

            # Create WebSocket mock
            mock_websocket = AsyncMock()

            # Test complex request handling
            await router_operations.handle_complex_request(
                router_state=router_state,
                files=["/path/to/data.csv"],
                agent_requirements=requirements,
                websocket=mock_websocket,
            )

            # Verify invoke_single was called (which internally calls process_files)
            mock_invoke.assert_called_once()

            # Verify file grouping was called with fully qualified parameters
            mock_determine_groups.assert_called_once_with(
                router_state=router_state,
                user_question=requirements.context_rich_agent_request,
                files=["/path/to/data.csv"],
            )

            # Verify worker was invoked with fully qualified parameters
            mock_invoke.assert_called_once_with(
                router_state=router_state,
                files=["/path/to/data.csv"],
                user_question="Analyse CSV data",
                instructions=[],  # empty list as no special instructions
                websocket=mock_websocket,
                agent_requirements=requirements,
            )
