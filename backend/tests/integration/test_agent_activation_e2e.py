"""
End-to-End Agent Activation Flow Integration Tests

This test suite validates the complete "Agents assemble!" activation flow from initial
user request through agent coordination and task execution. Focus is on async correctness
in realistic end-to-end scenarios with real database operations and component integration.

Key Test Areas:
- Complete agent activation lifecycle from request to execution
- Multi-agent coordination and task distribution
- Real-time WebSocket communication during activation
- Database consistency throughout activation flow
- Performance validation under realistic load
"""

import unittest
import asyncio
import tempfile
import uuid
import time
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from contextlib import asynccontextmanager

# Import async test utilities
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from async_test_utils import AsyncWarningCaptureMixin

# Import system components
from src.agent.models.agent_database import AgentDatabase
from src.agent.core.router import RouterAgent
from src.agent.tasks.planner_tasks import execute_initial_planning, execute_task_creation
from src.agent.tasks.worker_tasks import execute_standard_worker
from src.agent.tasks.planner_tasks import InitialExecutionPlan
from src.agent.tasks.task_utils import update_planner_next_task_and_queue, queue_worker_task
from src.agent.models.schemas import File
from src.agent.config.settings import settings


class AgentActivationE2ETestCase(unittest.IsolatedAsyncioTestCase, AsyncWarningCaptureMixin):
    """Base test case for agent activation end-to-end testing."""
    
    async def asyncSetUp(self):
        """Set up comprehensive test environment for e2e testing."""
        # Create temporary database for real async operations
        self.temp_db_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db_file.close()
        self.db = AgentDatabase(self.temp_db_file.name)
        
        # Test identifiers for multi-agent scenarios
        self.router_id = f"e2e_router_{uuid.uuid4().hex[:8]}"
        self.planner_id = f"e2e_planner_{uuid.uuid4().hex[:8]}"
        self.worker_ids = [f"e2e_worker_{i}_{uuid.uuid4().hex[:6]}" for i in range(3)]
        
        # Performance targets for e2e flows
        self.e2e_performance_targets = {
            'full_activation': 15.0,      # Complete activation flow
            'multi_agent_coordination': 20.0,  # Multiple agents working together
            'agent_lifecycle': 12.0,      # Single agent full lifecycle
            'concurrent_activation': 25.0  # Multiple concurrent activations
        }
        
        # Mock WebSocket for real-time communication testing
        self.mock_websocket = MockWebSocketConnection()
    
    async def asyncTearDown(self):
        """Clean up e2e test resources."""
        try:
            await self.db.close()
        except:
            pass
        
        try:
            Path(self.temp_db_file.name).unlink()
        except:
            pass
    
    async def measure_e2e_performance(self, test_name, async_func, *args, **kwargs):
        """Measure performance of end-to-end test scenarios."""
        start_time = time.time()
        
        try:
            result = await async_func(*args, **kwargs)
            execution_time = time.time() - start_time
            
            return {
                'test_name': test_name,
                'result': result,
                'execution_time': execution_time,
                'success': True,
                'error': None,
                'performance_data': {
                    'target': self.e2e_performance_targets.get(test_name, 30.0),
                    'actual': execution_time,
                    'within_target': execution_time <= self.e2e_performance_targets.get(test_name, 30.0)
                }
            }
        except Exception as e:
            execution_time = time.time() - start_time
            return {
                'test_name': test_name,
                'result': None,
                'execution_time': execution_time,
                'success': False,
                'error': str(e),
                'performance_data': {
                    'target': self.e2e_performance_targets.get(test_name, 30.0),
                    'actual': execution_time,
                    'within_target': False
                }
            }
    
    @asynccontextmanager
    async def e2e_mock_context(self):
        """E2E mocking context that preserves internal async flows."""
        # Mock external services but preserve internal async execution
        mock_llm = MagicMock()
        mock_llm.a_get_response = AsyncMock()
        mock_file_ops = MagicMock()
        
        # Import Task model for proper mock responses
        from src.agent.models.tasks import Task
        
        # Configure realistic responses for e2e scenarios
        mock_llm.a_get_response.side_effect = [
            # Response for execute_initial_planning - execution plan
            InitialExecutionPlan(
                objective="Execute comprehensive e2e validation",
                todos=[
                    "Initialise agent coordination system",
                    "Process user request through pipeline",
                    "Execute tasks with worker agents",
                    "Generate final response"
                ]
            ),
            # Response for execute_initial_planning - answer template
            type('MockResponse', (), {
                'content': "# E2E Integration Test Results\n\nAgent activation completed successfully."
            })(),
            # Response for execute_task_creation - task definition
            Task(
                user_request="Execute complete agent activation flow",
                task_description="Initialise agent coordination system",
                acceptance_criteria=["System initialised", "Agents ready"],
                image_keys=[],
                variable_keys=[],
                tools=[],
                querying_structured_data=False
            )
        ]
        
        with patch('src.agent.tasks.planner_tasks.llm', mock_llm), \
             patch('src.agent.tasks.worker_tasks.llm', mock_llm), \
             patch('src.agent.tasks.file_manager.save_variable_to_file', mock_file_ops), \
             patch('src.agent.tasks.file_manager.save_image_to_file', mock_file_ops):
            
            yield {
                'mock_llm': mock_llm,
                'mock_file_ops': mock_file_ops,
                'mock_websocket': self.mock_websocket
            }


