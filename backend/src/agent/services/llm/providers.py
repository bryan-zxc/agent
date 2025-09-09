"""LLM provider implementations for OpenAI, Anthropic, and Google."""

import json
import re
import base64
import logging
import requests
from pathlib import Path
from typing import List, Dict, Any, Optional, Union, Type
from pydantic import BaseModel, ValidationError
from openai import OpenAI
from anthropic import Anthropic
from google import genai
from google.genai import types
from google.genai.types import Tool, GenerateContentConfig, GoogleSearch, UrlContext

from .base import BaseLLMProvider, RequestType, delay_exp
from .usage_tracker import UsageTracker
from ...utils.message_utils import append_user_content

logger = logging.getLogger(__name__)

# Retry configuration
MAX_LLM_RETRIES = 3
FAIL_STRUCTURE_RESPONSE_RETRIES = 2


class OpenAIProvider(BaseLLMProvider):
    """OpenAI provider implementation for GPT models."""

    MODELS = {
        "gpt-5-nano": "gpt-5-nano-2025-08-07",
    }

    PRICING = {
        "gpt-5-nano-2025-08-07": {"input": 0.05, "output": 0.4},
    }
    
    # Track if we've shown the temperature deprecation warning
    _temperature_warning_shown = False

    def _setup_client(self) -> None:
        """Set up OpenAI client."""
        self.client = OpenAI(api_key=self.api_key)
        self.usage_tracker = UsageTracker(caller=self.caller)

    def supports_model(self, model: str) -> bool:
        """Check if OpenAI supports this model."""
        return model in self.MODELS or model.startswith("gpt")

    def get_actual_model_name(self, model: str) -> str:
        """Get actual OpenAI model name."""
        return self.MODELS.get(model, model)
    
    def _warn_temperature_deprecated(self, temperature: float) -> None:
        """Warn once if temperature is being used with gpt-5 models."""
        if not OpenAIProvider._temperature_warning_shown and temperature != 0:
            logger.warning(
                "Temperature parameter is deprecated for OpenAI gpt-5 models and will be ignored. "
                "The model uses its own internal temperature settings."
            )
            OpenAIProvider._temperature_warning_shown = True

    def text_response(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float,
        system_instruction: Optional[str] = None,
    ) -> Optional[str]:
        """Get text response using new Responses API."""
        try:
            actual_model = self.get_actual_model_name(model)
            
            # Warn about temperature deprecation
            self._warn_temperature_deprecated(temperature)

            # Temperature is not supported in gpt-5 models, so we don't pass it
            response = self.client.responses.create(
                model=actual_model,
                instructions=system_instruction,
                input=messages,  # Always pass messages directly
            )

            # Track usage
            if hasattr(response, "usage"):
                self.track_cost(actual_model, response.usage, RequestType.TEXT)

            return response.output_text

        except Exception as e:
            logger.error(f"OpenAI text response error: {e}")
            return None

    def structured_response(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float,
        response_format: Union[Type[BaseModel], str],  # Now accepts "json" string
        system_instruction: Optional[str] = None,
    ) -> Union[BaseModel, str, None]:
        """Get structured response using new Responses API."""
        try:
            actual_model = self.get_actual_model_name(model)
            
            # Warn about temperature deprecation
            self._warn_temperature_deprecated(temperature)

            # Check if response_format is a Pydantic model or "json" string
            if isinstance(response_format, type) and issubclass(
                response_format, BaseModel
            ):
                # Use parse() for Pydantic models - temperature not supported
                response = self.client.responses.parse(
                    model=actual_model,
                    instructions=system_instruction,
                    input=messages,  # Always pass messages directly
                    text_format=response_format,
                )

                # Track usage
                if hasattr(response, "usage"):
                    self.track_cost(
                        actual_model, response.usage, RequestType.STRUCTURED
                    )

                return response.output_parsed

            elif response_format == "json":
                # Use create() with format for generic JSON
                input_messages = messages.copy()  # Copy to avoid mutating original

                for attempt in range(MAX_LLM_RETRIES):
                    # Temperature not supported in gpt-5 models
                    response = self.client.responses.create(
                        model=actual_model,
                        instructions=system_instruction,
                        input=input_messages,
                        text={"format": {"type": "json_object"}},
                    )
                    
                    # Track usage immediately after API call (captures all retry attempts)
                    if hasattr(response, "usage"):
                        self.track_cost(
                            actual_model, response.usage, RequestType.STRUCTURED
                        )

                    json_str = response.output_text

                    # First validation attempt
                    try:
                        json.loads(json_str)
                        return json_str
                    except:
                        # Clean control characters and retry
                        json_str = re.sub(r"[\x00-\x1F]+", "", json_str)

                    try:
                        json.loads(json_str)
                        return json_str
                    except Exception as e:
                        if attempt < MAX_LLM_RETRIES - 1:
                            # Add error feedback for retry
                            input_messages.append(
                                {
                                    "role": "developer",  # Use developer role, not system
                                    "content": f"The JSON returned is:\n{json_str}\n\nIt cannot be converted by json.loads with the following error:\n{e}\n\nGenerate a new JSON without the error.",
                                }
                            )
                            logger.warning(
                                f"JSON validation failed, attempt {attempt + 1}: {e}"
                            )
                        else:
                            logger.error(
                                f"Failed to get valid JSON after {MAX_LLM_RETRIES} attempts"
                            )
                            return None
            else:
                logger.error(f"Invalid response_format: {response_format}")
                return None

        except Exception as e:
            logger.error(f"OpenAI structured response error: {e}")
            return None

    def tools_response(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float,
        tools: List[Dict],
        enable_web_search: bool = False,
        system_instruction: Optional[str] = None,
    ) -> Optional[Dict]:
        """Get tools response with native web search support."""
        try:
            actual_model = self.get_actual_model_name(model)
            
            # Warn about temperature deprecation
            self._warn_temperature_deprecated(temperature)

            # Build tools list with format transformation for OpenAI
            tools_list = []
            
            # Transform MCP tools from nested to OpenAI's flat format
            if tools:
                for tool in tools:
                    if tool.get("type") == "function" and "function" in tool:
                        # Extract from MCP's nested structure
                        func = tool["function"]
                        # Create OpenAI's flat structure
                        openai_tool = {
                            "type": "function",
                            "name": func.get("name"),
                            "description": func.get("description", ""),
                            "parameters": func.get("parameters", {})
                        }
                        tools_list.append(openai_tool)

            # Add native web search tool if enabled
            if enable_web_search:
                tools_list.append({"type": "web_search"})

            # Temperature not supported in gpt-5 models
            response = self.client.responses.create(
                model=actual_model,
                instructions=system_instruction,
                input=messages,  # Always pass messages directly
                tools=tools_list if tools_list else None,
            )

            # Determine request type based on response content
            request_type = RequestType.TEXT  # Default
            web_search_used = False  # Track if web search was used

            # Check for web search calls in output
            if hasattr(response, "output"):
                for output in response.output:
                    if hasattr(output, "type") and output.type == "web_search_call":
                        request_type = RequestType.TOOLS
                        web_search_used = True
                        break

            # Check for function calls in output (OpenAI's new format)
            normalised_calls = []
            if hasattr(response, "output") and response.output:
                for output in response.output:
                    if hasattr(output, "type") and output.type == "function_call":
                        # Parse arguments from JSON string
                        args = {}
                        if hasattr(output, "arguments") and output.arguments:
                            try:
                                args = json.loads(output.arguments)
                            except json.JSONDecodeError:
                                logger.warning(f"Failed to parse arguments for {output.name}: {output.arguments}")
                        
                        normalised_calls.append({
                            "name": output.name,
                            "arguments": args
                        })
                        request_type = RequestType.TOOLS
            
            # If we have tool calls, return them
            if normalised_calls:
                # Track usage before returning
                if hasattr(response, "usage"):
                    self.track_cost(actual_model, response.usage, RequestType.TOOLS)
                return {
                    "tool_calls": normalised_calls,
                    "content": response.output_text if hasattr(response, "output_text") else None,
                    "role": "assistant",
                }

            # Format content with web search prefix if needed
            content = response.output_text
            if web_search_used and content:
                content = f"Tool web_search was called and returned:\n{content}"

            # Track usage before returning (no tools case)
            if hasattr(response, "usage"):
                self.track_cost(actual_model, response.usage, request_type)
            return {
                "content": content,
                "role": "assistant",
            }

        except Exception as e:
            logger.error(f"OpenAI tools response error: {e}")
            return None

    def track_cost(
        self, model: str, usage_metadata: Any, request_type: RequestType
    ) -> None:
        """Calculate cost and track usage for OpenAI."""
        if not usage_metadata:
            return

        # Simple token access for OpenAI
        input_tokens = getattr(usage_metadata, "input_tokens", 0)
        output_tokens = getattr(usage_metadata, "output_tokens", 0)

        # Calculate cost
        cost = 0.0
        if model in self.PRICING:
            input_cost = (input_tokens / 1_000_000) * self.PRICING[model]["input"]
            output_cost = (output_tokens / 1_000_000) * self.PRICING[model]["output"]
            cost = input_cost + output_cost
        else:
            logger.warning(f"No pricing info for model {model}")

        # Fire and forget tracking
        self.usage_tracker.track_usage_sync(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            request_type=request_type,
        )

    def format_tool_result(self, tool_call: Any, tool_result: Any) -> Dict[str, Any]:
        """Format tool result for OpenAI API."""
        # OpenAI expects tool role with tool_call_id
        content = (
            json.dumps(tool_result) if not isinstance(tool_result, str) else tool_result
        )
        return {
            "tool_call_id": (
                tool_call.id if hasattr(tool_call, "id") else str(tool_call)
            ),
            "role": "tool",
            "content": content,
        }


