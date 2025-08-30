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


# ====================================================================
# MCP Testing Utilities
# ====================================================================

import os
from pathlib import Path
from unittest.mock import AsyncMock, Mock
from typing import Dict, Optional, Callable
import subprocess
import json


class MCPTestUtilities:
    """Utilities for testing MCP (Model Context Protocol) functionality."""
    
    @staticmethod
    def check_mcp_environment() -> Dict[str, bool]:
        """Check MCP-related environment variables and configuration.
        
        Returns:
            Dict with environment status for MCP testing
        """
        return {
            "github_token": bool(os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")),
            "openai_key": bool(os.getenv("OPENAI_API_KEY")),
            "anthropic_key": bool(os.getenv("ANTHROPIC_API_KEY")),
            "mcp_enabled": os.getenv("MCP_ENABLED", "true").lower() == "true",
            "mcp_filesystem": os.getenv("MCP_FILESYSTEM_ENABLED", "true").lower() == "true",
            "mcp_router": os.getenv("MCP_ROUTER_ENABLED", "false").lower() == "true",
            "mcp_planner": os.getenv("MCP_PLANNER_ENABLED", "false").lower() == "true",
            "mcp_worker": os.getenv("MCP_WORKER_ENABLED", "false").lower() == "true",
        }
    
    @staticmethod
    def check_node_availability() -> bool:
        """Check if Node.js ecosystem is available for MCP servers.
        
        Returns:
            True if Node.js, npm, and npx are available
        """
        commands = ["node", "npm", "npx"]
        for cmd in commands:
            try:
                result = subprocess.run(
                    ["which", cmd], 
                    capture_output=True, 
                    text=True, 
                    timeout=2
                )
                if result.returncode != 0:
                    return False
            except (subprocess.SubprocessError, FileNotFoundError):
                return False
        return True
    
    @staticmethod
    def run_mcp_diagnostics() -> str:
        """Run comprehensive MCP diagnostics and return formatted report.
        
        Returns:
            Formatted diagnostic report string
        """
        report = []
        report.append("=" * 60)
        report.append("MCP CONNECTIVITY DIAGNOSTICS")
        report.append("=" * 60)
        
        # Check environment
        env_status = MCPTestUtilities.check_mcp_environment()
        report.append("\n📋 Environment Variables:")
        for key, value in env_status.items():
            status = "✅" if value else "❌"
            report.append(f"  {key}: {status}")
        
        # Check Node.js
        node_available = MCPTestUtilities.check_node_availability()
        report.append(f"\n🔧 Node.js Ecosystem: {'✅ Available' if node_available else '❌ Not available'}")
        
        # Check configuration files
        report.append("\n📂 Configuration Files:")
        backend_path = Path(__file__).parent.parent
        config_files = {
            ".env": backend_path.parent / ".env",
            ".env.local": backend_path.parent / ".env.local",
            "mcp_config.yaml": backend_path / "config" / "mcp_config.yaml",
        }
        
        for name, path in config_files.items():
            status = "✅ Exists" if path.exists() else "❌ Not found"
            report.append(f"  {name}: {status}")
        
        return "\n".join(report)


def create_mock_mcp_manager(
    tools: Optional[list] = None,
    connected_servers: Optional[list] = None
) -> AsyncMock:
    """Create a mock MCP manager for testing.
    
    Args:
        tools: List of tools to return from get_tools_for_llm
        connected_servers: List of server names to return from list_connected_servers
    
    Returns:
        Configured AsyncMock MCP manager
    """
    mock_manager = AsyncMock()
    
    # Default tools if none provided
    if tools is None:
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "test__mock_tool",
                    "description": "Mock tool for testing",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "test_param": {"type": "string"}
                        },
                        "required": ["test_param"]
                    }
                }
            }
        ]
    
    # Default connected servers
    if connected_servers is None:
        connected_servers = ["test_server"]
    
    # Configure mock methods
    mock_manager.get_tools_for_llm.return_value = tools
    mock_manager.list_connected_servers.return_value = connected_servers
    mock_manager.execute_llm_tool_call.return_value = {"result": "Mock result"}
    
    # Add filtering support
    async def get_filtered_tools(filter_func):
        filtered = []
        for server in connected_servers:
            for tool in tools:
                if filter_func(server, tool):
                    filtered.append(tool)
        return filtered
    
    mock_manager.get_filtered_tools.side_effect = get_filtered_tools
    
    return mock_manager


def create_mock_tool_response(
    tool_name: str,
    tool_id: str = "call_123",
    arguments: Optional[Dict] = None
) -> Mock:
    """Create a mock LLM response with tool calls.
    
    Args:
        tool_name: Name of the tool being called
        tool_id: ID for the tool call
        arguments: Arguments for the tool call
    
    Returns:
        Mock response object with tool_calls
    """
    if arguments is None:
        arguments = {}
    
    mock_tool_call = Mock()
    mock_tool_call.function = Mock(
        name=tool_name,
        arguments=json.dumps(arguments) if isinstance(arguments, dict) else arguments
    )
    mock_tool_call.id = tool_id
    
    mock_response = Mock()
    mock_response.tool_calls = [mock_tool_call]
    mock_response.content = None
    
    return mock_response


def create_mock_text_response(content: str) -> Mock:
    """Create a mock LLM text response without tool calls.
    
    Args:
        content: Text content of the response
    
    Returns:
        Mock response object without tool_calls
    """
    mock_response = Mock()
    mock_response.tool_calls = None
    mock_response.content = content
    
    return mock_response


class MCPTestCase(AsyncTestCase):
    """Extended test case with MCP-specific helpers."""
    
    async def asyncSetUp(self):
        """Set up MCP test environment."""
        await super().asyncSetUp()
        
        # Reset global MCP manager for clean state
        import agent.core.mcp_client as mcp_module
        mcp_module._mcp_manager = None
        
        # Store environment status
        self.mcp_env = MCPTestUtilities.check_mcp_environment()
    
    async def asyncTearDown(self):
        """Clean up MCP test environment."""
        # Clean up MCP manager
        import agent.core.mcp_client as mcp_module
        if mcp_module._mcp_manager:
            for server in list(mcp_module._mcp_manager.clients.keys()):
                await mcp_module._mcp_manager.disconnect(server)
            mcp_module._mcp_manager = None
        
        await super().asyncTearDown()
    
    def require_mcp_environment(self, *required_vars):
        """Skip test if required MCP environment variables are not set.
        
        Args:
            *required_vars: Variable names to check (e.g., 'github_token', 'openai_key')
        """
        missing = []
        for var in required_vars:
            if var in self.mcp_env and not self.mcp_env[var]:
                missing.append(var)
        
        if missing:
            self.skipTest(f"Required MCP environment not set: {', '.join(missing)}")
    
    def create_test_mcp_manager(self, **kwargs) -> AsyncMock:
        """Create a mock MCP manager with test defaults.
        
        Args:
            **kwargs: Arguments to pass to create_mock_mcp_manager
        
        Returns:
            Configured mock MCP manager
        """
        return create_mock_mcp_manager(**kwargs)
