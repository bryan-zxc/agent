# Backend - Agent System API

FastAPI-based backend server that handles WebSocket communication, file processing, and AI agent orchestration.

## Structure

```
backend/
├── src/agent/              # Core agent system (existing codebase)
│   ├── agents/            # PlannerAgent and WorkerAgents
│   ├── core/              # RouterAgent and base classes
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
- **WebSocket endpoint** (`/chat/{conversation_id}`) - Real-time conversation interface
- **File upload** (`/upload`) - Handle file uploads for analysis
- **Health check** (`/health`) - Service status monitoring
- **Conversation API** (`/conversations/{conversation_id}`) - Get conversation history

### Agent System (src/agent/)
- **RouterAgent** - WebSocket-enabled chat interface with intelligent routing
- **PlannerAgent** - Breaks down complex tasks into subtasks (activated automatically)
- **WorkerAgents** - Execute individual tasks (general and SQL-specialized)
- **Database Layer** - SQLite-based conversation persistence

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
- **WebSocket**: ws://localhost:8000/chat/{conversation_id}
- **Docs**: http://localhost:8000/docs (FastAPI auto-generated)

## API Reference

### WebSocket Communication

Connect to `ws://localhost:8000/chat/{conversation_id}` and send JSON messages:

```json
{
  "content": "Analyze this sales data",
  "files": ["uploads/sales_data.csv"]
}
```

Response types:
- `{"type": "conversation_history", "messages": [...], "conversation_id": "..."}` - On connect
- `{"type": "status", "message": "Processing..."}` - Status updates
- `{"type": "message", "role": "assistant", "content": "Analysis result", "conversation_id": "..."}` - Chat messages
- `{"type": "error", "message": "Error details"}` - Error messages

### HTTP Endpoints

- `POST /upload` - Upload files for analysis
- `GET /health` - Health check
- `GET /conversations/{conversation_id}` - Get specific conversation history

## Agent Flow

### Intelligent Routing
The RouterAgent automatically switches between simple chat and complex analysis modes:

**Simple Chat Mode:**
- Direct LLM conversation for general questions
- Stored in database with conversation history
- Fast response times

**Analysis Mode (Auto-triggered by):**
1. **File uploads** - Images, PDFs, CSVs
2. **Keywords** - "analyze", "process", "generate", "report", "chart", "table", "data"
3. **Complex requests** - Multi-step tasks requiring planning

### Processing Pipeline
1. **WebSocket Connection** - Frontend connects with conversation ID
2. **Message Handling** - RouterAgent receives and stores user message
3. **Route Decision** - Simple chat OR complex analysis
4. **Processing** - Direct LLM response OR PlannerAgent → WorkerAgents
5. **Response** - Store and send result via WebSocket

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
1. Modify trigger detection in `RouterAgent`
2. Add new instruction templates
3. Create specialized `WorkerAgent` subclasses

### Database Integration
- **SQLite**: Default database with conversation persistence
- **Tables**: Conversations, RouterMessage, PlannerMessage, WorkerMessage
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