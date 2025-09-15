"""
Integration test for LLM service with MCP manager.

This test verifies the LLM service correctly integrates with MCP tools
and web search capabilities. Only one comprehensive test is needed.

IMPORTANT: Test Isolation Requirement
======================================
These tests MUST be run individually due to MCP stdio subprocess lifecycle issues:
- The MCP filesystem server uses stdio (stdin/stdout) communication via npx subprocess
- When pytest runs multiple tests sequentially, the stdio subprocess connection is lost
  between tests, causing "Client is not connected" errors
- This is a test-specific issue, NOT a production concern

To run tests individually:
- Single test: pytest tests/integration/test_llm_service_integration.py::TestLLMServiceIntegration::test_anthropic_mixed_tools
- All tests (will show failures): pytest -m llm_live

Production is unaffected because:
- The MCP manager singleton persists between API requests
- The stdio subprocess stays alive for the application lifetime
- Concurrent requests share the same MCP connection successfully

Run with: pytest -m llm_live to execute this test.
"""

import pytest
import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime, timezone

# Add backend src to path
backend_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_root / "src"))

from agent.services.llm_service import LLM
from agent.core.mcp_client import get_mcp_manager
from agent.config.settings import settings

import logging
logger = logging.getLogger(__name__)


@pytest.mark.llm_live
class TestLLMServiceIntegration:
    """Test LLM service integration with MCP and web search.
    
    NOTE: Run each test method individually to avoid MCP connection issues.
    The stdio subprocess connection is lost between tests when run together.
    """
    
    async def test_anthropic_mixed_tools(self, verify_cost_tracking):
        """Test Anthropic with both web search and MCP tools."""
        # Use path within MCP allowed directory (/app/files/uploads)
        test_file = "/app/files/uploads/test_anthropic_typescript.md"
        
        # Clean up any existing test file
        if os.path.exists(test_file):
            os.remove(test_file)
        
        # Get MCP manager with real tools
        mcp_manager = await get_mcp_manager()
        
        # Create LLM service with MCP support
        llm = LLM(caller="test", mcp_manager=mcp_manager)
        
        # Message that requires both web search and file writing
        messages = [
            {"role": "user", "content": f"Search for information about TypeScript 5.5 migration and write a summary to {test_file}"}
        ]
        
        # Use Anthropic model which supports both web search and MCP tools together
        model = "sonnet-4"
        
        # Execute with both capabilities enabled and system instruction
        response = await llm.a_get_response(
            messages=messages,
            model=model,
            temperature=0,
            system_instruction="You are a helpful assistant. Be concise and focus on key migration points.",
            use_tools=True,  # Enable MCP tools
            enable_web_search=True  # Enable web search
        )
        
        # Verify response exists
        assert response is not None, "Response should not be None"
        
        # Log response for debugging
        logger.info(f"Anthropic response: {response}")
        
        # Verify the file was actually created
        assert os.path.exists(test_file), f"File {test_file} should have been created"
        
        # Verify the file has content
        with open(test_file, 'r') as f:
            content = f.read()
            assert len(content) > 0, "File should not be empty"
            # Check for TypeScript-related content
            assert "typescript" in content.lower() or "5.5" in content, f"File should contain TypeScript migration information, got: {content[:200]}"
        
        # Clean up
        if os.path.exists(test_file):
            os.remove(test_file)
        
        # Verify cost tracking is working (minimal check)
        await asyncio.sleep(1.0)  # Wait for fire-and-forget tracking
        assert await verify_cost_tracking("test"), "Cost tracking should record LLM usage"
    
    async def test_google_mcp_tools_only(self, verify_cost_tracking):
        """Test Google provider with MCP tools only (no web search due to API limitation)."""
        # Use path within MCP allowed directory (/app/files/uploads)
        test_file = "/app/files/uploads/test_google.md"
        
        # Clean up any existing test file
        if os.path.exists(test_file):
            os.remove(test_file)
        
        # Get MCP manager with real tools
        mcp_manager = await get_mcp_manager()
        
        # Create LLM service with MCP support
        llm = LLM(caller="test", mcp_manager=mcp_manager)
        
        # Simple message that requires file writing (matching unit tests)
        messages = [
            {"role": "user", "content": f"Write the text 'Hello World' to the file {test_file}. Use the filesystem write_file tool."}
        ]
        
        # Use Google model
        model = "gemini-2.5-pro"
        
        # Execute with MCP tools only (no web search)
        response = await llm.a_get_response(
            messages=messages,
            model=model,
            temperature=0,
            system_instruction="You are a helpful assistant.",
            use_tools=True,  # Enable MCP tools
            enable_web_search=False  # No web search for Google
        )
        
        # Verify response exists
        assert response is not None, "Response should not be None"
        
        # Log response for debugging
        logger.info(f"Google response: {response}")
        
        # Verify the file was actually created
        assert os.path.exists(test_file), f"File {test_file} should have been created"
        
        # Verify the file has the expected content
        with open(test_file, 'r') as f:
            content = f.read()
            assert "Hello World" in content, f"File should contain 'Hello World', got: {content}"
        
        # Clean up
        if os.path.exists(test_file):
            os.remove(test_file)
        
        # Verify cost tracking
        await asyncio.sleep(1.0)
        assert await verify_cost_tracking("test"), "Cost tracking should record LLM usage"
    
    async def test_openai_mcp_tools_only(self, verify_cost_tracking):
        """Test OpenAI with MCP tools only (simplified test)."""
        # Use path within MCP allowed directory (/app/files/uploads)
        test_file = "/app/files/uploads/test_openai.md"
        
        # Clean up any existing test file
        if os.path.exists(test_file):
            os.remove(test_file)
        
        # Get MCP manager with real tools
        mcp_manager = await get_mcp_manager()
        
        # Create LLM service with MCP support
        llm = LLM(caller="test", mcp_manager=mcp_manager)
        
        # Simple message that requires file writing (same as Google test)
        messages = [
            {"role": "user", "content": f"Write the text 'Hello World' to the file {test_file}. Use the filesystem write_file tool."}
        ]
        
        # Use OpenAI model
        model = "gpt-5-mini"
        
        # Execute with MCP tools only (no web search)
        response = await llm.a_get_response(
            messages=messages,
            model=model,
            temperature=0,
            system_instruction="You are a helpful assistant.",
            use_tools=True,  # Enable MCP tools
            enable_web_search=False  # No web search
        )
        
        # Verify response exists
        assert response is not None, "Response should not be None"
        
        # Log response for debugging
        logger.info(f"OpenAI response: {response}")
        
        # Verify the file was actually created
        assert os.path.exists(test_file), f"File {test_file} should have been created"
        
        # Verify the file has the expected content
        with open(test_file, 'r') as f:
            content = f.read()
            assert "Hello World" in content, f"File should contain 'Hello World', got: {content}"
        
        # Clean up
        if os.path.exists(test_file):
            os.remove(test_file)
        
        # Verify cost tracking
        await asyncio.sleep(1.0)
        assert await verify_cost_tracking("test"), "Cost tracking should record LLM usage"


if __name__ == "__main__":
    # Run with: python -m pytest backend/tests/integration/test_llm_service_integration.py -m llm_live -v
    pytest.main([__file__, "-m", "llm_live", "-v", "--tb=short"])