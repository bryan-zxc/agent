# Backend - Agent System API

FastAPI-based backend server that handles WebSocket communication, file processing, and AI agent orchestration using frontend-orchestrated synchronous execution.

## Structure

```
backend/
├── src/agent/              # Core agent system
│   ├── core/              # Router operations
│   ├── tasks/             # Worker task execution
│   ├── models/            # Pydantic schemas and database models
│   ├── services/          # LLM, MCP, and processing services
│   │   ├── llm/          # LLM integration and MCP tools
│   │   │   ├── llm_service.py     # LLM API wrapper
│   │   │   ├── mcp_manager.py     # MCP tool management
│   │   │   ├── agent_tools.py     # Tool definitions
│   │   │   └── tool_hooks.py      # Pre/post processing
│   │   └── image_service.py       # Image processing
│   ├── security/          # Security guardrails
│   └── utils/             # Utility functions and tools
├── main.py                # FastAPI server entry point
├── pyproject.toml         # Python dependencies (managed by uv)
├── uv.lock               # Dependency lock file
└── Dockerfile            # Container configuration
```

## Key Components

### FastAPI Server (main.py)
- **WebSocket endpoint** (`/chat`) - Real-time router interface
- **File upload** (`/upload`) - Handle file uploads for analysis
- **Health check** (`/health`) - Service status monitoring
- **Router API** (`/routers/{router_id}`) - Get router history

### Agent System (src/agent/)
- **Router Operations** - WebSocket-enabled chat interface with MCP tool execution
- **MCP Tools** - execute_python, execute_sql, set_plan_and_answer
- **Tool Hooks** - Context injection and status management
- **Worker Execution** - Synchronous task execution
- **Database Layer** - SQLite-based router persistence with execution plans

## Architecture Overview

### Frontend-Orchestrated Execution
The system uses frontend-orchestrated synchronous execution where:
1. Frontend controls the execution flow via WebSocket
2. Router handles requests directly through MCP tools
3. No background processing or task queues
4. All operations are synchronous and immediate

### MCP Tool System
- **execute_python** - Run Python code for analysis
- **execute_sql** - Execute SQL queries on data
- **set_plan_and_answer** - Store execution plans and answers
- **Tool Hooks** - Pre/post processing for context and status

## Development Setup

### Prerequisites
- Python 3.13+
- uv (fast Python package manager)

### Installation

1. **Install uv:**
   ```bash
   pip install uv
   ```

2. **Install dependencies:**
   ```bash
   uv sync
   ```

3. **Set environment variables:**
   ```bash
   export PYTHONPATH=/path/to/backend/src
   export ENVIRONMENT=development
   ```

### Running the Server

```bash
python main.py
```

Server will be available at:
- **HTTP API**: http://localhost:8000
- **WebSocket**: ws://localhost:8000/chat
- **Docs**: http://localhost:8000/docs (FastAPI auto-generated)

## API Reference

### WebSocket Communication

Connect to `ws://localhost:8000/chat` and send JSON messages:

#### Request Format
```json
{
  "type": "message",
  "message": "Analyse this sales data",
  "files": ["uploads/sales_data.csv"],
  "router_id": "uuid"  // Optional - for continuing existing conversation
}
```

#### Response Types

**Connection Established**
```json
{
  "type": "connection_established",
  "session_id": "session_uuid"
}
```

**Message History** (On connect or router load)
```json
{
  "type": "message_history",
  "messages": [
    {"role": "user", "content": "...", "message_id": 123},
    {"role": "assistant", "content": "...", "message_id": 124}
  ],
  "router_id": "uuid"
}
```

**Status Updates**
```json
{
  "type": "status",
  "status": "thinking|executing|active",
  "router_id": "uuid"
}
```

**Assistant Response**
```json
{
  "type": "response",
  "message": "Analysis result here",
  "message_id": 125,
  "router_id": "uuid"
}
```

**Mode Updates**
```json
{
  "type": "mode_updated",
  "mode": "auto|agent",
  "router_id": "uuid"
}
```

**Phase Updates**
```json
{
  "type": "phase_updated",
  "agent_phase": "planning|executing|null",
  "router_id": "uuid"
}
```

**Tool Execution**
```json
{
  "type": "tool_call",
  "tool": "execute_python",
  "arguments": {...},
  "router_id": "uuid"
}
```

**Error Messages**
```json
{
  "type": "error",
  "message": "Error details"
}
```

### HTTP Endpoints

- `POST /upload` - Upload files for analysis
- `GET /health` - Health check
- `GET /routers/{router_id}` - Get specific router history
- `GET /usage` - Get LLM usage statistics

## Agent Flow

### Processing Modes

1. **Auto Mode** (Default)
   - Simple requests → Direct LLM response
   - Complex requests → Triggers agent mode with MCP tools
   - Files attached → Typically triggers agent mode

2. **Agent Mode**
   - Frontend orchestrates tool execution
   - Uses MCP tools for processing
   - Synchronous execution with real-time updates

### Execution Flow

```
User Message
    ↓
Router Assessment
    ↓
Simple Chat OR Agent Mode
    ↓
[Agent Mode]
    ↓
Frontend Orchestration
    ↓
MCP Tool Execution
    ↓
Result Processing
    ↓
Response to User
```

### Status Flow

- `idle` - No active conversation
- `active` - Processing message
- `thinking` - Generating response
- `executing` - Running MCP tools
- `plamarinating_awaiting_user` - Plan awaiting approval (future feature)

## Database Schema

### Core Tables

- **routers** - Conversation state and execution plans
- **router_messages** - Message history
- **workers** - Worker task state
- **worker_messages** - Worker execution logs

### Deprecated Tables (Commented Out)
- ~~task_queue~~ - No longer used
- ~~planners~~ - Router handles plans directly
- ~~planner_messages~~ - Unified into router messages

## Testing

Run the test suite:
```bash
uv run pytest tests/
```

Key test areas:
- Router operations
- MCP tool execution
- WebSocket communication
- Database operations
- Worker task execution

## Environment Variables

Required environment variables:
- `ENVIRONMENT` - development|production
- `OPENAI_API_KEY` - OpenAI API key
- `ANTHROPIC_API_KEY` - Anthropic API key (optional)
- `GROQ_API_KEY` - Groq API key (optional)

Optional MCP server configuration:
- `GITHUB_PERSONAL_ACCESS_TOKEN` - For GitHub MCP server
- `MCP_CONFIG_PATH` - Path to MCP config file

## Migration Notes

### From Background Processor to Frontend Orchestration
- Task queue removed completely
- Planner entities no longer created
- Router stores execution plans directly
- All execution is synchronous
- Frontend controls execution flow

### Database Changes
- Router table has `execution_plan` field
- TaskQueue table deprecated
- Planner tables commented out
- Message tables consolidated

## Performance

- Simple chat: <100ms response time
- Tool execution: 1-5 seconds per tool
- Complex workflows: 10-30 seconds total
- WebSocket: Real-time bidirectional updates

## Security

- Input validation on all endpoints
- File upload restrictions
- MCP tool sandboxing
- Database query parameterisation
- WebSocket rate limiting