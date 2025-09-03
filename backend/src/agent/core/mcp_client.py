"""
MCP Client Manager for external tool integration.

This module provides a manager for Model Context Protocol (MCP) clients,
enabling the agent system to connect to and use tools from external MCP servers.
"""

from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from typing import Dict, List, Any, Optional
import json
import logging
import subprocess
import os
from ..config.mcp_config import MCPServerDefinition

logger = logging.getLogger(__name__)


class MCPClientManager:
    """
    Manages MCP client connections to external servers.
    Handles tool discovery, formatting for LLMs, and execution.
    """
    
    def __init__(self):
        self.clients: Dict[str, Client] = {}
        self.connected: Dict[str, bool] = {}  # Track which clients are connected
        self.tool_mapping: Dict[str, Dict[str, str]] = {}  # LLM name -> {server, tool}
        self.tools_cache: Optional[List[Dict]] = None  # Cache discovered tools
    
    async def connect(self, name: str, server_config: Any) -> Client:
        """
        Connect to an MCP server.
        
        Args:
            name: Friendly name for the server (e.g., "github", "filesystem")
            server_config: Either a URL string, command list, or transport object
        
        Returns:
            Connected Client instance
        """
        client = Client(server_config)
        self.clients[name] = client
        self.connected[name] = False  # Not connected until we enter context
        logger.info(f"Created MCP client for: {name}")
        
        # Try to connect and cache tools immediately
        try:
            await self._ensure_connected(name)
            await self._cache_tools_for_server(name)
        except Exception as e:
            logger.warning(f"Initial connection to {name} failed, will retry on use: {e}")
        
        return client
    
    async def _ensure_connected(self, name: str):
        """Ensure a client is connected."""
        if not self.connected.get(name):
            client = self.clients[name]
            # Enter the context and keep the client connected
            # The __aenter__ returns the client itself, which maintains the connection
            connected_client = await client.__aenter__()
            self.connected[name] = True
            # Note: We're not exiting the context here - it stays open for the lifetime of the manager
    
    async def _cache_tools_for_server(self, name: str):
        """Cache tools from a specific server."""
        await self._ensure_connected(name)
        client = self.clients[name]
        tools = await client.list_tools()
        
        # Process and store tools
        for tool in tools:
            llm_tool_name = f"{name}__{tool.name}"
            self.tool_mapping[llm_tool_name] = {
                "server": name,
                "tool": tool.name
            }
    
    async def disconnect(self, name: str):
        """Disconnect from a specific MCP server."""
        if name in self.clients:
            # Properly exit the context if connected
            if self.connected.get(name):
                try:
                    client = self.clients[name]
                    await client.__aexit__(None, None, None)
                    logger.debug(f"Closed connection to MCP server: {name}")
                except Exception as e:
                    logger.warning(f"Error closing connection to {name}: {e}")
            
            # Clean up references
            del self.clients[name]
            if name in self.connected:
                del self.connected[name]
            
            # Clean up tool mappings for this server
            self.tool_mapping = {
                k: v for k, v in self.tool_mapping.items() 
                if v.get("server") != name
            }
            
            # Clear cache
            self.tools_cache = None
            
            logger.info(f"Disconnected from MCP server: {name}")
    
    async def get_tools_for_llm(self) -> List[Dict]:
        """
        Get all available MCP tools formatted for LLM function calling.
        Returns tools in OpenAI/Anthropic function schema format.
        """
        # Return cached tools if available
        if self.tools_cache is not None:
            return self.tools_cache
        
        llm_tools = []
        
        for server_name in list(self.clients.keys()):
            try:
                await self._ensure_connected(server_name)
                client = self.clients[server_name]
                tools = await client.list_tools()
                
                for tool in tools:
                    # Create unique name to avoid conflicts
                    llm_tool_name = f"{server_name}__{tool.name}"
                    
                    # Store mapping for execution
                    self.tool_mapping[llm_tool_name] = {
                        "server": server_name,
                        "tool": tool.name
                    }
                    
                    # Format for LLM
                    llm_tools.append({
                        "type": "function",
                        "function": {
                            "name": llm_tool_name,
                            "description": tool.description or f"Tool from {server_name}",
                            "parameters": tool.inputSchema if hasattr(tool, 'inputSchema') else {}
                        }
                    })
            except Exception as e:
                logger.error(f"Failed to get tools from {server_name}: {e}")
                continue
        
        # Cache the tools
        self.tools_cache = llm_tools
        return llm_tools
    
    async def execute_llm_tool_call(self, tool_name: str, tool_args: Dict[str, Any]) -> Any:
        """
        Execute a tool call from LLM response.
        
        Args:
            tool_name: Name of the tool to execute (e.g., "filesystem__write_file")
            tool_args: Arguments to pass to the tool
        
        Returns:
            Tool execution result
        """
        arguments = tool_args
        
        if tool_name not in self.tool_mapping:
            logger.error(f"Unknown tool requested: {tool_name}")
            return {"error": f"Unknown tool: {tool_name}"}
        
        mapping = self.tool_mapping[tool_name]
        server_name = mapping["server"]
        actual_tool_name = mapping["tool"]
        
        if server_name not in self.clients:
            logger.error(f"Server {server_name} not connected")
            return {"error": f"Server {server_name} not connected"}
        
        try:
            await self._ensure_connected(server_name)
            client = self.clients[server_name]
            result = await client.call_tool(actual_tool_name, arguments)
            logger.debug(f"Tool {tool_name} executed successfully")
            
            # Extract content from CallToolResult
            if hasattr(result, 'content') and result.content:
                # Get the first text content
                for content_item in result.content:
                    if hasattr(content_item, 'text'):
                        # Parse JSON if it's a JSON string
                        try:
                            return json.loads(content_item.text)
                        except json.JSONDecodeError:
                            return content_item.text
                    elif hasattr(content_item, 'type') and content_item.type == 'text':
                        try:
                            return json.loads(content_item.text)
                        except (json.JSONDecodeError, AttributeError):
                            return str(content_item)
            
            # Fallback to returning the raw result
            return result
        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {str(e)}")
            return {"error": str(e)}
    
    async def get_filtered_tools(self, filter_fn: callable) -> List[Dict]:
        """
        Get tools with filtering.
        
        Args:
            filter_fn: Function that receives (server_name, tool) and returns bool
        
        Returns:
            Filtered list of tools formatted for LLM
        """
        llm_tools = []
        
        for server_name in list(self.clients.keys()):
            try:
                await self._ensure_connected(server_name)
                client = self.clients[server_name]
                tools = await client.list_tools()
                
                for tool in tools:
                    # Apply filter
                    if filter_fn and not filter_fn(server_name, tool):
                        continue
                    
                    llm_tool_name = f"{server_name}__{tool.name}"
                    self.tool_mapping[llm_tool_name] = {
                        "server": server_name,
                        "tool": tool.name
                    }
                    
                    llm_tools.append({
                        "type": "function",
                        "function": {
                            "name": llm_tool_name,
                            "description": tool.description or f"Tool from {server_name}",
                            "parameters": tool.inputSchema if hasattr(tool, 'inputSchema') else {}
                        }
                    })
            except Exception as e:
                logger.error(f"Failed to get filtered tools from {server_name}: {e}")
                continue
        
        return llm_tools
    
    async def list_connected_servers(self) -> List[str]:
        """Get list of connected server names."""
        return list(self.clients.keys())


