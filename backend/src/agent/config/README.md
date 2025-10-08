# Config Module

Configuration management and application constants for the agent system.

## Modules

### `agent_names.py`
Character names for agent personality assignment.

#### Character Name Lists

**`PLANNER_NAMES`**
- Names assigned to PlannerAgent instances for personality
- **Sources:**
  - Bluey adults: Uncle Stripe, Aunt Trixie, Uncle Rad, Frisky, etc.
  - Peppa Pig adults: Daddy Pig, Mummy Pig, Grandpa Pig, etc.
  - Ryder from Paw Patrol (special inclusion)
  - Disney Princesses: Snow White, Cinderella, Aurora, Ariel, Belle, etc.

**`WORKER_NAMES`** 
- Names assigned to WorkerAgent instances for personality
- **Sources:**
  - Paw Patrol dogs: Marshall, Rubble, Chase, Rocky, etc.
  - Sofia the First children: Sofia, Amber, James, etc.
  - Spidey and His Amazing Friends: Peter Parker, Miles Morales, etc.
  - Peppa Pig children: Peppa, George, Rebecca Rabbit, etc.
  - Bluey children: Bluey, Bingo, Muffin, Socks, etc.

#### Functions

**`get_random_planner_name()`**
- Returns a random name from PLANNER_NAMES list
- Used during PlannerAgent creation when no specific name provided

**`get_random_worker_name()`**
- Returns a random name from WORKER_NAMES list  
- Used during WorkerAgent creation (always random)

### `constants.py`
Application-wide constants and configuration values.

#### Constants

**API Configuration**
- `DEFAULT_TIMEOUT`: Default API timeout (120000ms / 2 minutes)
- `MAX_TIMEOUT`: Maximum allowed timeout (600000ms / 10 minutes)

**File Processing**
- `SUPPORTED_IMAGE_FORMATS`: Set of supported image file extensions
- `SUPPORTED_DOCUMENT_FORMATS`: Set of supported document file extensions  
- `SUPPORTED_DATA_FORMATS`: Set of supported data file extensions

**Image Processing**
- `DEFAULT_IMAGE_QUALITY`: Default quality setting for image processing (95)
- `MAX_IMAGE_SIZE`: Maximum image dimensions in pixels (4096x4096)

**Logging**
- `LOG_FORMAT`: Standard log message format string
- `DEFAULT_LOG_LEVEL`: Default logging level ("INFO")

**Security**
- `MAX_CODE_EXECUTION_TIME`: Maximum time allowed for code execution (30 seconds)
- `ALLOWED_IMPORTS`: Set of Python modules allowed in sandboxed execution
- `DEFAULT_DB_TIMEOUT`: Default database operation timeout (30 seconds)

### `settings.py`
Application settings management using Pydantic BaseSettings.

#### Classes

**`AgentSettings(BaseSettings)`**
- Configuration class that manages all application settings
- Supports environment variable loading and validation
- Integrates with MCP configuration system

**Configuration Sections:**

**API Keys**
- `openai_api_key`: OpenAI API key (loaded from environment)
- `gemini_api_key`: Gemini API key (loaded from environment)
- `anthropic_api_key`: Anthropic API key (loaded from environment)

**Task Configuration**
- `max_retry_attempts`: Maximum retry attempts for failed tasks (5)
- `failed_task_limit`: Maximum failed tasks before termination (3)

**Processing Configuration**
- `min_image_tokens`: Minimum tokens for image processing (64)

**Model Configuration**
- `router_model`: Model used by RouterAgent (gpt-5-mini - the only accepted OpenAI model)
- `planner_model`: Model used by PlannerAgent (gemini-2.5-pro)
- `worker_model`: Model used by WorkerAgent (sonnet-4.5)

**Database Configuration**
- `database_path`: Path to SQLite database file
- `database_auto_migrate`: Enable automatic migrations
- `database_schema_version`: Current schema version

**MCP Integration**
- `mcp_enabled`: Enable MCP integration globally
- `mcp_config`: Lazy-loaded MCP configuration (property)
- `mcp_router_enabled`: Enable MCP for router (property)
- `mcp_planner_enabled`: Enable MCP for planner (property)
- `mcp_worker_enabled`: Enable MCP for workers (property)

