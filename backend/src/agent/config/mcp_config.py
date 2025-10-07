"""
MCP Server Configuration Module.

Provides configuration for Model Context Protocol (MCP) servers,
supporting both YAML files and environment variables for secure API key management.
"""

from typing import List, Dict, Optional
from pydantic import BaseModel, Field
import yaml
from pathlib import Path
import os
import json
import logging

logger = logging.getLogger(__name__)


class MCPServerDefinition(BaseModel):
    """Definition of an MCP server to connect to."""
    name: str = Field(..., description="Unique name for this server")
    server_type: str = Field(..., description="Type: 'stdio', 'http', 'websocket'")
    command: Optional[str] = Field(None, description="Command for stdio servers")
    url: Optional[str] = Field(None, description="URL for http/websocket servers")
    args: List[str] = Field(default_factory=list, description="Command arguments")
    env: Dict[str, str] = Field(default_factory=dict, description="Environment variables")
    enabled: bool = Field(True, description="Whether to connect to this server")
    description: Optional[str] = None
    auto_reconnect: bool = Field(True, description="Auto-reconnect on disconnect")


class MCPConfig(BaseModel):
    """MCP configuration for the agent system."""
    servers: List[MCPServerDefinition] = Field(default_factory=list)
    auto_discover: bool = Field(True, description="Auto-discover local MCP servers")
    refresh_interval: int = Field(300, description="Tool refresh interval in seconds")
    max_tool_rounds: int = Field(10, description="Max rounds of tool calling")
    
    # Per-agent configuration - these values are set from settings in merge_with_env()
    router_servers: List[str] = Field(
        default_factory=lambda: ["github", "filesystem", "web_search", "agent_tools"],
        description="Servers available to router"
    )
    planner_servers: List[str] = Field(
        default_factory=lambda: ["filesystem", "github"],
        description="Servers available to planner"
    )
    worker_servers: List[str] = Field(
        default_factory=lambda: ["filesystem"],
        description="Servers available to workers"
    )
    
    @classmethod
    def from_yaml(cls, path: Path) -> "MCPConfig":
        """Load configuration from YAML file."""
        if not path.exists():
            return cls()
        
        with open(path, 'r') as f:
            data = yaml.safe_load(f) or {}
        
        # Process environment variable substitution in YAML
        data = cls._substitute_env_vars(data)
        
        return cls(**data)
    
    @classmethod
    def _substitute_env_vars(cls, data: Dict) -> Dict:
        """Recursively substitute ${ENV_VAR} placeholders with actual environment values."""
        if isinstance(data, dict):
            result = {}
            for key, value in data.items():
                if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                    env_var = value[2:-1]
                    result[key] = os.getenv(env_var, value)
                elif isinstance(value, (dict, list)):
                    result[key] = cls._substitute_env_vars(value)
                else:
                    result[key] = value
            return result
        elif isinstance(data, list):
            return [cls._substitute_env_vars(item) for item in data]
        else:
            return data
    
    @classmethod
    def from_env(cls) -> "MCPConfig":
        """Create configuration from environment variables."""
        # Import settings here to avoid circular import
        from .settings import settings
        
        servers = []
        
        # GitHub MCP server
        if settings.github_personal_access_token and settings.mcp_github_enabled:
            servers.append(MCPServerDefinition(
                name="github",
                server_type="stdio",
                command="npx",
                args=["@modelcontextprotocol/server-github"],
                env={"GITHUB_PERSONAL_ACCESS_TOKEN": settings.github_personal_access_token},
                description="GitHub API integration"
            ))
        
        # Filesystem MCP server
        if settings.mcp_filesystem_enabled:
            # Use /app as default root since that's the working directory in container
            filesystem_root = settings.mcp_filesystem_root
            servers.append(MCPServerDefinition(
                name="filesystem",
                server_type="stdio",
                command="npx",
                args=[
                    "@modelcontextprotocol/server-filesystem",
                    filesystem_root
                ],
                description=f"Local filesystem access (root: {filesystem_root})"
            ))
        
        # Agent native tools MCP server
        if settings.mcp_agent_tools_enabled:
            servers.append(MCPServerDefinition(
                name="agent_tools",
                server_type="stdio",
                command="uv",
                args=["run", "python", "-m", "src.agent.utils.tools"],
                env={
                    "ROUTER_MODEL": settings.router_model,
                    "PLANNER_MODEL": settings.planner_model,
                    "WORKER_MODEL": settings.worker_model,
                    # Pass API keys so the subprocess can access them
                    "GEMINI_API_KEY": settings.gemini_api_key or "",
                    "OPENAI_API_KEY": settings.openai_api_key or "",
                    "ANTHROPIC_API_KEY": settings.anthropic_api_key or "",
                    # Pass database credentials for agent module import
                    "POSTGRES_PASSWORD": settings.postgres_password or "",
                    "POSTGRES_HOST": settings.postgres_host or "",
                    "POSTGRES_PORT": str(settings.postgres_port) if settings.postgres_port else "",
                    "PROJECT_NAME": settings.project_name or "",  # Database name is project_name
                    "POSTGRES_USER": settings.postgres_user or "",
                },
                description="Native agent tools for web search and PDF processing",
                enabled=True
            ))
        
        # Custom MCP servers from env
        custom_servers_json = settings.mcp_custom_servers
        if custom_servers_json:
            try:
                custom_servers = json.loads(custom_servers_json)
                for server_data in custom_servers:
                    servers.append(MCPServerDefinition(**server_data))
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Failed to parse MCP_CUSTOM_SERVERS: {e}")
        
        # Create config with servers only
        return cls(servers=servers)
    
    def merge_with_env(self) -> "MCPConfig":
        """Merge YAML config with environment variables (env takes precedence)."""
        # Import settings here to avoid circular import
        from .settings import settings
        
        env_config = MCPConfig.from_env()
        
        # Merge servers (env servers override yaml servers with same name)
        server_map = {s.name: s for s in self.servers}
        for env_server in env_config.servers:
            server_map[env_server.name] = env_server
        
        self.servers = list(server_map.values())
        
        return self


# Default configuration
DEFAULT_MCP_CONFIG = MCPConfig(
    servers=[
        MCPServerDefinition(
            name="filesystem",
            server_type="stdio",
            command="npx",
            args=["@modelcontextprotocol/server-filesystem", "/app"],
            description="File system access (default: /app)",
            enabled=True
        ),
    ]
)


def load_mcp_config(config_path: Optional[Path] = None) -> MCPConfig:
    """
    Load MCP configuration from file and environment.
    
    Args:
        config_path: Optional path to config file. Defaults to config/mcp_config.yaml
        
    Returns:
        Loaded MCP configuration with environment overrides applied
    """
    if config_path is None:
        config_path = Path("config/mcp_config.yaml")
    
    if config_path.exists():
        config = MCPConfig.from_yaml(config_path)
        config = config.merge_with_env()
    else:
        # Try environment only
        config = MCPConfig.from_env()
        
        # Fall back to defaults if no env config
        if not config.servers:
            config = DEFAULT_MCP_CONFIG
    
    return config