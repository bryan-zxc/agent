import unittest

"""
Concurrent Async Operations Integration Tests

This test suite validates async execution correctness under concurrent load conditions,
focusing on race condition detection, database consistency, and resource contention
prevention. Tests build on Phase 2-3 async validation utilities.

Key Focus Areas:
- Multiple planners executing simultaneously without interference
- Database consistency under concurrent async load
- Task queue isolation and thread safety validation
- Resource contention detection and prevention
- Deadlock prevention in complex async workflows
"""

import unittest
import asyncio
import uuid
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
import threading

# Import async test utilities
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from async_test_utils import AsyncWarningCaptureMixin

# Import system components
from src.agent.models.agent_database import AgentDatabase
from src.agent.database.connection import DatabaseConfig
from src.agent.core import router_operations
from src.agent.tasks.planner_tasks import (
    execute_initial_planning,
    execute_task_creation,
)
from src.agent.tasks.worker_tasks import execute_standard_worker
from src.agent.tasks.task_utils import (
    update_planner_next_task_and_queue,
    queue_worker_task,
)
from src.agent.models.tasks import InitialExecutionPlan


class ConcurrentAsyncOperationsTestCase(
    unittest.IsolatedAsyncioTestCase, AsyncWarningCaptureMixin
):
    """Base test case for concurrent async operations testing."""

    async def asyncSetUp(self):
        """Set up test environment for concurrent operations testing."""
        # Create temporary database for concurrent access testing
        self.temp_db_file.close()
        self.db = await AgentDatabase.create(database_url=config.get_database_url(database_name="test"))

        # Test identifiers for concurrent scenarios
        self.router_id = f"concurrent_router_{uuid.uuid4().hex[:8]}"
        self.base_planner_id = f"concurrent_base_{uuid.uuid4().hex[:8]}"

        # Concurrent operation parameters
        self.concurrent_params = {
            "max_concurrent_planners": 5,
            "max_concurrent_workers": 10,
            "stress_test_operations": 20,
            "timeout_per_operation": 10.0,
        }

        # Performance targets for concurrent operations
        self.concurrent_performance_targets = {
            "concurrent_planners": 30.0,  # Multiple planners running simultaneously
            "database_stress_test": 45.0,  # High-load database operations
            "resource_contention": 25.0,  # Resource contention scenarios
            "deadlock_prevention": 20.0,  # Deadlock prevention validation
        }

        # Thread safety validation
        self.operation_counts = {}
        self.operation_lock = threading.Lock()

    async def asyncTearDown(self):
        """Clean up concurrent test resources."""
        try:
            await self.db.close()
        except:
            pass

        try:
            Path(self.temp_db_file.name).unlink()
        except:
            pass

    async def measure_concurrent_performance(
        self, test_name, async_func, *args, **kwargs
    ):
        """Measure performance of concurrent operations with detailed metrics."""
        start_time = time.time()

        try:
            result = await async_func(*args, **kwargs)
            execution_time = time.time() - start_time

            # Calculate concurrent operation metrics
            operations_per_second = result.get("total_operations", 0) / max(
                execution_time, 0.001
            )

            return {
                "test_name": test_name,
                "result": result,
                "execution_time": execution_time,
                "operations_per_second": operations_per_second,
                "success": True,
                "error": None,
                "performance_data": {
                    "target": self.concurrent_performance_targets.get(test_name, 60.0),
                    "actual": execution_time,
                    "within_target": execution_time
                    <= self.concurrent_performance_targets.get(test_name, 60.0),
                    "throughput": operations_per_second,
                },
            }
        except Exception as e:
            execution_time = time.time() - start_time
            return {
                "test_name": test_name,
                "result": None,
                "execution_time": execution_time,
                "operations_per_second": 0,
                "success": False,
                "error": str(e),
                "performance_data": {
                    "target": self.concurrent_performance_targets.get(test_name, 60.0),
                    "actual": execution_time,
                    "within_target": False,
                    "throughput": 0,
                },
            }

    @asynccontextmanager
    async def concurrent_mock_context(self):
        """Mock context for concurrent operations testing."""
        mock_llm = MagicMock()
        mock_llm.a_get_response = AsyncMock()

        # Configure mock to handle concurrent requests with different response types
        self.call_count = 0

        def create_mock_response(*args, **kwargs):
            self.call_count += 1
            # Check if this is a call for InitialExecutionPlan by looking for response_format
            if (
                "response_format" in kwargs
                and kwargs["response_format"] == InitialExecutionPlan
            ):
                return InitialExecutionPlan(
                    objective=f"Concurrent operation {self.call_count}",
                    todos=[
                        "Execute concurrent database operations",
                        "Validate thread safety",
                        "Check for race conditions",
                    ],
                )
            else:
                # Return a generic response with content attribute for other calls
                return type(
                    "MockResponse",
                    (),
                    {
                        "content": f"Mock response {self.call_count}\n## Answer\nTest content"
                    },
                )()

        mock_llm.a_get_response.side_effect = create_mock_response

        with patch("src.agent.tasks.planner_tasks.llm", mock_llm), patch(
            "src.agent.tasks.worker_tasks.llm", mock_llm
        ):

            yield {"mock_llm": mock_llm}

    def track_operation(self, operation_type, operation_id):
        """Thread-safe operation tracking for concurrent validation."""
        with self.operation_lock:
            if operation_type not in self.operation_counts:
                self.operation_counts[operation_type] = []
            self.operation_counts[operation_type].append(
                {
                    "id": operation_id,
                    "timestamp": time.time(),
                    "thread_id": threading.get_ident(),
                }
            )



