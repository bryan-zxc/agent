"""
Async Testing Utilities

Helper functions and classes for testing async/await correctness in unit tests.
These utilities add runtime warning detection to existing test suites.
"""

import warnings
import unittest
from contextlib import asynccontextmanager
from typing import List, Any


class AsyncWarningCaptureMixin:
    """Mixin class to add async warning capture capabilities to test cases."""

    @asynccontextmanager
    async def capture_async_warnings(self):
        """Context manager to capture RuntimeWarnings about unawaited coroutines."""
        with warnings.catch_warnings(record=True) as warning_list:
            # Ensure RuntimeWarnings are always recorded
            warnings.simplefilter("always", RuntimeWarning)

            # Filter out common non-async warnings
            warnings.filterwarnings("ignore", module="PIL")
            warnings.filterwarnings("ignore", module="matplotlib")
            warnings.filterwarnings("ignore", module="pandas")
            warnings.filterwarnings("ignore", category=DeprecationWarning)

            yield warning_list

    def assert_no_unawaited_coroutines(self, warning_list: List[Any]) -> None:
        """Assert that no 'was never awaited' warnings were captured."""
        unawaited_warnings = [
            w for w in warning_list if "was never awaited" in str(w.message).lower()
        ]

        if unawaited_warnings:
            warning_messages = [str(w.message) for w in unawaited_warnings]
            self.fail(
                f"Found {len(unawaited_warnings)} unawaited coroutine(s):\n"
                + "\n".join(f"  - {msg}" for msg in warning_messages)
            )

    def assert_has_unawaited_coroutines(
        self, warning_list: List[Any], expected_count: int = None
    ) -> None:
        """Assert that unawaited coroutine warnings were captured (for negative testing)."""
        unawaited_warnings = [
            w for w in warning_list if "was never awaited" in str(w.message).lower()
        ]

        if not unawaited_warnings:
            self.fail("Expected unawaited coroutine warnings but none were found")

        if expected_count is not None and len(unawaited_warnings) != expected_count:
            self.fail(
                f"Expected {expected_count} unawaited coroutine warnings, "
                f"but found {len(unawaited_warnings)}"
            )

    def get_async_warnings(self, warning_list: List[Any]) -> List[str]:
        """Extract async-related warning messages from warning list."""
        async_warnings = []
        async_keywords = ["was never awaited", "coroutine", "async", "await"]

        for w in warning_list:
            message = str(w.message).lower()
            if any(keyword in message for keyword in async_keywords):
                async_warnings.append(str(w.message))

        return async_warnings


def async_warning_test(test_func):
    """Decorator to add automatic async warning detection to test methods."""

    async def wrapper(self, *args, **kwargs):
        if not hasattr(self, "capture_async_warnings"):
            raise RuntimeError(
                "async_warning_test decorator requires AsyncWarningCaptureMixin"
            )

        async with self.capture_async_warnings() as warning_list:
            result = await test_func(self, *args, **kwargs)

        # Automatically check for async warnings unless test name suggests it's expected
        if "negative" not in test_func.__name__ and "fail" not in test_func.__name__:
            self.assert_no_unawaited_coroutines(warning_list)

        return result

    return wrapper


class AsyncTestCase(unittest.IsolatedAsyncioTestCase, AsyncWarningCaptureMixin):
    """Base test case class that combines async testing with warning capture."""

    async def asyncSetUp(self):
        """Set up async test environment with warning capture."""
        await super().asyncSetUp()

        # Configure warning filters for cleaner async testing
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        warnings.filterwarnings("ignore", module="PIL")
        warnings.filterwarnings("ignore", module="matplotlib")


# Convenience functions for quick integration with existing tests
async def run_with_warning_check(async_func, *args, **kwargs):
    """Run an async function and check for unawaited coroutine warnings."""
    with warnings.catch_warnings(record=True) as warning_list:
        warnings.simplefilter("always", RuntimeWarning)

        result = await async_func(*args, **kwargs)

        # Check for async warnings
        unawaited_warnings = [
            w for w in warning_list if "was never awaited" in str(w.message).lower()
        ]

        if unawaited_warnings:
            warning_messages = [str(w.message) for w in unawaited_warnings]
            raise AssertionError(
                f"Found {len(unawaited_warnings)} unawaited coroutine(s):\n"
                + "\n".join(f"  - {msg}" for msg in warning_messages)
            )

        return result
