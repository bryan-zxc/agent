"""
Test suite for multiple conversations executing concurrently.

This test suite validates that multiple router conversations can execute 
simultaneously without interfering with each other, including message isolation,
router state management, and cross-conversation independence.
"""

import unittest
import tempfile
import uuid
import shutil
import asyncio
import threading
import time
from pathlib import Path
from unittest.mock import patch, MagicMock
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import the modules under test
from agent.models.agent_database import AgentDatabase
from agent.core.router import RouterAgent
from agent.tasks.task_utils import get_router_id_for_planner, is_router_busy
from agent.config.settings import settings


class TestMultipleConversationsConcurrent(unittest.TestCase):
    """Test concurrent execution of multiple router conversations."""
    
    def setUp(self):
        """Set up test environment before each test."""
        # Create temporary directory for testing
        self.test_dir = tempfile.mkdtemp()
        self.original_base_path = settings.collaterals_base_path
        
        # Mock settings to use test directory
        settings.collaterals_base_path = self.test_dir
        
        # Set up in-memory database for testing
        self.db = AgentDatabase()
        self.db.engine = self.db.create_engine("sqlite:///:memory:")
        self.db.Base.metadata.create_all(self.db.engine)
        self.db.SessionLocal = self.db.sessionmaker(bind=self.db.engine)
        
        # Test data
        self.test_routers = []
        self.test_conversations = [
            {
                "title": "Data Analysis Conversation",
                "messages": [
                    {"role": "user", "content": "Analyse the sales data from Q1"},
                    {"role": "assistant", "content": "I'll help you analyse the Q1 sales data. Let me start by examining the dataset."},
                    {"role": "user", "content": "Focus on regional performance differences"}
                ]
            },
            {
                "title": "Image Processing Conversation", 
                "messages": [
                    {"role": "user", "content": "Process these product images for the catalogue"},
                    {"role": "assistant", "content": "I'll process the product images for your catalogue. Starting with image enhancement."},
                    {"role": "user", "content": "Make sure to maintain aspect ratios"}
                ]
            },
            {
                "title": "Research Query Conversation",
                "messages": [
                    {"role": "user", "content": "Research the latest market trends in renewable energy"},
                    {"role": "assistant", "content": "I'll research the current renewable energy market trends for you."},
                    {"role": "user", "content": "Include solar and wind energy specifically"}
                ]
            }
        ]
        
    def tearDown(self):
        """Clean up after each test."""
        # Restore original settings
        settings.collaterals_base_path = self.original_base_path
        
        # Remove test directory
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def create_test_router(self, conversation_data: dict) -> str:
        """Create a test router with conversation data."""
        router_id = f"router_{uuid.uuid4().hex[:8]}"
        
        # Create router in database
        self.db.create_router(
            router_id=router_id,
            status="active",
            model="gpt-4",
            temperature=0.0,
            title=conversation_data["title"],
            preview=conversation_data["messages"][0]["content"][:100] if conversation_data["messages"] else ""
        )
        
        # Add messages to router
        for msg in conversation_data["messages"]:
            self.db.add_message(
                agent_id=router_id,
                agent_type="router",
                role=msg["role"],
                content=msg["content"]
            )
        
        self.test_routers.append(router_id)
        return router_id

    def test_concurrent_conversation_creation(self):
        """Test that multiple conversations can be created concurrently."""
        def create_conversation(conversation_data, index):
            """Create a conversation with unique router."""
            conversation_data = {**conversation_data, "title": f"{conversation_data['title']} #{index}"}
            router_id = self.create_test_router(conversation_data)
            
            # Verify router was created correctly
            router_data = self.db.get_router(router_id)
            self.assertIsNotNone(router_data)
            self.assertEqual(router_data["title"], conversation_data["title"])
            self.assertEqual(router_data["status"], "active")
            
            # Verify messages were added
            messages = self.db.get_messages_by_agent_id(router_id, "router")
            self.assertEqual(len(messages), len(conversation_data["messages"]))
            
            return router_id
        
        # Create multiple conversations concurrently
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(create_conversation, conv_data, i)
                for i, conv_data in enumerate(self.test_conversations)
            ]
            
            created_routers = []
            for future in as_completed(futures):
                created_routers.append(future.result())
        
        # Verify all conversations were created successfully
        self.assertEqual(len(created_routers), 3)
        self.assertEqual(len(set(created_routers)), 3)  # All unique
        
        # Verify each conversation maintains separate state
        for router_id in created_routers:
            router_data = self.db.get_router(router_id)
            self.assertIsNotNone(router_data)
            self.assertEqual(router_data["status"], "active")
            
            messages = self.db.get_messages_by_agent_id(router_id, "router")
            self.assertGreaterEqual(len(messages), 3)  # At least 3 messages per conversation

    def test_concurrent_message_addition(self):
        """Test concurrent message addition to different conversations."""
        # Create test routers
        router_ids = [self.create_test_router(conv) for conv in self.test_conversations]
        
        def add_messages_to_conversation(router_id, message_batch):
            """Add a batch of messages to a specific conversation."""
            added_messages = []
            
            for i, message_content in enumerate(message_batch):
                # Alternate between user and assistant messages
                role = "user" if i % 2 == 0 else "assistant"
                
                self.db.add_message(
                    agent_id=router_id,
                    agent_type="router",
                    role=role,
                    content=f"{message_content} (router: {router_id[-8:]})"
                )
                
                added_messages.append({
                    "role": role,
                    "content": f"{message_content} (router: {router_id[-8:]})"
                })
                
                # Small delay to simulate realistic message timing
                time.sleep(0.01)
            
            return added_messages
        
        # Prepare message batches for each conversation
        message_batches = [
            ["What's the revenue trend?", "Revenue increased by 15%", "Show me the quarterly breakdown"],
            ["Enhance image contrast", "Contrast enhanced successfully", "Apply sharpening filter"],
            ["Latest solar panel efficiency?", "Efficiency reached 22% average", "Compare with wind power"]
        ]
        
        # Add messages concurrently to different conversations
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(add_messages_to_conversation, router_id, batch)
                for router_id, batch in zip(router_ids, message_batches)
            ]
            
            all_added_messages = []
            for future in as_completed(futures):
                all_added_messages.append(future.result())
        
        # Verify messages were added correctly to each conversation
        for i, router_id in enumerate(router_ids):
            messages = self.db.get_messages_by_agent_id(router_id, "router")
            
            # Should have original messages + newly added messages
            expected_count = len(self.test_conversations[i]["messages"]) + len(message_batches[i])
            self.assertEqual(len(messages), expected_count)
            
            # Verify message content contains router-specific identifier
            router_suffix = router_id[-8:]
            recent_messages = messages[-len(message_batches[i]):]
            
            for msg in recent_messages:
                self.assertIn(router_suffix, msg["content"])

    def test_concurrent_planner_creation_across_conversations(self):
        """Test that planners can be created concurrently in different conversations."""
        # Create test routers
        router_ids = [self.create_test_router(conv) for conv in self.test_conversations]
        
        def create_planner_for_router(router_id, task_description):
            """Create a planner for a specific router/conversation."""
            planner_id = f"planner_{router_id}_{uuid.uuid4().hex[:8]}"
            
            # Create planner
            self.db.create_planner(
                planner_id=planner_id,
                planner_name=f"Planner for {router_id[-8:]}",
                user_question=task_description,
                instruction=f"Handle task: {task_description}",
                status="planning"
            )
            
            # Link planner to router
            self.db.link_router_planner(router_id, planner_id, "initiated")
            
            # Verify linkage
            planners = self.db.get_planners_by_router(router_id)
            self.assertEqual(len(planners), 1)
            self.assertEqual(planners[0]["planner_id"], planner_id)
            
            return planner_id
        
        # Task descriptions for each conversation
        task_descriptions = [
            "Analyse Q1 sales data and generate comprehensive report",
            "Process and enhance product images for online catalogue",
            "Research renewable energy market trends and opportunities"
        ]
        
        # Create planners concurrently across different conversations
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(create_planner_for_router, router_id, description)
                for router_id, description in zip(router_ids, task_descriptions)
            ]
            
            created_planners = []
            for future in as_completed(futures):
                created_planners.append(future.result())
        
        # Verify all planners were created successfully
        self.assertEqual(len(created_planners), 3)
        self.assertEqual(len(set(created_planners)), 3)  # All unique
        
        # Verify each router has exactly one planner
        for router_id in router_ids:
            planners = self.db.get_planners_by_router(router_id)
            self.assertEqual(len(planners), 1)
            
            planner = planners[0]
            self.assertEqual(planner["status"], "planning")
            self.assertIn("Q1 sales" if "sales" in planner["user_question"] 
                         else "images" if "images" in planner["user_question"]
                         else "renewable", planner["user_question"])

    def test_concurrent_conversation_file_operations(self):
        """Test file operations across different conversations remain isolated."""
        # Create test routers
        router_ids = [self.create_test_router(conv) for conv in self.test_conversations]
        
        def perform_file_operations(router_id, file_prefix):
            """Perform file operations for a specific conversation."""
            conversation_dir = Path(self.test_dir) / f"conversation_{router_id}"
            conversation_dir.mkdir(exist_ok=True)
            
            # Create conversation-specific files
            files_created = []
            for i in range(3):
                file_path = conversation_dir / f"{file_prefix}_{i}.txt"
                file_content = f"Content for {file_prefix}_{i} in conversation {router_id[-8:]}"
                file_path.write_text(file_content)
                files_created.append(str(file_path))
            
            # Create a subdirectory with nested files
            sub_dir = conversation_dir / "processed"
            sub_dir.mkdir(exist_ok=True)
            
            for i in range(2):
                sub_file = sub_dir / f"processed_{file_prefix}_{i}.json"
                sub_content = f'{{"data": "processed {file_prefix} {i}", "conversation": "{router_id[-8:]}"}}'
                sub_file.write_text(sub_content)
                files_created.append(str(sub_file))
            
            return files_created
        
        # File prefixes for each conversation type
        file_prefixes = ["sales_data", "product_image", "research_doc"]
        
        # Perform file operations concurrently across conversations
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(perform_file_operations, router_id, prefix)
                for router_id, prefix in zip(router_ids, file_prefixes)
            ]
            
            all_created_files = []
            for future in as_completed(futures):
                all_created_files.extend(future.result())
        
        # Verify file isolation between conversations
        self.assertEqual(len(all_created_files), 15)  # 3 conversations × 5 files each
        
        # Check that each conversation has its own directory
        conversation_dirs = list(Path(self.test_dir).glob("conversation_*"))
        self.assertEqual(len(conversation_dirs), 3)
        
        # Verify file content is conversation-specific
        for router_id, prefix in zip(router_ids, file_prefixes):
            conversation_dir = Path(self.test_dir) / f"conversation_{router_id}"
            self.assertTrue(conversation_dir.exists())
            
            # Check main files
            main_files = list(conversation_dir.glob(f"{prefix}_*.txt"))
            self.assertEqual(len(main_files), 3)
            
            for file_path in main_files:
                content = file_path.read_text()
                self.assertIn(router_id[-8:], content)
                self.assertIn(prefix, content)
            
            # Check processed files
            processed_dir = conversation_dir / "processed"
            self.assertTrue(processed_dir.exists())
            
            processed_files = list(processed_dir.glob(f"processed_{prefix}_*.json"))
            self.assertEqual(len(processed_files), 2)
            
            for file_path in processed_files:
                content = file_path.read_text()
                self.assertIn(router_id[-8:], content)
                self.assertIn(prefix, content)

    def test_concurrent_conversation_state_updates(self):
        """Test that conversation state updates remain isolated."""
        # Create test routers
        router_ids = [self.create_test_router(conv) for conv in self.test_conversations]
        
        def update_conversation_state(router_id, status_sequence):
            """Update conversation state through a sequence of status changes."""
            state_changes = []
            
            for i, status in enumerate(status_sequence):
                # Update router status
                self.db.update_router_status(router_id, status)
                
                # Update title to reflect status
                new_title = f"Conversation {router_id[-8:]} - {status.title()} (Step {i+1})"
                self.db.update_router_title(router_id, new_title)
                
                # Verify state change
                router_data = self.db.get_router(router_id)
                self.assertEqual(router_data["status"], status)
                self.assertEqual(router_data["title"], new_title)
                
                state_changes.append({
                    "step": i + 1,
                    "status": status,
                    "title": new_title,
                    "timestamp": time.time()
                })
                
                # Small delay to simulate processing time
                time.sleep(0.02)
            
            return state_changes
        
        # Different status sequences for each conversation
        status_sequences = [
            ["active", "processing", "completed"],
            ["active", "processing", "paused", "active", "completed"],
            ["active", "error", "active", "completed"]
        ]
        
        # Update conversation states concurrently
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(update_conversation_state, router_id, sequence)
                for router_id, sequence in zip(router_ids, status_sequences)
            ]
            
            all_state_changes = []
            for future in as_completed(futures):
                all_state_changes.append(future.result())
        
        # Verify final states are correct and isolated
        for i, router_id in enumerate(router_ids):
            router_data = self.db.get_router(router_id)
            
            # Should be in final status
            expected_final_status = status_sequences[i][-1]
            self.assertEqual(router_data["status"], expected_final_status)
            
            # Title should reflect final state
            self.assertIn(router_id[-8:], router_data["title"])
            self.assertIn(expected_final_status.title(), router_data["title"])
            
            # Verify state change history length
            expected_changes = len(status_sequences[i])
            self.assertEqual(len(all_state_changes[i]), expected_changes)

    def test_conversation_isolation_under_load(self):
        """Test conversation isolation under high concurrent load."""
        # Create multiple conversations
        num_conversations = 5
        router_ids = []
        
        for i in range(num_conversations):
            conv_data = {
                "title": f"Load Test Conversation {i}",
                "messages": [
                    {"role": "user", "content": f"Task {i}: Process data batch {i}"},
                    {"role": "assistant", "content": f"Starting processing for batch {i}"}
                ]
            }
            router_ids.append(self.create_test_router(conv_data))
        
        def stress_test_conversation(router_id, operation_count):
            """Perform multiple operations on a conversation under load."""
            operations_completed = []
            
            for i in range(operation_count):
                # Add message
                self.db.add_message(
                    agent_id=router_id,
                    agent_type="router",
                    role="user" if i % 2 == 0 else "assistant",
                    content=f"Load test message {i} for {router_id[-8:]}"
                )
                
                # Update status
                new_status = "processing" if i % 3 == 0 else "active"
                self.db.update_router_status(router_id, new_status)
                
                # Create and link planner (occasionally)
                if i % 5 == 0:
                    planner_id = f"load_planner_{router_id}_{i}_{uuid.uuid4().hex[:6]}"
                    self.db.create_planner(
                        planner_id=planner_id,
                        planner_name=f"Load Planner {i}",
                        user_question=f"Load test task {i}",
                        instruction=f"Process load test task {i}",
                        status="planning"
                    )
                    self.db.link_router_planner(router_id, planner_id, "load_test")
                
                operations_completed.append(f"op_{i}")
                
                # Micro delay to allow context switching
                time.sleep(0.001)
            
            return operations_completed
        
        # Run stress test on all conversations concurrently
        operations_per_conversation = 20
        with ThreadPoolExecutor(max_workers=num_conversations) as executor:
            futures = [
                executor.submit(stress_test_conversation, router_id, operations_per_conversation)
                for router_id in router_ids
            ]
            
            results = []
            for future in as_completed(futures):
                results.append(future.result())
        
        # Verify all operations completed successfully
        self.assertEqual(len(results), num_conversations)
        for result in results:
            self.assertEqual(len(result), operations_per_conversation)
        
        # Verify conversation isolation maintained
        for i, router_id in enumerate(router_ids):
            # Check message count
            messages = self.db.get_messages_by_agent_id(router_id, "router")
            expected_messages = 2 + operations_per_conversation  # Original + load test messages
            self.assertEqual(len(messages), expected_messages)
            
            # Verify messages contain router-specific content
            router_suffix = router_id[-8:]
            load_test_messages = [msg for msg in messages if "Load test" in msg["content"]]
            
            for msg in load_test_messages:
                self.assertIn(router_suffix, msg["content"])
            
            # Check planner count (every 5th operation creates a planner)
            planners = self.db.get_planners_by_router(router_id)
            expected_planners = operations_per_conversation // 5
            self.assertEqual(len(planners), expected_planners)


if __name__ == '__main__':
    # Run the tests
    unittest.main(verbosity=2)