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

### `mcp_client.py`
Model Context Protocol (MCP) client manager for external tool integration.

#### Classes

**`MCPClientManager`**
- Manages connections to external MCP servers (GitHub, databases, file systems, etc.)
- Handles tool discovery, formatting for LLMs, and execution
- Provides singleton pattern for global access across the application

**Key Methods:**
- `connect(name, server_url)`: Connect to an MCP server
- `disconnect(name)`: Disconnect from a specific MCP server
- `get_tools_for_llm()`: Get all available tools formatted for LLM function calling
- `execute_llm_tool_call(tool_call)`: Execute a tool call from LLM response
- `get_filtered_tools(filter_fn)`: Get tools with custom filtering
- `list_connected_servers()`: Get list of connected server names

**Features:**
- **Tool Discovery**: Automatically discovers tools from connected MCP servers
- **LLM Integration**: Formats tools in OpenAI/Anthropic function schema format
- **Name Conflict Resolution**: Prefixes tool names with server name to avoid conflicts
- **Error Handling**: Comprehensive error handling for tool execution
- **Singleton Access**: Global instance accessible via `get_mcp_manager()`

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
- `activate_conversation(user_message, websocket, files?, mode?)`: Initialize new conversation via WebSocket with optional mode
- `handle_message(router_state, message_data, websocket)`: Main message handler with mode-based routing
  - **Auto Mode**: Assesses requirements and routes to simple/complex handling
  - **Rapid Mode**: Always routes to simple chat for fastest responses
  - **Agent Mode**: Always activates complex handling with agents
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

### MCP Client Integration

**Prerequisites:**
- Node.js 20 LTS installed in container (included in Dockerfile)
- MCP servers installed via npm (e.g., `@modelcontextprotocol/server-github`)
- Environment variables configured for MCP servers (e.g., `GITHUB_TOKEN`)

```python
from agent.core.mcp_client import get_mcp_manager

# Get the global MCP manager instance
# This automatically connects to configured servers from settings
mcp_manager = await get_mcp_manager()

# MCP servers can be stdio (Node.js), HTTP, or WebSocket based
# Stdio servers spawn Node.js processes with command lists:
# ["npx", "@modelcontextprotocol/server-github"]

# Get tools for LLM
tools = await mcp_manager.get_tools_for_llm()
# Tools are formatted for OpenAI/Anthropic function calling

# Execute a tool call from LLM response
result = await mcp_manager.execute_llm_tool_call(tool_call)

# Filter tools by custom criteria
def filter_fn(server_name, tool):
    return server_name == "github"  # Only GitHub tools

github_tools = await mcp_manager.get_filtered_tools(filter_fn)

# List connected servers
servers = await mcp_manager.list_connected_servers()
# Returns: ["github", "filesystem"]
```

**Configuration:** MCP servers are configured in environment variables and loaded via `MCPConfiguration` in the settings module. See `backend/src/agent/config/mcp_config.py` for server definitions.

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
- **MCP Client Manager**: Connects to external MCP servers for tool integration

## Error Handling

- Graceful handling of unsupported file types
- Image processing error recovery
- Database connection management
- Comprehensive error reporting to users