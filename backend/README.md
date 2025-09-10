# Backend - Agent System API

FastAPI-based backend server that handles WebSocket communication, file processing, and AI agent orchestration.

## Structure

```
backend/
├── src/agent/              # Core agent system (existing codebase)
│   ├── agents/            # PlannerAgent and WorkerAgents
│   ├── core/              # Router operations and base classes
│   ├── models/            # Pydantic schemas and database models
│   ├── services/          # LLM, document, and image processing services
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
- **Router Operations** - WebSocket-enabled chat interface with intelligent routing (functional architecture)
- **PlannerAgent** - Breaks down complex tasks into subtasks (activated automatically)
- **WorkerAgents** - Execute individual tasks (general and SQL-specialized)
- **Database Layer** - SQLite-based router persistence with mode/phase tracking

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

```json
{
  "content": "Analyze this sales data",
  "files": ["uploads/sales_data.csv"]
}
```

Response types:
- `{"type": "message_history", "messages": [...], "router_id": "..."}` - On connect
- `{"type": "status", "message": "Processing..."}` - Status updates
- `{"type": "message", "role": "assistant", "content": "Analysis result", "router_id": "..."}` - Chat messages
- `{"type": "error", "message": "Error details"}` - Error messages

### HTTP Endpoints

- `POST /upload` - Upload files for analysis
- `GET /health` - Health check
- `GET /routers/{router_id}` - Get specific router history

## Agent Flow

### Modes and Phases Architecture
The system operates with three primary modes and two agent-specific phases:

#### Processing Modes
1. **Auto Mode** (Default)
   - Intelligent routing based on request complexity
   - Simple requests → Direct response via simple chat
   - Complex requests → Automatically triggers agent mode with plamarination phase
   - Files attached → Typically triggers agent mode

2. **Rapid Mode**
   - Fast, lightweight responses without agent processing
   - Always uses simple chat, bypassing all agent assessment
   - No file processing capabilities
   - Warns users when questions may need deeper analysis

3. **Agent Mode**
   - Advanced processing with explicit planning and execution phases
   - Always involves deeper analysis and tool usage
   - Supports complex multi-step operations
   - Two distinct phases: Plamarination and Execution

#### Agent Mode Phases
When in agent mode, the system operates in one of two phases:

**Plamarination Phase** (Default for agent mode):
- Thoroughly analyses the request and any attached files
- Researches using available tools (file reading, web search, etc.)
- Builds comprehensive context
- Generates a structured execution plan
- Presents plan for user approval

**Execution Phase**:
- Skips plamarination entirely
- Immediately proceeds to handle_complex_request
- Executes task with available tools
- Returns results directly

### Message Routing Logic
The `handle_message` function routes based on **status first**, then mode and phase:

1. **Check router status** (prevents double-triggering):
   - `plamarinating` → Return immediately (no trigger)
   - `plamarinating_awaiting_user` → Process user input, continue planning
   - `awaiting_approval` → Handle approval/rejection
   - `executing` → Execution in progress
   - `active` → Check mode for new request routing

2. **When status is active, check router mode**:
   - `rapid` → Always simple chat
   - `agent` → Invalid state (raises error)
   - `auto` → Assess complexity

### Processing Pipeline
1. **WebSocket Connection** - Frontend connects with router ID
2. **Message Handling** - Router receives and stores user message
3. **Route Decision** - Simple chat OR complex analysis
4. **Processing** - Direct LLM response OR PlannerAgent → WorkerAgents
5. **Response** - Store and send result via WebSocket

### WebSocket Message Formats

#### Mode Change
```json
{
  "type": "update_mode",
  "router_id": "uuid",
  "mode": "auto|rapid|agent"
}
```

#### Phase Change (Agent Mode Only)
```json
{
  "type": "update_phase",
  "router_id": "uuid",
  "agent_phase": "plamarination|execution"
}
```

#### Status Updates
```json
{
  "type": "status",
  "router_id": "uuid",
  "status": "active|plamarinating|executing|awaiting_approval|..."
}
```

### Database Schema
The Router table includes:
- `mode`: String(10) - "auto", "rapid", or "agent"
- `agent_phase`: String(20) - "plamarination" or "execution" (NULL by default, only set when agent mode is active)
- `status`: String(50) - Current processing status

## Configuration

### Environment Variables
- `PYTHONPATH` - Python module path (should include `src/`)
- `ENVIRONMENT` - Runtime environment (development/production)

### Dependencies (pyproject.toml)
- **FastAPI** - Web framework and WebSocket support
- **Anthropic/OpenAI** - LLM service clients
- **PyMuPDF** - PDF processing
- **Pillow** - Image processing
- **SQLAlchemy** - Database ORM
- **Pydantic** - Data validation and serialization

## Development Notes

### Adding New Endpoints
1. Add route handlers to `main.py`
2. Define Pydantic models for request/response
3. Update CORS settings if needed

### Extending Agent Capabilities
1. Modify trigger detection in `router_operations.py`
2. Add new instruction templates
3. Create specialized `WorkerAgent` subclasses

### Database Integration
- **SQLite**: Default database with router persistence
- **Tables**: Routers, RouterMessage, PlannerMessage, WorkerMessage
- **Location**: `/Users/bryanye/agent/db/agent_messages.db` (configurable)
- **Migration**: Can be upgraded to PostgreSQL for production scalability

## Docker Development

Build and run with Docker:
```bash
docker build -t agent-backend .
docker run -p 8000:8000 agent-backend
```

Or use docker-compose from the root directory:
```bash
docker-compose up backend
```

## Troubleshooting

### Common Issues
1. **Import errors** - Ensure `PYTHONPATH` includes `src/` directory
2. **Port conflicts** - Change port in `main.py` if 8000 is occupied
3. **WebSocket connections** - Check CORS settings for frontend origin
4. **File upload errors** - Verify `uploads/` directory permissions

### Logs
Server logs are written to stdout. In production, configure proper logging:
```python
import logging
logging.basicConfig(level=logging.INFO)
```