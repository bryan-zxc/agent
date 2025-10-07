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
    github_personal_access_token: Optional[str] = Field(
        default=None, description="GitHub Personal Access Token for MCP"
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

    # PostgreSQL Configuration
    postgres_host: str = Field(
        default="postgres", description="PostgreSQL host (docker service name or hostname)"
    )
    postgres_port: int = Field(
        default=5432, description="PostgreSQL port"
    )
    postgres_user: str = Field(
        default="agent_user", description="PostgreSQL username"
    )
    postgres_password: str = Field(
        description="PostgreSQL password - REQUIRED"
    )

    # Project Configuration
    project_name: str = Field(
        default="general", description="Project database name (auto-created on startup)"
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
    
    # MCP Server Configuration
    mcp_github_enabled: bool = Field(
        default=False,
        description="Enable GitHub MCP server"
    )
    mcp_filesystem_enabled: bool = Field(
        default=True,
        description="Enable filesystem MCP server"
    )
    mcp_filesystem_root: str = Field(
        default="/app",
        description="Root directory for filesystem MCP server"
    )
    mcp_agent_tools_enabled: bool = Field(
        default=True,
        description="Enable agent native tools MCP server"
    )
    mcp_custom_servers: Optional[str] = Field(
        default=None,
        description="JSON string of custom MCP server configurations"
    )
    
    # MCP Agent Configuration
    mcp_router_enabled: bool = Field(
        default=True,
        description="Enable MCP for router agent"
    )
    mcp_planner_enabled: bool = Field(
        default=True,
        description="Enable MCP for planner agent"
    )
    mcp_worker_enabled: bool = Field(
        default=False,
        description="Enable MCP for worker agent"
    )
    
    # Load MCP configuration
    @property
    def mcp_config(self) -> MCPConfig:
        """Lazy load MCP configuration."""
        if not hasattr(self, '_mcp_config'):
            self._mcp_config = load_mcp_config()
        return self._mcp_config

    model_config = ConfigDict(
        env_file=[".env", ".env.local"],  # Load both files, .env.local overrides .env
        env_prefix="",  # No prefix for API keys
    )


# Global settings instance
settings = AgentSettings()
