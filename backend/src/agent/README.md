# Agent Library

A comprehensive AI agent system for processing various file types and executing complex tasks using large language models with frontend-orchestrated synchronous execution.

## Architecture Overview

This library implements a frontend-orchestrated execution system where the frontend controls task sequencing via WebSocket, and the router handles all operations through MCP (Model Context Protocol) tools. The system provides synchronous, immediate execution without background processing or task queues.

## Directory Structure

```
agent/
├── config/          # Configuration and settings
├── core/            # Router operations and WebSocket handling
├── models/          # Pydantic models, database schemas, and API responses
├── security/        # Security and safety guardrails
├── services/        # External service integrations and MCP tools
│   └── llm/        # LLM service and MCP tool management
├── tasks/           # Worker task implementations and file management
└── utils/           # Utility functions and tools
```

## Key Components

### Core (`core/`)
- **Router Operations**: WebSocket-enabled chat interface with direct MCP tool execution
- **Message routing**: Intelligent routing between simple chat and agent mode

### Services (`services/`)
- **LLM Service**: Unified interface for multiple language models (OpenAI, Anthropic, Google)
- **MCP Manager**: Tool discovery and execution management
- **Agent Tools**: MCP tool definitions (execute_python, execute_sql, set_plan_and_answer)
- **Tool Hooks**: Pre/post processing for context injection and status updates
- **Image Service**: Image analysis and content recognition

### Tasks (`tasks/`)
- **Worker Functions**: Synchronous task execution
- **File Manager**: Variable/image storage with collision avoidance and lazy loading
- ~~**Planner Functions**~~: DEPRECATED - Router handles plans directly

### Models (`models/`)
- **Agent Database**: SQLite-based storage with router execution plans
- **Task Models**: Define task structure and execution flow
- **Response Models**: Structure API responses and validations
- **Schema Models**: Data models for files, images, and documents

## Getting Started

### WebSocket Integration (Recommended)
```python
from agent.core import router_operations
from fastapi import FastAPI, WebSocket

app = FastAPI()

@app.websocket("/chat")
async def websocket_endpoint(websocket: WebSocket):
    router_state = await router_operations.create_router()
    await router_operations.send_message_history(router_state, websocket)

    # Handle messages with synchronous execution
    while True:
        data = await websocket.receive_json()
        await router_operations.handle_message(router_state, data, websocket)
```

### MCP Tool Usage
```python
from agent.services.llm.mcp_manager import MCPManager
from agent.services.llm.tool_hooks import tool_hooks

# Initialize MCP manager
mcp_manager = MCPManager()

# Execute tool with hooks
tool_args = await tool_hooks.apply_pre_hook(
    "agent_tools__execute_python",
    {"code": "import pandas as pd\nprint('Hello')"},
    {"router_id": "abc123"},
    websocket
)
result = await mcp_manager.execute_tool("agent_tools__execute_python", tool_args)
result = await tool_hooks.apply_post_hook(
    "agent_tools__execute_python",
    result,
    {"router_id": "abc123"},
    websocket
)
```

### File Management
```python
from agent.tasks.file_manager import save_worker_variable, get_worker_variable

# Save complex data structures with collision avoidance
analysis_results = {"insights": [...], "metrics": {...}}
file_path, final_key = save_worker_variable(
    worker_id="worker123",
    key="analysis_results",
    value=analysis_results,
    check_existing=True
)

# Lazy load when needed
data = get_worker_variable("worker123", "analysis_results")
```

## Features

- **Frontend Orchestration**: Frontend controls execution flow via WebSocket
- **Synchronous Execution**: All operations are immediate without task queues
- **MCP Tool System**: Extensible tool architecture with pre/post hooks
- **Real-time Communication**: WebSocket-based chat interface with router persistence
- **Intelligent Routing**: Automatically switches between simple chat and agent mode
- **File Processing**: Supports images, PDFs, CSVs, and text files
- **Multi-LLM Support**: Works with OpenAI, Anthropic, and Groq models

## Architecture Changes

### Before (Background Processor)
- Task queue with async execution
- Background processor polling
- Planner entities created separately
- Complex state synchronisation

### After (Frontend Orchestration)
- Direct synchronous execution
- No background processing
- Router handles execution plans directly
- Simple, traceable flow

## Database Schema

### Active Tables
- **routers**: Stores execution_plan directly
- **router_messages**: Conversation history
- **workers**: Worker task state
- **worker_messages**: Worker execution logs

### Deprecated Tables (Commented Out)
- ~~task_queue~~: No longer needed
- ~~planners~~: Router handles plans
- ~~planner_messages~~: Unified into router

## Testing

```bash
# Run unit tests
pytest tests/unit/

# Run integration tests
pytest tests/integration/
```

## Environment Variables

Required:
- `ENVIRONMENT`: development|production
- `OPENAI_API_KEY`: OpenAI API key

Optional:
- `ANTHROPIC_API_KEY`: Anthropic API key
- `GROQ_API_KEY`: Groq API key
- `GITHUB_PERSONAL_ACCESS_TOKEN`: GitHub MCP server

## Migration Notes

The system has been completely restructured from background processing to frontend orchestration:
1. No task queues or background processor
2. Planner functions are deprecated
3. Router stores and manages execution plans
4. All execution is synchronous
5. Frontend controls the flow