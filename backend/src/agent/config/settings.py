from pydantic import Field
from pydantic_settings import BaseSettings
from typing import Optional


class AgentSettings(BaseSettings):
    """Configuration settings for the agent library."""

    # API Keys (loaded from .env.local)
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API key")
    gemini_api_key: Optional[str] = Field(default=None, description="Gemini API key")
    anthropic_api_key: Optional[str] = Field(
        default=None, description="Anthropic API key"
    )

    # Task Configuration
    max_retry_tasks: int = Field(
        default=5, description="Maximum retry attempts for failed tasks"
    )
    failed_task_limit: int = Field(
        default=3, description="Maximum failed tasks before termination"
    )

    # Processing Configuration
    min_image_tokens: int = Field(
        default=64, description="Minimum tokens for image processing"
    )

    # Environment
    environment: str = Field(default="development", description="Current environment")
    debug_mode: bool = Field(default=False, description="Enable debug mode")

    class Config:
        env_file = [".env", ".env.local"]  # Load both files, .env.local overrides .env
        env_prefix = ""  # No prefix for API keys


# Global settings instance
settings = AgentSettings()
