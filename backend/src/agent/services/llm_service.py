"""LLM service - main interface that delegates to refactored providers.

This file maintains backward compatibility while using the new modular architecture.
All internal implementation has been moved to the llm/ subfolder.
"""

import json
import logging
from typing import List, Dict, Any, Optional, Union, Type, Callable, Literal
from pathlib import Path
from pydantic import BaseModel
import httpx
from google import genai
from google.genai import types

from ..config.settings import settings
from ..config.llm_config import (
    get_provider_for_model,
    get_actual_model_name,
    validate_provider_config,
    RETRY_CONFIG,
)
from .llm.base import BaseLLMProvider, RequestType, delay_exp
from .llm.providers import OpenAIProvider, AnthropicProvider, GoogleProvider
from .llm.usage_tracker import UsageTracker

logger = logging.getLogger(__name__)

# Export constants for backward compatibility
MAX_LLM_RETRIES = RETRY_CONFIG["max_retries"]
FAIL_STRUCTURE_RESPONSE_RETRIES = RETRY_CONFIG["max_structured_retries"]

# Re-export MODEL_MAPPING for backward compatibility
MODEL_MAPPING = {
    "sonnet-4": "claude-sonnet-4-20250514",
    "gpt-5-nano": "gpt-5-nano-2025-08-07",
    "gemini-2.5-pro": "gemini-2.5-pro",
}

# Re-export PRICING for backward compatibility (loaded from config)
PRICING = {
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
    "gpt-5-nano-2025-08-07": {"input": 0.05, "output": 0.4},
    "gemini-2.5-pro": {
        "input_low": 1.25,
        "output_low": 10.0,
        "input_high": 2.50,
        "output_high": 15.0,
        "threshold": 200000,
    },
}


