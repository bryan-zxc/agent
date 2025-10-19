"""LLM service - main interface that delegates to refactored providers.

This file maintains backward compatibility while using the new modular architecture.
All internal implementation has been moved to the llm/ subfolder.
"""

import json
import logging
from typing import List, Dict, Any, Optional, Union, Type, Callable
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
                api_key=settings.openai_api_key, caller=self.caller
            )

        if validate_provider_config("anthropic", settings):
            self.providers["anthropic"] = AnthropicProvider(
                api_key=settings.anthropic_api_key, caller=self.caller
            )

        if validate_provider_config("google", settings):
            self.providers["google"] = GoogleProvider(
                api_key=settings.gemini_api_key, caller=self.caller
            )

        if not self.providers:
            logger.warning("No LLM providers configured. Check API keys.")

    def _get_provider_for_model(self, model: str) -> BaseLLMProvider:
        """Get the appropriate provider for a model."""
        provider_name = get_provider_for_model(model)

        if provider_name not in self.providers:
            raise ValueError(
                f"Provider '{provider_name}' not available for model '{model}'"
            )

        return self.providers[provider_name]

    def get_response(
        self,
        messages: List[Dict[str, Any]],
        model: str,
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
        model: str,
        temperature: float = 0,
        response_format: Any = None,
        system_instruction: Optional[str] = None,  # NEW: System instruction parameter
        use_tools: bool = False,  # NEW: Master switch for ALL tools (default: False)
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
                    result = self.get_response(
                        messages,
                        model,
                        temperature,
                        response_format,
                        system_instruction,
                    )

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

                    logger.info(
                        f"[TOOLS DEBUG] use_tools={use_tools}, mcp_manager exists={self.mcp_manager is not None}, tool_filter exists={tool_filter is not None}"
                    )

                    # Only load MCP tools if tools are enabled
                    if use_tools and self.mcp_manager:
                        try:
                            if tool_filter:
                                logger.info(
                                    f"[TOOLS DEBUG] Loading filtered MCP tools with filter"
                                )
                                mcp_tools = await self.mcp_manager.get_filtered_tools(
                                    tool_filter
                                )
                            else:
                                logger.info(f"[TOOLS DEBUG] Loading all MCP tools")
                                mcp_tools = await self.mcp_manager.get_tools_for_llm()
                            final_tools.extend(mcp_tools)
                            logger.info(
                                f"[TOOLS DEBUG] Loaded {len(mcp_tools)} MCP tools: {[t.get('function', {}).get('name', 'unknown') if t.get('type') == 'function' else 'non-function' for t in mcp_tools[:5]]}"
                            )
                        except Exception as e:
                            logger.warning(
                                f"[TOOLS DEBUG] Failed to load MCP tools: {e}"
                            )
                    else:
                        logger.info(
                            f"[TOOLS DEBUG] Not loading MCP tools - use_tools={use_tools}, has mcp_manager={self.mcp_manager is not None}"
                        )

                    # Without tools and without web search, use sync get_response
                    if not final_tools and not enable_web_search:
                        result = self.get_response(
                            messages,
                            model,
                            temperature,
                            response_format,
                            system_instruction,
                        )

                        # Validate result
                        if result is not None and result != "":
                            return result

                        logger.warning(
                            f"Attempt {retry + 1}/{MAX_LLM_RETRIES}: Got None or empty content from {model} "
                            f"(no tools, no web search path)"
                        )
                    else:
                        # Tool-enabled flow - returns list of message dicts
                        result = await self._get_response_with_tools(
                            messages=messages,
                            model=model,
                            temperature=temperature,
                            system_instruction=system_instruction,
                            tools=final_tools,
                            enable_web_search=enable_web_search,
                            websocket=websocket,
                            payload=payload,
                        )

                        # Validate - result is list of message dicts
                        if result is not None and len(result) > 0:
                            return result

                        logger.warning(
                            f"Attempt {retry + 1}/{MAX_LLM_RETRIES}: Got None or empty message list from {model} "
                            f"(tools path)"
                        )

            except Exception as e:
                logger.error(
                    f"Attempt {retry + 1}/{MAX_LLM_RETRIES} failed with exception: {e}"
                )

            # Exponential backoff before next retry (except on last iteration)
            if retry < MAX_LLM_RETRIES - 1:
                delay_exp(
                    None, retry
                )  # Pass None since we're handling both exceptions and content validation

        # All retries exhausted - return default message
        logger.error(
            f"Failed to get valid response from {model} after {MAX_LLM_RETRIES} attempts"
        )
        return "I'm processing your request. Please continue."

    async def _get_response_with_tools(
        self,
        messages: List[Dict],
        model: str,
        temperature: float,
        system_instruction: Optional[str] = None,
        tools: List[Dict] = None,
        enable_web_search: bool = False,
        websocket: Optional[Any] = None,
        payload: Optional[Dict[str, Any]] = None,
    ):
        """
        Execute tools and return message list for storage.

        Makes a single API call, executes any requested tools, and returns
        a list of message dictionaries ready for storage via message_manager.

        Returns:
            List of dictionaries with keys 'technical_message', 'display_message', 'message_from'
        """
        from ..utils.message_utils import format_tool_call_display

        # Make single API call
        provider = self._get_provider_for_model(model)
        actual_model = get_actual_model_name(model)
        provider_name = get_provider_for_model(model)

        response = provider.tools_response(
            messages=messages,
            model=actual_model,
            temperature=temperature,
            tools=tools,
            system_instruction=system_instruction,
        )

        if not response:
            return []

        message_list = []

        if provider_name == "openai":
            # Process response.output items in order: reasoning -> functions -> text
            for item in response.output:
                if item.type == "reasoning":
                    # Reasoning: display_message = None
                    message_list.append(
                        {
                            "technical_message": item.model_dump(exclude_none=True),
                            "display_message": None,
                            "message_from": "Bandit",
                        }
                    )

                elif item.type == "function_call":
                    # Function call: display formatted call, execute, append result
                    message_list.append(
                        {
                            "technical_message": item.model_dump(exclude_none=True),
                            "display_message": format_tool_call_display(item),
                            "message_from": "Bandit",
                        }
                    )

                    # Execute tool
                    tool_name = item.name
                    tool_args = (
                        json.loads(item.arguments)
                        if isinstance(item.arguments, str)
                        else item.arguments
                    )
                    result_text = await self._execute_tool(
                        tool_name, tool_args, websocket, payload
                    )

                    # Append result immediately
                    message_list.append(
                        {
                            "technical_message": {
                                "type": "function_call_output",
                                "call_id": item.id,
                                "output": result_text,
                            },
                            "display_message": result_text,
                            "message_from": "Bandit",
                        }
                    )

                elif item.type == "text":
                    # Text: display using response.output_text
                    message_list.append(
                        {
                            "technical_message": item.model_dump(exclude_none=True),
                            "display_message": response.output_text,
                            "message_from": "Bandit",
                        }
                    )

        elif provider_name == "anthropic":
            # Anthropic: response is response.content (list of TextBlock and ToolUseBlock)
            # Need to wrap blocks in role/content messages as per Anthropic API format
            for block in response:
                if block.type == "text":
                    # Text block: wrap in assistant message with content array
                    technical_message = {
                        "role": "assistant",
                        "content": [block.model_dump(exclude_none=True)]
                    }

                    message_list.append({
                        "technical_message": technical_message,
                        "display_message": block.text if hasattr(block, 'text') else None,
                        "message_from": "Bandit"
                    })

                elif block.type == "tool_use":
                    # Tool use block: wrap in assistant message
                    technical_message = {
                        "role": "assistant",
                        "content": [block.model_dump(exclude_none=True)]
                    }

                    message_list.append({
                        "technical_message": technical_message,
                        "display_message": format_tool_call_display(block),
                        "message_from": "Bandit"
                    })

                    # Execute tool
                    tool_name = block.name
                    tool_args = block.input
                    result_text = await self._execute_tool(tool_name, tool_args, websocket, payload)

                    # Append result wrapped in user message with tool_result
                    tool_result_technical = {
                        "role": "user",
                        "content": [{
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result_text
                        }]
                    }

                    message_list.append({
                        "technical_message": tool_result_technical,
                        "display_message": result_text,
                        "message_from": "Bandit"
                    })

        return message_list

    async def _execute_tool(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        websocket: Optional[Any] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Execute a single tool and return result as string."""
        # Log execution
        args_preview = str(tool_args)[:150]
        logger.info(
            f"[TOOL CALL] Executing: {tool_name} with args: {args_preview}{'...' if len(str(tool_args)) > 150 else ''}"
        )

        # Websocket status
        if websocket:
            try:
                await websocket.send_json(
                    {"type": "tool_execution", "tool": tool_name, "status": "starting"}
                )
            except Exception as e:
                logger.warning(f"Failed to send websocket update: {e}")

        # Pre-hook
        tool_args = await tool_hooks.apply_pre_hook(
            tool_name, tool_args, payload, websocket
        )

        # Execute
        try:
            if self.mcp_manager:
                result = await self.mcp_manager.execute_llm_tool_call(
                    tool_name=tool_name, tool_args=tool_args
                )
            else:
                result = {"error": "MCP manager not available"}

            # Post-hook
            result = await tool_hooks.apply_post_hook(
                tool_name, result, payload, websocket
            )

            # Log success
            result_preview = str(result)[:150] if result else "None"
            logger.info(
                f"[TOOL RESULT] {tool_name} completed - Result: {result_preview}{'...' if len(str(result)) > 150 else ''}"
            )

            # Websocket completion
            if websocket:
                try:
                    await websocket.send_json(
                        {
                            "type": "tool_execution",
                            "tool": tool_name,
                            "status": "completed",
                        }
                    )
                except:
                    pass

        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}")
            result = {"error": str(e)}

            # Websocket error
            if websocket:
                try:
                    await websocket.send_json(
                        {
                            "type": "tool_execution",
                            "tool": tool_name,
                            "status": "error",
                            "error": str(e),
                        }
                    )
                except:
                    pass

        # Convert to string
        return json.dumps(result, indent=2) if isinstance(result, dict) else str(result)

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