class MockWebSocketConnection:
    """Mock WebSocket connection for testing real-time communication."""
    
    def __init__(self):
        self.sent_messages = []
        self.connection_status = "connected"
        self.message_history = []
    
    async def send_json(self, data):
        """Mock WebSocket message sending with validation."""
        message = {
            'timestamp': time.time(),
            'data': data,
            'connection_id': 'e2e_test_connection'
        }
        self.sent_messages.append(message)
        self.message_history.append(data)
    
    async def broadcast_to_router(self, router_id, message):
        """Mock broadcast functionality for router-level communication."""
        await self.send_json({
            'type': 'router_broadcast',
            'router_id': router_id,
            'message': message
        })
    
    def get_message_count(self):
        """Get total message count for validation."""
        return len(self.sent_messages)
    
    def get_messages_by_type(self, message_type):
        """Filter messages by type for validation."""
        return [msg for msg in self.message_history if msg.get('type') == message_type]


class TestCompleteAgentActivationFlow(AgentActivationE2ETestCase):
    """Test the complete agent activation flow from start to finish."""
    
    async def test_full_agent_activation_lifecycle_e2e(self):
        """Test complete 'Agents assemble!' flow with all components."""
        
        async with self.capture_async_warnings() as warnings_list:
            async with self.e2e_mock_context() as mocks:
                # Measure complete activation flow
                performance = await self.measure_e2e_performance(
                    'full_activation',
                    self._execute_complete_activation_flow
                )
                
                # Validate async execution correctness
                self.assertTrue(performance['success'], 
                               f"Full activation flow failed: {performance['error']}")
                self.assert_no_unawaited_coroutines(warnings_list)
                
                # Validate performance targets
                perf_data = performance['performance_data']
                self.assertTrue(perf_data['within_target'],
                               f"Activation took {perf_data['actual']:.2f}s "
                               f"(target: {perf_data['target']}s)")
                
                # Validate database state after activation
                await self._validate_activation_database_state()
                
                # Validate WebSocket communications occurred
                self.assertGreater(mocks['mock_websocket'].get_message_count(), 0,
                                 "WebSocket messages should be sent during activation")
    
    async def _execute_complete_activation_flow(self):
        """Execute the complete agent activation flow."""
        # Step 1: Create router for agent coordination
        router_agent = RouterAgent(self.router_id)
        
        # Step 2: Create planner (initial agent activation)
        await self.db.create_planner(
            planner_id=self.planner_id,
            planner_name="E2EActivationTester",
            user_question="Execute complete agent activation flow",
            instruction="Validate end-to-end agent coordination with async correctness",
            status="planning"
        )
        
        # Step 3: Execute initial planning (agent assembly begins)
        initial_planning_data = {
            "entity_id": self.planner_id,
            "payload": {
                "user_question": "Execute complete agent activation flow",
                "instruction": "Validate end-to-end agent coordination",
                "files": [],
                "planner_name": "E2EActivationTester",
                "router_id": self.router_id
            }
        }
        
        await execute_initial_planning(initial_planning_data)
        
        # Step 4: Progress through task creation (agents organising)
        await update_planner_next_task_and_queue(
            self.planner_id,
            "execute_task_creation"
        )
        
        # Step 5: Execute task creation
        task_creation_data = {
            "entity_id": self.planner_id,
            "payload": {
                "planner_name": "E2EActivationTester",
                "router_id": self.router_id
            }
        }
        
        await execute_task_creation(task_creation_data)
        
        # Step 6: Queue worker tasks (worker agents activated)
        for worker_id in self.worker_ids[:2]:  # Use 2 workers for e2e test
            await queue_worker_task(
                worker_id=worker_id,
                planner_id=self.planner_id
            )
        
        # Step 7: Simulate worker execution
        await asyncio.gather(*[
            self._simulate_worker_execution(worker_id) 
            for worker_id in self.worker_ids[:2]
        ])
        
        return {
            'activation_complete': True,
            'agents_activated': len(self.worker_ids[:2]) + 1,  # workers + planner
            'router_id': self.router_id,
            'planner_id': self.planner_id
        }
    
    async def _simulate_worker_execution(self, worker_id):
        """Simulate worker agent execution in e2e context."""
        # Create worker entry in database
        await self.db.create_worker(
            worker_id=worker_id,
            planner_id=self.planner_id,
            worker_name="E2E Test Worker",
            task_status="executing",
            task_description="E2E validation task",
            acceptance_criteria=["Complete E2E validation", "Verify async execution"],
            user_request="Perform E2E test",
            wip_answer_template="## E2E Test Results\nPending...",
            task_result="",
            querying_structured_data=False,
            image_keys=[],
            variable_keys=[],
            tools=[],
            input_variable_filepaths={},
            input_image_filepaths={},
            tables=[],
            filepaths=[]
        )
        
        # Simulate async worker task execution
        await asyncio.sleep(0.1)  # Brief async operation simulation
        
        # Update worker status
        await self.db.update_worker(
            worker_id=worker_id,
            status="completed",
            result_summary="E2E validation completed successfully"
        )
    
    async def _validate_activation_database_state(self):
        """Validate database state after complete activation."""
        # Verify planner exists and progressed
        planner_data = await self.db.get_planner(self.planner_id)
        self.assertIsNotNone(planner_data)
        self.assertIn(planner_data['status'], ['executing', 'planning'])
        
        # Verify workers were created
        # Note: Actual worker validation would depend on specific database schema
        # This serves as a placeholder for the validation logic


