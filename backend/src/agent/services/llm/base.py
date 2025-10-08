"""Base classes and interfaces for LLM providers."""

import random
import time
import logging
import enum
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Union, Type
from pydantic import BaseModel

from ...config.llm_config import (
    get_actual_model_name as config_get_actual_model_name,
    PROVIDER_MODELS
)

logger = logging.getLogger(__name__)


class RequestType(enum.Enum):
    """Types of LLM requests for tracking purposes."""

    TEXT = "text"
    TOOLS = "tools"
    STRUCTURED = "structured"


def delay_exp(e: Exception, x: int) -> None:
    """
    Delay function to handle exceptions with exponential backoff.

    Args:
        e: The exception that occurred
        x: The retry attempt number
    """
    delay_secs = 5 * (x + 1)
    randomness_collision_avoidance = random.randint(0, 1000) / 1000.0
    sleep_dur = delay_secs + randomness_collision_avoidance
    logger.warning(f"Retrying in {round(sleep_dur, 2)} seconds due to: {e}")
    time.sleep(sleep_dur)


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers."""

    # Each provider must define its provider_name
    provider_name: str = None

    def __init__(self, api_key: str, caller: str = "general"):
        """
        Initialise the provider with API credentials.

        Args:
            api_key: API key for the provider
            caller: Identifier for tracking usage
        """
        self.api_key = api_key
        self.caller = caller
        self._setup_client()

    @abstractmethod
    def _setup_client(self) -> None:
        """Set up the provider-specific client."""
        pass

    def supports_model(self, model: str) -> bool:
        """
        Check if this provider supports the given model.

        Args:
            model: Model identifier to check

        Returns:
            True if the provider supports this model
        """
        if model in PROVIDER_MODELS:
            provider, _ = PROVIDER_MODELS[model]
            return provider == self.provider_name
        return False

    def get_actual_model_name(self, model: str) -> str:
        """
        Get the actual model name for API calls from central config.

        Args:
            model: Friendly model name

        Returns:
            Actual model identifier for API
        """
        return config_get_actual_model_name(model)

    @abstractmethod
    def text_response(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float,
        system_instruction: Optional[str] = None,
    ) -> Optional[str]:
        """
        Get a simple text response from the model.

        Args:
            messages: Conversation messages
            model: Model to use
            temperature: Temperature for response generation
            system_instruction: Optional system instruction

        Returns:
            Text response or None if failed
        """
        pass

    @abstractmethod
    def structured_response(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float,
        response_format: Union[Type[BaseModel], str],
        system_instruction: Optional[str] = None,
    ) -> Union[BaseModel, str, None]:
        """
        Get a structured response (Pydantic model or JSON).

        Args:
            messages: Conversation messages
            model: Model to use
            temperature: Temperature for response generation
            response_format: Either a Pydantic model class or "json" for generic JSON output
            system_instruction: Optional system instruction

        Returns:
            Structured response or None if failed
        """
        pass

    @abstractmethod
    def tools_response(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        temperature: float,
        tools: List[Dict],
        system_instruction: Optional[str] = None,
    ) -> Optional[Dict]:
        """
        Get a response with tool/function calling.

        Args:
            messages: Conversation messages
            model: Model to use
            temperature: Temperature for response generation
            tools: List of available tools (MCP tools only)
            system_instruction: Optional system instruction

        Returns:
            Response with tool calls or None if failed
        """
        pass

    @abstractmethod
    def track_cost(
        self, model: str, usage_metadata: Any, request_type: RequestType
    ) -> None:
        """
        Calculate cost and track usage in a fire-and-forget manner.

        Args:
            model: Model used
            usage_metadata: Provider-specific usage metadata from response
            request_type: Type of request (text, tools, structured)
        """
        pass

    @abstractmethod
    def format_tool_result(self, tool_call: Any, tool_result: Any) -> Dict[str, Any]:
        """
        Format tool execution result for provider-specific API.

        Args:
            tool_call: The original tool call from the model
            tool_result: The result from executing the tool

        Returns:
            Formatted message dict ready to append to conversation
        """
        pass

