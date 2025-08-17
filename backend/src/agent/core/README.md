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
- `add_message(role, content, image, verbose)`: Add messages to router history
  - Supports text content and image attachments
  - Handles multimodal content with base64 image encoding
  - Optional verbose logging for debugging

**Features:**
- **Multimodal Support**: Handles text and image content in conversations
- **Image Processing**: Automatic base64 encoding for image attachments
- **Router Management**: Maintains message history across interactions
- **Logging Integration**: Built-in logging with configurable verbosity

### `router.py`
WebSocket-enabled router for real-time chat and file processing orchestration.

#### Classes

**`RouterAgent(BaseAgent)`**
- Main entry point for WebSocket-based chat interface
- Intelligently routes between simple router and complex analysis
- Built-in database persistence for router history

**Key Methods:**
- `__init__(router_id)`: Initialize with router ID for persistence
- `connect_websocket(websocket)`: Connect WebSocket and send router history
- `handle_message(message_data)`: Main message handler for user input
- `handle_simple_chat(user_message)`: Direct LLM router
- `handle_complex_request(user_message, files)`: Delegate to PlannerAgent
- `needs_planner(message)`: Determine if planner activation is needed
- `process_files(file_paths)`: Convert file paths to File objects

**WebSocket Communication:**
- `send_user_message(content)`: Send user messages to frontend
- `send_assistant_message(content, message_id?)`: Send assistant messages to frontend
- `send_status(status)`: Send processing status updates
- `send_error(error)`: Send error messages
- `send_router_history()`: Send full router history on connect

**Message Flow:**
1. **Simple Chat**: User message → LLM → Response (stored in database)
2. **Complex Analysis**: User message + files → PlannerAgent → WorkerAgents → Response
3. **File Processing**: Automatic categorization and preprocessing for analysis

#### Constants

**`INSTRUCTION_LIBRARY`**
- Predefined processing instructions for different file types
- **Data Instructions**: SQL query guidance for CSV files
- **Image Instructions**: Specialized handling for:
  - `chart`: Chart reading and data extraction
  - `table`: Table content extraction as JSON
  - `diagram`: Diagram interpretation and mermaid conversion
  - `text`: Text extraction from images
- **Document Instructions**: Document processing guidance for:
  - `pdf`: Fact extraction using question-answer pairs with citations
  - `text`: Content analysis with inline citations from loaded text

## Usage Patterns

### Basic Agent Setup
```python
from agent.core.base import BaseAgent

class CustomAgent(BaseAgent):
    def __init__(self):
        super().__init__()
        self.add_message("system", "You are a helpful assistant")
```

### WebSocket Chat Interface
```python
from agent.core.router import RouterAgent
from fastapi import WebSocket

async def websocket_handler(websocket: WebSocket, router_id: str):
    router = RouterAgent(router_id=router_id)
    await router.connect_websocket(websocket)
    
    while True:
        data = await websocket.receive_json()
        await router.handle_message(data)
```

### Direct Message Handling
```python
from agent.core.router import RouterAgent

router = RouterAgent(router_id="user-123")
message_data = {
    "content": "What's the average sales from this data?",
    "files": ["sales_data.csv"]
}
await router.handle_message(message_data)
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

### Document Files 
**PDF Documents:**
- Content extraction with text and images
- Metadata analysis (page count, text length, image count)
- Image-based PDF detection
- Tool-based fact extraction using question-answer pairs

**Text Documents:**
- Multi-encoding detection (UTF-8, UTF-16, Windows-1252)
- Content truncation to 1 million characters for performance
- Direct content loading into planner message history
- Support for various text file formats

### Image Files
- Content analysis and element categorization
- Support for charts, tables, diagrams, and text
- Error handling for unreadable images

## Integration Points

- **WebSocket Communication**: Real-time bidirectional messaging with frontend
- **Database Persistence**: SQLite integration for router history
- **LLM Service**: All agents use unified LLM interface
- **PlannerAgent**: Router delegates complex tasks to planner
- **File Services**: Leverages document and image processing services
- **Models**: Uses Pydantic models for structured data handling

## Error Handling

- Graceful handling of unsupported file types
- Image processing error recovery
- Database connection management
- Comprehensive error reporting to users