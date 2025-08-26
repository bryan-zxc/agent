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

### `router_operations.py`
Function-based router operations for real-time chat and file processing orchestration.

#### Architecture
- **Function-based design**: All router operations are standalone async functions
- **State passing pattern**: Router state is passed as dictionary between functions
- **WebSocket-only communication**: All user interactions happen via WebSocket `/chat` endpoint
- **No HTTP activation**: Router activation happens through WebSocket, not HTTP endpoints

#### Core Functions

**Router Management:**
- `create_router(router_id?)`: Create or load router instance, returns state dictionary
- `load_existing_router_state(router_id, agent_db)`: Load router state from database
- `generate_and_update_title(router_state)`: Generate LLM-based title for conversation

**Message Processing:**
- `activate_conversation(user_message, websocket, files?)`: Initialize new conversation via WebSocket
- `handle_message(router_state, message_data, websocket)`: Main message handler
- `handle_simple_chat(router_state)`: Process simple conversational messages
- `handle_complex_request(router_state, websocket, files?, agent_requirements?)`: Handle complex requests
- `assess_agent_requirements(router_state)`: Determine if agent assistance is needed

**File Processing:**
- `process_files(file_paths)`: Process and categorise uploaded files
- `determine_file_groups(router_state, user_question, files)`: Group files by type for processing
- `invoke_single(router_state, instructions, files, websocket)`: Execute worker agent for file processing

**WebSocket Communication:**
- `send_user_message(content, router_id, websocket)`: Send user messages to frontend
- `send_assistant_message(content, router_id, websocket, message_id?)`: Send assistant responses
- `send_status(status, router_id, websocket)`: Send processing status updates
- `send_error(error, router_id, websocket)`: Send error messages
- `send_message_history(router_state, websocket)`: Send conversation history
- `send_input_lock(router_id, agent_db, websocket)`: Lock user input during processing
- `send_input_unlock(router_id, agent_db, websocket)`: Unlock input when complete

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
from agent.core import router_operations
from fastapi import WebSocket

async def websocket_handler(websocket: WebSocket, router_id: str):
    router_state = await router_operations.create_router(router_id=router_id)
    await router_operations.send_message_history(
        router_state=router_state, 
        websocket=websocket
    )
    
    while True:
        data = await websocket.receive_json()
        await router_operations.handle_message(
            router_state=router_state, 
            message_data=data, 
            websocket=websocket
        )
```

### New Conversation Activation
```python
from agent.core import router_operations
from fastapi import WebSocket

async def start_new_conversation(websocket: WebSocket, user_message: str, files: list = None):
    # activate_conversation creates its own router internally
    router_state = await router_operations.activate_conversation(
        user_message=user_message, 
        websocket=websocket, 
        files=files
    )
    # Router ID available as router_state["id"]
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