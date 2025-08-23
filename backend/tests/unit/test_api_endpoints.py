"""
API Endpoint Test Suite

Tests for FastAPI HTTP endpoints including file upload, router management,
health checks, and usage statistics.
"""

import unittest
import asyncio
import tempfile
import uuid
import json
import hashlib
from unittest.mock import patch, AsyncMock, MagicMock
from pathlib import Path

# Mock FastAPI components for testing
class MockUploadFile:
    """Mock FastAPI UploadFile for testing."""
    
    def __init__(self, filename: str, content: bytes, content_type: str = "text/plain"):
        self.filename = filename
        self.content = content
        self.content_type = content_type
        self._position = 0
    
    async def read(self) -> bytes:
        """Mock async read method."""
        return self.content
    
    async def seek(self, position: int):
        """Mock async seek method."""
        self._position = position


class MockHTTPException(Exception):
    """Mock HTTPException for testing."""
    
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"{status_code}: {detail}")


class TestAPIEndpoints(unittest.IsolatedAsyncioTestCase):
    """Test FastAPI endpoint functionality."""

    async def asyncSetUp(self):
        """Set up test environment."""
        # Mock database
        self.mock_db = AsyncMock()
        self.test_user_id = "bryan000"  # From main.py
        
        # Test file data
        self.test_file_content = b"Test file content for upload testing"
        self.test_file_hash = hashlib.sha256(self.test_file_content).hexdigest()

    async def test_upload_file_no_duplicate(self):
        """Test file upload endpoint with no duplicate."""
        # Import after mocking dependencies
        with patch('main.AgentDatabase') as MockDB, \
             patch('main.calculate_file_hash') as mock_hash, \
             patch('main.sanitise_filename') as mock_sanitise, \
             patch('builtins.open', unittest.mock.mock_open()) as mock_open, \
             patch('pathlib.Path.mkdir') as mock_mkdir:
            
            # Setup mocks
            mock_db_instance = AsyncMock()
            MockDB.return_value = mock_db_instance
            mock_db_instance.get_file_by_hash.return_value = None  # No duplicate
            mock_db_instance.create_file_metadata.return_value = True
            
            mock_hash.return_value = self.test_file_hash
            mock_sanitise.return_value = "test_file.txt"
            
            # Mock file upload
            mock_file = MockUploadFile("test_file.txt", self.test_file_content)
            
            # Import endpoint function
            from main import upload_file
            
            # Test upload
            result = await upload_file(mock_file)
            
            # Verify response
            self.assertFalse(result["duplicate_found"])
            self.assertIn("file_id", result)
            self.assertEqual(result["filename"], "test_file.txt")
            self.assertEqual(result["size"], len(self.test_file_content))
            
            # Verify database operations
            mock_db_instance.get_file_by_hash.assert_awaited_once_with(
                self.test_file_hash, self.test_user_id
            )
            mock_db_instance.create_file_metadata.assert_awaited_once()

    async def test_upload_file_with_duplicate(self):
        """Test file upload endpoint with duplicate detection."""
        with patch('main.AgentDatabase') as MockDB, \
             patch('main.calculate_file_hash') as mock_hash:
            
            # Setup mocks
            mock_db_instance = AsyncMock()
            MockDB.return_value = mock_db_instance
            
            # Mock existing file (duplicate)
            existing_file_data = {
                "file_id": "existing_123",
                "original_filename": "existing_file.txt",
                "file_size": 1000,
                "upload_timestamp": MagicMock()
            }
            existing_file_data["upload_timestamp"].isoformat.return_value = "2024-01-01T00:00:00"
            
            mock_db_instance.get_file_by_hash.return_value = existing_file_data
            mock_hash.return_value = self.test_file_hash
            
            # Mock file upload
            mock_file = MockUploadFile("duplicate_file.txt", self.test_file_content)
            
            # Import endpoint function
            from main import upload_file
            
            # Test upload
            result = await upload_file(mock_file)
            
            # Verify duplicate response
            self.assertTrue(result["duplicate_found"])
            self.assertEqual(result["existing_file"]["file_id"], "existing_123")
            self.assertEqual(result["new_filename"], "duplicate_file.txt")
            self.assertIn("options", result)
            self.assertIn("use_existing", result["options"])

    async def test_resolve_duplicate_use_existing(self):
        """Test duplicate resolution with 'use_existing' action."""
        with patch('main.AgentDatabase') as MockDB:
            
            # Setup mocks
            mock_db_instance = AsyncMock()
            MockDB.return_value = mock_db_instance
            
            existing_file_data = {
                "file_id": "existing_123",
                "original_filename": "existing_file.txt",
                "file_path": "/path/to/existing_file.txt",
                "file_size": 1000
            }
            mock_db_instance.get_file_by_id.return_value = existing_file_data
            mock_db_instance.increment_file_reference.return_value = True
            
            # Mock file upload (not used for use_existing)
            mock_file = MockUploadFile("new_file.txt", b"content")
            
            # Import endpoint function
            from main import resolve_duplicate
            
            # Test resolve duplicate
            result = await resolve_duplicate(
                action="use_existing",
                existing_file_id="existing_123",
                new_filename="new_file.txt",
                file=mock_file
            )
            
            # Verify response
            self.assertEqual(result["action"], "use_existing")
            self.assertEqual(result["file_id"], "existing_123")
            self.assertEqual(result["filename"], "existing_file.txt")
            self.assertEqual(result["files"], ["/path/to/existing_file.txt"])
            
            # Verify database operations
            mock_db_instance.increment_file_reference.assert_awaited_once_with("existing_123")

    async def test_resolve_duplicate_cancel(self):
        """Test duplicate resolution with 'cancel' action."""
        # Mock file upload
        mock_file = MockUploadFile("cancelled_file.txt", b"content")
        
        # Import endpoint function
        from main import resolve_duplicate
        
        # Test cancel action
        result = await resolve_duplicate(
            action="cancel",
            existing_file_id="any_id",
            new_filename="any_name.txt",
            file=mock_file
        )
        
        # Verify response
        self.assertEqual(result["action"], "cancel")
        self.assertEqual(result["files"], [])

    async def test_health_check_endpoint(self):
        """Test health check endpoint."""
        # Import endpoint function
        from main import health_check
        
        # Test health check
        result = await health_check()
        
        # Verify response
        self.assertEqual(result["status"], "healthy")
        self.assertEqual(result["service"], "agent-system")

    async def test_get_routers_endpoint(self):
        """Test get routers endpoint."""
        with patch('main.AgentDatabase') as MockDB:
            
            # Setup mocks
            mock_db_instance = AsyncMock()
            MockDB.return_value = mock_db_instance
            
            mock_routers = [
                {
                    "router_id": "router_1",
                    "title": "Test Router 1",
                    "preview": "First test router",
                    "updated_at": MagicMock()
                },
                {
                    "router_id": "router_2", 
                    "title": "Test Router 2",
                    "preview": "Second test router",
                    "updated_at": MagicMock()
                }
            ]
            
            # Mock timestamp formatting
            mock_routers[0]["updated_at"].isoformat.return_value = "2024-01-01T00:00:00"
            mock_routers[1]["updated_at"].isoformat.return_value = "2024-01-02T00:00:00"
            
            mock_db_instance.get_all_routers.return_value = mock_routers
            
            # Import endpoint function
            from main import get_routers
            
            # Test get routers
            result = await get_routers()
            
            # Verify response
            self.assertEqual(len(result), 2)
            self.assertEqual(result[0]["id"], "router_1")
            self.assertEqual(result[0]["title"], "Test Router 1")
            self.assertEqual(result[0]["timestamp"], "2024-01-01T00:00:00")
            
            # Verify database operation
            mock_db_instance.get_all_routers.assert_awaited_once()

    async def test_get_router_endpoint(self):
        """Test get specific router endpoint."""
        with patch('main.RouterAgent') as MockRouter:
            
            # Setup mock router
            mock_router_instance = MagicMock()
            mock_router_instance.messages = [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"}
            ]
            MockRouter.return_value = mock_router_instance
            
            # Import endpoint function
            from main import get_router
            
            # Test get router
            result = await get_router("test_router_123")
            
            # Verify response
            self.assertEqual(result["router_id"], "test_router_123")
            self.assertEqual(len(result["messages"]), 2)
            self.assertEqual(result["messages"][0]["role"], "user")
            
            # Verify router creation
            MockRouter.assert_called_once_with(router_id="test_router_123")

    async def test_get_message_planner_info_endpoint(self):
        """Test get message planner info endpoint."""
        with patch('main.AgentDatabase') as MockDB:
            
            # Setup mocks
            mock_db_instance = AsyncMock()
            MockDB.return_value = mock_db_instance
            
            planner_data = {
                "planner_id": "planner_123",
                "execution_plan": "## Plan\n1. Step one\n2. Step two",
                "status": "executing",
                "planner_name": "Test Planner",
                "user_question": "Test question",
                "message_id": 42,
                "router_id": "router_123"
            }
            mock_db_instance.get_planner_by_message.return_value = planner_data
            
            # Import endpoint function
            from main import get_message_planner_info
            
            # Test get planner info
            result = await get_message_planner_info(42)
            
            # Verify response
            self.assertTrue(result["has_planner"])
            self.assertEqual(result["planner_id"], "planner_123")
            self.assertEqual(result["status"], "executing")
            self.assertEqual(result["message_id"], 42)
            
            # Verify database operation
            mock_db_instance.get_planner_by_message.assert_awaited_once_with(42)

    async def test_get_message_planner_info_no_planner(self):
        """Test get message planner info when no planner exists."""
        with patch('main.AgentDatabase') as MockDB:
            
            # Setup mocks
            mock_db_instance = AsyncMock()
            MockDB.return_value = mock_db_instance
            mock_db_instance.get_planner_by_message.return_value = None
            
            # Import endpoint function
            from main import get_message_planner_info
            
            # Test get planner info
            result = await get_message_planner_info(42)
            
            # Verify response
            self.assertFalse(result["has_planner"])
            self.assertIsNone(result["execution_plan"])
            self.assertIsNone(result["planner_id"])

    async def test_update_router_title_endpoint(self):
        """Test update router title endpoint."""
        with patch('main.RouterAgent') as MockRouter, \
             patch('asyncio.create_task') as mock_create_task:
            
            # Setup mock router
            mock_router_instance = AsyncMock()
            MockRouter.return_value = mock_router_instance
            
            # Import endpoint function
            from main import update_router_title
            
            # Test update title
            result = await update_router_title("test_router_123")
            
            # Verify response
            self.assertEqual(result["status"], "started")
            
            # Verify router creation and task creation
            MockRouter.assert_called_once_with(router_id="test_router_123")
            mock_create_task.assert_called_once()

    async def test_usage_stats_endpoint(self):
        """Test usage statistics endpoint."""
        with patch('main.create_engine') as mock_create_engine, \
             patch('main.sessionmaker') as mock_sessionmaker, \
             patch('main.Session') as MockSession:
            
            # Setup mocks
            mock_engine = MagicMock()
            mock_create_engine.return_value = mock_engine
            
            mock_session_class = MagicMock()
            mock_sessionmaker.return_value = mock_session_class
            
            mock_session = MagicMock()
            mock_session_class.return_value.__enter__.return_value = mock_session
            
            # Mock query results
            mock_session.query.return_value.filter.return_value.scalar.side_effect = [
                1.25,  # today
                5.50,  # week
                15.75, # month
                50.00  # total
            ]
            
            # Import endpoint function
            from main import get_usage_stats
            
            # Test get usage stats
            result = await get_usage_stats()
            
            # Verify response
            self.assertEqual(result["today"], 1.25)
            self.assertEqual(result["week"], 5.5)
            self.assertEqual(result["month"], 15.75)
            self.assertEqual(result["total"], 50.0)

    async def test_error_handling_in_endpoints(self):
        """Test error handling in API endpoints."""
        with patch('main.AgentDatabase') as MockDB:
            
            # Setup mock to raise exception
            mock_db_instance = AsyncMock()
            MockDB.return_value = mock_db_instance
            mock_db_instance.get_all_routers.side_effect = Exception("Database error")
            
            # Import endpoint function
            from main import get_routers
            
            # Test error handling
            with self.assertRaises(Exception) as context:
                await get_routers()
            
            # In real FastAPI, this would be handled by exception handlers
            # but we can test that the error propagates correctly
            self.assertIn("Database error", str(context.exception))

    async def test_file_upload_error_handling(self):
        """Test file upload error handling."""
        with patch('main.AgentDatabase') as MockDB:
            
            # Setup mock to raise exception
            mock_db_instance = AsyncMock()
            MockDB.return_value = mock_db_instance
            mock_db_instance.get_file_by_hash.side_effect = Exception("Database connection failed")
            
            # Mock file upload
            mock_file = MockUploadFile("error_file.txt", b"content")
            
            # Import endpoint function
            from main import upload_file
            
            # Test error handling
            with self.assertRaises(Exception) as context:
                await upload_file(mock_file)
            
            self.assertIn("Database connection failed", str(context.exception))

    async def test_endpoint_input_validation(self):
        """Test endpoint input validation."""
        with patch('main.AgentDatabase') as MockDB:
            
            # Setup mocks
            mock_db_instance = AsyncMock()
            MockDB.return_value = mock_db_instance
            mock_db_instance.get_file_by_id.return_value = None  # File not found
            
            # Mock file upload
            mock_file = MockUploadFile("test_file.txt", b"content")
            
            # Import endpoint function
            from main import resolve_duplicate
            
            # Test with invalid existing_file_id (should raise HTTPException)
            with self.assertRaises(Exception):  # Would be HTTPException in real FastAPI
                await resolve_duplicate(
                    action="use_existing",
                    existing_file_id="nonexistent_id",
                    new_filename="test.txt",
                    file=mock_file
                )

    async def test_concurrent_api_requests(self):
        """Test concurrent API request handling."""
        with patch('main.AgentDatabase') as MockDB:
            
            # Setup mocks
            mock_db_instance = AsyncMock()
            MockDB.return_value = mock_db_instance
            mock_db_instance.get_all_routers.return_value = [
                {
                    "router_id": f"router_{i}",
                    "title": f"Router {i}",
                    "preview": f"Preview {i}",
                    "updated_at": MagicMock()
                }
                for i in range(5)
            ]
            
            # Mock timestamp formatting
            for i, router in enumerate(mock_db_instance.get_all_routers.return_value):
                router["updated_at"].isoformat.return_value = f"2024-01-0{i+1}T00:00:00"
            
            # Import endpoint function
            from main import get_routers
            
            # Run concurrent requests
            results = await asyncio.gather(
                *[get_routers() for _ in range(3)]
            )
            
            # Verify all requests succeeded
            self.assertEqual(len(results), 3)
            for result in results:
                self.assertEqual(len(result), 5)
                self.assertTrue(all("id" in router for router in result))


if __name__ == '__main__':
    unittest.main(verbosity=2)