class TestMultiAgentCoordination(AgentActivationE2ETestCase):
    """Test coordination between multiple agents during activation."""
    
    async def test_concurrent_multi_agent_activation(self):
        """Test multiple agents activating and coordinating concurrently."""
        
        async with self.capture_async_warnings() as warnings_list:
            async with self.e2e_mock_context() as mocks:
                # Measure multi-agent coordination performance
                performance = await self.measure_e2e_performance(
                    'multi_agent_coordination',
                    self._execute_multi_agent_coordination
                )
                
                # Validate async execution
                self.assertTrue(performance['success'],
                               f"Multi-agent coordination failed: {performance['error']}")
                self.assert_no_unawaited_coroutines(warnings_list)
                
                # Validate performance
                perf_data = performance['performance_data']
                self.assertTrue(perf_data['within_target'],
                               f"Multi-agent coordination took {perf_data['actual']:.2f}s "
                               f"(target: {perf_data['target']}s)")
                
                # Validate coordination results
                result = performance['result']
                self.assertEqual(result['planners_created'], 2)
                self.assertEqual(result['workers_activated'], 4)  # 2 per planner
    
    async def _execute_multi_agent_coordination(self):
        """Execute multi-agent coordination scenario."""
        planner_ids = [
            f"coord_planner_1_{uuid.uuid4().hex[:6]}",
            f"coord_planner_2_{uuid.uuid4().hex[:6]}"
        ]
        
        # Create multiple planners concurrently
        planner_tasks = []
        for i, planner_id in enumerate(planner_ids):
            task = self.db.create_planner(
                planner_id=planner_id,
                planner_name=f"CoordinatedAgent{i+1}",
                user_question=f"Multi-agent coordination test {i+1}",
                instruction="Coordinate with other agents for task completion",
                status="active"
            )
            planner_tasks.append(task)
        
        await asyncio.gather(*planner_tasks)
        
        # Execute coordination tasks concurrently
        coordination_tasks = []
        for planner_id in planner_ids:
            task = self._coordinate_single_agent(planner_id)
            coordination_tasks.append(task)
        
        coordination_results = await asyncio.gather(*coordination_tasks)
        
        return {
            'planners_created': len(planner_ids),
            'workers_activated': sum(result['workers_count'] for result in coordination_results),
            'coordination_successful': all(result['success'] for result in coordination_results)
        }
    
    async def _coordinate_single_agent(self, planner_id):
        """Coordinate a single agent with async operations."""
        try:
            # Progress planner through coordination tasks
            await update_planner_next_task_and_queue(
                planner_id,
                "execute_task_creation"
            )
            
            # Create worker agents for this planner
            worker_count = 2
            coordination_workers = [
                f"coord_worker_{planner_id}_{i}" for i in range(worker_count)
            ]
            
            # Queue workers concurrently
            worker_tasks = [
                queue_worker_task(worker_id=worker_id, planner_id=planner_id)
                for worker_id in coordination_workers
            ]
            
            await asyncio.gather(*worker_tasks)
            
            return {
                'success': True,
                'planner_id': planner_id,
                'workers_count': worker_count
            }
            
        except Exception as e:
            return {
                'success': False,
                'planner_id': planner_id,
                'workers_count': 0,
                'error': str(e)
            }


