import os
import random
import time
import json
import re
import logging
import enum
import requests
from pathlib import Path
from datetime import datetime
from pydantic import BaseModel, ValidationError
from openai import OpenAI
from anthropic import Anthropic
from google import genai
from google.genai import types
import httpx
from typing import Literal, Optional, Union, Type
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Float,
    DateTime,
    Enum,
    Index,
)
from sqlalchemy.orm import declarative_base, sessionmaker

from ..config.settings import AgentSettings

logger = logging.getLogger(__name__)


MAX_LLM_RETRIES = 3
FAIL_STRUCTURE_RESPONSE_RETRIES = 2

MODEL_MAPPING = {
    "sonnet-4": "claude-sonnet-4-20250514",
    "gpt-4.1-nano": "gpt-4.1-nano-2025-04-14",
    "gemini-2.5-pro": "gemini-2.5-pro",
}

# Pricing per 1M tokens (input, output) in USD
PRICING = {
    "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
    "gpt-4.1-nano-2025-04-14": {"input": 0.1, "output": 0.4},
    "gemini-2.5-pro": {
        "input_low": 1.25,  # ≤200k tokens
        "output_low": 10.0,  # ≤200k tokens
        "input_high": 2.50,  # >200k tokens
        "output_high": 15.0,  # >200k tokens
        "threshold": 200000,  # 200k token threshold
    },
}

# SQLAlchemy setup
Base = declarative_base()


class RequestType(enum.Enum):
    TEXT = "text"
    TOOLS = "tools"
    STRUCTURED = "structured"


class LLMUsage(Base):
    __tablename__ = "llm_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.now, index=True)  # ADDED INDEX for cost queries
    model = Column(String(100), nullable=False)
    input_tokens = Column(Integer, nullable=False)
    output_tokens = Column(Integer, nullable=False)
    cost = Column(Float, nullable=False)
    request_type = Column(Enum(RequestType), nullable=False)
    caller = Column(String(100), nullable=False, index=True)  # ADDED INDEX for caller filtering
    
    # Add composite index for cost card queries
    __table_args__ = (
        Index('idx_caller_timestamp', 'caller', 'timestamp'),  # For filtering by caller and time range
    )


def delay_exp(e, x):
    """
    Delay function to handle exceptions with exponential backoff.
    """
    delay_secs = 5 * (x + 1)
    randomness_collision_avoidance = random.randint(0, 1000) / 1000.0
    sleep_dur = delay_secs + randomness_collision_avoidance
    logger.warning(f"Retrying in {round(sleep_dur,2)} seconds due to: {e}")
    time.sleep(sleep_dur)


