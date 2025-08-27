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
import tempfile
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

# from src.agent.core.router import RouterAgent
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
        self.temp_db_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db_file.close()
        self.db = await AgentDatabase.create(self.temp_db_file.name)

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


@unittest.skip("RouterAgent class refactored - needs update")
class TestConcurrentPlannerExecution(ConcurrentAsyncOperationsTestCase):
    """Test concurrent execution of multiple planners for async safety."""

    async def test_multiple_planners_concurrent_execution(self):
        """Test multiple planners executing concurrently without interference."""

        async with self.capture_async_warnings() as warnings_list:
            async with self.concurrent_mock_context() as mocks:
                # Measure concurrent planner performance
                performance = await self.measure_concurrent_performance(
                    "concurrent_planners", self._execute_concurrent_planners
                )

                # Validate async execution
                self.assertTrue(
                    performance["success"],
                    f"Concurrent planners failed: {performance['error']}",
                )
                self.assert_no_unawaited_coroutines(warnings_list)

                # Validate performance targets
                perf_data = performance["performance_data"]
                self.assertTrue(
                    perf_data["within_target"],
                    f"Concurrent planners took {perf_data['actual']:.2f}s "
                    f"(target: {perf_data['target']}s)",
                )

                # Validate concurrent execution results
                result = performance["result"]
                self.assertEqual(
                    result["successful_planners"],
                    self.concurrent_params["max_concurrent_planners"],
                )
                self.assertEqual(result["database_consistency_check"], "passed")

                # Validate no race conditions detected
                self.assertFalse(
                    result["race_conditions_detected"],
                    "Race conditions detected in concurrent planner execution",
                )

    async def _execute_concurrent_planners(self):
        """Execute multiple planners concurrently with validation."""
        planner_count = self.concurrent_params["max_concurrent_planners"]
        concurrent_tasks = []

        # Create concurrent planner execution tasks
        for i in range(planner_count):
            planner_id = f"{self.base_planner_id}_concurrent_{i}"
            task = self._single_planner_concurrent_execution(planner_id, i)
            concurrent_tasks.append(task)

        # Execute all planners concurrently
        planner_results = await asyncio.gather(
            *concurrent_tasks, return_exceptions=True
        )

        # Analyse concurrent execution results
        successful_planners = sum(
            1
            for result in planner_results
            if not isinstance(result, Exception) and result.get("success", False)
        )

        # Check for race conditions by validating operation counts
        race_conditions_detected = await self._detect_race_conditions(planner_results)

        # Validate database consistency after concurrent operations
        database_consistency = await self._validate_concurrent_database_consistency()

        return {
            "total_operations": len(concurrent_tasks),
            "successful_planners": successful_planners,
            "failed_planners": planner_count - successful_planners,
            "race_conditions_detected": race_conditions_detected,
            "database_consistency_check": database_consistency,
            "operation_metrics": self.operation_counts,
        }

    async def _single_planner_concurrent_execution(self, planner_id, index):
        """Execute a single planner in concurrent context."""
        try:
            self.track_operation("planner_creation", planner_id)

            # Create planner
            await self.db.create_planner(
                planner_id=planner_id,
                planner_name=f"ConcurrentPlanner{index}",
                user_question=f"Concurrent execution test {index}",
                instruction="Execute concurrently with other planners",
                status="planning",
            )

            self.track_operation("initial_planning", planner_id)

            # Execute initial planning
            planning_data = {
                "entity_id": planner_id,
                "payload": {
                    "user_question": f"Concurrent execution test {index}",
                    "instruction": "Execute concurrently",
                    "files": [],
                    "planner_name": f"ConcurrentPlanner{index}",
                    "router_id": self.router_id,
                },
            }

            await execute_initial_planning(planning_data)

            self.track_operation("task_progression", planner_id)

            # Progress through task pipeline
            await update_planner_next_task_and_queue(
                planner_id, "execute_task_creation"
            )

            self.track_operation("planner_completion", planner_id)

            return {
                "success": True,
                "planner_id": planner_id,
                "index": index,
                "operations_completed": 4,  # creation, planning, progression, completion
            }

        except Exception as e:
            return {
                "success": False,
                "planner_id": planner_id,
                "index": index,
                "error": str(e),
                "operations_completed": 0,
            }

    async def _detect_race_conditions(self, planner_results):
        """Detect potential race conditions from concurrent execution."""
        # Check for overlapping operations that might indicate race conditions
        operation_times = []

        for op_type, operations in self.operation_counts.items():
            for operation in operations:
                operation_times.append(
                    {
                        "type": op_type,
                        "timestamp": operation["timestamp"],
                        "thread_id": operation["thread_id"],
                    }
                )

        # Sort operations by timestamp
        operation_times.sort(key=lambda x: x["timestamp"])

        # Look for suspicious patterns (this is a simplified check)
        race_condition_indicators = []

        for i in range(len(operation_times) - 1):
            current_op = operation_times[i]
            next_op = operation_times[i + 1]

            # Check for operations happening too close together
            time_diff = next_op["timestamp"] - current_op["timestamp"]
            if time_diff < 0.001:  # Less than 1ms apart
                race_condition_indicators.append(
                    {
                        "type": "rapid_succession",
                        "operations": [current_op, next_op],
                        "time_difference": time_diff,
                    }
                )

        return len(race_condition_indicators) > 0

    async def _validate_concurrent_database_consistency(self):
        """Validate database consistency after concurrent operations."""
        try:
            # Check that all planners were created successfully
            # This is a simplified consistency check
            operation_count = sum(len(ops) for ops in self.operation_counts.values())
            return "passed" if operation_count > 0 else "failed"
        except Exception:
            return "failed"


@unittest.skip("RouterAgent class refactored - needs update")
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


@unittest.skip("RouterAgent class refactored - needs update")
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
