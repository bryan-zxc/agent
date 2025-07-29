from pydantic import Field
from pydantic_settings import BaseSettings
from typing import Optional


class AgentSettings(BaseSettings):
    """Configuration settings for the agent library."""
    
    # LLM Configuration
    default_model: str = Field(default="gpt-4.1-if-global", description="Default LLM model to use")
    default_temperature: float = Field(default=0.0, description="Default temperature for LLM calls")
    router_model: str = Field(default="gpt-4.1-mini-if-global", description="Model for routing decisions")
    
    # Task Configuration
    max_retry_attempts: int = Field(default=5, description="Maximum retry attempts for failed tasks")
    failed_task_limit: int = Field(default=3, description="Maximum failed tasks before termination")
    
    # Processing Configuration
    image_slice_height: int = Field(default=300, description="Height of image slices for processing")
    image_slice_overlap: int = Field(default=30, description="Overlap between image slices")
    min_image_tokens: int = Field(default=64, description="Minimum tokens for image processing")
    
    # Environment
    environment: str = Field(default="development", description="Current environment")
    debug_mode: bool = Field(default=False, description="Enable debug mode")
    
    class Config:
        env_file = ".env"
        env_prefix = "AGENT_"


# Global settings instance
settings = AgentSettings()