class AnthropicProvider(BaseLLMProvider):
    """Anthropic provider implementation for Claude models."""

    MODELS = {
        "sonnet-4": "claude-sonnet-4-20250514",
    }

    PRICING = {
        "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
    }

    def _setup_client(self) -> None:
        """Set up Anthropic client."""
        self.client = Anthropic(api_key=self.api_key)
        self.usage_tracker = UsageTracker(caller=self.caller)

    def supports_model(self, model: str) -> bool:
        """Check if Anthropic supports this model."""
        return (
            model in self.MODELS
            or model.startswith("claude")
            or model.startswith("sonnet")
        )

    def get_actual_model_name(self, model: str) -> str:
        """Get actual Anthropic model name."""
        return self.MODELS.get(model, model)


    def text_response(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float,
        system_instruction: Optional[str] = None,
    ) -> Optional[str]:
        """Get text response from Anthropic."""
        try:
            actual_model = self.get_actual_model_name(model)

            kwargs = {
                "model": actual_model,
                "max_tokens": 4096,
                "temperature": temperature,
                "messages": messages,
            }

            if system_instruction:
                kwargs["system"] = system_instruction

            response = self.client.messages.create(**kwargs)
            
            # Track usage
            if hasattr(response, 'usage'):
                self.track_cost(actual_model, response.usage, RequestType.TEXT)
            
            return response.content[0].text

        except Exception as e:
            logger.error(f"Anthropic text response error: {e}")
            return None

    def structured_response(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float,
        response_format: Union[Type[BaseModel], str],  # Now accepts "json"
        system_instruction: Optional[str] = None,
    ) -> Union[BaseModel, str, None]:
        """Get structured response from Anthropic using prefill technique."""
        try:
            actual_model = self.get_actual_model_name(model)

            # Determine format type
            is_pydantic = isinstance(response_format, type) and issubclass(
                response_format, BaseModel
            )
            is_json = response_format == "json"  # Changed from {"type": "json_object"}

            if is_pydantic:
                schema = response_format.model_json_schema()
                format_instruction = f"Please respond with a JSON object that matches this schema:\n\n{json.dumps(schema, indent=2)}"
            elif is_json:
                format_instruction = "Respond in JSON format."
            else:
                logger.error(f"Unsupported response_format: {response_format}")
                return None

            # Add format instruction using append_user_content helper
            enhanced_messages = append_user_content(messages, format_instruction)

            for attempt in range(MAX_LLM_RETRIES):
                kwargs = {
                    "model": actual_model,
                    "max_tokens": 4096,
                    "temperature": temperature,
                    "messages": enhanced_messages
                    + [
                        {
                            "role": "assistant",
                            "content": [{"type": "text", "text": "{"}],
                        }
                    ],
                }

                if system_instruction:
                    kwargs["system"] = system_instruction

                response = self.client.messages.create(**kwargs)
                
                # Track usage immediately after API call (captures all retry attempts)
                if hasattr(response, 'usage'):
                    self.track_cost(actual_model, response.usage, RequestType.STRUCTURED)
                
                json_content = "{" + response.content[0].text

                # First validation attempt
                try:
                    json_data = json.loads(json_content)
                    if is_pydantic:
                        return response_format.model_validate(json_data)
                    else:
                        return json_content
                except:
                    # Clean control characters and retry
                    json_content = re.sub(r"[\x00-\x1F]+", "", json_content)

                try:
                    json_data = json.loads(json_content)
                    if is_pydantic:
                        return response_format.model_validate(json_data)
                    else:
                        return json_content
                except (json.JSONDecodeError, ValidationError) as e:
                    if attempt < MAX_LLM_RETRIES - 1:
                        logger.warning(f"Attempt {attempt + 1} failed: {e}")
                        # Add error feedback
                        enhanced_messages.extend(
                            [
                                {
                                    "role": "assistant",
                                    "content": [{"type": "text", "text": json_content}],
                                },
                                {
                                    "role": "user",
                                    "content": [
                                        {
                                            "type": "text",
                                            "text": f"The JSON returned is:\n{json_content}\n\nIt cannot be converted by json.loads with the following error:\n{e}\n\nGenerate a new JSON without the error.",
                                        }
                                    ],
                                },
                            ]
                        )
                    else:
                        logger.error(f"Failed after {MAX_LLM_RETRIES} attempts: {e}")
                        return None

        except Exception as e:
            logger.error(f"Anthropic structured response error: {e}")
            return None

    def tools_response(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float,
        tools: List[Dict],
        enable_web_search: bool = False,
        system_instruction: Optional[str] = None,
    ) -> Optional[Dict]:
        """Get response with tool/function calling.

        Supports native Anthropic web search when enable_web_search=True.
        Web search and MCP tools can be used together in the same response.
        """
        try:
            actual_model = self.get_actual_model_name(model)

            # Build complete tools list (MCP tools + web search if enabled)
            anthropic_tools = []
            
            # Convert MCP tools to Anthropic format
            if tools:
                for tool in tools:
                    # Handle MCP's nested structure: {"type": "function", "function": {...}}
                    if tool.get("type") == "function" and "function" in tool:
                        func = tool["function"]
                        anthropic_tools.append(
                            {
                                "name": func.get("name"),
                                "description": func.get("description", ""),
                                "input_schema": func.get(
                                    "parameters", {"type": "object", "properties": {}}
                                ),
                            }
                        )

            # Add native web search tool if enabled
            if enable_web_search:
                anthropic_tools.append(
                    {
                        "type": "web_search_20250305",
                        "name": "web_search",
                        "max_uses": 5,
                    }
                )

            # Make SINGLE API call with all available tools
            kwargs = {
                "model": actual_model,
                "max_tokens": 4096,
                "temperature": temperature,
                "messages": messages,
            }

            if anthropic_tools:
                kwargs["tools"] = anthropic_tools

            if system_instruction:
                kwargs["system"] = system_instruction

            response = self.client.messages.create(**kwargs)
            
            # Analyze response to determine what happened
            has_web_search = False
            has_tool_calls = False
            
            if response.content:
                for content_block in response.content:
                    if hasattr(content_block, "type"):
                        if content_block.type == "server_tool_use":
                            if hasattr(content_block, "name") and content_block.name == "web_search":
                                has_web_search = True
                        elif content_block.type == "tool_use":
                            has_tool_calls = True
            
            # Track costs with appropriate request type
            request_type = RequestType.TOOLS if (has_web_search or has_tool_calls) else RequestType.TEXT
            if hasattr(response, 'usage'):
                self.track_cost(actual_model, response.usage, request_type)
            
            # Process response based on what actually happened
            if has_web_search:
                # Process web search with citations (may also include tool_calls!)
                return self._process_web_search_response(response)
            else:
                # Standard response processing for text and/or tool calls
                content_text = None
                tool_calls = []
                
                if response.content:
                    for content_block in response.content:
                        if hasattr(content_block, "text"):
                            content_text = content_block.text
                        elif hasattr(content_block, "type") and content_block.type == "tool_use":
                            # Normalise to standard format
                            tool_calls.append({
                                "name": content_block.name,
                                "arguments": content_block.input if hasattr(content_block, 'input') else {}
                            })
                
                return {
                    "content": content_text or "",
                    "tool_calls": tool_calls if tool_calls else None,
                    "role": "assistant",
                }

        except Exception as e:
            logger.error(f"Anthropic tools response error: {e}")
            return None

    def _process_web_search_response(self, response) -> Dict:
        """Process Anthropic response with web search results and citations.

        Handles content blocks from web search, inserts citations, and formats output.
        Also extracts any MCP tool calls that may be present alongside web search.
        Returns string for single search, list of content blocks for multiple searches.
        """
        if not response.content:
            return {"content": "", "tool_calls": None, "role": "assistant"}

        search_results = []  # List of search result strings
        current_search_parts = []  # Parts for current search
        tool_calls = []  # MCP tool calls (can coexist with web search)
        in_search_result = False
        current_query = None

        for content_block in response.content:
            # Check for web search tool use (start of search result)
            if (
                hasattr(content_block, "type")
                and content_block.type == "server_tool_use"
            ):
                if (
                    hasattr(content_block, "name")
                    and content_block.name == "web_search"
                ):
                    # Save previous search if exists
                    if current_search_parts:
                        search_results.append("\n".join(current_search_parts))
                        current_search_parts = []

                    # Start new search result
                    in_search_result = True
                    query = (
                        content_block.input.get("query", "unknown query")
                        if hasattr(content_block, "input")
                        else "unknown query"
                    )
                    current_query = (
                        f"Tool web_search was called with query '{query}' and returned:"
                    )
                    current_search_parts = [current_query]

            # Check for MCP tool calls (can coexist with web search)
            elif hasattr(content_block, "type") and content_block.type == "tool_use":
                # Normalise to standard format
                tool_calls.append({
                    "name": content_block.name,
                    "arguments": content_block.input if hasattr(content_block, 'input') else {}
                })
            
            # Process text blocks
            elif hasattr(content_block, "type") and content_block.type == "text":
                text = content_block.text or ""

                # Add citations if available
                if hasattr(content_block, "citations") and content_block.citations:
                    # Insert citations using title format
                    for citation in content_block.citations:
                        if hasattr(citation, "title") and hasattr(citation, "url"):
                            title = citation.title
                            url = citation.url
                            # Replace citation placeholders or append at end
                            citation_text = f"[{title}]({url})"
                            # For simplicity, append citations at the end of the text
                            text = f"{text} {citation_text}"

                if in_search_result:
                    # Part of current search result
                    current_search_parts.append(text)
                else:
                    # Regular text, not part of search
                    if current_search_parts:
                        # Save any pending search
                        search_results.append("\n".join(current_search_parts))
                        current_search_parts = []
                        in_search_result = False
                    # Add as separate result
                    search_results.append(text)

        # Save final search if exists
        if current_search_parts:
            search_results.append("\n".join(current_search_parts))

        # Format return based on number of searches
        if len(search_results) == 0:
            return {"content": "", "tool_calls": tool_calls if tool_calls else None, "role": "assistant"}
        elif len(search_results) == 1:
            # Single search or text - return string
            return {
                "content": search_results[0],
                "tool_calls": tool_calls if tool_calls else None,
                "role": "assistant",
            }
        else:
            # Multiple searches - return list of content blocks
            content_blocks = [
                {"type": "text", "text": result} for result in search_results
            ]
            return {"content": content_blocks, "tool_calls": tool_calls if tool_calls else None, "role": "assistant"}

    def track_cost(self, model: str, usage_metadata: Any, request_type: RequestType) -> None:
        """Calculate cost and track usage for Anthropic."""
        if not usage_metadata:
            return
        
        # Simple token access for Anthropic
        input_tokens = getattr(usage_metadata, 'input_tokens', 0)
        output_tokens = getattr(usage_metadata, 'output_tokens', 0)
        
        # Calculate cost
        cost = 0.0
        if model in self.PRICING:
            input_cost = (input_tokens / 1_000_000) * self.PRICING[model]["input"]
            output_cost = (output_tokens / 1_000_000) * self.PRICING[model]["output"]
            cost = input_cost + output_cost
        else:
            logger.warning(f"No pricing info for model {model}")
        
        # Fire and forget tracking
        self.usage_tracker.track_usage_sync(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            request_type=request_type
        )

    def format_tool_result(self, tool_call: Any, tool_result: Any) -> Dict[str, Any]:
        """Format tool result for Anthropic API."""
        # Anthropic expects user role with tool_result content block
        content = (
            json.dumps(tool_result) if not isinstance(tool_result, str) else tool_result
        )
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": (
                        tool_call.id if hasattr(tool_call, "id") else str(tool_call)
                    ),
                    "content": content,
                }
            ],
        }


