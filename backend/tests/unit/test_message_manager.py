"""
MessageManager Test Suite

Tests for the MessageManager class that provides in-memory message caching
with database synchronisation for efficient message handling.
"""

import unittest
import asyncio
import tempfile
import uuid
import os
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from src.agent.tasks.message_manager import MessageManager
from src.agent.models.agent_database import AgentDatabase


class TestMessageManager(unittest.IsolatedAsyncioTestCase):
    """Test MessageManager functionality."""

    async def asyncSetUp(self):
        """Set up test environment with temporary database."""
        # Set up temporary database
        self.db_fd, self.test_db_path = tempfile.mkstemp(suffix='.db')
        os.close(self.db_fd)
        self.db = AgentDatabase(database_path=self.test_db_path)
        
        # Test data
        self.agent_id = f"test_agent_{uuid.uuid4().hex[:8]}"
        self.agent_type = "planner"

    async def asyncTearDown(self):
        """Clean up test database."""
        try:
            os.unlink(self.test_db_path)
        except (OSError, FileNotFoundError):
            pass

    async def test_message_manager_initialisation(self):
        """Test MessageManager initialisation with correct parameters."""
        message_manager = MessageManager(self.db, self.agent_type, self.agent_id)
        
        # Verify initial state
        self.assertEqual(message_manager.db, self.db)
        self.assertEqual(message_manager.agent_type, self.agent_type)
        self.assertEqual(message_manager.agent_id, self.agent_id)
        self.assertEqual(message_manager.message_count(), 0)
        self.assertFalse(message_manager._synced)

    async def test_add_message_returns_updated_list(self):
        """Test add_message returns the updated complete message list."""
        with patch.object(self.db, 'add_message', new_callable=AsyncMock) as mock_add, \
             patch.object(self.db, 'get_messages', new_callable=AsyncMock) as mock_get:
            
            # Mock database responses
            mock_add.return_value = "msg_123"  # Message ID
            mock_get.return_value = [
                {"role": "system", "content": "System message"},
                {"role": "user", "content": "User message"}
            ]
            
            message_manager = MessageManager(self.db, self.agent_type, self.agent_id)
            
            # Add a message
            messages = await message_manager.add_message("user", "Test message")
            
            # Verify message was added to database
            mock_add.assert_awaited_once_with(
                self.agent_type, self.agent_id, "user", "Test message"
            )
            
            # Verify updated message list is returned (2 existing + 1 new = 3)
            self.assertEqual(len(messages), 3)
            self.assertEqual(messages[2]["role"], "user")
            self.assertEqual(messages[2]["content"], "Test message")
            
            # Verify message count updated
            self.assertEqual(message_manager.message_count(), 3)

    async def test_get_messages_syncs_on_first_call(self):
        """Test get_messages syncs from database on first call."""
        with patch.object(self.db, 'get_messages', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = [
                {"role": "system", "content": "System message"},
                {"role": "user", "content": "User message"}
            ]
            
            message_manager = MessageManager(self.db, self.agent_type, self.agent_id)
            
            # First call should sync from database
            messages = await message_manager.get_messages()
            
            # Verify database was queried
            mock_get.assert_awaited_once_with(self.agent_type, self.agent_id)
            
            # Verify messages returned
            self.assertEqual(len(messages), 2)
            self.assertEqual(messages[0]["role"], "system")
            self.assertEqual(messages[1]["role"], "user")
            
            # Verify synced flag set
            self.assertTrue(message_manager._synced)
            
            # Second call should not query database again
            mock_get.reset_mock()
            messages2 = await message_manager.get_messages()
            mock_get.assert_not_awaited()
            self.assertEqual(messages, messages2)

    async def test_clear_messages_removes_all(self):
        """Test clear_messages removes all messages from database and memory."""
        with patch.object(self.db, 'clear_messages', new_callable=AsyncMock) as mock_clear:
            message_manager = MessageManager(self.db, self.agent_type, self.agent_id)
            
            # Add some test messages to internal list
            message_manager._messages = [
                {"role": "user", "content": "Test 1"},
                {"role": "assistant", "content": "Test 2"}
            ]
            message_manager._synced = True
            
            # Clear messages
            await message_manager.clear_messages()
            
            # Verify database clear was called
            mock_clear.assert_awaited_once_with(self.agent_type, self.agent_id)
            
            # Verify internal messages cleared
            self.assertEqual(len(message_manager._messages), 0)
            self.assertEqual(message_manager.message_count(), 0)
            self.assertTrue(message_manager._synced)

    async def test_refresh_from_db_forces_sync(self):
        """Test refresh_from_db forces a fresh sync from database."""
        with patch.object(self.db, 'get_messages', new_callable=AsyncMock) as mock_get:
            # Mock different database states
            mock_get.side_effect = [
                [{"role": "user", "content": "Message 1"}],
                [{"role": "user", "content": "Message 1"}, {"role": "assistant", "content": "Message 2"}]
            ]
            
            message_manager = MessageManager(self.db, self.agent_type, self.agent_id)
            
            # First sync
            messages1 = await message_manager.refresh_from_db()
            self.assertEqual(len(messages1), 1)
            
            # Force refresh should get updated messages
            messages2 = await message_manager.refresh_from_db()
            self.assertEqual(len(messages2), 2)
            
            # Verify database queried twice
            self.assertEqual(mock_get.await_count, 2)

    async def test_concurrent_message_operations(self):
        """Test concurrent message operations work correctly."""
        with patch.object(self.db, 'add_message', new_callable=AsyncMock) as mock_add, \
             patch.object(self.db, 'get_messages', new_callable=AsyncMock) as mock_get:
            
            # Mock database responses
            mock_add.return_value = "msg_id"
            mock_get.return_value = []  # Start with empty
            
            message_manager = MessageManager(self.db, self.agent_type, self.agent_id)
            
            # Add multiple messages concurrently
            async def add_message(i):
                return await message_manager.add_message("user", f"Message {i}")
            
            # Run concurrent operations
            results = await asyncio.gather(
                *[add_message(i) for i in range(3)]
            )
            
            # All operations should succeed
            self.assertEqual(len(results), 3)
            
            # Verify database operations were called
            self.assertEqual(mock_add.await_count, 3)

    async def test_message_manager_string_representation(self):
        """Test MessageManager string representation."""
        message_manager = MessageManager(self.db, self.agent_type, self.agent_id)
        message_manager._messages = [{"role": "user", "content": "test"}]
        
        repr_str = repr(message_manager)
        self.assertIn(self.agent_type, repr_str)
        self.assertIn(self.agent_id, repr_str)
        self.assertIn("1 messages", repr_str)

    async def test_message_manager_length_operator(self):
        """Test MessageManager len() operator."""
        message_manager = MessageManager(self.db, self.agent_type, self.agent_id)
        
        # Initially empty
        self.assertEqual(len(message_manager), 0)
        
        # Add messages to internal list
        message_manager._messages = [
            {"role": "user", "content": "test1"},
            {"role": "assistant", "content": "test2"}
        ]
        
        # Check length
        self.assertEqual(len(message_manager), 2)

    async def test_error_handling_in_sync(self):
        """Test error handling when database sync fails."""
        with patch.object(self.db, 'get_messages', new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = Exception("Database error")
            
            message_manager = MessageManager(self.db, self.agent_type, self.agent_id)
            
            # Should handle error gracefully
            messages = await message_manager.get_messages()
            
            # Should return empty list on error
            self.assertEqual(messages, [])
            self.assertFalse(message_manager._synced)

    async def test_add_message_with_failed_database_write(self):
        """Test add_message handles database write failures."""
        with patch.object(self.db, 'add_message', new_callable=AsyncMock) as mock_add, \
             patch.object(self.db, 'get_messages', new_callable=AsyncMock) as mock_get:
            
            # Mock database write failure
            mock_add.return_value = None  # Indicates failure
            mock_get.return_value = []
            
            message_manager = MessageManager(self.db, self.agent_type, self.agent_id)
            
            # Add message should handle failure gracefully
            messages = await message_manager.add_message("user", "Test message")
            
            # Should still return message list (empty in this case)
            self.assertEqual(messages, [])
            
            # Internal state should remain consistent
            self.assertEqual(message_manager.message_count(), 0)

    async def test_different_agent_types(self):
        """Test MessageManager works with different agent types."""
        agent_types = ["planner", "worker", "router"]
        
        for agent_type in agent_types:
            with self.subTest(agent_type=agent_type):
                message_manager = MessageManager(self.db, agent_type, self.agent_id)
                
                # Verify agent type stored correctly
                self.assertEqual(message_manager.agent_type, agent_type)
                
                # Test basic functionality
                self.assertEqual(message_manager.message_count(), 0)
                repr_str = repr(message_manager)
                self.assertIn(agent_type, repr_str)

    async def test_message_immutability(self):
        """Test that get_messages returns a copy to prevent external modification."""
        with patch.object(self.db, 'get_messages', new_callable=AsyncMock) as mock_get:
            mock_get.return_value = [{"role": "user", "content": "original"}]
            
            message_manager = MessageManager(self.db, self.agent_type, self.agent_id)
            
            # Get messages
            messages = await message_manager.get_messages()
            
            # Modify returned list
            messages.append({"role": "assistant", "content": "external"})
            
            # Internal state should be unchanged
            internal_messages = await message_manager.get_messages()
            self.assertEqual(len(internal_messages), 1)
            self.assertEqual(internal_messages[0]["content"], "original")