class LLM:
    """Main LLM service that delegates to provider implementations."""
    
    def __init__(
        self,
        db_path: Union[str, Path] = Path("/app/db/llm_usage.db"),
        caller: str = "general",
        mcp_manager=None,
    ):
        """
        Initialise the LLM service.
        
        Args:
            db_path: Database path (kept for compatibility but not used directly)
            caller: Identifier for tracking usage
            mcp_manager: Optional MCP manager for tool integration
        """
        self.caller = caller
        self.mcp_manager = mcp_manager
        self.usage_tracker = UsageTracker(caller=caller)
        
        # Store db_path for compatibility
        self.db_path = Path(db_path)
        
        # Initialise providers
        self.providers: Dict[str, BaseLLMProvider] = {}
        self._initialise_providers()
        
        # Special clients for Google-specific features
        if settings.gemini_api_key:
            self.gemini_client = genai.Client(api_key=settings.gemini_api_key)
    
    def _initialise_providers(self) -> None:
        """Initialise available LLM providers."""
        if validate_provider_config("openai", settings):
            self.providers["openai"] = OpenAIProvider(
                api_key=settings.openai_api_key,
                caller=self.caller
            )
        
        if validate_provider_config("anthropic", settings):
            self.providers["anthropic"] = AnthropicProvider(
                api_key=settings.anthropic_api_key,
                caller=self.caller
            )
        
        if validate_provider_config("google", settings):
            self.providers["google"] = GoogleProvider(
                api_key=settings.gemini_api_key,
                caller=self.caller
            )
        
        if not self.providers:
            logger.warning("No LLM providers configured. Check API keys.")
    
    def _get_provider_for_model(self, model: str) -> BaseLLMProvider:
        """Get the appropriate provider for a model."""
        provider_name = get_provider_for_model(model)
        
        if provider_name not in self.providers:
            raise ValueError(f"Provider '{provider_name}' not available for model '{model}'")
        
        return self.providers[provider_name]
    
    def get_response(
        self,
        messages: List[Dict[str, Any]],
        model: Literal["gpt-5-nano", "sonnet-4", "gemini-2.5-pro"],
        temperature: float = 0,
        response_format: Optional[Union[Type[BaseModel], Dict]] = None,
        system_instruction: Optional[str] = None,
    ):
        """Get LLM response without tools.
        
        Args:
            messages: Conversation messages
            model: Model to use
            temperature: Temperature for response generation
            response_format: Optional structured response format
            system_instruction: Optional system instruction for the model
        """
        for retry in range(FAIL_STRUCTURE_RESPONSE_RETRIES):
            try:
                provider = self._get_provider_for_model(model)
                actual_model = get_actual_model_name(model)
                
                if response_format:
                    result = provider.structured_response(
                        messages=messages,
                        model=actual_model,
                        temperature=temperature,
                        response_format=response_format,
                        system_instruction=system_instruction,
                    )
                else:
                    result = provider.text_response(
                        messages=messages,
                        model=actual_model,
                        temperature=temperature,
                        system_instruction=system_instruction,
                    )
                    # Return string directly for text responses
                
                return result
                
            except Exception as e:
                logger.error(f"Attempt {retry + 1} failed: {e}")
                if retry < FAIL_STRUCTURE_RESPONSE_RETRIES - 1:
                    delay_exp(e, retry)
                    
        logger.error(f"All {FAIL_STRUCTURE_RESPONSE_RETRIES} attempts failed")
        return None
    
    
    async def a_get_response(
        self,
        messages: List[Dict],
        model: Literal["gpt-5-nano", "sonnet-4", "gemini-2.5-pro"],
        temperature: float = 0,
        response_format: Any = None,
        use_tools: bool = False,          # NEW: Master switch for ALL tools (default: False)
        enable_web_search: bool = False,  # NEW: Enable provider-native web search
        # REMOVED: tools parameter - violates MCP-only principle
        tool_filter: Optional[Callable] = None,  # Existing: MCP tool filter
        websocket: Optional[Any] = None,  # Existing: WebSocket for status updates
    ):
        """Async LLM response with optional tool support.
        
        Args:
            messages: Conversation messages
            model: Model to use
            temperature: Temperature for response generation
            response_format: Optional structured response format
            use_tools: Master switch for ALL tools (MCP tools) - default False
            enable_web_search: Enable provider-native web search
            tool_filter: Optional filter for MCP tools
            websocket: Optional websocket for sending status updates
        """
        # Early exit if no tools
        if not use_tools:
            return self.get_response(messages, model, temperature, response_format)
        
        # Build tools list - MCP ONLY
        final_tools = []
        
        # Only load MCP tools if tools are enabled
        if use_tools and self.mcp_manager:
            try:
                if tool_filter:
                    mcp_tools = await self.mcp_manager.get_filtered_tools(tool_filter)
                else:
                    mcp_tools = await self.mcp_manager.get_tools_for_llm()
                final_tools.extend(mcp_tools)
                logger.info(f"Loaded {len(mcp_tools)} MCP tools")
            except Exception as e:
                logger.warning(f"Failed to load MCP tools: {e}")
        
        # Without tools and without web search, use sync get_response
        if not final_tools and not enable_web_search:
            return self.get_response(messages, model, temperature, response_format)
        
        # Tool-enabled flow - pass websocket and web search flag for status updates
        return await self._get_response_with_tools(
            messages=messages,
            model=model,
            temperature=temperature,
            tools=final_tools,
            enable_web_search=enable_web_search,  # Pass to providers
            websocket=websocket,
        )
    
    async def _get_response_with_tools(
        self,
        messages: List[Dict],
        model: str,
        temperature: float,
        tools: List[Dict],
        enable_web_search: bool = False,  # NEW
        websocket: Optional[Any] = None,
    ):
        """
        Execute tools and return formatted text response.
        
        Makes a single API call, executes any requested tools, and returns
        text describing what happened. No tool artifacts in the response.
        
        Args:
            messages: Conversation messages
            model: Model to use
            temperature: Temperature for response generation
            tools: List of available tools (MCP tools only)
            enable_web_search: Enable provider-native web search
            websocket: Optional websocket for sending execution status updates
        
        Returns:
            String for single tool execution, or list of content blocks for multiple tools
        """
        # Make single API call to get tool calls
        provider = self._get_provider_for_model(model)
        actual_model = get_actual_model_name(model)
        
        response = provider.tools_response(
            messages=messages,
            model=actual_model,
            temperature=temperature,
            tools=tools,
            enable_web_search=enable_web_search,  # Pass to provider
        )
        
        # If no tools requested, return the text content
        if not response or not response.get("tool_calls"):
            return response.get("content", "") if response else ""
        
        # Execute each tool and collect results
        tool_messages = []
        for tool_call in response["tool_calls"]:
            # Extract tool info (handles both OpenAI and Anthropic formats)
            if hasattr(tool_call, "function"):
                tool_name = tool_call.function.name
                try:
                    tool_args = json.loads(tool_call.function.arguments)
                except:
                    tool_args = {}
            else:
                tool_name = getattr(tool_call, "name", str(tool_call))
                tool_args = getattr(tool_call, "input", {})
            
            # Send status update via websocket
            if websocket:
                try:
                    await websocket.send_json({
                        "type": "tool_execution",
                        "tool": tool_name,
                        "status": "starting"
                    })
                except Exception as e:
                    logger.warning(f"Failed to send websocket update: {e}")
            
            # Execute tool - MCP only
            try:
                if "__" in tool_name:  # MCP tools have server prefix
                    if self.mcp_manager:
                        result = await self.mcp_manager.execute_llm_tool_call(tool_call)
                    else:
                        result = {"error": "MCP manager not available"}
                else:
                    # This should never happen with MCP-only architecture
                    result = {
                        "error": f"Non-MCP tool '{tool_name}' not allowed. "
                                f"All tools must be served through MCP (Model Context Protocol)."
                    }
                
                # Send completion status
                if websocket:
                    try:
                        await websocket.send_json({
                            "type": "tool_execution",
                            "tool": tool_name,
                            "status": "completed"
                        })
                    except:
                        pass
                
            except Exception as e:
                logger.error(f"Tool {tool_name} failed: {e}")
                result = {"error": str(e)}
                
                # Send error status
                if websocket:
                    try:
                        await websocket.send_json({
                            "type": "tool_execution",
                            "tool": tool_name,
                            "status": "error",
                            "error": str(e)
                        })
                    except:
                        pass
            
            # Format result as text
            result_text = json.dumps(result, indent=2) if isinstance(result, dict) else str(result)
            tool_messages.append(
                f"Tool {tool_name} was called and returned:\n{result_text}"
            )
        
        # Return formatted response
        if len(tool_messages) == 1:
            return tool_messages[0]  # Single tool - return string
        else:
            # Multiple tools - return list format compatible with content parameter
            return [{"type": "text", "text": msg} for msg in tool_messages]
    
    def get_response_pdf(
        self,
        pdf_source: Union[str, Path],
        prompt: str,
        temperature: float = 0,
        response_format: Optional[Type[BaseModel]] = None,
    ) -> Union[str, BaseModel]:
        """Get response from Gemini with PDF support."""
        if not str(pdf_source).lower().endswith(".pdf"):
            return "Not a pdf"
        
        if not hasattr(self, "gemini_client"):
            raise ValueError("Gemini client not initialised")
        
        model = "gemini-2.5-pro"
        
        # Get PDF data
        if isinstance(pdf_source, str) and pdf_source.startswith("http"):
            pdf_data = httpx.get(pdf_source).content
        else:
            pdf_path = Path(pdf_source)
            if not pdf_path.exists():
                raise FileNotFoundError(f"PDF not found: {pdf_path}")
            pdf_data = pdf_path.read_bytes()
        
        # Create request
        pdf_part = types.Part.from_bytes(data=pdf_data, mime_type="application/pdf")
        contents = [pdf_part, prompt]
        
        config = {"temperature": temperature}
        if response_format:
            config["response_mime_type"] = "application/json"
            config["response_schema"] = response_format
        
        try:
            response = self.gemini_client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
            
            if response_format:
                return response.parsed
            return response.text
            
        except Exception as e:
            logger.error(f"PDF processing error: {e}")
            raise
    
    def search_web(self, query: str, temperature: float = 0) -> str:
        """Web search using Google's grounding."""
        if not hasattr(self, "gemini_client"):
            raise ValueError("Gemini client not initialised")
        
        grounding_tool = types.Tool(google_search=types.GoogleSearch())
        config = types.GenerateContentConfig(
            tools=[grounding_tool],
            temperature=temperature,
        )
        
        model = "gemini-2.5-pro"
        
        try:
            response = self.gemini_client.models.generate_content(
                model=model,
                contents=query,
                config=config,
            )
            
            return add_citations(response)
            
        except Exception as e:
            logger.error(f"Web search error: {e}")
            raise
    


