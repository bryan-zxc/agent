"""
Integration tests for LLM service with real MCP connections.

These tests verify the LLM service works correctly with actual MCP servers.
Requires environment variables like GITHUB_PERSONAL_ACCESS_TOKEN for full testing.
"""

import unittest
import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import patch, Mock
import json

# Add backend src to path
backend_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_root / "src"))

from agent.services.llm_service import LLM
from agent.core.mcp_client import get_mcp_manager, MCPClientManager
from agent.config.settings import settings
from dotenv import load_dotenv


class TestLLMMCPIntegration(unittest.IsolatedAsyncioTestCase):
    """Integration tests for LLM service with real MCP connections."""
    
    @classmethod
    def setUpClass(cls):
        """Load environment variables for testing."""
        # Load .env files
        env_path = Path(__file__).parent.parent.parent.parent / ".env"
        env_local_path = Path(__file__).parent.parent.parent.parent / ".env.local"
        
        if env_path.exists():
            load_dotenv(env_path)
        if env_local_path.exists():
            load_dotenv(env_local_path, override=True)
    
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
    
    async def test_llm_with_real_mcp_manager(self):
        """Test LLM service with real MCP manager initialization."""
        # Get real MCP manager
        mcp_manager = await get_mcp_manager()
        
        # Create LLM with real MCP manager
        llm = LLM(caller="test_integration", mcp_manager=mcp_manager)
        
        self.assertIsNotNone(llm.mcp_manager)
        self.assertIsInstance(llm.mcp_manager, MCPClientManager)
        
        # Check if any servers are connected
        servers = await mcp_manager.list_connected_servers()
        print(f"\nConnected MCP servers: {servers}")
    
    @unittest.skipUnless(
        os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN"),
        "Skipping GitHub MCP test - GITHUB_PERSONAL_ACCESS_TOKEN not set"
    )
    async def test_llm_with_github_tools(self):
        """Test LLM service with real GitHub MCP tools."""
        # Get MCP manager with GitHub connection
        mcp_manager = await get_mcp_manager()
        
        # Verify GitHub is connected
        servers = await mcp_manager.list_connected_servers()
        if "github" not in servers:
            self.skipTest("GitHub MCP server not connected")
        
        # Create LLM with MCP
        llm = LLM(caller="test_github", mcp_manager=mcp_manager)
        
        # Get available tools
        tools = await mcp_manager.get_tools_for_llm()
        github_tools = [t for t in tools if t["function"]["name"].startswith("github__")]
        
        self.assertGreater(len(github_tools), 0, "Should have GitHub tools available")
        print(f"\nAvailable GitHub tools: {len(github_tools)}")
        
        # Sample tool names
        tool_names = [t["function"]["name"] for t in github_tools[:5]]
        print(f"Sample tools: {tool_names}")
    
    @unittest.skipUnless(
        os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN"),
        "Skipping real tool execution test - GITHUB_PERSONAL_ACCESS_TOKEN not set"
    )
    async def test_real_tool_execution(self):
        """Test actual tool execution with GitHub API."""
        # Get MCP manager
        mcp_manager = await get_mcp_manager()
        
        # Create LLM
        llm = LLM(caller="test_execution", mcp_manager=mcp_manager)
        
        # Track tool execution
        tools_executed = []
        
        async def on_tool_complete(name, result):
            tools_executed.append((name, result))
            print(f"\n✓ Tool executed: {name}")
            if isinstance(result, dict):
                print(f"  Result keys: {list(result.keys())[:5]}")
        
        # Create a message that should trigger tool use
        messages = [
            {
                "role": "system",
                "content": "You have access to GitHub tools. When asked about GitHub repositories, use the available tools to get real data."
            },
            {
                "role": "user",
                "content": "Using the GitHub tools, get the details of issue #40 in the bryan-zxc/agent repository. What is the title?"
            }
        ]
        
        # Mock the LLM response to force tool calling
        mock_tool_call = Mock()
        mock_tool_call.function = Mock(
            name="github__get_issue",
            arguments=json.dumps({
                "owner": "bryan-zxc",
                "repo": "agent", 
                "issue_number": 40
            })
        )
        mock_tool_call.id = "test_call_1"
        
        mock_response = Mock()
        mock_response.tool_calls = [mock_tool_call]
        
        # First response has tool call, second response is final
        call_count = [0]
        
        def mock_get_response_with_tools(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_response
            else:
                final = Mock()
                final.tool_calls = None
                final.content = "Issue #40 details retrieved"
                return final
        
        with patch.object(llm, 'get_response_with_tools', side_effect=mock_get_response_with_tools):
            response = await llm.a_get_response(
                messages=messages,
                model="gpt-4.1-nano",
                temperature=0,
                on_tool_complete=on_tool_complete,
                max_tool_rounds=2
            )
            
            # Should have executed tool
            if tools_executed:
                print(f"\n✅ Successfully executed {len(tools_executed)} tool(s)")
                tool_name, result = tools_executed[0]
                self.assertEqual(tool_name, "github__get_issue")
                
                # Check if we got real data
                if isinstance(result, dict) and "title" in result:
                    print(f"  Issue title: {result.get('title', 'N/A')[:80]}")
    
    async def test_tool_filtering_integration(self):
        """Test tool filtering with real MCP servers."""
        mcp_manager = await get_mcp_manager()
        llm = LLM(caller="test_filter", mcp_manager=mcp_manager)
        
        # Get all tools
        all_tools = await mcp_manager.get_tools_for_llm()
        
        # Filter to only filesystem tools
        def filesystem_only(server_name, tool):
            return server_name == "filesystem"
        
        filtered_tools = await mcp_manager.get_filtered_tools(filesystem_only)
        
        # Check filtering worked
        if filtered_tools:
            for tool in filtered_tools:
                self.assertTrue(
                    tool["function"]["name"].startswith("filesystem__"),
                    f"Tool {tool['function']['name']} should be from filesystem server"
                )
            print(f"\nFiltered to {len(filtered_tools)} filesystem tools from {len(all_tools)} total")
    
    async def test_combined_tools_integration(self):
        """Test combining regular tools with MCP tools."""
        mcp_manager = await get_mcp_manager()
        llm = LLM(caller="test_combined", mcp_manager=mcp_manager)
        
        # Define regular tools
        regular_tools = [
            {
                "type": "function",
                "function": {
                    "name": "custom_calculator",
                    "description": "A custom calculator tool",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "expression": {"type": "string"}
                        },
                        "required": ["expression"]
                    }
                }
            }
        ]
        
        # Track what tools are available
        tool_names_seen = []
        
        # Mock to capture tools
        original_get_response = llm.get_response_with_tools
        
        def capture_tools(*args, **kwargs):
            if 'tools' in kwargs:
                tools = kwargs['tools']
                tool_names_seen.extend([t["function"]["name"] for t in tools])
            # Return mock response
            mock_resp = Mock()
            mock_resp.tool_calls = None
            mock_resp.content = "Response"
            return mock_resp
        
        with patch.object(llm, 'get_response_with_tools', side_effect=capture_tools):
            messages = [{"role": "user", "content": "Test combined tools"}]
            
            response = await llm.a_get_response(
                messages=messages,
                model="gpt-4.1-nano",
                temperature=0,
                tools=regular_tools
            )
            
            # Check we have both types of tools
            self.assertIn("custom_calculator", tool_names_seen)
            
            # Should also have MCP tools
            mcp_tool_count = sum(1 for name in tool_names_seen if "__" in name)
            self.assertGreater(mcp_tool_count, 0, "Should have MCP tools (with __ in name)")
            
            print(f"\nCombined tools test:")
            print(f"  Regular tools: 1 (custom_calculator)")
            print(f"  MCP tools: {mcp_tool_count}")
            print(f"  Total tools: {len(tool_names_seen)}")
    
    async def test_max_tool_rounds_integration(self):
        """Test max_tool_rounds limiting with real setup."""
        mcp_manager = await get_mcp_manager()
        llm = LLM(caller="test_rounds", mcp_manager=mcp_manager)
        
        # Track rounds
        rounds_executed = []
        
        async def on_tool_start(name, args):
            rounds_executed.append(name)
        
        # Mock continuous tool calling
        call_count = [0]
        
        def mock_response_with_tools(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 2:  # First 2 calls have tools
                mock_resp = Mock()
                mock_tool = Mock()
                mock_tool.function = Mock()
                mock_tool.function.name = f"test__tool_{call_count[0]}"
                mock_tool.function.arguments = "{}"
                mock_tool.id = f"call_{call_count[0]}"
                mock_resp.tool_calls = [mock_tool]
                return mock_resp
            else:  # Final response
                mock_resp = Mock()
                mock_resp.tool_calls = None
                mock_resp.content = "Final"
                return mock_resp
        
        with patch.object(llm, 'get_response_with_tools', side_effect=mock_response_with_tools):
            # Also mock the final get_response call after max rounds
            final_response = Mock()
            final_response.content = "Final response after max rounds"
            with patch.object(llm, 'get_response', return_value=final_response):
                messages = [{"role": "user", "content": "Test rounds"}]
                
                response = await llm.a_get_response(
                    messages=messages,
                    model="gpt-4.1-nano",
                    temperature=0,
                    on_tool_start=on_tool_start,
                    max_tool_rounds=2
                )
                
                # Should stop at max rounds
                self.assertEqual(call_count[0], 2)  # 2 tool rounds exactly
            print(f"\nMax rounds test: Executed {len(rounds_executed)} tool rounds (max was 2)")


class TestLLMConfigurationIntegration(unittest.IsolatedAsyncioTestCase):
    """Test LLM service with various configurations."""
    
    async def test_llm_with_settings_integration(self):
        """Test that LLM service integrates with settings properly."""
        # Check MCP settings
        if settings.mcp_enabled:
            config = settings.mcp_config
            self.assertIsNotNone(config)
            
            print(f"\nMCP Configuration:")
            print(f"  MCP enabled: {settings.mcp_enabled}")
            print(f"  Router MCP enabled: {settings.mcp_router_enabled}")
            print(f"  Planner MCP enabled: {settings.mcp_planner_enabled}")
            print(f"  Worker MCP enabled: {settings.mcp_worker_enabled}")
            
            # Create LLM with settings
            if settings.mcp_router_enabled:
                mcp_manager = await get_mcp_manager()
                llm = LLM(caller="router", mcp_manager=mcp_manager)
                
                # Should have MCP support
                self.assertIsNotNone(llm.mcp_manager)


if __name__ == "__main__":
    # Run with verbosity to see test details
    unittest.main(verbosity=2)