class TestAgentActivationPerformance(AgentActivationE2ETestCase):
    """Test agent activation performance under various conditions."""
    
    async def test_agent_activation_performance_under_load(self):
        """Test agent activation performance with multiple concurrent activations."""
        
        async with self.capture_async_warnings() as warnings_list:
            async with self.e2e_mock_context() as mocks:
                # Measure concurrent activation performance
                performance = await self.measure_e2e_performance(
                    'concurrent_activation',
                    self._execute_concurrent_activations
                )
                
                # Validate async execution
                self.assertTrue(performance['success'],
                               f"Concurrent activations failed: {performance['error']}")
                self.assert_no_unawaited_coroutines(warnings_list)
                
                # Validate performance under load
                perf_data = performance['performance_data']
                self.assertTrue(perf_data['within_target'],
                               f"Concurrent activations took {perf_data['actual']:.2f}s "
                               f"(target: {perf_data['target']}s)")
                
                # Validate all activations succeeded
                result = performance['result']
                self.assertEqual(result['successful_activations'], result['total_activations'])
    
    async def _execute_concurrent_activations(self):
        """Execute multiple concurrent agent activations."""
        activation_count = 3
        activation_tasks = []
        
        for i in range(activation_count):
            planner_id = f"perf_planner_{i}_{uuid.uuid4().hex[:6]}"
            activation_task = self._single_agent_activation_flow(planner_id, i)
            activation_tasks.append(activation_task)
        
        # Execute all activations concurrently
        activation_results = await asyncio.gather(*activation_tasks, return_exceptions=True)
        
        # Analyse results
        successful_activations = sum(
            1 for result in activation_results 
            if not isinstance(result, Exception) and result.get('success', False)
        )
        
        return {
            'total_activations': activation_count,
            'successful_activations': successful_activations,
            'activation_results': activation_results
        }
    
    async def _single_agent_activation_flow(self, planner_id, index):
        """Execute a single agent activation flow for performance testing."""
        try:
            # Create planner
            await self.db.create_planner(
                planner_id=planner_id,
                planner_name=f"PerfTester{index}",
                user_question=f"Performance test activation {index}",
                instruction="Execute under performance load conditions",
                status="active"
            )
            
            # Execute initial planning
            planning_data = {
                "entity_id": planner_id,
                "payload": {
                    "user_question": f"Performance test activation {index}",
                    "instruction": "Execute under load",
                    "files": [],
                    "planner_name": f"PerfTester{index}",
                    "router_id": self.router_id
                }
            }
            
            await execute_initial_planning(planning_data)
            
            # Progress through task creation
            await update_planner_next_task_and_queue(
                planner_id,
                "execute_task_creation"
            )
            
            return {
                'success': True,
                'planner_id': planner_id,
                'index': index
            }
            
        except Exception as e:
            return {
                'success': False,
                'planner_id': planner_id,
                'index': index,
                'error': str(e)
            }


if __name__ == '__main__':
    unittest.main()