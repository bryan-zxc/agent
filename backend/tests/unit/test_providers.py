"""
Unit tests for LLM providers with real API calls.

These tests directly test provider methods without going through the LLM service layer.
They are marked with @pytest.mark.llm_live and skipped by default.

Run with: pytest -m llm_live to execute these tests.
Or specifically: pytest backend/tests/unit/test_providers.py -m llm_live -v
"""

import pytest
import asyncio
import json
import sys
from pathlib import Path
from pydantic import BaseModel, Field
import logging

# Add backend src to path
backend_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_root / "src"))

from agent.services.llm.providers import (
    OpenAIProvider,
    AnthropicProvider,
    GoogleProvider,
)
from agent.services.llm.base import RequestType
from agent.core.mcp_client import get_mcp_manager
from agent.config.settings import settings

logger = logging.getLogger(__name__)


# =============================================================================
# Test Models
# =============================================================================


class SimpleAnswer(BaseModel):
    """Simple Pydantic model for structured response testing."""

    answer: str = Field(description="The answer to the question")


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def mcp_tools():
    """Get real MCP tools once for all tests."""
    mcp_manager = await get_mcp_manager()

    # Get all available tools
    all_tools = await mcp_manager.get_tools_for_llm()

    # Filter to just filesystem tools for testing
    filesystem_tools = [
        tool
        for tool in all_tools
        if tool.get("function", {}).get("name", "").startswith("filesystem__")
    ]

    # Find the write_file tool specifically
    write_file_tool = None
    for tool in filesystem_tools:
        if "write" in tool["function"]["name"].lower():
            write_file_tool = tool
            break

    if not write_file_tool:
        # Fallback if no write tool found
        write_file_tool = filesystem_tools[0] if filesystem_tools else None

    return write_file_tool


# =============================================================================
# OpenAI Provider Tests
# =============================================================================


@pytest.mark.llm_live
class TestOpenAIProviderUnit:
    """Test OpenAI provider methods directly."""

    @pytest.fixture
    def provider(self):
        """Create OpenAI provider instance."""
        return OpenAIProvider(api_key=settings.openai_api_key, caller="test")

    async def test_text_response(self, provider, verify_cost_tracking):
        """Test simple text response."""
        messages = [{"role": "user", "content": "What is 2+2?"}]

        response = provider.text_response(
            messages=messages,
            model="gpt-5-nano",
            temperature=0,
            system_instruction="Answer concisely.",
        )

        assert response is not None
        assert isinstance(response, str)
        assert "4" in response or "four" in response.lower()

        # Verify cost tracking is working (minimal check)
        await asyncio.sleep(1.0)  # Wait for fire-and-forget tracking
        assert await verify_cost_tracking("test"), "Cost tracking should record usage"

    async def test_structured_response_pydantic(self, provider):
        """Test Pydantic model response."""
        messages = [{"role": "user", "content": "What is 2+2?"}]

        response = provider.structured_response(
            messages=messages,
            model="gpt-5-nano",
            temperature=0,
            response_format=SimpleAnswer,
        )

        assert response is not None
        assert isinstance(response, SimpleAnswer)
        assert "4" in response.answer or "four" in response.answer.lower()

    async def test_structured_response_json(self, provider):
        """Test JSON mode response."""
        messages = [
            {"role": "user", "content": "Return JSON with name='test' and value=123"}
        ]

        response = provider.structured_response(
            messages=messages, model="gpt-5-nano", temperature=0, response_format="json"
        )

        assert response is not None
        assert isinstance(response, str), "JSON mode should return string"
        parsed = json.loads(response)
        assert isinstance(parsed, dict)
        assert "name" in parsed or "value" in parsed

    async def test_tools_response_websearch_only(self, provider):
        """Test with web search only."""
        messages = [
            {"role": "user", "content": "How do I update a web app to TypeScript 5.5?"}
        ]

        response = provider.tools_response(
            messages=messages,
            model="gpt-5-nano",
            temperature=0,
            tools=[],
            enable_web_search=True,
        )

        assert response is not None
        assert isinstance(response, dict)
        assert "content" in response
        assert response["content"] is not None
        # Check for the specific pattern in content
        assert response["content"].startswith("Tool web_search"), \
            f"Response should start with 'Tool web_search' but got: {response['content'][:100]}"

    async def test_tools_response_tools_only(self, provider, mcp_tools):
        """Test with MCP tools only."""
        messages = [{"role": "user", "content": "Write 'test' to /tmp/file.md"}]

        # Use real MCP tool
        tools = [mcp_tools] if mcp_tools else []

        response = provider.tools_response(
            messages=messages,
            model="gpt-5-nano",
            temperature=0,
            tools=tools,
            enable_web_search=False,
        )

        assert response is not None
        assert isinstance(response, dict)
        assert "tool_calls" in response or "content" in response

    async def test_tools_response_mixed(self, provider, mcp_tools):
        """Test with both web search and MCP tools."""
        messages = [
            {
                "role": "user",
                "content": "Search for TypeScript 5.5 info and write to /tmp/ts.md",
            }
        ]

        # Use real MCP tool
        tools = [mcp_tools] if mcp_tools else []

        response = provider.tools_response(
            messages=messages,
            model="gpt-5-nano",
            temperature=0,
            tools=tools,
            enable_web_search=True,
        )

        assert response is not None
        assert isinstance(response, dict)
        assert "content" in response
        # With web search enabled, content should contain Tool web_search
        if response["content"]:
            assert "Tool web_search" in response["content"], \
                f"Response should contain 'Tool web_search' but got: {response['content'][:200]}"


