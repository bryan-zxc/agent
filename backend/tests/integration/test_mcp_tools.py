"""
Integration tests for MCP tools functionality.

This module contains tests for MCP (Model Context Protocol) tools integration,
including both signature verification tests (run by default) and actual tool
execution tests (marked with @pytest.mark.mcp_tools and skipped by default).

Regular tests (always run):
- Tool signature extraction from MCP manager

Expensive tests (run with pytest -m mcp_tools):
- PDF extraction from financial documents
- Google web search functionality

Run all tests: pytest tests/integration/test_mcp_tools.py -m mcp_tools
Run only signature tests: pytest tests/integration/test_mcp_tools.py
"""

import pytest
import asyncio
import json
import sys
from pathlib import Path
import logging

# Add backend src to path
backend_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_root / "src"))

from agent.core.mcp_client import get_mcp_manager
from agent.config.settings import settings
from agent.utils.tools import (
    google_search,  # This is the MCP-wrapped FunctionTool
    get_facts_from_pdf,  # This is the MCP-wrapped FunctionTool
    GOOGLE_SEARCH_DOC,
    GET_FACTS_FROM_PDF_DOC,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Test Configuration
# =============================================================================

# Path to test PDFs
TEST_PDF_PATH = Path(__file__).parent.parent / "experimental" / "Financial_year_statement_Zheyu_YE_091_2024-07-01_2025-06-30.pdf"


# =============================================================================
# Regular Tests (Run by Default)
# =============================================================================

@pytest.mark.asyncio
async def test_mcp_tool_signatures():
    """
    Test that MCP manager correctly extracts tool descriptions and input schemas.
    
    This test verifies:
    1. Tools are discovered by MCP manager
    2. Tool descriptions match the defined constants
    3. Input schemas contain expected parameters
    
    This is a regular test that runs in CI/CD without making external API calls.
    """
    # Get MCP manager instance
    mcp_manager = await get_mcp_manager()
    
    # Get all available tools
    all_tools = await mcp_manager.get_tools_for_llm()
    
    # Find our agent_tools
    google_search_tool = None
    get_facts_tool = None
    
    for tool in all_tools:
        tool_name = tool.get("function", {}).get("name", "")
        if tool_name == "agent_tools__google_search":
            google_search_tool = tool
        elif tool_name == "agent_tools__get_facts_from_pdf":
            get_facts_tool = tool
    
    # Test google_search tool signature
    assert google_search_tool is not None, "google_search tool not found in MCP manager"
    
    # Check description matches our constant
    assert google_search_tool["function"]["description"] == GOOGLE_SEARCH_DOC, \
        "google_search description doesn't match GOOGLE_SEARCH_DOC constant"
    
    # Check input schema has query parameter
    params = google_search_tool["function"].get("parameters", {})
    assert "properties" in params, "google_search missing properties in parameters"
    assert "query" in params["properties"], "google_search missing 'query' parameter"
    assert params["properties"]["query"]["type"] == "string", "query parameter should be string type"
    
    # Test get_facts_from_pdf tool signature
    assert get_facts_tool is not None, "get_facts_from_pdf tool not found in MCP manager"
    
    # Check description matches our constant
    assert get_facts_tool["function"]["description"] == GET_FACTS_FROM_PDF_DOC, \
        "get_facts_from_pdf description doesn't match GET_FACTS_FROM_PDF_DOC constant"
    
    # Check input schema has required parameters
    params = get_facts_tool["function"].get("parameters", {})
    assert "properties" in params, "get_facts_from_pdf missing properties in parameters"
    assert "question" in params["properties"], "get_facts_from_pdf missing 'question' parameter"
    assert "pdf_source" in params["properties"], "get_facts_from_pdf missing 'pdf_source' parameter"
    
    # Check required fields
    assert "required" in params, "get_facts_from_pdf missing required field list"
    assert "question" in params["required"], "'question' should be required"
    assert "pdf_source" in params["required"], "'pdf_source' should be required"
    
    logger.info("✓ MCP tool signatures verified successfully")


# =============================================================================
# Expensive Tests (Marked for Selective Execution)
# =============================================================================

@pytest.mark.mcp_tools
@pytest.mark.asyncio
async def test_pdf_extraction_financial_data():
    """
    Test PDF extraction tool with a real financial year statement.
    
    This test:
    1. Loads a financial year statement PDF
    2. Asks for income, expenses, and net position
    3. Verifies the extracted data contains financial information
    
    Marked with @pytest.mark.mcp_tools - run with: pytest -m mcp_tools
    """
    # Skip if PDF doesn't exist
    if not TEST_PDF_PATH.exists():
        pytest.skip(f"Test PDF not found: {TEST_PDF_PATH}")
    
    # Skip if required API keys not configured
    if not settings.gemini_api_key:
        pytest.skip("Gemini API key not configured")
    
    # Call get_facts_from_pdf with financial questions
    question = "What are the total income, total expenses, and net position for this financial year?"
    
    logger.info(f"Testing PDF extraction with question: {question}")
    logger.info(f"Using PDF: {TEST_PDF_PATH.name}")
    
    # Execute the actual function (not the MCP wrapper)
    result = await get_facts_from_pdf.fn(
        question=question,
        pdf_source=str(TEST_PDF_PATH)
    )
    
    # Parse the JSON response
    assert result, "PDF extraction returned empty result"
    
    try:
        data = json.loads(result)
    except json.JSONDecodeError as e:
        pytest.fail(f"Failed to parse PDF extraction result as JSON: {e}\nResult: {result}")
    
    # Verify structure
    assert "fact_question_answer" in data, "Missing 'fact_question_answer' in response"
    assert "unanswered_questions" in data, "Missing 'unanswered_questions' in response"
    
    # Check that we got some facts
    facts = data.get("fact_question_answer", [])
    assert len(facts) > 0, "No facts extracted from PDF"
    
    # Convert all facts to a single string for easier searching
    all_facts_str = json.dumps(facts)
    
    # Check for specific financial figures
    assert "31,950" in all_facts_str or "31950" in all_facts_str, \
        "Income amount ($31,950) not found in extracted facts"
    
    assert "1,907" in all_facts_str or "1907" in all_facts_str, \
        "Expense amount ($1,907) not found in extracted facts"
    
    assert "30,042" in all_facts_str or "30042" in all_facts_str, \
        "Net position amount ($30,042) not found in extracted facts"
    
    logger.info(f"✓ Successfully extracted {len(facts)} facts from PDF")
    
    # Log any unanswered questions for debugging
    unanswered = data.get("unanswered_questions", [])
    if unanswered:
        logger.info(f"Unanswered questions: {[q.get('question') for q in unanswered]}")


@pytest.mark.mcp_tools
@pytest.mark.asyncio
async def test_google_search_typescript():
    """
    Test Google search tool with a TypeScript query.
    
    This test:
    1. Searches for "How do I update a web app to TypeScript 5.5?"
    2. Verifies the response contains TypeScript-related information
    3. Checks for proper citations and source URLs
    
    Marked with @pytest.mark.mcp_tools - run with: pytest -m mcp_tools
    """
    # Skip if required API keys not configured
    if not settings.gemini_api_key:
        pytest.skip("Gemini API key not configured")
    
    query = "How do I update a web app to TypeScript 5.5?"
    
    logger.info(f"Testing Google search with query: {query}")
    
    # Execute the actual function (not the MCP wrapper)
    result = await google_search.fn(query=query)
    
    # Verify we got a response
    assert result, "Google search returned empty result"
    assert not result.startswith("Error"), f"Google search returned error: {result}"
    
    # Convert to lowercase for checking
    result_lower = result.lower()
    
    # Check for TypeScript-related content
    assert "typescript" in result_lower, \
        "Search result doesn't mention TypeScript"
    
    # Check for version 5.5 or migration/update related content
    assert "5.5" in result or "migration" in result_lower or "update" in result_lower, \
        "Search result doesn't contain version 5.5 or migration/update information"
    
    # Check for citations/sources (common patterns)
    has_citations = (
        "http://" in result or 
        "https://" in result or 
        "source:" in result_lower or
        "according to" in result_lower or
        "[" in result  # Often used for citation markers
    )
    
    assert has_citations, "Search result doesn't contain citations or source references"
    
    # Log the full result to see what's returned
    logger.info("=" * 80)
    logger.info("FULL GOOGLE SEARCH RESULT:")
    logger.info("=" * 80)
    logger.info(result)
    logger.info("=" * 80)
    
    # Note: URL metadata table is optional - it only appears when URL context is triggered
    if "| Retrieved URL |" in result:
        logger.info("✓ Found markdown table of retrieved URLs")
    
    logger.info("✓ Google search completed successfully with TypeScript information")


# =============================================================================
# Test Runner
# =============================================================================

if __name__ == "__main__":
    # Run all tests including expensive ones
    # Usage: python -m pytest backend/tests/integration/test_mcp_tools.py -m mcp_tools -v
    pytest.main([__file__, "-m", "mcp_tools", "-v", "--tb=short"])