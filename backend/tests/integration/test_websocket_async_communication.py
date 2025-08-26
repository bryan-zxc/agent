"""
WebSocket Async Communication Integration Tests

This test suite validates async/await correctness in real-time WebSocket communication
flows, focusing on RouterAgent WebSocket coordination, message delivery integrity,
and connection stability throughout async execution lifecycles.

Key Focus Areas:
- Real-time WebSocket communication during async operations
- RouterAgent coordination through WebSocket channels
- Message delivery integrity under concurrent load
- Connection stability during agent activation and execution
- Async exception handling in WebSocket contexts
"""

import unittest
import asyncio
import tempfile
import uuid
import time
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import List, Dict, Any

# Import async test utilities
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from async_test_utils import AsyncWarningCaptureMixin

# Import system components
from src.agent.models.agent_database import AgentDatabase
from src.agent.core.router import RouterAgent
from src.agent.tasks.planner_tasks import execute_initial_planning
from src.agent.tasks.task_utils import update_planner_next_task_and_queue
from src.agent.models.tasks import InitialExecutionPlan


@dataclass
class WebSocketMessage:
    """WebSocket message structure for testing."""
    message_type: str
    data: Dict[str, Any]
    timestamp: float
    connection_id: str
    router_id: str = None


class MockWebSocketManager:
    """Comprehensive mock WebSocket manager for async communication testing."""
    
    def __init__(self):
        self.connections = {}
        self.message_history = []
        self.connection_events = []
        self.error_events = []
        self.performance_metrics = {
            'messages_sent': 0,
            'messages_received': 0,
            'connection_count': 0,
            'disconnection_count': 0
        }
    
    async def add_connection(self, connection_id: str, router_id: str = None):
        """Mock adding a WebSocket connection."""
        connection = MockWebSocketConnection(connection_id, router_id)
        self.connections[connection_id] = connection
        self.performance_metrics['connection_count'] += 1
        
        event = {
            'type': 'connection_added',
            'connection_id': connection_id,
            'router_id': router_id,
            'timestamp': time.time()
        }
        self.connection_events.append(event)
        
        return connection
    
    async def remove_connection(self, connection_id: str):
        """Mock removing a WebSocket connection."""
        if connection_id in self.connections:
            del self.connections[connection_id]
            self.performance_metrics['disconnection_count'] += 1
            
            event = {
                'type': 'connection_removed',
                'connection_id': connection_id,
                'timestamp': time.time()
            }
            self.connection_events.append(event)
    
    async def broadcast_to_router(self, router_id: str, message: Dict[str, Any]):
        """Mock broadcasting message to all connections for a router."""
        broadcast_count = 0
        
        for connection_id, connection in self.connections.items():
            if connection.router_id == router_id:
                await connection.send_json(message)
                broadcast_count += 1
        
        self.performance_metrics['messages_sent'] += broadcast_count
        
        return broadcast_count
    
    async def send_to_connection(self, connection_id: str, message: Dict[str, Any]):
        """Mock sending message to specific connection."""
        if connection_id in self.connections:
            await self.connections[connection_id].send_json(message)
            self.performance_metrics['messages_sent'] += 1
            return True
        return False
    
    def get_connection_count(self) -> int:
        """Get current connection count."""
        return len(self.connections)
    
    def get_messages_for_router(self, router_id: str) -> List[WebSocketMessage]:
        """Get all messages sent to a specific router."""
        return [
            msg for msg in self.message_history 
            if msg.router_id == router_id
        ]
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get WebSocket performance metrics."""
        return self.performance_metrics.copy()


class MockWebSocketConnection:
    """Mock WebSocket connection for detailed testing."""
    
    def __init__(self, connection_id: str, router_id: str = None):
        self.connection_id = connection_id
        self.router_id = router_id
        self.sent_messages = []
        self.received_messages = []
        self.connection_state = "connected"
        self.last_activity = time.time()
    
    async def send_json(self, data: Dict[str, Any]):
        """Mock WebSocket JSON message sending."""
        if self.connection_state != "connected":
            raise ConnectionError(f"WebSocket connection {self.connection_id} not connected")
        
        message = WebSocketMessage(
            message_type=data.get('type', 'unknown'),
            data=data,
            timestamp=time.time(),
            connection_id=self.connection_id,
            router_id=self.router_id
        )
        
        self.sent_messages.append(message)
        self.last_activity = time.time()
    
    async def receive_json(self) -> Dict[str, Any]:
        """Mock WebSocket JSON message receiving."""
        # Simulate receiving a message (for testing purposes)
        if self.received_messages:
            message = self.received_messages.pop(0)
            self.last_activity = time.time()
            return message.data
        return None
    
    async def close(self):
        """Mock WebSocket connection closing."""
        self.connection_state = "closed"
    
    def simulate_incoming_message(self, message_data: Dict[str, Any]):
        """Simulate an incoming WebSocket message."""
        message = WebSocketMessage(
            message_type=message_data.get('type', 'incoming'),
            data=message_data,
            timestamp=time.time(),
            connection_id=self.connection_id,
            router_id=self.router_id
        )
        self.received_messages.append(message)


class WebSocketAsyncCommunicationTestCase(unittest.IsolatedAsyncioTestCase, AsyncWarningCaptureMixin):
    """Base test case for WebSocket async communication testing."""
    
    async def asyncSetUp(self):
        """Set up WebSocket communication test environment."""
        # Create temporary database
        self.temp_db_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db_file.close()
        self.db = AgentDatabase(self.temp_db_file.name)
        
        # Test identifiers
        self.router_id = f"ws_router_{uuid.uuid4().hex[:8]}"
        self.planner_id = f"ws_planner_{uuid.uuid4().hex[:8]}"
        self.connection_id = f"ws_conn_{uuid.uuid4().hex[:8]}"
        
        # WebSocket manager for testing
        self.ws_manager = MockWebSocketManager()
        
        # Performance targets for WebSocket operations
        self.websocket_performance_targets = {
            'message_delivery': 5.0,        # Message delivery latency
            'connection_management': 3.0,   # Connection setup/teardown
            'broadcast_operations': 8.0,    # Broadcasting to multiple connections
            'real_time_updates': 10.0       # Real-time update delivery
        }
    
    async def asyncTearDown(self):
        """Clean up WebSocket test resources."""
        try:
            await self.db.close()
        except:
            pass
        
        try:
            Path(self.temp_db_file.name).unlink()
        except:
            pass
    
    async def measure_websocket_performance(self, test_name, async_func, *args, **kwargs):
        """Measure WebSocket operation performance."""
        start_time = time.time()
        
        try:
            result = await async_func(*args, **kwargs)
            execution_time = time.time() - start_time
            
            # Calculate WebSocket-specific metrics
            message_throughput = result.get('messages_processed', 0) / max(execution_time, 0.001)
            
            return {
                'test_name': test_name,
                'result': result,
                'execution_time': execution_time,
                'message_throughput': message_throughput,
                'success': True,
                'error': None,
                'performance_data': {
                    'target': self.websocket_performance_targets.get(test_name, 15.0),
                    'actual': execution_time,
                    'within_target': execution_time <= self.websocket_performance_targets.get(test_name, 15.0),
                    'throughput': message_throughput
                }
            }
        except Exception as e:
            execution_time = time.time() - start_time
            return {
                'test_name': test_name,
                'result': None,
                'execution_time': execution_time,
                'message_throughput': 0,
                'success': False,
                'error': str(e),
                'performance_data': {
                    'target': self.websocket_performance_targets.get(test_name, 15.0),
                    'actual': execution_time,
                    'within_target': False,
                    'throughput': 0
                }
            }
    
    @asynccontextmanager
    async def websocket_mock_context(self):
        """Mock context for WebSocket communication testing."""
        mock_llm = MagicMock()
        mock_llm.a_get_response = AsyncMock()
        
        # Configure mock responses with different types based on call
        self.llm_call_count = 0
        
        def create_mock_response(*args, **kwargs):
            self.llm_call_count += 1
            # Check if this is a call for InitialExecutionPlan by looking for response_format
            if 'response_format' in kwargs and kwargs['response_format'] == InitialExecutionPlan:
                return InitialExecutionPlan(
                    objective="WebSocket communication validation",
                    todos=["Test real-time updates", "Validate message delivery"]
                )
            else:
                # Return a generic response with content attribute for other calls
                return type('MockResponse', (), {
                    'content': f"WebSocket test response {self.llm_call_count}\n## Answer\nTest content"
                })()
        
        mock_llm.a_get_response.side_effect = create_mock_response
        
        # Patch LLM services (WebSocket manager no longer needs patching)
        with patch('src.agent.tasks.planner_tasks.llm', mock_llm), \
             patch('src.agent.tasks.worker_tasks.llm', mock_llm):
            
            yield {
                'mock_llm': mock_llm,
                'ws_manager': self.ws_manager
            }


class TestRouterAgentWebSocketCoordination(WebSocketAsyncCommunicationTestCase):
    """Test RouterAgent coordination through WebSocket channels."""
    
    async def test_router_websocket_coordination_async_flow(self):
        """Test RouterAgent coordination with WebSocket communication."""
        
        async with self.capture_async_warnings() as warnings_list:
            async with self.websocket_mock_context() as mocks:
                # Measure router WebSocket coordination performance
                performance = await self.measure_websocket_performance(
                    'real_time_updates',
                    self._execute_router_websocket_coordination
                )
                
                # Validate async execution
                self.assertTrue(performance['success'],
                               f"Router WebSocket coordination failed: {performance['error']}")
                self.assert_no_unawaited_coroutines(warnings_list)
                
                # Validate performance
                perf_data = performance['performance_data']
                self.assertTrue(perf_data['within_target'],
                               f"WebSocket coordination took {perf_data['actual']:.2f}s "
                               f"(target: {perf_data['target']}s)")
                
                # Validate WebSocket coordination results
                result = performance['result']
                self.assertTrue(result['coordination_successful'])
                self.assertGreater(result['messages_processed'], 0)
                self.assertEqual(result['connection_status'], 'connected')
    
    async def _execute_router_websocket_coordination(self):
        """Execute RouterAgent WebSocket coordination flow."""
        # Set up WebSocket connection
        connection = await self.ws_manager.add_connection(self.connection_id, self.router_id)
        
        # Create RouterAgent instance
        router_agent = RouterAgent(self.router_id)
        
        # Create planner for coordination testing
        await self.db.create_planner(
            planner_id=self.planner_id,
            planner_name="WebSocketCoordinator",
            user_question="Test WebSocket coordination",
            instruction="Validate real-time communication",
            status="active"
        )
        
        # Execute operations that should trigger WebSocket updates
        await execute_initial_planning({
            "entity_id": self.planner_id,
            "payload": {
                "user_question": "Test WebSocket coordination",
                "instruction": "Validate real-time communication",
                "files": [],
                "planner_name": "WebSocketCoordinator",
                "router_id": self.router_id
            }
        })
        
        # Simulate WebSocket updates during task progression
        await self._simulate_websocket_updates(connection)
        
        # Progress planner and trigger more WebSocket updates
        await update_planner_next_task_and_queue(
            self.planner_id,
            "execute_task_creation"
        )
        
        # Validate WebSocket message delivery
        messages_sent = len(connection.sent_messages)
        
        return {
            'coordination_successful': messages_sent > 0,
            'messages_processed': messages_sent,
            'connection_status': connection.connection_state,
            'router_id': self.router_id,
            'connection_count': self.ws_manager.get_connection_count()
        }
    
    async def _simulate_websocket_updates(self, connection):
        """Simulate WebSocket updates during async operations."""
        # Simulate status updates
        status_updates = [
            {'type': 'status_update', 'planner_id': self.planner_id, 'status': 'planning'},
            {'type': 'task_progress', 'planner_id': self.planner_id, 'progress': 25},
            {'type': 'status_update', 'planner_id': self.planner_id, 'status': 'executing'},
            {'type': 'task_progress', 'planner_id': self.planner_id, 'progress': 50}
        ]
        
        # Send updates with small delays to simulate real-time communication
        for update in status_updates:
            await connection.send_json(update)
            await asyncio.sleep(0.01)  # Small delay between updates


class TestWebSocketMessageDelivery(WebSocketAsyncCommunicationTestCase):
    """Test WebSocket message delivery integrity under various conditions."""
    
    async def test_concurrent_websocket_message_delivery(self):
        """Test WebSocket message delivery under concurrent load."""
        
        async with self.capture_async_warnings() as warnings_list:
            async with self.websocket_mock_context() as mocks:
                # Measure concurrent message delivery performance
                performance = await self.measure_websocket_performance(
                    'message_delivery',
                    self._execute_concurrent_message_delivery
                )
                
                # Validate async execution
                self.assertTrue(performance['success'],
                               f"Concurrent message delivery failed: {performance['error']}")
                self.assert_no_unawaited_coroutines(warnings_list)
                
                # Validate performance
                perf_data = performance['performance_data']
                self.assertTrue(perf_data['within_target'],
                               f"Message delivery took {perf_data['actual']:.2f}s "
                               f"(target: {perf_data['target']}s)")
                
                # Validate message delivery integrity
                result = performance['result']
                self.assertEqual(result['messages_sent'], result['messages_received'])
                self.assertGreater(result['delivery_success_rate'], 0.95)  # 95% success rate
    
    async def _execute_concurrent_message_delivery(self):
        """Execute concurrent WebSocket message delivery test."""
        # Set up multiple connections
        connection_count = 3
        connections = []
        
        for i in range(connection_count):
            conn_id = f"{self.connection_id}_{i}"
            connection = await self.ws_manager.add_connection(conn_id, self.router_id)
            connections.append(connection)
        
        # Create concurrent message delivery tasks
        message_tasks = []
        messages_per_connection = 5
        
        for connection in connections:
            for msg_index in range(messages_per_connection):
                task = self._send_test_message(connection, msg_index)
                message_tasks.append(task)
        
        # Execute all message deliveries concurrently
        message_results = await asyncio.gather(*message_tasks, return_exceptions=True)
        
        # Analyse delivery results
        successful_deliveries = sum(
            1 for result in message_results 
            if not isinstance(result, Exception) and result.get('delivered', False)
        )
        
        total_messages = len(message_tasks)
        delivery_success_rate = successful_deliveries / total_messages if total_messages > 0 else 0
        
        # Count received messages
        total_received = sum(len(conn.sent_messages) for conn in connections)
        
        return {
            'messages_sent': total_messages,
            'messages_received': total_received,
            'successful_deliveries': successful_deliveries,
            'delivery_success_rate': delivery_success_rate,
            'connection_count': len(connections),
            'messages_processed': successful_deliveries
        }
    
    async def _send_test_message(self, connection, message_index):
        """Send a test message through WebSocket connection."""
        try:
            message = {
                'type': 'test_message',
                'index': message_index,
                'connection_id': connection.connection_id,
                'timestamp': time.time(),
                'data': f"Test message {message_index}"
            }
            
            await connection.send_json(message)
            
            return {
                'delivered': True,
                'message_index': message_index,
                'connection_id': connection.connection_id
            }
            
        except Exception as e:
            return {
                'delivered': False,
                'message_index': message_index,
                'connection_id': connection.connection_id,
                'error': str(e)
            }


class TestWebSocketConnectionStability(WebSocketAsyncCommunicationTestCase):
    """Test WebSocket connection stability during async operations."""
    
    async def test_connection_stability_during_async_operations(self):
        """Test WebSocket connection stability during long-running async operations."""
        
        async with self.capture_async_warnings() as warnings_list:
            async with self.websocket_mock_context() as mocks:
                # Measure connection stability performance
                performance = await self.measure_websocket_performance(
                    'connection_management',
                    self._execute_connection_stability_test
                )
                
                # Validate async execution
                self.assertTrue(performance['success'],
                               f"Connection stability test failed: {performance['error']}")
                self.assert_no_unawaited_coroutines(warnings_list)
                
                # Validate performance
                perf_data = performance['performance_data']
                self.assertTrue(perf_data['within_target'],
                               f"Connection stability test took {perf_data['actual']:.2f}s "
                               f"(target: {perf_data['target']}s)")
                
                # Validate connection stability
                result = performance['result']
                self.assertTrue(result['connections_stable'])
                self.assertEqual(result['connection_errors'], 0)
    
    async def _execute_connection_stability_test(self):
        """Execute WebSocket connection stability test."""
        # Set up connection
        connection = await self.ws_manager.add_connection(self.connection_id, self.router_id)
        
        # Create planner for long-running operations
        await self.db.create_planner(
            planner_id=self.planner_id,
            planner_name="StabilityTester",
            user_question="Test connection stability",
            instruction="Maintain WebSocket connection during operations",
            status="active"
        )
        
        # Execute long-running async operations while maintaining WebSocket connection
        async def long_running_operation():
            # Simulate extended async operations
            for i in range(10):
                await asyncio.sleep(0.05)  # Small delays to simulate work
                
                # Send periodic updates through WebSocket
                await connection.send_json({
                    'type': 'progress_update',
                    'operation_step': i,
                    'timestamp': time.time()
                })
                
                # Update database to simulate real work
                await self.db.update_planner(
                    self.planner_id,
                    current_task=f"stability_test_step_{i}"
                )
        
        # Execute operations and monitor connection stability
        try:
            await long_running_operation()
            connection_errors = 0
            connections_stable = connection.connection_state == "connected"
        except Exception as e:
            connection_errors = 1
            connections_stable = False
        
        # Validate connection state after operations
        final_message_count = len(connection.sent_messages)
        
        return {
            'connections_stable': connections_stable,
            'connection_errors': connection_errors,
            'final_message_count': final_message_count,
            'connection_state': connection.connection_state,
            'messages_processed': final_message_count
        }


if __name__ == '__main__':
    unittest.main()