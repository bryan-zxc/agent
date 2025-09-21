"""
Lightweight Database Operations Tests

Unit tests for core database functionality following lightweight testing principles.
Tests focus on basic CRUD operations that actually work, avoiding complex integrations.
"""

import unittest
import asyncio
import uuid
import os

from src.agent.models.agent_database import AgentDatabase
from src.agent.database.connection import DatabaseConfig


class TestDatabaseOperationsSimple(unittest.IsolatedAsyncioTestCase):
    """Lightweight tests for core database operations."""

    async def asyncSetUp(self):
        """Set up test database for each test."""
        # Use PostgreSQL test database
        config = DatabaseConfig()
        test_db_url = config.get_database_url(database_name="test")
        self.db = await AgentDatabase.create(database_url=test_db_url)

        # Test data
        self.router_id = f"test_router_{uuid.uuid4().hex[:8]}"
        self.planner_id = f"test_planner_{uuid.uuid4().hex[:8]}"
        self.worker_id = f"test_worker_{uuid.uuid4().hex[:8]}"

    async def asyncTearDown(self):
        """Clean up test resources."""
        # PostgreSQL test database is reused, no cleanup needed
        pass

    async def test_database_connection_establishment(self):
        """Test async database connection works correctly."""
        # Test basic connection by creating a router
        result = await self.db.create_router(
            router_id=self.router_id,
            status="active",
            model="gpt-4",
            temperature=0.7,
            title="Test Router",
            preview="Test router preview",
        )

        # Should not raise exceptions
        self.assertIsNone(result)  # create_router returns None on success

    async def test_message_operations(self):
        """Test message storage and retrieval operations."""
        # Add a message
        message_id = await self.db.add_message(
            "planner", self.planner_id, "user", "Test message"
        )

        # Message should be created
        self.assertIsNotNone(message_id)

        # Retrieve messages
        messages = await self.db.get_messages("planner", self.planner_id)

        # Should have our message
        self.assertEqual(len(messages), 1)
        # Content is returned as a list of dictionaries in Anthropic format
        self.assertEqual(messages[0]["content"], [{"type": "text", "text": "Test message"}])

    async def test_planner_operations(self):
        """Test planner Create, Read, Update operations."""
        # Create planner
        create_result = await self.db.create_planner(
            planner_id=self.planner_id,
            user_question="Test question",
            status="active",
            model="gpt-4",
            temperature=0.7,
        )
        self.assertIsNone(create_result)  # create_planner returns None on success

        # Read planner
        planner_data = await self.db.get_planner(self.planner_id)
        self.assertEqual(planner_data["planner_id"], self.planner_id)

        # Update planner
        update_result = await self.db.update_planner(
            self.planner_id, status="completed"
        )
        self.assertTrue(update_result)  # update_planner returns True on success

    async def test_worker_operations(self):
        """Test worker Create, Read, Update operations."""
        # First create the planner that the worker references
        await self.db.create_planner(
            planner_id=self.planner_id,
            user_question="Test question for worker",
            status="active",
            model="gpt-4",
            temperature=0.7,
        )

        # Create worker
        create_result = await self.db.create_worker(
            worker_id=self.worker_id,
            planner_id=self.planner_id,
            worker_name="Test Worker",
            task_status="active",
            task_description="Test task description",
            acceptance_criteria=["Test criteria"],
            user_request="Test request",
            wip_answer_template="Test template",
            task_result="",
            querying_structured_data=False,
            image_keys=[],
            variable_keys=[],
            tools=[],
            input_variable_filepaths={},
            input_image_filepaths={},
            tables=[],
            filepaths=[],
        )
        self.assertIsNone(create_result)  # create_worker returns None on success

        # Read worker
        worker_data = await self.db.get_worker(self.worker_id)
        self.assertEqual(worker_data["worker_id"], self.worker_id)

        # Update worker
        update_result = await self.db.update_worker(self.worker_id, status="completed")
        self.assertTrue(update_result)  # update_worker returns True on success