**Environment**
- `environment`: Current environment ("development")
- `debug_mode`: Enable debug mode (False)

### `mcp_config.py`
Model Context Protocol (MCP) server configuration management.

#### Classes

**`MCPServerDefinition(BaseModel)`**
- Definition for individual MCP servers
- Supports stdio, HTTP, and WebSocket server types
- **Fields:**
  - `name`: Unique server identifier
  - `server_type`: Type of server (stdio/http/websocket)
  - `command`: Command for stdio servers
  - `url`: URL for HTTP/WebSocket servers
  - `args`: Command arguments list
  - `env`: Environment variables dict
  - `enabled`: Whether to connect to this server
  - `description`: Optional server description
  - `auto_reconnect`: Auto-reconnect on disconnect

**`MCPConfig(BaseModel)`**
- Complete MCP configuration for the agent system
- **Fields:**
  - `servers`: List of MCPServerDefinition
  - `auto_discover`: Auto-discover local MCP servers
  - `refresh_interval`: Tool refresh interval in seconds
  - `max_tool_rounds`: Maximum rounds of tool calling
  - Per-agent server whitelists (router/planner/worker)

**Key Methods:**
- `from_yaml(path)`: Load configuration from YAML file
- `from_env()`: Create configuration from environment variables
- `merge_with_env()`: Merge YAML with environment (env takes precedence)

#### Functions

**`load_mcp_config(config_path)`**
- Load MCP configuration from file and environment
- Falls back to defaults if no configuration found
- Returns merged MCPConfig instance

#### Global Instance

**`settings`**
- Global settings instance available throughout the application
- Automatically loads from environment variables
- Falls back to `.env` and `.env.local` files

## Usage

### Accessing Settings
```python
from agent.config.settings import settings

# Get API keys
api_key = settings.openai_api_key

# Get task configuration  
max_retries = settings.max_retry_attempts
task_limit = settings.failed_task_limit

# Get processing configuration
min_tokens = settings.min_image_tokens

# Get MCP configuration
if settings.mcp_enabled:
    config = settings.mcp_config
    for server in config.servers:
        print(f"MCP Server: {server.name} ({server.server_type})")
```

### Using MCP Configuration
```python
from agent.config.mcp_config import load_mcp_config, MCPServerDefinition

# Load configuration from file and environment
config = load_mcp_config()

# Create custom server definition
custom_server = MCPServerDefinition(
    name="custom",
    server_type="http",
    url="http://localhost:8000",
    enabled=True
)

# Check per-agent enablement
from agent.config.settings import settings
if settings.mcp_router_enabled:
    # Router can use MCP tools
    pass
```

### Using Constants
```python
from agent.config.constants import SUPPORTED_IMAGE_FORMATS, MAX_CODE_EXECUTION_TIME

# Check file type support
if file_extension in SUPPORTED_IMAGE_FORMATS:
    process_image()

# Set execution timeout
timeout = MAX_CODE_EXECUTION_TIME
```

### Environment Variables
Configure settings via environment variables:
```bash
# API Keys (in .env.local)
export OPENAI_API_KEY="your-openai-api-key"
export GEMINI_API_KEY="your-gemini-api-key"
export ANTHROPIC_API_KEY="your-anthropic-api-key"

# MCP Configuration
export MCP_ENABLED=true
export MCP_ROUTER_ENABLED=true
export GITHUB_TOKEN="ghp_your_token"
export MCP_FILESYSTEM_ROOT="/workspace"

# Environment settings
export DEBUG_MODE=true
export ENVIRONMENT="production"
```

### YAML Configuration
Create `config/mcp_config.yaml`:
```yaml
servers:
  - name: github
    server_type: stdio
    command: npx
    args: ["@modelcontextprotocol/server-github"]
    env:
      GITHUB_TOKEN: ${GITHUB_TOKEN}  # From environment
    enabled: true

router_enabled: true
router_servers:
  - github
  - filesystem
```

## Best Practices

- Use constants for all configurable values
- Environment-specific settings should use environment variables
- Validate configuration on startup
- Group related settings in logical sections
- Provide sensible defaults for all settings