# Standalone helper functions for backward compatibility
def get_actual_url_from_redirect(redirect_url: str) -> str:
    """Extract actual URL from Google redirect."""
    try:
        import requests
        response = requests.get(redirect_url, allow_redirects=False, timeout=10)
        if response.status_code in [301, 302]:
            return response.headers.get("Location", redirect_url)
        return redirect_url
    except:
        return redirect_url


def add_citations(response) -> str:
    """Add citations to response text."""
    if not hasattr(response, "candidates") or not response.candidates:
        return response.text
    
    candidate = response.candidates[0]
    if not hasattr(candidate, "grounding_metadata"):
        return response.text
    
    text = response.text
    metadata = candidate.grounding_metadata
    
    if not hasattr(metadata, "grounding_supports") or not hasattr(metadata, "grounding_chunks"):
        return text
    
    supports = metadata.grounding_supports
    chunks = metadata.grounding_chunks
    
    # Sort by end_index descending to avoid position shifts
    sorted_supports = sorted(supports, key=lambda s: s.segment.end_index, reverse=True)
    
    for support in sorted_supports:
        end_index = support.segment.end_index
        if support.grounding_chunk_indices:
            citations = []
            for i in support.grounding_chunk_indices:
                if i < len(chunks):
                    uri = chunks[i].web.uri
                    if "vertexaisearch.cloud.google.com" in uri:
                        uri = get_actual_url_from_redirect(uri)
                    citations.append(f"[{i + 1}]({uri})")
            
            citation_str = ", ".join(citations)
            text = text[:end_index] + citation_str + text[end_index:]
    
    return text