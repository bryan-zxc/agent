import os
import random
import time
import json
import re
import logging
import enum
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
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

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
        "threshold": 200000  # 200k token threshold
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
    timestamp = Column(DateTime, nullable=False, default=datetime.now)
    model = Column(String(100), nullable=False)
    input_tokens = Column(Integer, nullable=False)
    output_tokens = Column(Integer, nullable=False)
    cost = Column(Float, nullable=False)
    request_type = Column(Enum(RequestType), nullable=False)
    caller = Column(String(100), nullable=False)


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
    def __init__(self, db_path: str | Path = Path("/app/db/llm_usage.db"), caller: str = "general"):
        # Load settings which automatically loads .env and .env.local
        settings = AgentSettings()

        # Initialize clients with API keys from settings
        self.openai_client = OpenAI(api_key=settings.openai_api_key)
        self.gemini_client = OpenAI(
            api_key=settings.gemini_api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
        self.anthropic_openai_client = OpenAI(
            api_key=settings.anthropic_api_key,
            base_url="https://api.anthropic.com/v1/",
        )
        self.anthropic_client = Anthropic(api_key=settings.anthropic_api_key)
        self.google_client = genai.Client(api_key=settings.gemini_api_key)

        # Store caller for usage tracking
        self.caller = caller
        
        # SQLAlchemy setup
        self.engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

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
        """Select the appropriate client based on the model name."""
        if model.startswith("gpt"):
            return self.openai_client
        elif model.startswith("gemini"):
            return self.gemini_client
        elif self._is_anthropic_model(model):
            return self.anthropic_openai_client
        else:
            raise ValueError(f"Unknown model: {model}")

    def _is_anthropic_model(self, model: str):
        """Check if model is an Anthropic model."""
        return model.startswith("sonnet") or model.startswith("claude")

    def _get_anthropic_pydantic_response(
        self, messages, model, temperature, response_format: BaseModel
    ) -> BaseModel:
        """Get structured response from Anthropic using Pydantic model."""
        schema = response_format.model_json_schema()

        # Add schema information to the messages
        enhanced_messages = messages + [
            {
                "role": "user",
                "content": f"Please respond with a JSON object that is compliant with this schema from the .model_json_schema() of a Pydantic model:\n\n{json.dumps(schema, indent=2)}",
            }
        ]

        for attempt in range(MAX_LLM_RETRIES):
            try:
                # Use prefill with assistant message containing "{"
                response = self.anthropic_client.messages.create(
                    model=model,
                    temperature=temperature,
                    messages=enhanced_messages
                    + [{"role": "assistant", "content": "{"}],
                )

                # Extract JSON content and add opening brace back
                json_content = "{" + response.content[0].text

                # Track usage
                self._track_usage(
                    model=model,
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    request_type="structured",
                )

                # Parse JSON and validate with Pydantic
                json_data = json.loads(json_content)
                return response_format.model_validate(json_data)

            except (json.JSONDecodeError, ValidationError) as e:
                logger.warning(f"Attempt {attempt + 1} failed: {e}")
                if attempt < MAX_LLM_RETRIES - 1:
                    # Add error message to conversation and retry
                    enhanced_messages.append(
                        {
                            "role": "assistant",
                            "content": json_content,
                        }
                    )
                    enhanced_messages.append(
                        {
                            "role": "user",
                            "content": f"The previous response failed validation with error: {e}\nPlease provide a corrected JSON response that matches the schema exactly.",
                        }
                    )
                else:
                    raise e

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
        # Select the appropriate client based on model
        client = self._get_client_for_model(model)
        # Map to actual model name
        actual_model = MODEL_MAPPING.get(model, model)

        for x in range(FAIL_STRUCTURE_RESPONSE_RETRIES):
            try:
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
        # Use the single Google model from MODEL_MAPPING
        model = "gemini-2.5-pro"
        
        # Determine if source is URL or local file
        if isinstance(pdf_source, str) and (pdf_source.startswith('http://') or pdf_source.startswith('https://')):
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
            mime_type='application/pdf',
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
            response = self.google_client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
            
            # Track usage using usage_metadata
            if hasattr(response, 'usage_metadata'):
                input_tokens = response.usage_metadata.prompt_token_count
                output_tokens = response.usage_metadata.candidates_token_count
                
                self._track_usage(
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    request_type="pdf_processing",
                )
            else:
                logger.warning(f"Google Gemini response missing usage_metadata for PDF processing")
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

    def search_web(self, query: str, temperature: float = 0, response_format: Optional[Type[BaseModel]] = None) -> Union[str, BaseModel]:
        """
        Perform web search using Google's grounding tool.
        
        Args:
            query: The search query
            temperature: Temperature for response generation
            response_format: Optional Pydantic model for structured response
            
        Returns:
            String response or Pydantic model instance with grounded web search results
        """
        # Define the grounding tool
        grounding_tool = types.Tool(
            google_search=types.GoogleSearch()
        )
        
        # Configure generation settings
        config = types.GenerateContentConfig(
            tools=[grounding_tool],
            temperature=temperature,
        )
        
        # Add structured output configuration if response_format is provided
        if response_format:
            config.response_mime_type = "application/json"
            config.response_schema = response_format
        
        # Use fixed model for web search
        model = "gemini-2.5-pro"
        
        try:
            # Make the request
            response = self.google_client.models.generate_content(
                model=model,
                contents=query,
                config=config,
            )
            
            # Track usage if available
            if hasattr(response, 'usage_metadata'):
                input_tokens = response.usage_metadata.prompt_token_count
                output_tokens = response.usage_metadata.candidates_token_count
                
                self._track_usage(
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    request_type="web_search",
                )
            else:
                logger.warning(f"Google Gemini response missing usage_metadata for web search")
                self._track_usage(
                    model=model,
                    input_tokens=0,
                    output_tokens=0,
                    request_type="web_search",
                )
            
            # Handle structured response
            if response_format:
                return response.parsed
            
            return response.text
            
        except Exception as e:
            logger.error(f"Error in search_web: {e}")
            raise