class LLM:
    def __init__(
        self,
        db_path: str | Path = Path("/app/db/llm_usage.db"),
        caller: str = "general",
    ):
        # Load settings which automatically loads .env and .env.local
        settings = AgentSettings()

        # Initialize clients with API keys from settings
        self.openai_client = OpenAI(api_key=settings.openai_api_key)
        self.gemini_openai_client = OpenAI(
            api_key=settings.gemini_api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
        self.anthropic_openai_client = OpenAI(
            api_key=settings.anthropic_api_key,
            base_url="https://api.anthropic.com/v1/",
        )
        self.anthropic_client = Anthropic(api_key=settings.anthropic_api_key)
        self.gemini_client = genai.Client(api_key=settings.gemini_api_key)

        # Store caller for usage tracking
        self.caller = caller

        # SQLAlchemy setup with WAL mode and connection pooling
        self.db_path = Path(db_path)
        
        # Ensure directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            # Connection pool settings for better concurrency
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=3600,  # Recycle connections every hour
            # SQLite-specific connection arguments
            connect_args={
                "check_same_thread": False,  # Allow connections across threads
                "timeout": 30,  # 30 second timeout for database locks
            },
            echo=False  # Set to True for SQL debugging
        )
        
        # Configure WAL mode and other SQLite optimisations
        self._configure_sqlite_optimisations()
        
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
    
    def _configure_sqlite_optimisations(self):
        """Configure SQLite for optimal concurrent performance"""
        with self.engine.connect() as conn:
            # Enable WAL mode for concurrent readers and writers
            conn.execute("PRAGMA journal_mode=WAL")
            
            # Set busy timeout to handle lock contention gracefully
            conn.execute("PRAGMA busy_timeout=5000")  # 5 second timeout
            
            # Enable synchronous mode for durability while maintaining performance
            conn.execute("PRAGMA synchronous=NORMAL")  # Balance safety vs performance
            
            # Set cache size for better performance (negative value = KB)
            conn.execute("PRAGMA cache_size=-32000")  # 32MB cache
            
            # Optimize temp storage
            conn.execute("PRAGMA temp_store=MEMORY")
            
            conn.commit()
            logger.info("SQLite WAL mode and optimisations enabled for LLM usage database")

    def _calculate_cost(
        self, model: str, input_tokens: int, output_tokens: int
    ) -> float:
        """Calculate cost based on model pricing."""
        pricing = PRICING.get(model, {"input": 0, "output": 0})

        # Handle Gemini's tiered pricing based on input tokens only
        if model == "gemini-2.5-pro" and "threshold" in pricing:
            if input_tokens <= pricing["threshold"]:
                # Use low-tier pricing
                input_rate = pricing["input_low"]
                output_rate = pricing["output_low"]
            else:
                # Use high-tier pricing
                input_rate = pricing["input_high"]
                output_rate = pricing["output_high"]

            return (input_tokens * input_rate + output_tokens * output_rate) / 1000000

        # Standard pricing for other models
        return (
            input_tokens * pricing["input"] + output_tokens * pricing["output"]
        ) / 1000000

    def _track_usage(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        request_type: str = "text",
    ):
        """Track usage to SQLite database using SQLAlchemy."""
        cost = self._calculate_cost(model, input_tokens, output_tokens)

        session = self.Session()
        try:
            usage_record = LLMUsage(
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=cost,
                request_type=request_type,
                caller=self.caller,
            )
            session.add(usage_record)
            session.commit()
            logger.info(
                f"LLM Usage: {model}, Input: {input_tokens}, Output: {output_tokens}, Cost: ${cost:.6f}"
            )
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to track usage: {e}")
        finally:
            session.close()

    def _get_client_for_model(self, model: str):
        """Select the appropriate client based on the model name.

        Note: Anthropic models now use native SDK, this is only for OpenAI/Gemini.
        """
        if model.startswith("gpt"):
            return self.openai_client
        elif model.startswith("gemini"):
            return self.gemini_openai_client
        else:
            raise ValueError(f"Unknown model for OpenAI-compatible client: {model}")

    def _is_anthropic_model(self, model: str):
        """Check if model is an Anthropic model."""
        return model.startswith("sonnet") or model.startswith("claude")

    def _normalise_content_to_structured(self, content: str | list) -> list:
        """Convert content to structured list format for Anthropic API.

        Args:
            content: Either string or existing list of content blocks

        Returns:
            List of content blocks in format [{"type": "text", "text": "content"}, ...]
        """
        if isinstance(content, str):
            return [{"type": "text", "text": content}]
        elif isinstance(content, list):
            # Already in structured format, return as-is
            return content
        else:
            # Fallback for unexpected types
            return [{"type": "text", "text": str(content)}]

    def _convert_openai_to_anthropic_messages(
        self, messages: list[dict]
    ) -> tuple[list[dict], str | None]:
        """Convert OpenAI format messages to Anthropic format with structured content.

        Returns:
            tuple: (anthropic_messages, system_content)
        """
        system_content = None
        anthropic_messages = []

        for message in messages:
            message_copy = message.copy()
            role = message_copy.get("role")
            content = message_copy.get("content", "")

            if role == "system":
                # Extract system content for separate system parameter
                if isinstance(content, list):
                    # Extract text from structured content
                    text_parts = [
                        block.get("text", "")
                        for block in content
                        if block.get("type") == "text"
                    ]
                    system_text = " ".join(text_parts)
                else:
                    system_text = str(content)

                if system_content is None:
                    system_content = system_text
                else:
                    system_content += "\n\n" + system_text
            elif role == "developer":
                # Convert developer role to user role with structured content
                message_copy["role"] = "user"
                message_copy["content"] = self._normalise_content_to_structured(content)
                anthropic_messages.append(message_copy)
            else:
                # Normalise content to structured format for user, assistant, and tool messages
                message_copy["content"] = self._normalise_content_to_structured(content)
                anthropic_messages.append(message_copy)

        # Merge consecutive messages with same role
        merged_messages = self._merge_consecutive_messages(anthropic_messages)

        return merged_messages, system_content

    def _merge_consecutive_messages(self, messages: list[dict]) -> list[dict]:
        """Merge consecutive messages with the same role by combining content arrays."""
        if not messages:
            return messages

        merged_messages = []

        for message in messages:
            current_role = message.get("role")
            current_content = message.get("content", [])

            # If this is the first message or different role, add it
            if not merged_messages or merged_messages[-1].get("role") != current_role:
                merged_messages.append(message.copy())
            else:
                # Same role as previous message - merge content arrays
                prev_content = merged_messages[-1].get("content", [])

                # Extend with current message content
                prev_content.extend(current_content)
                merged_messages[-1]["content"] = prev_content

        return merged_messages

    def _anthropic_text_response(
        self,
        messages: list[dict],
        model: str,
        temperature: float,
        system_content: str | None = None,
    ) -> str | None:
        """Get simple text response from Anthropic using native SDK."""
        try:
            kwargs = {
                "model": model,
                "max_tokens": 4096,
                "temperature": temperature,
                "messages": messages,
            }

            if system_content:
                kwargs["system"] = system_content

            response = self.anthropic_client.messages.create(**kwargs)

            # Track usage
            self._track_usage(
                model=model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                request_type="text",
            )

            return response.content[0].text

        except Exception as e:
            logger.error(f"Anthropic text response error: {e}")
            return None

    def _anthropic_structured_response(
        self,
        messages: list[dict],
        model: str,
        temperature: float,
        response_format: BaseModel | dict,
        system_content: str | None = None,
    ) -> BaseModel | str | None:
        """Unified structured response handler for both Pydantic models and JSON objects."""

        # Determine if this is Pydantic model or JSON object request
        is_pydantic = isinstance(response_format, type) and issubclass(
            response_format, BaseModel
        )
        is_json_object = response_format == {"type": "json_object"}

        if is_pydantic:
            # Pydantic model - add schema information
            schema = response_format.model_json_schema()
            format_instruction = f"Please respond with a JSON object that is compliant with this schema from the .model_json_schema() of a Pydantic model:\n\n{json.dumps(schema, indent=2)}"
            request_type = "structured"
        elif is_json_object:
            # Generic JSON object
            format_instruction = "Respond in JSON format."
            request_type = "json_object"
        else:
            logger.error(f"Unsupported response_format: {response_format}")
            return None

        # Add format instruction to messages
        enhanced_messages = messages + [
            {"role": "user", "content": [{"type": "text", "text": format_instruction}]}
        ]

        for attempt in range(MAX_LLM_RETRIES):
            try:
                kwargs = {
                    "model": model,
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

                if system_content:
                    kwargs["system"] = system_content

                response = self.anthropic_client.messages.create(**kwargs)

                # Extract JSON content and add opening brace back
                json_content = "{" + response.content[0].text

                # Track usage (only on first attempt to avoid double-counting retries)
                if attempt == 0:
                    self._track_usage(
                        model=model,
                        input_tokens=response.usage.input_tokens,
                        output_tokens=response.usage.output_tokens,
                        request_type=request_type,
                    )

                # Clean up JSON content
                try:
                    json_data = json.loads(json_content)
                except json.JSONDecodeError:
                    # Try cleaning control characters
                    cleaned_json = re.sub(r"[\x00-\x1F]+", "", json_content)
                    json_data = json.loads(cleaned_json)
                    json_content = cleaned_json

                # Return based on format type
                if is_pydantic:
                    return response_format.model_validate(json_data)
                else:
                    return json_content

            except (json.JSONDecodeError, ValidationError) as e:
                logger.warning(f"Attempt {attempt + 1} failed: {e}")
                if attempt < MAX_LLM_RETRIES - 1:
                    # Add error message to conversation and retry - FIXED: use "user" role
                    enhanced_messages.append(
                        {
                            "role": "assistant",
                            "content": [{"type": "text", "text": json_content}],
                        }
                    )
                    enhanced_messages.append(
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"The previous response failed validation with error: {e}\nPlease provide a corrected JSON response that matches the format exactly.",
                                }
                            ],
                        }
                    )
                else:
                    logger.error(
                        f"Failed to get valid structured response after {MAX_LLM_RETRIES} attempts: {e}"
                    )
                    return None

        return None

    def _anthropic_tools_response(
        self,
        messages: list[dict],
        model: str,
        temperature: float,
        tools: list,
        system_content: str | None = None,
    ) -> dict | None:
        """Get tools/function calling response from Anthropic using native SDK."""
        try:
            kwargs = {
                "model": model,
                "max_tokens": 4096,
                "temperature": temperature,
                "messages": messages,
                "tools": tools,
            }

            if system_content:
                kwargs["system"] = system_content

            response = self.anthropic_client.messages.create(**kwargs)

            # Track usage
            self._track_usage(
                model=model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                request_type="tools",
            )

            # Convert Anthropic response format to OpenAI-compatible format for backward compatibility
            content_text = (
                response.content[0].text
                if response.content and hasattr(response.content[0], "text")
                else None
            )
            tool_calls = None

            # Extract tool calls from response content
            for content_block in response.content:
                if hasattr(content_block, "type") and content_block.type == "tool_use":
                    if tool_calls is None:
                        tool_calls = []
                    tool_calls.append(content_block)

            return {
                "content": content_text,
                "tool_calls": tool_calls,
                "role": "assistant",
            }

        except Exception as e:
            logger.error(f"Anthropic tools response error: {e}")
            return None

    async def a_get_response(
        self,
        messages: list[dict],
        model: Literal["gpt-4.1-nano", "sonnet-4", "gemini-2.5-pro"],
        temperature: float = 0,
        response_format: BaseModel = None,
        tools: list = None,
    ):
        return self.get_response(messages, model, temperature, response_format, tools)

    def get_response(
        self,
        messages: list[dict],
        model: Literal["gpt-4.1-nano", "sonnet-4", "gemini-2.5-pro"],
        temperature: float = 0,
        response_format: BaseModel | dict = None,
        tools: list = None,
    ):
        # Map to actual model name
        actual_model = MODEL_MAPPING.get(model, model)

        for x in range(FAIL_STRUCTURE_RESPONSE_RETRIES):
            try:
                if self._is_anthropic_model(model):
                    # Use native Anthropic SDK with message conversion
                    anthropic_messages, system_content = (
                        self._convert_openai_to_anthropic_messages(messages)
                    )

                    if tools:
                        result = self._anthropic_tools_response(
                            anthropic_messages,
                            actual_model,
                            temperature,
                            tools,
                            system_content,
                        )
                        if result is None:
                            raise Exception("Anthropic tools response returned None")
                        return type(
                            "MockMessage", (), result
                        )()  # Convert dict to object for compatibility
                    elif response_format:
                        # Unified handler for both Pydantic models and JSON objects
                        result = self._anthropic_structured_response(
                            anthropic_messages,
                            actual_model,
                            temperature,
                            response_format,
                            system_content,
                        )
                        if result is None:
                            raise Exception(
                                "Anthropic structured response returned None"
                            )
                        return result
                    else:
                        result = self._anthropic_text_response(
                            anthropic_messages,
                            actual_model,
                            temperature,
                            system_content,
                        )
                        if result is None:
                            raise Exception("Anthropic text response returned None")
                        return type(
                            "MockMessage", (), {"content": result}
                        )()  # Convert to object for compatibility
                else:
                    # Use existing logic for OpenAI and Gemini models
                    client = self._get_client_for_model(model)

                    if tools:
                        return self._get_response_tools(
                            messages, actual_model, temperature, tools, client
                        )
                    if response_format:
                        return self._get_response_structured(
                            messages, actual_model, temperature, response_format, client
                        )
                    return self._get_response_text_only(
                        messages, actual_model, temperature, client
                    )
            except ValidationError as e:
                logger.error(f"Validation error: {e}")
                delay_exp(e, x)
            except Exception as e:
                logger.error(f"Error: {e}")
                delay_exp(e, x)

        # If all retries failed, return None to prevent crashes
        logger.error(
            f"All {FAIL_STRUCTURE_RESPONSE_RETRIES} attempts failed for model {model}"
        )
        return None

    def _get_response_text_only(self, messages, model, temperature, client):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
        )

        # Track usage for completions API
        self._track_usage(
            model=model,
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
            request_type="text",
        )

        return response.choices[0].message

    def _get_response_tools(self, messages, model, temperature, tools, client):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            tools=tools,
        )

        # Track usage for completions API
        self._track_usage(
            model=model,
            input_tokens=response.usage.prompt_tokens,
            output_tokens=response.usage.completion_tokens,
            request_type="tools",
        )

        return response.choices[0].message

    def _get_response_structured(
        self, messages, model, temperature, response_format, client
    ) -> BaseModel | str:
        if issubclass(response_format, BaseModel):
            # Handle Anthropic models with native client and prefill
            if self._is_anthropic_model(model):
                return self._get_anthropic_pydantic_response(
                    messages, model, temperature, response_format
                )
            else:
                # Use OpenAI structured output for other models
                response = client.beta.chat.completions.parse(
                    messages=messages,
                    model=model,
                    temperature=temperature,
                    response_format=response_format,
                )

                # Track usage for completions API
                self._track_usage(
                    model=model,
                    input_tokens=response.usage.prompt_tokens,
                    output_tokens=response.usage.completion_tokens,
                    request_type="structured",
                )

                return response.choices[0].message.parsed
        elif response_format == {"type": "json_object"}:
            error_msg = []
            for _ in range(FAIL_STRUCTURE_RESPONSE_RETRIES):
                if self._is_anthropic_model(model):
                    # Use Anthropic native client with prefill
                    enhanced_messages = (
                        messages
                        + error_msg
                        + [
                            {
                                "role": "user",
                                "content": "Respond in JSON format.",
                            }
                        ]
                    )
                    response = self.anthropic_client.messages.create(
                        model=model,
                        max_tokens=4096,
                        temperature=temperature,
                        messages=enhanced_messages
                        + [{"role": "assistant", "content": "{"}],
                    )
                    json_str = "{" + response.content[0].text

                    # Track usage for successful Anthropic calls
                    if (
                        _ == 0
                    ):  # Only track on first attempt to avoid double-counting retries
                        self._track_usage(
                            model=model,
                            input_tokens=response.usage.input_tokens,
                            output_tokens=response.usage.output_tokens,
                            request_type="json_object",
                        )
                else:
                    # Use OpenAI-compatible client
                    response = client.chat.completions.create(
                        model=model,
                        messages=messages + error_msg,
                        temperature=temperature,
                        response_format=response_format,
                    )
                    json_str = response.choices[0].message.content

                    # Track usage for completions API (only on first attempt)
                    if _ == 0:
                        self._track_usage(
                            model=model,
                            input_tokens=response.usage.prompt_tokens,
                            output_tokens=response.usage.completion_tokens,
                            request_type="json_object",
                        )

                try:
                    json.loads(json_str)
                    return json_str
                except:
                    json_str = re.sub(r"[\x00-\x1F]+", "", json_str)
                try:
                    json.loads(json_str)
                    return json_str
                except Exception as e:
                    error_msg.append(
                        {
                            "role": "system",
                            "content": f"The JSON returned is:\n{json_str}\n\nIt cannot be converted by json.loads with the following error:\n{e}\n\nGenerate a new JSON without the error.",
                        }
                    )
        else:
            # This is not expected, just leaving it in case there are acceptable values I'm not aware of.
            logging.warning(
                "Unknown response_format input, expected BaseModel or {'type': 'json_object'} and got %s",
                response_format,
            )
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                response_format=response_format,
            )

            # Track usage for completions API
            self._track_usage(
                model=model,
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
                request_type="unknown",
            )

            return response.choices[0].message.content

    def get_response_pdf(
        self,
        pdf_source: Union[str, Path],
        prompt: str,
        temperature: float = 0,
        response_format: Optional[Type[BaseModel]] = None,
    ) -> Union[str, BaseModel]:
        """
        Get response from Google Gemini with inline PDF support.

        Args:
            pdf_source: Path to local PDF file or URL to web PDF
            prompt: Text prompt to send along with the PDF
            temperature: Temperature for response generation
            response_format: Optional Pydantic model for structured response

        Returns:
            String response or Pydantic model instance
        """

        # Check if pdf_source ends with .pdf extension
        if not str(pdf_source).lower().endswith(".pdf"):
            return "Not a pdf"

        # Use the single Google model from MODEL_MAPPING
        model = "gemini-2.5-pro"

        # Determine if source is URL or local file
        if isinstance(pdf_source, str) and (
            pdf_source.startswith("http://") or pdf_source.startswith("https://")
        ):
            # Web URL
            try:
                pdf_data = httpx.get(pdf_source).content
            except Exception as e:
                raise ValueError(f"Failed to fetch PDF from URL {pdf_source}: {e}")
        else:
            # Local file
            pdf_path = Path(pdf_source)
            if not pdf_path.exists():
                raise FileNotFoundError(f"PDF file not found: {pdf_path}")
            pdf_data = pdf_path.read_bytes()

        # Create PDF part using inline bytes
        pdf_part = types.Part.from_bytes(
            data=pdf_data,
            mime_type="application/pdf",
        )

        # Prepare the content
        contents = [pdf_part, prompt]

        # Configure the request
        config = {
            "temperature": temperature,
        }

        # Add structured output configuration if response_format is provided
        if response_format:
            config["response_mime_type"] = "application/json"
            config["response_schema"] = response_format

        try:
            # Make the request
            response = self.gemini_client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )

            # Track usage using usage_metadata
            if hasattr(response, "usage_metadata"):
                input_tokens = response.usage_metadata.prompt_token_count
                output_tokens = response.usage_metadata.candidates_token_count

                self._track_usage(
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    request_type="pdf_processing",
                )
            else:
                logger.warning(
                    f"Google Gemini response missing usage_metadata for PDF processing"
                )
                self._track_usage(
                    model=model,
                    input_tokens=0,
                    output_tokens=0,
                    request_type="pdf_processing",
                )

            # Handle structured response
            if response_format:
                return response.parsed

            return response.text

        except Exception as e:
            logger.error(f"Error in get_response_pdf: {e}")
            raise

    def search_web(self, query: str, temperature: float = 0) -> str:
        """
        Perform web search using Google's grounding tool.

        Args:
            query: The search query
            temperature: Temperature for response generation

        Returns:
            String response with grounded web search results
        """
        # Define the grounding tool
        grounding_tool = types.Tool(google_search=types.GoogleSearch())

        # Configure generation settings
        config = types.GenerateContentConfig(
            tools=[grounding_tool],
            temperature=temperature,
        )

        # Use fixed model for web search
        model = "gemini-2.5-pro"

        try:
            # Make the request
            response = self.gemini_client.models.generate_content(
                model=model,
                contents=query,
                config=config,
            )

            # Track usage if available
            if hasattr(response, "usage_metadata"):
                input_tokens = response.usage_metadata.prompt_token_count
                output_tokens = response.usage_metadata.candidates_token_count

                self._track_usage(
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    request_type="web_search",
                )
            else:
                logger.warning(
                    f"Google Gemini response missing usage_metadata for web search"
                )
                self._track_usage(
                    model=model,
                    input_tokens=0,
                    output_tokens=0,
                    request_type="web_search",
                )

            # Add citations to the response
            return add_citations(response)

        except Exception as e:
            logger.error(f"Error in search_web: {e}")
            raise


