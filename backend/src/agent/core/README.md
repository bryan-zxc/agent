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

**Features:**
- **LLM Integration**: Unified interface for language model interactions
- **Logging Integration**: Built-in logging with configurable verbosity

### `router.py`
WebSocket-enabled router for real-time chat and file processing orchestration.

#### Classes

**`RouterAgent`**
- Main entry point for WebSocket-based chat interface  
- Intelligently routes between simple router and complex analysis
- Built-in database persistence for router history
- **Simplified Architecture**: Uses simple attributes and direct database calls
- **MessageManager Integration**: All message operations handled via MessageManager
- **Architecture**: All communication methods require active WebSocket connections (no optional WebSocket parameters)

**Key Methods (all async):**
- `__init__(router_id)`: Initialize with router ID for persistence
- `activate_conversation(user_message, websocket, files?)`: Initialize new router with first message
- `handle_message(message_data, websocket)`: Main message handler with required WebSocket
- `handle_simple_chat()`: Direct LLM router for simple responses
- `handle_complex_request(websocket, files?, agent_requirements?)`: Delegate to background agents
- `assess_agent_requirements()`: LLM-based assessment for agent assistance needs
- `process_files(file_paths)`: Convert file paths to File objects

**Router State Management:**
- **Model/Temperature**: Simple attributes set during initialization, never change
- **Status**: Direct database calls via `update_router(id, status="value")` and `get_router(id)`
- **Messages**: Handled exclusively through MessageManager instance
- **Database Pattern**: Consistent with planner and worker agents

**WebSocket Communication (Required Parameter):**
- `send_user_message(content, websocket)`: Send user messages to frontend
- `send_assistant_message(content, websocket, message_id?)`: Send assistant messages to frontend  
- `send_status(status, websocket)`: Send processing status updates
- `send_error(error, websocket)`: Send error messages
- `send_message_history(websocket)`: Send full router history on connect
- `send_input_lock(websocket)`: Lock input during processing
- `send_input_unlock(websocket)`: Unlock input when processing complete

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
from agent.tasks.message_manager import MessageManager

class CustomAgent(BaseAgent):
    def __init__(self, agent_id: str):
        super().__init__()
        self.message_manager = MessageManager(db, "custom", agent_id)
        # Messages handled through MessageManager
```

### WebSocket Chat Interface
```python
from agent.core.router import RouterAgent
from fastapi import WebSocket

async def websocket_handler(websocket: WebSocket, router_id: str):
    router = RouterAgent(router_id=router_id)
    await router.send_message_history(websocket=websocket)
    
    while True:
        data = await websocket.receive_json()
        await router.handle_message(message_data=data, websocket=websocket)
```

### New Router Activation
```python
from agent.core.router import RouterAgent
from fastapi import WebSocket

async def start_new_conversation(websocket: WebSocket, user_message: str, files: list = None):
    router = RouterAgent()  # Creates new router with UUID
    await router.activate_conversation(
        user_message=user_message, 
        websocket=websocket, 
        files=files
    )
```

### MessageManager Integration
```python
from agent.tasks.message_manager import MessageManager

# Initialize MessageManager for any agent type
message_manager = MessageManager(db, "router", router_id)

# Add messages with qualified parameters
await message_manager.add_message(role="user", content="Hello")
await message_manager.add_message(role="assistant", content="Hi there!")

# Get message history
messages = await message_manager.get_messages()
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