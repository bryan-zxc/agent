"""LLM service - main interface that delegates to refactored providers.

This file maintains backward compatibility while using the new modular architecture.
All internal implementation has been moved to the llm/ subfolder.
"""

import json
import logging
from typing import List, Dict, Any, Optional, Union, Type, Callable, Literal
from pathlib import Path
from pydantic import BaseModel

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
from .llm.tool_hooks import tool_hooks

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
        
        return result
    
    
    async def a_get_response(
        self,
        messages: List[Dict],
        model: Literal["gpt-5-nano", "sonnet-4", "gemini-2.5-pro"],
        temperature: float = 0,
        response_format: Any = None,
        system_instruction: Optional[str] = None,  # NEW: System instruction parameter
        use_tools: bool = False,          # NEW: Master switch for ALL tools (default: False)
        enable_web_search: bool = False,  # NEW: Enable provider-native web search
        # REMOVED: tools parameter - violates MCP-only principle
        tool_filter: Optional[Callable] = None,  # Existing: MCP tool filter
        websocket: Optional[Any] = None,  # Existing: WebSocket for status updates
        payload: Optional[Dict[str, Any]] = None,  # NEW: Context payload for tool hooks
    ):
        """Async LLM response with optional tool support.
        
        Args:
            messages: Conversation messages
            model: Model to use
            temperature: Temperature for response generation
            response_format: Optional structured response format
            system_instruction: Optional system instruction for the model
            use_tools: Master switch for ALL tools (MCP tools) - default False
            enable_web_search: Enable provider-native web search
            tool_filter: Optional filter for MCP tools
            websocket: Optional websocket for sending status updates
            payload: Optional context data for tool hooks (e.g., router_id)
        """
        # Retry loop wrapping all execution paths
        for retry in range(MAX_LLM_RETRIES):
            try:
                # Early exit if no tools
                if not use_tools:
                    result = self.get_response(messages, model, temperature, response_format, system_instruction)
                    
                    # Validate result for non-tool responses
                    if result is not None and result != "":
                        return result
                    
                    # Log and continue retry loop if result was invalid  
                    logger.warning(
                        f"Attempt {retry + 1}/{MAX_LLM_RETRIES}: Got None or empty content from {model} "
                        f"(no tools path)"
                    )
                    
                else:
                    # Build tools list - MCP ONLY
                    final_tools = []
                    
                    logger.info(f"[TOOLS DEBUG] use_tools={use_tools}, mcp_manager exists={self.mcp_manager is not None}, tool_filter exists={tool_filter is not None}")
                    
                    # Only load MCP tools if tools are enabled
                    if use_tools and self.mcp_manager:
                        try:
                            if tool_filter:
                                logger.info(f"[TOOLS DEBUG] Loading filtered MCP tools with filter")
                                mcp_tools = await self.mcp_manager.get_filtered_tools(tool_filter)
                            else:
                                logger.info(f"[TOOLS DEBUG] Loading all MCP tools")
                                mcp_tools = await self.mcp_manager.get_tools_for_llm()
                            final_tools.extend(mcp_tools)
                            logger.info(f"[TOOLS DEBUG] Loaded {len(mcp_tools)} MCP tools: {[t.get('function', {}).get('name', 'unknown') if t.get('type') == 'function' else 'non-function' for t in mcp_tools[:5]]}")
                        except Exception as e:
                            logger.warning(f"[TOOLS DEBUG] Failed to load MCP tools: {e}")
                    else:
                        logger.info(f"[TOOLS DEBUG] Not loading MCP tools - use_tools={use_tools}, has mcp_manager={self.mcp_manager is not None}")
                    
                    # Without tools and without web search, use sync get_response
                    if not final_tools and not enable_web_search:
                        result = self.get_response(messages, model, temperature, response_format, system_instruction)
                        
                        # Validate result
                        if result is not None and result != "":
                            return result
                        
                        logger.warning(
                            f"Attempt {retry + 1}/{MAX_LLM_RETRIES}: Got None or empty content from {model} "
                            f"(no tools, no web search path)"
                        )
                    else:
                        # Tool-enabled flow - pass websocket and web search flag for status updates
                        result = await self._get_response_with_tools(
                            messages=messages,
                            model=model,
                            temperature=temperature,
                            system_instruction=system_instruction,
                            tools=final_tools,
                            enable_web_search=enable_web_search,  # Pass to providers
                            websocket=websocket,
                            payload=payload,  # Pass context for hooks
                        )
                        
                        # For tool responses, validate content
                        if result is not None and result != "":
                            return result
                        
                        logger.warning(
                            f"Attempt {retry + 1}/{MAX_LLM_RETRIES}: Got None or empty content from {model} "
                            f"(tools path)"
                        )
                
            except Exception as e:
                logger.error(f"Attempt {retry + 1}/{MAX_LLM_RETRIES} failed with exception: {e}")
            
            # Exponential backoff before next retry (except on last iteration)
            if retry < MAX_LLM_RETRIES - 1:
                delay_exp(None, retry)  # Pass None since we're handling both exceptions and content validation
        
        # All retries exhausted - return default message
        logger.error(f"Failed to get valid response from {model} after {MAX_LLM_RETRIES} attempts")
        return "I'm processing your request. Please continue."
    
    async def _get_response_with_tools(
        self,
        messages: List[Dict],
        model: str,
        temperature: float,
        system_instruction: Optional[str] = None,
        tools: List[Dict] = None,
        enable_web_search: bool = False,  # NEW
        websocket: Optional[Any] = None,
        payload: Optional[Dict[str, Any]] = None,  # NEW: Context for hooks
    ):
        """
        Execute tools and return formatted text response.
        
        Makes a single API call, executes any requested tools, and returns
        text describing what happened. No tool artifacts in the response.
        
        Args:
            messages: Conversation messages
            model: Model to use
            temperature: Temperature for response generation
            system_instruction: Optional system instruction for the model
            tools: List of available tools (MCP tools only)
            enable_web_search: Enable provider-native web search
            websocket: Optional websocket for sending execution status updates
            payload: Optional context data for tool hooks (e.g., router_id)
        
        Returns:
            String for single tool execution, or list of content blocks for multiple tools
        """
        # Google Web Search Architecture:
        # ================================
        # Unlike OpenAI and Anthropic which support native web search in tools_response,
        # Google's grounding tools (GoogleSearch/UrlContext) conflict with function
        # calling in Gemini's tools_response method.
        #
        # Solution: Google uses the google_search MCP tool (from agent_tools server)
        # which internally calls GoogleProvider.search_web() method. This provides
        # web search capability through the standard tools interface.
        #
        # The agent_tools MCP server is enabled by default and includes:
        # - google_search: Web search functionality for Google provider
        # - get_facts_from_pdf: PDF document analysis
        #
        # No special handling needed here - tools are loaded from MCP servers.
        
        # Make single API call to get tool calls
        provider = self._get_provider_for_model(model)
        actual_model = get_actual_model_name(model)
        
        response = provider.tools_response(
            messages=messages,
            model=actual_model,
            temperature=temperature,
            tools=tools,
            enable_web_search=enable_web_search,  # Pass to provider
            system_instruction=system_instruction,  # Pass system instruction
        )
        
        # If no tools requested, return the text content
        if not response or not response.get("tool_calls"):
            return response.get("content", "") if response else ""
        
        # Log the tools that were called
        tool_names_for_logging = [call["name"] for call in response["tool_calls"]]
        logger.info(f"Tools used: {tool_names_for_logging}")
        
        # Execute each tool and collect results
        tool_messages = []
        tool_names = []  # Track tool names for structured response
        
        for tool_call in response["tool_calls"]:
            # All providers now return normalised format
            tool_name = tool_call["name"]
            tool_args = tool_call["arguments"]
            tool_names.append(tool_name)  # Collect tool name
            
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
            
            # Apply pre-processing hook to potentially modify arguments
            tool_args = await tool_hooks.apply_pre_hook(
                tool_name, tool_args, payload, websocket
            )
            
            # Execute MCP tool (all tools are MCP tools)
            try:
                if self.mcp_manager:
                    result = await self.mcp_manager.execute_llm_tool_call(
                        tool_name=tool_name,
                        tool_args=tool_args
                    )
                else:
                    result = {"error": "MCP manager not available"}
                
                # Apply post-processing hook to potentially modify result
                result = await tool_hooks.apply_post_hook(
                    tool_name, result, payload, websocket
                )
                
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
        
        # Format content based on number of tools
        if len(tool_messages) == 1:
            content = tool_messages[0]  # Single tool - simple string
        else:
            # Multiple tools - return list format compatible with content parameter
            content = [{"type": "text", "text": msg} for msg in tool_messages]
        
        # Return structured response with tool call information
        return {
            "content": content,
            "tool_calls": tool_names  # List of tool names that were called
        }
    
    def get_response_pdf(
        self,
        pdf_source: Union[str, Path],
        prompt: str,
        temperature: float = 0,
        response_format: Optional[Type[BaseModel]] = None,
    ) -> Union[str, BaseModel]:
        """Get response from Gemini with PDF support.
        
        .. deprecated::
            This method is kept for backwards compatibility.
            Implementation has been moved to GoogleProvider.process_pdf().
        """
        if "google" not in self.providers:
            raise ValueError("Google provider not configured for PDF processing")
        
        return self.providers["google"].process_pdf(
            pdf_source, prompt, temperature, response_format
        )
    
    def search_web(self, query: str) -> str:
        """Web search using Google's grounding.
        
        .. deprecated::
            This method is kept for backwards compatibility.
            Implementation has been moved to GoogleProvider.search_web().
        """
        if "google" not in self.providers:
            raise ValueError("Google provider not configured for web search")
        
        return self.providers["google"].search_web(query)