class GoogleProvider(BaseLLMProvider):
    """Google provider implementation for Gemini models."""

    MODELS = {
        "gemini-2.5-pro": "gemini-2.5-pro",
    }

    PRICING = {
        "gemini-2.5-pro": {
            "input_low": 1.25,
            "output_low": 10.0,
            "input_high": 2.50,
            "output_high": 15.0,
            "threshold": 200000,
        }
    }

    URL_STATUS_MAPPING = {
        "URL_RETRIEVAL_STATUS_SUCCESS": "Url retrieval is successful.",
        "URL_RETRIEVAL_STATUS_ERROR": "Url retrieval is failed due to error.",
        "URL_RETRIEVAL_STATUS_PAYWALL": "Url retrieval is failed because the content is behind paywall.",
        "URL_RETRIEVAL_STATUS_UNSAFE": "Url retrieval is failed because the content is unsafe.",
    }

    def _setup_client(self) -> None:
        """Set up Google Gemini client."""
        self.client = genai.Client(api_key=self.api_key)
        # Also set up OpenAI-compatible client for backward compatibility
        self.openai_client = OpenAI(
            api_key=self.api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
        self.usage_tracker = UsageTracker(caller=self.caller)

    def supports_model(self, model: str) -> bool:
        """Check if Google supports this model."""
        return model in self.MODELS or model.startswith("gemini")

    def get_actual_model_name(self, model: str) -> str:
        """Get actual Google model name."""
        return self.MODELS.get(model, model)

    def _convert_messages(self, messages: List[Dict]) -> List:
        """Convert OpenAI format messages to Gemini format."""
        gemini_contents = []

        role_map = {
            "user": "user",
            "assistant": "model",
        }

        for message in messages:
            role = message.get("role")

            if role == "system" or role not in role_map:
                continue

            gemini_role = role_map[role]
            content = message.get("content", "")

            parts = []

            if isinstance(content, list):
                # Handle structured content
                for block in content:
                    block_type = block.get("type")

                    if block_type in ["text", "input_text"]:
                        text = block.get("text", "")
                        if text:
                            parts.append(types.Part.from_text(text=text))

                    elif block_type in ["image", "input_image"]:
                        # Handle base64 images
                        image_url = block.get("image_url", "")
                        if image_url and image_url.startswith("data:"):
                            try:
                                header, base64_data = image_url.split(",", 1)
                                mime_type = header.split(";")[0].split(":")[1]
                                image_bytes = base64.b64decode(base64_data)
                                parts.append(
                                    types.Part.from_bytes(
                                        data=image_bytes, mime_type=mime_type
                                    )
                                )
                            except Exception as e:
                                logger.warning(f"Failed to process image: {e}")
            else:
                # Simple text content
                if content:
                    parts.append(types.Part.from_text(text=str(content)))

            if parts:
                gemini_contents.append(types.Content(role=gemini_role, parts=parts))

        return gemini_contents

    def _convert_mcp_to_google_schema(self, json_schema: Dict[str, Any]) -> "types.Schema":
        """Convert MCP's JSON Schema format to Google's Schema format.
        
        MCP uses standard JSON Schema with metadata fields like $schema.
        Google uses its own Schema format without metadata.
        """
        # Map JSON Schema types to Google Schema types
        type_mapping = {
            "string": "STRING",
            "number": "NUMBER",
            "integer": "INTEGER",
            "boolean": "BOOLEAN",
            "array": "ARRAY",
            "object": "OBJECT",
        }
        
        # Remove metadata fields that Google doesn't accept
        schema_copy = {k: v for k, v in json_schema.items() 
                      if not k.startswith('$') and k != 'additionalProperties'}
        
        # Convert type
        json_type = schema_copy.get("type", "object")
        google_type = type_mapping.get(json_type, json_type.upper())
        
        # Build Google Schema
        google_schema = {"type": google_type}
        
        # Handle object properties
        if "properties" in schema_copy:
            google_properties = {}
            for prop_name, prop_schema in schema_copy["properties"].items():
                # Recursively convert nested schemas
                google_properties[prop_name] = self._convert_mcp_to_google_schema(prop_schema)
            google_schema["properties"] = google_properties
        
        # Handle required fields
        if "required" in schema_copy:
            google_schema["required"] = schema_copy["required"]
        
        # Handle array items
        if "items" in schema_copy:
            google_schema["items"] = self._convert_mcp_to_google_schema(schema_copy["items"])
        
        # Handle other fields like description, enum
        for field in ["description", "enum", "default"]:
            if field in schema_copy:
                google_schema[field] = schema_copy[field]
        
        return types.Schema(**google_schema)

    def text_response(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float,
        system_instruction: Optional[str] = None,
    ) -> Optional[str]:
        """Get text response from Gemini."""
        try:
            actual_model = self.get_actual_model_name(model)
            gemini_contents = self._convert_messages(messages)

            config = types.GenerateContentConfig(
                temperature=temperature,
                system_instruction=system_instruction if system_instruction else None,
            )

            response = self.client.models.generate_content(
                model=actual_model,
                contents=gemini_contents,
                config=config,
            )
            
            # Track usage
            if hasattr(response, 'usage_metadata'):
                self.track_cost(actual_model, response.usage_metadata, RequestType.TEXT)

            return response.text

        except Exception as e:
            logger.error(f"Gemini text response error: {e}")
            return None

    def structured_response(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float,
        response_format: Union[Type[BaseModel], str],  # Now accepts "json"
        system_instruction: Optional[str] = None,
    ) -> Union[BaseModel, str, None]:
        """Get structured response from Gemini."""
        try:
            actual_model = self.get_actual_model_name(model)
            gemini_contents = self._convert_messages(messages)

            config = types.GenerateContentConfig(
                temperature=temperature,
                response_mime_type="application/json",
                system_instruction=system_instruction if system_instruction else None,
            )

            # Handle response format
            is_pydantic = isinstance(response_format, type) and issubclass(
                response_format, BaseModel
            )

            if is_pydantic:
                config.response_schema = response_format
            elif response_format != "json":  # Changed from {"type": "json_object"}
                logger.warning(
                    f"Unsupported response_format for Gemini: {response_format}"
                )
                return None

            for attempt in range(MAX_LLM_RETRIES):
                response = self.client.models.generate_content(
                    model=actual_model,
                    contents=gemini_contents,
                    config=config,
                )
                
                # Track usage immediately after API call (captures all retry attempts)
                if hasattr(response, 'usage_metadata'):
                    self.track_cost(actual_model, response.usage_metadata, RequestType.STRUCTURED)

                json_content = response.text

                # First validation attempt
                try:
                    if is_pydantic:
                        json_data = json.loads(json_content)
                        return response_format.model_validate(json_data)
                    else:
                        json.loads(json_content)
                        return json_content
                except:
                    # Clean control characters and retry
                    json_content = re.sub(r"[\x00-\x1F]+", "", json_content)

                try:
                    if is_pydantic:
                        json_data = json.loads(json_content)
                        return response_format.model_validate(json_data)
                    else:
                        json.loads(json_content)
                        return json_content
                except (json.JSONDecodeError, ValidationError) as e:
                    if attempt < MAX_LLM_RETRIES - 1:
                        logger.warning(f"Attempt {attempt + 1} failed: {e}")
                        # For Gemini, we might need to adjust the prompt
                        gemini_contents.append(
                            types.Content(
                                role="user",
                                parts=[
                                    types.Part.from_text(
                                        text=f"The JSON returned is:\n{json_content}\n\nIt cannot be converted by json.loads with the following error:\n{e}\n\nGenerate a new JSON without the error."
                                    )
                                ],
                            )
                        )
                    else:
                        logger.error(f"Failed after {MAX_LLM_RETRIES} attempts: {e}")
                        return None

        except Exception as e:
            logger.error(f"Gemini structured response error: {e}")
            return None


    def tools_response(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float,
        tools: List[Dict],
        system_instruction: Optional[str] = None,
    ) -> Optional[Dict]:
        """Get tools response from Gemini with MCP tools support."""
        try:
            
            actual_model = self.get_actual_model_name(model)
            gemini_contents = self._convert_messages(messages)

            # Build tools list - MCP tools only
            all_tools = []

            # Add MCP tools as function declarations
            if tools:
                gemini_functions = []
                for tool in tools:
                    # Extract from MCP's nested structure (similar to OpenAI fix)
                    if tool.get("type") == "function" and "function" in tool:
                        func = tool["function"]
                        
                        # Convert MCP's JSON Schema parameters to Google's Schema format
                        parameters = func.get("parameters", {})
                        google_schema = self._convert_mcp_to_google_schema(parameters)
                        
                        gemini_functions.append(
                            types.FunctionDeclaration(
                                name=func.get("name"),
                                description=func.get("description", ""),
                                parameters=google_schema,
                            )
                        )

                if gemini_functions:
                    # Add function declarations wrapped in Tool object
                    all_tools.append(types.Tool(function_declarations=gemini_functions))

            # Create config with tools and system instruction
            config = types.GenerateContentConfig(
                temperature=temperature,
                tools=all_tools if all_tools else None,
                system_instruction=system_instruction if system_instruction else None,
            )

            # Make request
            response = self.client.models.generate_content(
                model=actual_model,
                contents=gemini_contents,
                config=config,
            )
            
            # Determine request type based on response content
            request_type = RequestType.TEXT  # Default
            
            # Check for tool calls in response
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, "function_call"):
                        request_type = RequestType.TOOLS
                        break
            
            # Track usage immediately after API call
            if hasattr(response, 'usage_metadata'):
                self.track_cost(actual_model, response.usage_metadata, request_type)

            # Extract MCP tool calls ONLY from parts
            tool_calls = []

            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, "function_call") and part.function_call:
                        fc = part.function_call
                        # Normalise to standard format
                        tool_calls.append({
                            "name": fc.name,
                            "arguments": fc.args if fc.args else {}
                        })

            # Return based on whether MCP tools were called
            if tool_calls:
                # MCP tools were called
                return {
                    "content": None,
                    "tool_calls": tool_calls,
                    "role": "assistant",
                }
            else:
                # Simple text response
                return {
                    "content": response.text if hasattr(response, "text") else "",
                    "tool_calls": None,
                    "role": "assistant",
                }

        except Exception as e:
            logger.error(f"Gemini tools response error: {e}")
            return None

    def track_cost(self, model: str, usage_metadata: Any, request_type: RequestType) -> None:
        """Calculate cost and track usage for Google."""
        if not usage_metadata:
            return
        
        # Aggregate Google's multiple input token types (handle None values)
        input_tokens = (
            (usage_metadata.prompt_token_count or 0) +
            (usage_metadata.thoughts_token_count or 0) +
            (usage_metadata.tool_use_prompt_token_count or 0)
        )
        output_tokens = usage_metadata.candidates_token_count or 0
        
        # Calculate cost with tiered pricing
        cost = 0.0
        pricing = self.PRICING.get(model, {})
        
        if "threshold" in pricing:
            # Tiered pricing based on input tokens
            if input_tokens <= pricing["threshold"]:
                input_rate = pricing["input_low"]
                output_rate = pricing["output_low"]
            else:
                input_rate = pricing["input_high"]
                output_rate = pricing["output_high"]
            
            cost = (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000
        else:
            logger.warning(f"No pricing info for model {model}")
        
        # Fire and forget tracking
        self.usage_tracker.track_usage_sync(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
            request_type=request_type
        )

    def format_tool_result(self, tool_call: Any, tool_result: Any) -> Dict[str, Any]:
        """Format tool result for Google Gemini API."""
        # Gemini expects functionResponse in parts
        # Extract function name from tool_call
        if hasattr(tool_call, "function"):
            func_name = tool_call.function.name
        elif hasattr(tool_call, "name"):
            func_name = tool_call.name
        else:
            func_name = "unknown_function"

        return {
            "role": "user",
            "parts": [
                {
                    "functionResponse": {
                        "name": func_name,
                        "response": {"result": tool_result},
                    }
                }
            ],
        }

    def _get_actual_url_from_redirect(self, redirect_url: str) -> str:
        """Extract actual URL from Google redirect."""
        if "vertexaisearch.cloud.google.com" not in redirect_url:
            return redirect_url
        try:
            response = requests.get(redirect_url, allow_redirects=False, timeout=10)
            if response.status_code in [301, 302]:
                return response.headers.get("Location", redirect_url)
            return redirect_url
        except:
            return redirect_url

    def _generate_url_metadata_table(self, url_metadata) -> str:
        """Generate markdown table from URL metadata."""
        if not url_metadata:
            return ""

        table_rows = []
        table_rows.append("| Retrieved URL | Status |")
        table_rows.append("|---------------|--------|")

        for metadata in url_metadata:
            # Get actual URL from redirect
            actual_url = self._get_actual_url_from_redirect(metadata.retrieved_url)

            # Get status description
            status_value = (
                metadata.url_retrieval_status.value
                if hasattr(metadata.url_retrieval_status, "value")
                else str(metadata.url_retrieval_status)
            )
            status_desc = self.URL_STATUS_MAPPING.get(status_value, "Unknown status")

            # Add row to table
            table_rows.append(f"| {actual_url} | {status_desc} |")

        return "\n".join(table_rows)

    def _add_citations(self, response) -> str:
        """Add citations to response text from grounding metadata."""
        if not hasattr(response, "candidates") or not response.candidates:
            return response.text if hasattr(response, "text") else ""

        candidate = response.candidates[0]
        if not hasattr(candidate, "grounding_metadata"):
            return response.text if hasattr(response, "text") else ""

        text = response.text if hasattr(response, "text") else ""
        metadata = candidate.grounding_metadata

        if not hasattr(metadata, "grounding_supports") or not hasattr(
            metadata, "grounding_chunks"
        ):
            return text

        supports = metadata.grounding_supports
        chunks = metadata.grounding_chunks

        # Sort by end_index descending to avoid position shifts
        sorted_supports = sorted(
            supports, key=lambda s: s.segment.end_index, reverse=True
        )

        for support in sorted_supports:
            end_index = support.segment.end_index
            if support.grounding_chunk_indices:
                citations = []
                for i in support.grounding_chunk_indices:
                    if i < len(chunks):
                        uri = chunks[i].web.uri
                        # Use the extracted method
                        uri = self._get_actual_url_from_redirect(uri)
                        citations.append(f"[{i + 1}]({uri})")

                citation_str = ", ".join(citations)
                text = text[:end_index] + citation_str + text[end_index:]

        return text
    
    def search_web(self, query: str) -> str:
        """Web search using Google's grounding with full formatting.
        
        Args:
            query: Search query to execute
            
        Returns:
            Search results with citations and URL metadata, or error message
        """
        try:
            model = "gemini-2.5-pro"
            
            # Build grounding tools (search + URL context)
            grounding_tools = [
                types.Tool(url_context=types.UrlContext()),
                types.Tool(google_search=types.GoogleSearch())
            ]
            
            logger.info("Enabled Gemini native grounding tools (search + URL context)")
            
            # Use temperature 0 for factual search results
            config = types.GenerateContentConfig(
                tools=grounding_tools,
                temperature=0,
            )
            
            response = self.client.models.generate_content(
                model=model,
                contents=query,
                config=config,
            )
            
            # Track usage
            if hasattr(response, 'usage_metadata'):
                self.track_cost(model, response.usage_metadata, RequestType.TOOLS)
            
            # Check if web search actually happened
            web_search_happened = False
            text_content = ""
            
            if response.candidates:
                candidate = response.candidates[0]
                
                # Check for grounding data (search results)
                if hasattr(candidate, "grounding_metadata") and hasattr(
                    candidate.grounding_metadata, "grounding_supports"
                ):
                    web_search_happened = True
                    text_content = self._add_citations(response)
                    logger.info(
                        f"Web search returned {len(candidate.grounding_metadata.grounding_supports)} results"
                    )
                
                # Check for URL context metadata
                if hasattr(candidate, "url_context_metadata") and candidate.url_context_metadata:
                    web_search_happened = True
                    url_metadata = candidate.url_context_metadata
                    url_table = self._generate_url_metadata_table(url_metadata)
                    
                    # Append URL table to existing content
                    if text_content:
                        text_content += "\n\nThe following websites were retrieved:\n" + url_table
                    else:
                        text_content = "The following websites were retrieved:\n" + url_table
                        
                    logger.info(f"URL context extracted from {len(url_metadata)} URLs")
            
            # IMPORTANT: Only return content if web search actually happened
            if web_search_happened and text_content:
                return text_content
            else:
                logger.warning("Web search was called but no grounding occurred")
                return "No search results found. The search may have failed or returned no relevant results."
            
        except Exception as e:
            logger.error(f"Web search error: {e}")
            raise
    
    def process_pdf(
        self,
        pdf_source: Union[str, Path],
        prompt: str,
        temperature: float = 0,
        response_format: Optional[Type[BaseModel]] = None,
    ) -> Union[str, BaseModel]:
        """Process PDF with Gemini and return response.
        
        Args:
            pdf_source: Path or URL to PDF file
            prompt: Prompt to process the PDF with
            temperature: Temperature for response generation
            response_format: Optional structured response format
            
        Returns:
            Text response or structured response based on format
        """
        if not str(pdf_source).lower().endswith(".pdf"):
            return "Not a pdf"
        
        model = "gemini-2.5-pro"
        
        # Get PDF data
        if isinstance(pdf_source, str) and pdf_source.startswith("http"):
            import httpx
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
            response = self.client.models.generate_content(
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
