"""
Integration tests for MCP (Model Context Protocol) server connectivity.

These tests verify that MCP servers can be connected to and tools discovered.
Run with: pytest tests/integration/test_mcp_connection.py -v
Or standalone: python tests/integration/test_mcp_connection.py
"""

import unittest
import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import patch

# Add backend src to path for standalone execution
backend_root = Path(__file__).parent.parent.parent
if backend_root.name == "tests":
    backend_root = backend_root.parent
sys.path.insert(0, str(backend_root / "src"))

from agent.core.mcp_client import get_mcp_manager, MCPClientManager
from agent.config.settings import settings
from agent.config.mcp_config import load_mcp_config


class TestMCPConnection(unittest.IsolatedAsyncioTestCase):
    """Integration tests for MCP server connections."""
    
    async def asyncSetUp(self):
        """Set up test environment."""
        # Reset the global MCP manager for each test
        import agent.core.mcp_client as mcp_module
        mcp_module._mcp_manager = None
        
    async def asyncTearDown(self):
        """Clean up after tests."""
        # Reset the global MCP manager
        import agent.core.mcp_client as mcp_module
        if mcp_module._mcp_manager:
            # Disconnect all servers
            for server in list(mcp_module._mcp_manager.clients.keys()):
                await mcp_module._mcp_manager.disconnect(server)
            mcp_module._mcp_manager = None
    
    async def test_mcp_manager_initialisation(self):
        """Test that MCP manager can be initialised."""
        manager = await get_mcp_manager()
        self.assertIsInstance(manager, MCPClientManager)
        
        # Second call should return same instance (singleton)
        manager2 = await get_mcp_manager()
        self.assertIs(manager, manager2)
    
    async def test_mcp_configuration_loading(self):
        """Test that MCP configuration loads correctly."""
        config = load_mcp_config()
        self.assertIsNotNone(config)
        
        # Check that configuration has expected structure
        self.assertTrue(hasattr(config, 'servers'))
        self.assertTrue(hasattr(config, 'router_enabled'))
        self.assertTrue(hasattr(config, 'planner_enabled'))
        self.assertTrue(hasattr(config, 'worker_enabled'))
    
    @unittest.skipUnless(
        os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN"),
        "Skipping GitHub MCP test - GITHUB_PERSONAL_ACCESS_TOKEN not set"
    )
    async def test_github_mcp_connection(self):
        """Test connection to GitHub MCP server (requires GITHUB_PERSONAL_ACCESS_TOKEN)."""
        # This test only runs if GITHUB_PERSONAL_ACCESS_TOKEN is available
        manager = await get_mcp_manager()
        
        # Check if GitHub server is connected
        servers = await manager.list_connected_servers()
        
        if "github" in servers:
            # If connected, verify tools are available
            tools = await manager.get_tools_for_llm()
            
            # Should have GitHub tools
            github_tools = [t for t in tools if t["function"]["name"].startswith("github__")]
            self.assertGreater(len(github_tools), 0, "Should have GitHub tools available")
            
            print(f"\n✅ GitHub MCP: Connected with {len(github_tools)} tools")
        else:
            print("\n⚠️ GitHub MCP: Not connected (check configuration)")
    
    async def test_filesystem_mcp_connection(self):
        """Test connection to filesystem MCP server."""
        # Filesystem should be enabled by default
        if os.getenv("MCP_FILESYSTEM_ENABLED", "true").lower() == "true":
            manager = await get_mcp_manager()
            
            servers = await manager.list_connected_servers()
            
            if "filesystem" in servers:
                # If connected, verify tools are available
                tools = await manager.get_tools_for_llm()
                
                # Should have filesystem tools
                fs_tools = [t for t in tools if t["function"]["name"].startswith("filesystem__")]
                self.assertGreater(len(fs_tools), 0, "Should have filesystem tools available")
                
                print(f"\n✅ Filesystem MCP: Connected with {len(fs_tools)} tools")
            else:
                print("\n⚠️ Filesystem MCP: Not connected (check configuration)")
    
    async def test_tool_discovery(self):
        """Test that tools can be discovered from connected servers."""
        manager = await get_mcp_manager()
        
        # Get all available tools
        tools = await manager.get_tools_for_llm()
        
        # Tools should be in correct format
        for tool in tools:
            self.assertIn("type", tool)
            self.assertEqual(tool["type"], "function")
            self.assertIn("function", tool)
            self.assertIn("name", tool["function"])
            self.assertIn("description", tool["function"])
            
            # Tool names should follow server__tool format
            tool_name = tool["function"]["name"]
            self.assertIn("__", tool_name, f"Tool {tool_name} should follow server__tool format")
    
    async def test_settings_integration(self):
        """Test that MCP settings integrate properly."""
        # Check MCP enablement flags
        if settings.mcp_enabled:
            config = settings.mcp_config
            self.assertIsNotNone(config)
            
            # Test convenience properties
            router_enabled = settings.mcp_router_enabled
            planner_enabled = settings.mcp_planner_enabled
            worker_enabled = settings.mcp_worker_enabled
            
            # These should be booleans
            self.assertIsInstance(router_enabled, bool)
            self.assertIsInstance(planner_enabled, bool)
            self.assertIsInstance(worker_enabled, bool)
            
            print(f"\n📋 MCP Settings:")
            print(f"  Router enabled: {router_enabled}")
            print(f"  Planner enabled: {planner_enabled}")
            print(f"  Worker enabled: {worker_enabled}")


def run_connection_diagnostics():
    """Run diagnostic tests for MCP connectivity."""
    print("\n" + "="*70)
    print("MCP CONNECTION DIAGNOSTICS")
    print("="*70 + "\n")
    
    print("📋 Environment Check:")
    print(f"  - GITHUB_PERSONAL_ACCESS_TOKEN: {'✅ Set' if os.getenv('GITHUB_PERSONAL_ACCESS_TOKEN') else '❌ Not set'}")
    print(f"  - MCP_ENABLED: {os.getenv('MCP_ENABLED', 'not set')}")
    print(f"  - MCP_FILESYSTEM_ENABLED: {os.getenv('MCP_FILESYSTEM_ENABLED', 'not set')}")
    print(f"  - MCP_ROUTER_ENABLED: {os.getenv('MCP_ROUTER_ENABLED', 'not set')}")
    
    print("\n📂 Configuration Files:")
    backend_path = Path(__file__).parent.parent.parent
    env_file = backend_path.parent / ".env"
    env_local_file = backend_path.parent / ".env.local"
    config_yaml = backend_path / "config" / "mcp_config.yaml"
    
    print(f"  - .env: {'✅ Exists' if env_file.exists() else '❌ Not found'}")
    print(f"  - .env.local: {'✅ Exists' if env_local_file.exists() else '❌ Not found'}")
    print(f"  - mcp_config.yaml: {'✅ Exists' if config_yaml.exists() else '⚠️ Not found (optional)'}")
    
    print("\n" + "-"*70)
    print("Running integration tests...\n")


if __name__ == "__main__":
    # Load environment variables for standalone execution
    from dotenv import load_dotenv
    
    backend_path = Path(__file__).parent.parent.parent
    env_path = backend_path.parent / ".env"
    env_local_path = backend_path.parent / ".env.local"
    
    if env_path.exists():
        load_dotenv(env_path)
    if env_local_path.exists():
        load_dotenv(env_local_path, override=True)
    
    # Run diagnostics
    run_connection_diagnostics()
    
    # Run tests
    unittest.main(verbosity=2)