# =============================================================================
# Anthropic Provider Tests
# =============================================================================


@pytest.mark.llm_live
class TestAnthropicProviderUnit:
    """Test Anthropic provider methods directly."""

    @pytest.fixture
    def provider(self):
        """Create Anthropic provider instance."""
        return AnthropicProvider(api_key=settings.anthropic_api_key, caller="test")

    async def test_text_response(self, provider, verify_cost_tracking):
        """Test simple text response."""
        messages = [{"role": "user", "content": "What is 2+2?"}]

        response = provider.text_response(
            messages=messages,
            model="sonnet-4",
            temperature=0,
            system_instruction="Answer concisely.",
        )

        assert response is not None
        assert isinstance(response, str)
        assert "4" in response or "four" in response.lower()

        # Verify cost tracking is working (minimal check)
        await asyncio.sleep(1.0)  # Wait for fire-and-forget tracking
        assert await verify_cost_tracking("test"), "Cost tracking should record usage"

    async def test_structured_response_pydantic(self, provider):
        """Test Pydantic model response."""
        messages = [{"role": "user", "content": "What is 2+2?"}]

        response = provider.structured_response(
            messages=messages,
            model="sonnet-4",
            temperature=0,
            response_format=SimpleAnswer,
        )

        assert response is not None
        assert isinstance(response, SimpleAnswer)
        assert "4" in response.answer or "four" in response.answer.lower()

    async def test_structured_response_json(self, provider):
        """Test JSON mode response."""
        messages = [
            {"role": "user", "content": "Return JSON with name='test' and value=123"}
        ]

        response = provider.structured_response(
            messages=messages, model="sonnet-4", temperature=0, response_format="json"
        )

        assert response is not None
        assert isinstance(response, str), "JSON mode should return string"
        parsed = json.loads(response)
        assert isinstance(parsed, dict)
        assert "name" in parsed or "value" in parsed

    async def test_tools_response_websearch_only(self, provider):
        """Test with Anthropic native web search."""
        messages = [
            {"role": "user", "content": "How do I update a web app to TypeScript 5.5?"}
        ]

        response = provider.tools_response(
            messages=messages,
            model="sonnet-4",
            temperature=0,
            tools=[],
            enable_web_search=True,
        )

        assert response is not None
        assert isinstance(response, dict)
        assert "content" in response
        assert response["content"] is not None
        
        # Check for the specific pattern in content
        # Anthropic can return either string or list depending on number of searches
        content = response["content"]
        if isinstance(content, str):
            assert content.startswith("Tool web_search"), \
                f"Response should start with 'Tool web_search' but got: {content[:100]}"
        elif isinstance(content, list):
            # For multiple searches, check that at least one contains the prefix
            assert len(content) > 0, "Content list should not be empty"
            has_web_search = any(
                "Tool web_search" in (block.get("text", "") if isinstance(block, dict) else str(block))
                for block in content
            )
            assert has_web_search, \
                f"At least one content block should contain 'Tool web_search' but got: {content}"

    async def test_tools_response_tools_only(self, provider, mcp_tools):
        """Test with MCP tools only."""
        messages = [{"role": "user", "content": "Write 'test' to /tmp/file.md"}]

        # Use real MCP tool
        tools = [mcp_tools] if mcp_tools else []

        response = provider.tools_response(
            messages=messages,
            model="sonnet-4",
            temperature=0,
            tools=tools,
            enable_web_search=False,
        )

        assert response is not None
        assert "tool_calls" in response or "filesystem" in str(response).lower()

    async def test_tools_response_mixed(self, provider, mcp_tools):
        """Test with both web search and MCP tools."""
        messages = [
            {
                "role": "user",
                "content": "Search for TypeScript 5.5 info and write to /tmp/ts.md",
            }
        ]

        # Use real MCP tool
        tools = [mcp_tools] if mcp_tools else []

        response = provider.tools_response(
            messages=messages,
            model="sonnet-4",
            temperature=0,
            tools=tools,
            enable_web_search=True,
        )

        assert response is not None
        assert isinstance(response, dict)
        assert "content" in response
        # With web search enabled, content should contain Tool web_search
        if response["content"]:
            content = response["content"]
            # Handle both string and list of content blocks
            if isinstance(content, str):
                assert "Tool web_search" in content, \
                    f"Response should contain 'Tool web_search' but got: {content[:200]}"
            elif isinstance(content, list):
                # For multiple searches, check that at least one contains the prefix
                has_web_search = any(
                    "Tool web_search" in (block.get("text", "") if isinstance(block, dict) else str(block))
                    for block in content
                )
                assert has_web_search, \
                    f"At least one content block should contain 'Tool web_search' but got: {content}"


