# Core Module

Core foundational classes and routing logic for the agent system.

## Modules

### `base.py`
Base agent class that provides common functionality for all agents in the system.

#### Classes

**`BaseAgent`**
- Foundation class for all agent implementations
- Provides common messaging and LLM interaction capabilities

**Key Methods:**
- `__init__()`: Initialize base agent with LLM service
- `add_message(role, content, image, verbose)`: Add messages to conversation history
  - Supports text content and image attachments
  - Handles multimodal content with base64 image encoding
  - Optional verbose logging for debugging

**Features:**
- **Multimodal Support**: Handles text and image content in conversations
- **Image Processing**: Automatic base64 encoding for image attachments
- **Conversation Management**: Maintains message history across interactions
- **Logging Integration**: Built-in logging with configurable verbosity

### `router.py`
Request routing and file processing orchestration.

#### Classes

**`RouterAgent(BaseAgent)`**
- Main entry point for processing user requests with attached files
- Routes requests to appropriate processing pipelines based on file types

**Key Methods:**
- `__init__(user_request, test_mode)`: Initialize with user request context
- `load_files()`: Process and categorize input files
- `invoke()`: Main routing logic - determines single vs multiple file processing
- `_invoke_single(files)`: Process files and delegate to PlannerAgent
- `get_response_to_user()`: Return formatted response to user

**File Processing Flow:**
1. **CSV Files**: Load into DuckDB database with metadata extraction
2. **PDF Files**: Extract content and determine if image-based
3. **Image Files**: Analyze content and categorize elements (charts, tables, etc.)

#### Constants

**`INSTRUCTION_LIBRARY`**
- Predefined processing instructions for different file types
- **Data Instructions**: SQL query guidance for CSV files
- **Image Instructions**: Specialized handling for:
  - `chart`: Chart reading and data extraction
  - `table`: Table content extraction as JSON
  - `diagram`: Diagram interpretation and mermaid conversion
  - `text`: Text extraction from images

## Usage Patterns

### Basic Agent Setup
```python
from agent.core.base import BaseAgent

class CustomAgent(BaseAgent):
    def __init__(self):
        super().__init__()
        self.add_message("system", "You are a helpful assistant")
```

### Request Routing
```python
from agent.core.router import RouterAgent

router = RouterAgent(user_request=request_object)
await router.invoke()
response = await router.get_response_to_user()
```

### Adding Multimodal Content
```python
agent = BaseAgent()
agent.add_message("user", "Analyze this image", image="path/to/image.png")
```

## File Type Processing

### Data Files (CSV)
- Automatic database table creation
- Column name sanitization and metadata extraction
- SQL query interface through DuckDB

### Document Files (PDF)
- Content extraction with text and images
- Metadata analysis (page count, text length, image count)
- Image-based PDF detection

### Image Files
- Content analysis and element categorization
- Support for charts, tables, diagrams, and text
- Error handling for unreadable images

## Integration Points

- **LLM Service**: All agents use unified LLM interface
- **PlannerAgent**: Router delegates complex tasks to planner
- **File Services**: Leverages document and image processing services
- **Models**: Uses Pydantic models for structured data handling

## Error Handling

- Graceful handling of unsupported file types
- Image processing error recovery
- Database connection management
- Comprehensive error reporting to users