def get_actual_url_from_redirect(redirect_url: str) -> str:
    """Extract actual URL from Google redirect (generalised from get_pdf_url_from_redirect)."""
    try:
        response_redirect = requests.get(
            redirect_url, allow_redirects=False, timeout=10
        )
        if response_redirect.status_code in [301, 302]:
            redirect_location = response_redirect.headers.get("Location", "")
            if redirect_location:
                return redirect_location

        # If no direct redirect, try to extract from HTML
        response_redirect = requests.get(redirect_url, timeout=10)
        # Look for common URL patterns in the HTML
        url_match = re.search(r'HREF="([^"]*)"', response_redirect.text)
        if url_match:
            return url_match.group(1)

        return redirect_url  # Return original if no redirect found
    except Exception as e:
        logger.warning(f"Failed to resolve redirect {redirect_url}: {e}")
        return redirect_url


def add_citations(response):
    """Add citations to the response text based on grounding metadata."""
    if not hasattr(response, "candidates") or not response.candidates:
        return response.text

    candidate = response.candidates[0]
    if not hasattr(candidate, "grounding_metadata") or not candidate.grounding_metadata:
        return response.text

    text = response.text
    grounding_metadata = candidate.grounding_metadata

    if not hasattr(grounding_metadata, "grounding_supports") or not hasattr(
        grounding_metadata, "grounding_chunks"
    ):
        return text

    supports = grounding_metadata.grounding_supports
    chunks = grounding_metadata.grounding_chunks

    # Sort supports by end_index in descending order to avoid shifting issues when inserting
    sorted_supports = sorted(supports, key=lambda s: s.segment.end_index, reverse=True)

    for support in sorted_supports:
        end_index = support.segment.end_index
        if support.grounding_chunk_indices:
            # Create citation string like [1](link1)[2](link2)
            citation_links = []
            for i in support.grounding_chunk_indices:
                if i < len(chunks):
                    uri = chunks[i].web.uri

                    # Convert Google redirect URLs to actual URLs
                    if "vertexaisearch.cloud.google.com/grounding-api-redirect" in uri:
                        uri = get_actual_url_from_redirect(uri)

                    citation_links.append(f"[{i + 1}]({uri})")

            citation_string = ", ".join(citation_links)
            text = text[:end_index] + citation_string + text[end_index:]

    return text
