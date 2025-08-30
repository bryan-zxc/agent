"""
Test script for MCP Client Manager.
"""

import asyncio
import unittest
from unittest.mock import Mock, AsyncMock, patch
from src.agent.core.mcp_client import MCPClientManager, get_mcp_manager


class TestMCPClientManager(unittest.IsolatedAsyncioTestCase):
    """Test cases for MCP Client Manager."""

    async def test_mcp_manager_singleton(self):
        """Test that get_mcp_manager returns the same instance."""
        manager1 = await get_mcp_manager()
        manager2 = await get_mcp_manager()
        self.assertIs(manager1, manager2)

    async def test_connect_disconnect(self):
        """Test connecting and disconnecting from an MCP server."""
        manager = MCPClientManager()
        
        # Mock the Client class
        with patch('src.agent.core.mcp_client.Client') as mock_client_class:
            mock_client = Mock()
            mock_client_class.return_value = mock_client
            
            # Connect
            client = await manager.connect("test_server", "http://localhost:8000")
            self.assertIn("test_server", manager.clients)
            self.assertEqual(manager.clients["test_server"], mock_client)
            
            # Disconnect
            await manager.disconnect("test_server")
            self.assertNotIn("test_server", manager.clients)


    async def test_get_tools_for_llm(self):
        """Test formatting tools for LLM consumption."""
        manager = MCPClientManager()
        
        # Mock client with tools
        mock_client = AsyncMock()
        mock_tool = Mock()
        mock_tool.name = "test_tool"
        mock_tool.description = "A test tool"
        mock_tool.inputSchema = {"type": "object", "properties": {}}
        
        mock_client.list_tools.return_value = [mock_tool]
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        
        manager.clients["test_server"] = mock_client
        
        # Get tools
        tools = await manager.get_tools_for_llm()
        
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]["type"], "function")
        self.assertEqual(tools[0]["function"]["name"], "test_server__test_tool")
        self.assertEqual(tools[0]["function"]["description"], "A test tool")
        self.assertIn("test_server__test_tool", manager.tool_mapping)


    async def test_execute_llm_tool_call(self):
        """Test executing a tool call from LLM."""
        manager = MCPClientManager()
        
        # Set up mock client
        mock_client = AsyncMock()
        mock_client.call_tool.return_value = {"result": "success"}
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        
        manager.clients["test_server"] = mock_client
        manager.tool_mapping["test_server__test_tool"] = {
            "server": "test_server",
            "tool": "test_tool"
        }
        
        # Create mock tool call
        mock_tool_call = Mock()
        mock_tool_call.function.name = "test_server__test_tool"
        mock_tool_call.function.arguments = '{"param": "value"}'
        
        # Execute
        result = await manager.execute_llm_tool_call(mock_tool_call)
        
        self.assertEqual(result, {"result": "success"})
        mock_client.call_tool.assert_called_once_with("test_tool", {"param": "value"})


    async def test_execute_unknown_tool(self):
        """Test executing an unknown tool returns error."""
        manager = MCPClientManager()
        
        mock_tool_call = Mock()
        mock_tool_call.function.name = "unknown_tool"
        mock_tool_call.function.arguments = '{}'
        
        result = await manager.execute_llm_tool_call(mock_tool_call)
        
        self.assertIn("error", result)
        self.assertIn("Unknown tool", result["error"])


    async def test_get_filtered_tools(self):
        """Test getting filtered tools."""
        manager = MCPClientManager()
        
        # Mock client with multiple tools
        mock_client = AsyncMock()
        mock_tool1 = Mock()
        mock_tool1.name = "allowed_tool"
        mock_tool1.description = "Allowed"
        mock_tool1.inputSchema = {}
        
        mock_tool2 = Mock()
        mock_tool2.name = "filtered_tool"
        mock_tool2.description = "Filtered"
        mock_tool2.inputSchema = {}
        
        mock_client.list_tools.return_value = [mock_tool1, mock_tool2]
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        
        manager.clients["test_server"] = mock_client
        
        # Filter function that only allows "allowed_tool"
        def filter_fn(server_name, tool):
            return tool.name == "allowed_tool"
        
        tools = await manager.get_filtered_tools(filter_fn)
        
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]["function"]["name"], "test_server__allowed_tool")


    async def test_list_connected_servers(self):
        """Test listing connected servers."""
        manager = MCPClientManager()
        manager.clients["server1"] = Mock()
        manager.clients["server2"] = Mock()
        
        servers = await manager.list_connected_servers()
        
        self.assertEqual(len(servers), 2)
        self.assertIn("server1", servers)
        self.assertIn("server2", servers)


if __name__ == "__main__":
    unittest.main()