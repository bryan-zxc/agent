# Config Module

Configuration management and application constants for the agent system.

## Modules

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

**Environment**
- `environment`: Current environment ("development")
- `debug_mode`: Enable debug mode (False)

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
export OPENAI_API_KEY="your-openai-api-key"
export GEMINI_API_KEY="your-gemini-api-key"
export ANTHROPIC_API_KEY="your-anthropic-api-key"
export DEBUG_MODE=true
export ENVIRONMENT="production"
```

## Best Practices

- Use constants for all configurable values
- Environment-specific settings should use environment variables
- Validate configuration on startup
- Group related settings in logical sections
- Provide sensible defaults for all settings