# Global instance
_mcp_manager: Optional[MCPClientManager] = None


async def get_mcp_manager() -> MCPClientManager:
    """
    Get or create the global MCP client manager with configuration.
    This ensures we have a single instance across the application.
    """
    global _mcp_manager
    if _mcp_manager is None:
        _mcp_manager = MCPClientManager()
        
        # Load and connect configured servers
        from ..config.settings import settings
        
        if settings.mcp_enabled:
            config = settings.mcp_config
            
            for server_def in config.servers:
                if not server_def.enabled:
                    continue
                
                try:
                    await _connect_mcp_server(_mcp_manager, server_def)
                    logger.info(f"Connected to MCP server: {server_def.name}")
                    
                except Exception as e:
                    logger.error(f"Failed to connect to {server_def.name}: {e}")
        
        logger.info("MCP Manager initialised")
    
    return _mcp_manager


async def _connect_mcp_server(manager: MCPClientManager, server_def: MCPServerDefinition):
    """
    Connect to an MCP server based on its definition.
    
    Args:
        manager: MCP Client Manager instance
        server_def: Server definition with connection details
    """
    if server_def.server_type == "stdio":
        # For stdio servers, construct the command with environment
        if not server_def.command:
            raise ValueError(f"stdio server {server_def.name} requires 'command'")
        
        # Create StdioTransport with explicit configuration
        # This is required for non-Python executables like npx
        transport = StdioTransport(
            command=server_def.command,
            args=server_def.args,
            env=server_def.env  # Pass environment variables directly to transport
        )
        
        # Connect with the transport object
        await manager.connect(server_def.name, transport)
        
    elif server_def.server_type in ["http", "websocket"]:
        if not server_def.url:
            raise ValueError(f"{server_def.server_type} server {server_def.name} requires 'url'")
        
        await manager.connect(server_def.name, server_def.url)
        
    else:
        raise ValueError(f"Unknown server type: {server_def.server_type}")