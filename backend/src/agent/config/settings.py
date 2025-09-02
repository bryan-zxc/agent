from pydantic import Field, ConfigDict
from pydantic_settings import BaseSettings
from typing import Optional
from .mcp_config import load_mcp_config, MCPConfig


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

    # Model Configuration
    router_model: str = Field(
        description="Model used by RouterAgent"
    )
    planner_model: str = Field(
        description="Model used by PlannerAgent"
    )
    worker_model: str = Field(
        description="Model used by WorkerAgent"
    )

    # Database Configuration
    database_schema_version: int = Field(
        default=1, description="Current database schema version"
    )
    database_auto_migrate: bool = Field(
        default=True, description="Enable automatic database migrations"
    )
    database_path: str = Field(
        default="./db/agent_database.db", description="Path to SQLite database file"
    )

    # File Storage Configuration
    collaterals_base_path: str = Field(
        default="/app/files/agent_collaterals",
        description="Base path for agent collateral files",
    )
    execution_plan_model_filename: str = Field(
        default="execution_plan_model.json",
        description="Filename for execution plan model in planner directory",
    )
    current_task_filename: str = Field(
        default="current_task.json",
        description="Filename for current task in planner directory",
    )
    worker_message_history_filename: str = Field(
        default="worker_message_history.json",
        description="Filename for worker message history in planner directory",
    )
    answer_template_filename: str = Field(
        default="answer_template.md",
        description="Filename for answer template in planner directory",
    )
    wip_answer_template_filename: str = Field(
        default="wip_answer_template.md",
        description="Filename for work-in-progress answer template in planner directory",
    )

    # Environment
    environment: str = Field(default="development", description="Current environment")
    debug_mode: bool = Field(default=False, description="Enable debug mode")
    
    # MCP Integration
    mcp_enabled: bool = Field(
        default=True,
        description="Enable MCP integration globally"
    )
    
    # Load MCP configuration
    @property
    def mcp_config(self) -> MCPConfig:
        """Lazy load MCP configuration."""
        if not hasattr(self, '_mcp_config'):
            self._mcp_config = load_mcp_config()
        return self._mcp_config
    
    # Convenience accessors
    @property
    def mcp_router_enabled(self) -> bool:
        return self.mcp_enabled and self.mcp_config.router_enabled
    
    @property
    def mcp_planner_enabled(self) -> bool:
        return self.mcp_enabled and self.mcp_config.planner_enabled
    
    @property
    def mcp_worker_enabled(self) -> bool:
        return self.mcp_enabled and self.mcp_config.worker_enabled

    model_config = ConfigDict(
        env_file=[".env", ".env.local"],  # Load both files, .env.local overrides .env
        env_prefix="",  # No prefix for API keys
    )


# Global settings instance
settings = AgentSettings()