# =============================================================================
# Google Provider Tests
# =============================================================================


@pytest.mark.llm_live
class TestGoogleProviderUnit:
    """Test Google provider methods directly."""

    @pytest.fixture
    def provider(self):
        """Create Google provider instance."""
        return GoogleProvider(api_key=settings.gemini_api_key, caller="test")

    async def test_text_response(self, provider, verify_cost_tracking):
        """Test simple text response."""
        messages = [{"role": "user", "content": "What is 2+2?"}]

        response = provider.text_response(
            messages=messages,
            model="gemini-2.5-pro",
            temperature=0,
            system_instruction="Answer concisely.",
        )

        assert response is not None
        assert isinstance(response, str)
        assert "4" in response or "four" in response.lower()

        # Verify cost tracking is working (minimal check)
        await asyncio.sleep(1.0)  # Wait for fire-and-forget tracking
        assert await verify_cost_tracking("test"), "Cost tracking should record usage"

    async def test_structured_response_pydantic(self, provider):
        """Test Pydantic model response."""
        messages = [{"role": "user", "content": "What is 2+2?"}]

        response = provider.structured_response(
            messages=messages,
            model="gemini-2.5-pro",
            temperature=0,
            response_format=SimpleAnswer,
        )

        assert response is not None
        assert isinstance(response, SimpleAnswer)
        assert "4" in response.answer or "four" in response.answer.lower()

    async def test_structured_response_json(self, provider):
        """Test JSON mode response."""
        messages = [
            {"role": "user", "content": "Return JSON with name='test' and value=123"}
        ]

        response = provider.structured_response(
            messages=messages,
            model="gemini-2.5-pro",
            temperature=0,
            response_format="json",
        )

        assert response is not None
        assert isinstance(response, str), "JSON mode should return string"
        parsed = json.loads(response)
        assert isinstance(parsed, dict)
        assert "name" in parsed or "value" in parsed

    async def test_tools_response_tools_only(self, provider, mcp_tools):
        """Test with MCP tools only."""
        messages = [{"role": "user", "content": "Write 'test' to /tmp/file.md"}]

        # Use real MCP tool
        tools = [mcp_tools] if mcp_tools else []

        response = provider.tools_response(
            messages=messages,
            model="gemini-2.5-pro",
            temperature=0,
            tools=tools,
            enable_web_search=False,
        )

        assert response is not None
        assert "tool_calls" in response or "function_call" in str(response).lower()


if __name__ == "__main__":
    # Run with: python -m pytest backend/tests/unit/test_providers.py -m llm_live -v
    pytest.main([__file__, "-m", "llm_live", "-v", "--tb=short"])
