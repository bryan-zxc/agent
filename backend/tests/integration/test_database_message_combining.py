"""
Integration tests for message combining functionality in AgentDatabase.

These tests verify that consecutive same-role messages are properly combined
in the database to maintain alternating user/assistant message patterns.
"""

import unittest
import asyncio
import tempfile
import uuid
import os
from pathlib import Path

from src.agent.models.agent_database import AgentDatabase


class TestDatabaseMessageCombining(unittest.IsolatedAsyncioTestCase):
    """Integration tests for message combining in AgentDatabase."""

    async def asyncSetUp(self):
        """Set up test environment with temporary database."""
        # Create temporary database file
        self.temp_db_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db_file.close()
        self.db = await AgentDatabase.create(self.temp_db_file.name)
        
        # Generate unique test identifiers
        self.planner_id = f"planner_{uuid.uuid4().hex[:8]}"
        self.worker_id = f"worker_{uuid.uuid4().hex[:8]}"
        self.router_id = f"router_{uuid.uuid4().hex[:8]}"

    async def asyncTearDown(self):
        """Clean up test resources."""
        try:
            await self.db.close()
        except:
            pass
        
        try:
            os.unlink(self.temp_db_file.name)
        except:
            pass

    async def test_combine_consecutive_same_role_messages_planner(self):
        """Test that consecutive same-role messages are combined for planner."""
        # Add first user message
        msg1_id = await self.db.add_message("planner", self.planner_id, "user", "First message")
        self.assertIsNotNone(msg1_id)
        
        # Add second user message - should combine with first
        msg2_id = await self.db.add_message("planner", self.planner_id, "user", "Second message")
        self.assertEqual(msg2_id, msg1_id, "Should return same message ID when combining")
        
        # Verify messages are combined
        messages = await self.db.get_messages("planner", self.planner_id)
        self.assertEqual(len(messages), 1, "Should have only one message after combining")
        self.assertEqual(messages[0]["role"], "user")
        
        # Content should be a list with both parts
        content = messages[0]["content"]
        self.assertIsInstance(content, list)
        self.assertEqual(len(content), 2)
        self.assertEqual(content[0]["text"], "First message")
        self.assertEqual(content[1]["text"], "Second message")

    async def test_alternating_roles_create_separate_messages(self):
        """Test that alternating roles create separate messages."""
        # Add user message
        user_msg_id = await self.db.add_message("planner", self.planner_id, "user", "User message")
        
        # Add assistant message - should create new message
        assistant_msg_id = await self.db.add_message("planner", self.planner_id, "assistant", "Assistant response")
        self.assertNotEqual(assistant_msg_id, user_msg_id, "Different roles should create new messages")
        
        # Add another user message - should create third message
        user2_msg_id = await self.db.add_message("planner", self.planner_id, "user", "Another user message")
        self.assertNotEqual(user2_msg_id, assistant_msg_id)
        self.assertNotEqual(user2_msg_id, user_msg_id)
        
        # Verify we have 3 separate messages
        messages = await self.db.get_messages("planner", self.planner_id)
        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[1]["role"], "assistant")
        self.assertEqual(messages[2]["role"], "user")

    async def test_combine_worker_messages(self):
        """Test message combining for worker agent type."""
        # Add multiple assistant messages
        msg1_id = await self.db.add_message("worker", self.worker_id, "assistant", "First output")
        msg2_id = await self.db.add_message("worker", self.worker_id, "assistant", "Second output")
        msg3_id = await self.db.add_message("worker", self.worker_id, "assistant", "Third output")
        
        # All should combine into the same message
        self.assertEqual(msg2_id, msg1_id)
        self.assertEqual(msg3_id, msg1_id)
        
        # Verify combined content
        messages = await self.db.get_messages("worker", self.worker_id)
        self.assertEqual(len(messages), 1)
        self.assertEqual(len(messages[0]["content"]), 3)

    async def test_combine_router_messages(self):
        """Test message combining for router agent type."""
        # Create a router first (required due to foreign key constraint)
        await self.db.create_router(self.router_id, status="active")
        
        # Add multiple user messages
        msg1_id = await self.db.add_message("router", self.router_id, "user", "First input")
        msg2_id = await self.db.add_message("router", self.router_id, "user", "Second input")
        
        # Should combine
        self.assertEqual(msg2_id, msg1_id)
        
        # Add assistant message
        assistant_msg_id = await self.db.add_message("router", self.router_id, "assistant", "Response")
        self.assertNotEqual(assistant_msg_id, msg1_id)
        
        # Verify structure
        messages = await self.db.get_messages("router", self.router_id)
        self.assertEqual(len(messages), 2)
        self.assertEqual(len(messages[0]["content"]), 2)  # Combined user messages

    async def test_mixed_content_types(self):
        """Test combining messages with different content types."""
        # Add string content
        msg_id = await self.db.add_message("planner", self.planner_id, "user", "String content")
        
        # Add list content to same role
        list_content = [
            {"type": "text", "text": "List item 1"},
            {"type": "text", "text": "List item 2"}
        ]
        msg_id2 = await self.db.add_message("planner", self.planner_id, "user", list_content)
        self.assertEqual(msg_id2, msg_id, "Should combine different content types")
        
        # Add dict content to same role
        dict_content = {"type": "text", "text": "Dict content"}
        msg_id3 = await self.db.add_message("planner", self.planner_id, "user", dict_content)
        self.assertEqual(msg_id3, msg_id, "Should combine dict content")
        
        # Verify all content is combined
        messages = await self.db.get_messages("planner", self.planner_id)
        self.assertEqual(len(messages), 1)
        
        content = messages[0]["content"]
        self.assertIsInstance(content, list)
        self.assertEqual(len(content), 4)  # 1 string + 2 list items + 1 dict
        self.assertEqual(content[0]["text"], "String content")
        self.assertEqual(content[1]["text"], "List item 1")
        self.assertEqual(content[2]["text"], "List item 2")
        self.assertEqual(content[3]["text"], "Dict content")

    async def test_empty_content_handling(self):
        """Test handling of empty content."""
        # Add empty string content
        msg1_id = await self.db.add_message("planner", self.planner_id, "user", "")
        self.assertIsNotNone(msg1_id)
        
        # Add empty list content - should combine
        msg2_id = await self.db.add_message("planner", self.planner_id, "user", [])
        self.assertEqual(msg2_id, msg1_id)
        
        # Verify messages
        messages = await self.db.get_messages("planner", self.planner_id)
        self.assertEqual(len(messages), 1)
        self.assertIsInstance(messages[0]["content"], list)

    async def test_multiple_consecutive_combines(self):
        """Test multiple consecutive messages of same role combine correctly."""
        # Add 5 consecutive user messages
        msg_ids = []
        for i in range(5):
            msg_id = await self.db.add_message(
                "planner", self.planner_id, "user", f"Message {i+1}"
            )
            msg_ids.append(msg_id)
        
        # All should have same ID
        for msg_id in msg_ids[1:]:
            self.assertEqual(msg_id, msg_ids[0], "All same-role messages should combine")
        
        # Verify we have only 1 message with 5 parts
        messages = await self.db.get_messages("planner", self.planner_id)
        self.assertEqual(len(messages), 1)
        self.assertEqual(len(messages[0]["content"]), 5)
        
        # Verify content order is preserved
        for i in range(5):
            self.assertEqual(messages[0]["content"][i]["text"], f"Message {i+1}")

    async def test_system_role_messages(self):
        """Test that system role messages also combine correctly."""
        # Add multiple system messages
        msg1_id = await self.db.add_message("planner", self.planner_id, "system", "System prompt 1")
        msg2_id = await self.db.add_message("planner", self.planner_id, "system", "System prompt 2")
        
        # Should combine
        self.assertEqual(msg2_id, msg1_id)
        
        # Add user message
        user_msg_id = await self.db.add_message("planner", self.planner_id, "user", "User input")
        self.assertNotEqual(user_msg_id, msg1_id)
        
        # Verify structure
        messages = await self.db.get_messages("planner", self.planner_id)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1]["role"], "user")

    async def test_display_text_generation(self):
        """Test that display text is correctly generated from combined messages."""
        # Add messages that will be combined
        msg_id = await self.db.add_message("planner", self.planner_id, "user", "Part 1")
        await self.db.add_message("planner", self.planner_id, "user", [
            {"type": "text", "text": "Part 2"},
            {"type": "image", "url": "image.png"},  # Non-text content
            {"type": "text", "text": "Part 3"}
        ])
        
        # Get display text using the message ID
        display_text = await self.db.get_message_display_text("planner", msg_id)
        
        # Should concatenate only text parts
        self.assertIn("Part 1", display_text)
        self.assertIn("Part 2", display_text)
        self.assertIn("Part 3", display_text)
        # Image URL should not be in display text
        self.assertNotIn("image.png", display_text)


if __name__ == "__main__":
    unittest.main()