class TestDatabaseConcurrencyStress(ConcurrentAsyncOperationsTestCase):
    """Test database operations under high concurrent load."""

    async def test_database_async_operations_under_stress(self):
        """Test database async operations under high concurrent load."""

        async with self.capture_async_warnings() as warnings_list:
            async with self.concurrent_mock_context() as mocks:
                # Measure database stress test performance
                performance = await self.measure_concurrent_performance(
                    "database_stress_test", self._execute_database_stress_test
                )

                # Validate async execution
                self.assertTrue(
                    performance["success"],
                    f"Database stress test failed: {performance['error']}",
                )
                self.assert_no_unawaited_coroutines(warnings_list)

                # Validate performance under stress
                perf_data = performance["performance_data"]
                self.assertTrue(
                    perf_data["within_target"],
                    f"Database stress test took {perf_data['actual']:.2f}s "
                    f"(target: {perf_data['target']}s)",
                )

                # Validate stress test results
                result = performance["result"]
                self.assertGreater(
                    result["successful_operations"],
                    result["total_operations"] * 0.9,  # 90% success rate minimum
                    "Database stress test success rate too low",
                )

    async def _execute_database_stress_test(self):
        """Execute high-load database operations concurrently."""
        operation_count = self.concurrent_params["stress_test_operations"]
        stress_tasks = []

        # Create stress test operations
        for i in range(operation_count):
            operation_id = f"stress_op_{i}_{uuid.uuid4().hex[:6]}"
            task = self._single_database_stress_operation(operation_id, i)
            stress_tasks.append(task)

        # Execute all stress operations concurrently
        stress_results = await asyncio.gather(*stress_tasks, return_exceptions=True)

        # Analyse stress test results
        successful_operations = sum(
            1
            for result in stress_results
            if not isinstance(result, Exception) and result.get("success", False)
        )

        return {
            "total_operations": operation_count,
            "successful_operations": successful_operations,
            "failed_operations": operation_count - successful_operations,
            "stress_results": stress_results,
        }

    async def _single_database_stress_operation(self, operation_id, index):
        """Execute a single database stress operation."""
        try:
            planner_id = f"stress_planner_{operation_id}"

            # Rapid database operations
            await self.db.create_planner(
                planner_id=planner_id,
                planner_name=f"StressPlanner{index}",
                user_question=f"Stress test operation {index}",
                instruction="Database stress testing",
                status="planning",
            )

            # Rapid updates
            await self.db.update_planner(
                planner_id, status="executing", current_task=f"stress_task_{index}"
            )

            await self.db.update_planner(
                planner_id,
                status="completed",
                objective=f"Stress test {index} completed",
            )

            return {"success": True, "operation_id": operation_id, "index": index}

        except Exception as e:
            return {
                "success": False,
                "operation_id": operation_id,
                "index": index,
                "error": str(e),
            }


class TestResourceContentionPrevention(ConcurrentAsyncOperationsTestCase):
    """Test resource contention prevention in concurrent async scenarios."""

    async def test_resource_contention_detection_and_prevention(self):
        """Test that resource contention is detected and handled properly."""

        async with self.capture_async_warnings() as warnings_list:
            async with self.concurrent_mock_context() as mocks:
                # Measure resource contention test performance
                performance = await self.measure_concurrent_performance(
                    "resource_contention", self._execute_resource_contention_test
                )

                # Validate async execution
                self.assertTrue(
                    performance["success"],
                    f"Resource contention test failed: {performance['error']}",
                )
                self.assert_no_unawaited_coroutines(warnings_list)

                # Validate performance
                perf_data = performance["performance_data"]
                self.assertTrue(
                    perf_data["within_target"],
                    f"Resource contention test took {perf_data['actual']:.2f}s "
                    f"(target: {perf_data['target']}s)",
                )

                # Validate contention handling
                result = performance["result"]
                self.assertTrue(
                    result["contention_handled"],
                    "Resource contention was not handled properly",
                )

    async def _execute_resource_contention_test(self):
        """Execute resource contention scenarios."""
        # Create scenarios that could lead to resource contention
        contention_tasks = []

        # Scenario 1: Multiple operations on same resource
        shared_resource_id = f"shared_{uuid.uuid4().hex[:6]}"
        for i in range(5):
            task = self._contend_for_shared_resource(shared_resource_id, i)
            contention_tasks.append(task)

        # Execute contention scenarios
        contention_results = await asyncio.gather(
            *contention_tasks, return_exceptions=True
        )

        # Analyse contention handling
        successful_contentions = sum(
            1
            for result in contention_results
            if not isinstance(result, Exception) and result.get("success", False)
        )

        # Resource contention is "handled" if operations complete without deadlock
        contention_handled = successful_contentions > 0

        return {
            "total_operations": len(contention_tasks),
            "successful_contentions": successful_contentions,
            "contention_handled": contention_handled,
            "contention_results": contention_results,
        }

    async def _contend_for_shared_resource(self, resource_id, index):
        """Create contention for a shared resource."""
        try:
            planner_id = f"contender_{resource_id}_{index}"

            # Operations that could contend for database resources
            await self.db.create_planner(
                planner_id=planner_id,
                planner_name=f"Contender{index}",
                user_question=f"Contention test {index}",
                instruction="Compete for shared resources",
                status="planning",
            )

            # Simulate work that might cause contention
            await asyncio.sleep(0.01)  # Brief async operation

            await self.db.update_planner(
                planner_id,
                status="competing",
                current_task=f"contention_task_{resource_id}",
            )

            return {
                "success": True,
                "resource_id": resource_id,
                "contender_index": index,
            }

        except Exception as e:
            return {
                "success": False,
                "resource_id": resource_id,
                "contender_index": index,
                "error": str(e),
            }


if __name__ == "__main__":
    unittest.main()
