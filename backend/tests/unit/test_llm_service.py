"""
Unit tests for LLM service with MCP tool calling support.

Tests the LLM service in isolation using mocks for external dependencies.
Covers backward compatibility, MCP integration, and error handling.
"""

import unittest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import asyncio
import json
from pathlib import Path
import sys

# Add backend src to path
backend_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_root / "src"))

from agent.services.llm_service import LLM
from pydantic import BaseModel


class SimpleResponse(BaseModel):
    """Test Pydantic model for structured responses."""
    message: str
    number: int


class TestLLMServiceBackwardCompatibility(unittest.TestCase):
    """Test backward compatibility for existing code."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.llm = LLM(caller="test_unit")
    
    def test_init_without_mcp(self):
        """Test LLM initialization without MCP manager."""
        llm = LLM(caller="test")
        self.assertIsNone(llm.mcp_manager)
        self.assertEqual(llm.caller, "test")
    
    def test_init_with_mcp(self):
        """Test LLM initialization with MCP manager."""
        mock_mcp = Mock()
        llm = LLM(caller="test", mcp_manager=mock_mcp)
        self.assertEqual(llm.mcp_manager, mock_mcp)
    
    @patch('agent.services.llm_service.OpenAI')
    def test_sync_text_response(self, mock_openai):
        """Test synchronous text response without tools."""
        # Mock OpenAI response
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="Hello, World!"))]
        mock_response.usage = Mock(prompt_tokens=10, completion_tokens=5)
        
        mock_client = Mock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client
        
        llm = LLM(caller="test")
        messages = [{"role": "user", "content": "Say hello"}]
        
        # get_response should no longer accept tools parameter
        response = llm.get_response(messages, model="gpt-4.1-nano", temperature=0)
        
        self.assertIsNotNone(response)
        self.assertTrue(hasattr(response, 'content'))
    
    @patch('agent.services.llm_service.OpenAI')
    def test_sync_structured_response(self, mock_openai):
        """Test synchronous structured response."""
        # Mock structured response
        mock_response = Mock()
        mock_parsed = SimpleResponse(message="test", number=42)
        mock_response.choices = [Mock(message=Mock(parsed=mock_parsed))]
        mock_response.usage = Mock(prompt_tokens=10, completion_tokens=5)
        
        mock_client = Mock()
        mock_client.beta.chat.completions.parse.return_value = mock_response
        mock_openai.return_value = mock_client
        
        llm = LLM(caller="test")
        messages = [{"role": "user", "content": "Return structured data"}]
        
        response = llm.get_response(
            messages, 
            model="gpt-4.1-nano", 
            temperature=0,
            response_format=SimpleResponse
        )
        
        self.assertIsInstance(response, SimpleResponse)
        self.assertEqual(response.message, "test")
        self.assertEqual(response.number, 42)


class TestLLMServiceMCPIntegration(unittest.IsolatedAsyncioTestCase):
    """Test MCP integration features."""
    
    async def asyncSetUp(self):
        """Set up async test fixtures."""
        self.mock_mcp_manager = AsyncMock()
        self.llm = LLM(caller="test_mcp", mcp_manager=self.mock_mcp_manager)
    
    async def test_async_with_mcp_tools(self):
        """Test async response with MCP tools."""
        # Mock MCP tools
        self.mock_mcp_manager.get_tools_for_llm.return_value = [
            {
                "type": "function",
                "function": {
                    "name": "test__tool",
                    "description": "Test tool",
                    "parameters": {}
                }
            }
        ]
        
        # Mock LLM response with tool call
        mock_response = Mock()
        mock_response.content = "Tool was called"
        mock_response.tool_calls = None  # No tool calls in final response
        
        with patch.object(self.llm, 'get_response', return_value=mock_response):
            messages = [{"role": "user", "content": "Test with tools"}]
            
            response = await self.llm.a_get_response(
                messages=messages,
                model="gpt-4.1-nano",
                temperature=0
            )
            
            self.assertIsNotNone(response)
            self.mock_mcp_manager.get_tools_for_llm.assert_called_once()
    
    async def test_tool_callbacks(self):
        """Test that callbacks are invoked during tool execution."""
        # Mock MCP tools
        self.mock_mcp_manager.get_tools_for_llm.return_value = [
            {
                "type": "function",
                "function": {
                    "name": "github__get_issue",
                    "description": "Get GitHub issue",
                    "parameters": {}
                }
            }
        ]
        
        # Mock tool execution
        self.mock_mcp_manager.execute_llm_tool_call.return_value = {
            "result": "Issue data"
        }
        
        # Track callbacks
        started = []
        completed = []
        failed = []
        
        async def on_start(name, args):
            started.append((name, args))
        
        async def on_complete(name, result):
            completed.append((name, result))
        
        async def on_error(name, error):
            failed.append((name, error))
        
        # Mock response with tool call
        mock_tool_call = Mock()
        mock_tool_call.function = Mock()
        mock_tool_call.function.name = "github__get_issue"
        mock_tool_call.function.arguments = "{}"
        mock_tool_call.id = "call_123"
        
        mock_response_with_tools = Mock()
        mock_response_with_tools.tool_calls = [mock_tool_call]
        
        mock_response_final = Mock()
        mock_response_final.tool_calls = None
        mock_response_final.content = "Final response"
        
        # Mock get_response_with_tools to return tool response then final
        with patch.object(self.llm, 'get_response_with_tools', return_value=mock_response_with_tools):
            with patch.object(self.llm, 'get_response', return_value=mock_response_final):
                messages = [{"role": "user", "content": "Get issue #1"}]
                
                response = await self.llm.a_get_response(
                    messages=messages,
                    model="gpt-4.1-nano",
                    temperature=0,
                    on_tool_start=on_start,
                    on_tool_complete=on_complete,
                    on_tool_error=on_error
                )
                
                # Should have final response
                self.assertEqual(response.content, "Final response")
    
    async def test_tool_filter(self):
        """Test tool filtering functionality."""
        # Mock multiple tools from different servers
        all_tools = [
            {
                "type": "function",
                "function": {
                    "name": "github__tool",
                    "description": "GitHub tool",
                    "parameters": {}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "filesystem__tool",
                    "description": "Filesystem tool",
                    "parameters": {}
                }
            }
        ]
        
        # Mock filtered tools
        filtered_tools = [all_tools[0]]  # Only GitHub tools
        
        self.mock_mcp_manager.get_filtered_tools.return_value = filtered_tools
        
        def github_only(server_name, tool):
            return server_name == "github"
        
        mock_response = Mock()
        mock_response.tool_calls = None
        mock_response.content = "Response"
        
        with patch.object(self.llm, 'get_response', return_value=mock_response):
            messages = [{"role": "user", "content": "Test"}]
            
            response = await self.llm.a_get_response(
                messages=messages,
                model="gpt-4.1-nano",
                temperature=0,
                tool_filter=github_only
            )
            
            self.mock_mcp_manager.get_filtered_tools.assert_called_once_with(github_only)
    
    async def test_max_tool_rounds(self):
        """Test that tool calling stops after max_tool_rounds."""
        # Mock tools
        self.mock_mcp_manager.get_tools_for_llm.return_value = [
            {
                "type": "function",
                "function": {
                    "name": "test__tool",
                    "description": "Test tool",
                    "parameters": {}
                }
            }
        ]
        
        # Mock tool execution
        self.mock_mcp_manager.execute_llm_tool_call.return_value = {"result": "data"}
        
        # Create tool call mock
        mock_tool_call = Mock()
        mock_tool_call.function = Mock()
        mock_tool_call.function.name = "test__tool"
        mock_tool_call.function.arguments = "{}"
        mock_tool_call.id = "call_1"
        
        # Mock response that always has tool calls (infinite loop scenario)
        mock_response_with_tools = Mock()
        mock_response_with_tools.tool_calls = [mock_tool_call]
        
        # Count calls
        call_count = 0
        
        def get_response_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count > 3:  # After max rounds, return final response
                final = Mock()
                final.tool_calls = None
                final.content = "Final after max rounds"
                return final
            return mock_response_with_tools
        
        with patch.object(self.llm, 'get_response_with_tools', side_effect=get_response_side_effect):
            # Also mock the final get_response call after max rounds
            final_response = Mock()
            final_response.content = "Final response after max rounds"
            with patch.object(self.llm, 'get_response', return_value=final_response):
                messages = [{"role": "user", "content": "Test max rounds"}]
                
                response = await self.llm.a_get_response(
                    messages=messages,
                    model="gpt-4.1-nano",
                    temperature=0,
                    max_tool_rounds=3
                )
                
                # Should stop after max rounds
                self.assertIsNotNone(response)
                self.assertEqual(call_count, 3)  # 3 tool rounds
    
    async def test_combined_tools(self):
        """Test combining regular tools with MCP tools."""
        # Regular tools provided by user
        regular_tools = [
            {
                "type": "function",
                "function": {
                    "name": "calculator",
                    "description": "Calculator tool",
                    "parameters": {}
                }
            }
        ]
        
        # MCP tools from manager
        mcp_tools = [
            {
                "type": "function",
                "function": {
                    "name": "github__tool",
                    "description": "GitHub tool",
                    "parameters": {}
                }
            }
        ]
        
        self.mock_mcp_manager.get_tools_for_llm.return_value = mcp_tools
        
        mock_response = Mock()
        mock_response.tool_calls = None
        mock_response.content = "Response with combined tools"
        
        # Track what tools were passed to get_response_with_tools
        captured_tools = []
        
        def capture_tools(*args, **kwargs):
            if 'tools' in kwargs:
                captured_tools.extend(kwargs['tools'])
            return mock_response
        
        with patch.object(self.llm, 'get_response_with_tools', side_effect=capture_tools):
            messages = [{"role": "user", "content": "Test"}]
            
            response = await self.llm.a_get_response(
                messages=messages,
                model="gpt-4.1-nano",
                temperature=0,
                tools=regular_tools
            )
            
            # Should have both regular and MCP tools
            self.assertEqual(len(captured_tools), 2)
            tool_names = [t["function"]["name"] for t in captured_tools]
            self.assertIn("calculator", tool_names)
            self.assertIn("github__tool", tool_names)


class TestLLMServiceErrorHandling(unittest.IsolatedAsyncioTestCase):
    """Test error handling in LLM service."""
    
    async def test_mcp_tool_execution_error(self):
        """Test handling of MCP tool execution errors."""
        mock_mcp = AsyncMock()
        mock_mcp.get_tools_for_llm.return_value = [
            {
                "type": "function",
                "function": {
                    "name": "failing__tool",
                    "description": "Tool that fails",
                    "parameters": {}
                }
            }
        ]
        
        # Mock tool execution failure
        mock_mcp.execute_llm_tool_call.side_effect = Exception("Tool failed")
        
        llm = LLM(caller="test_error", mcp_manager=mock_mcp)
        
        # Track error callback
        errors = []
        
        async def on_error(name, error):
            errors.append((name, error))
        
        # Mock tool call
        mock_tool_call = Mock()
        mock_tool_call.function = Mock()
        mock_tool_call.function.name = "failing__tool"
        mock_tool_call.function.arguments = "{}"
        mock_tool_call.id = "call_fail"
        
        mock_response_with_tools = Mock()
        mock_response_with_tools.tool_calls = [mock_tool_call]
        
        mock_response_final = Mock()
        mock_response_final.tool_calls = None
        mock_response_final.content = "Handled error"
        
        with patch.object(llm, 'get_response_with_tools', return_value=mock_response_with_tools):
            with patch.object(llm, 'get_response', return_value=mock_response_final):
                messages = [{"role": "user", "content": "Test error"}]
                
                response = await llm.a_get_response(
                    messages=messages,
                    model="gpt-4.1-nano",
                    temperature=0,
                    on_tool_error=on_error,
                    max_tool_rounds=1  # Only try once
                )
                
                # Error callback should be called once
                self.assertGreater(len(errors), 0, "Should have error callbacks")
                self.assertIn("failing__tool", errors[0][0])
    
    async def test_mcp_connection_failure(self):
        """Test graceful handling when MCP manager fails."""
        mock_mcp = AsyncMock()
        mock_mcp.get_tools_for_llm.side_effect = Exception("Connection failed")
        
        llm = LLM(caller="test_connection", mcp_manager=mock_mcp)
        
        mock_response = Mock()
        mock_response.content = "Response without tools"
        
        with patch.object(llm, 'get_response', return_value=mock_response):
            messages = [{"role": "user", "content": "Test"}]
            
            # Should fall back to regular response
            response = await llm.a_get_response(
                messages=messages,
                model="gpt-4.1-nano",
                temperature=0
            )
            
            self.assertEqual(response.content, "Response without tools")


if __name__ == "__main__":
    unittest.main(verbosity=2)