# Agent System

A conversational AI agent system with real-time frontend interface. The system features a conversational router that handles normal chat interactions and automatically activates the planner agent when specific triggers are detected (e.g., image analysis, complex tasks).

## Project Structure (Monorepo)

```
agent/
├── backend/                 # FastAPI server
│   ├── src/agent/          # Existing agent code
│   │   ├── agents/         # PlannerAgent, WorkerAgents
│   │   ├── core/           # RouterAgent, BaseAgent
│   │   ├── models/         # Pydantic schemas and database
│   │   └── services/       # LLM, document, image services
│   ├── main.py             # FastAPI server entry point
│   ├── pyproject.toml      # Python dependencies
│   └── Dockerfile
├── frontend/               # Next.js application
│   ├── src/
│   │   ├── components/     # Chat UI components
│   │   ├── hooks/          # WebSocket and state hooks
│   │   ├── stores/         # Zustand state management
│   │   └── app/            # Next.js pages
│   ├── package.json
│   └── Dockerfile
├── shared/                 # Shared type definitions
│   └── types/
├── docker-compose.yml      # Local development setup
└── README.md
```

## Features

### Real-time Interaction
- Token-by-token response streaming for smooth UX
- Multi-message sequences with user interruption
- Agent status updates ("Analyzing image...", "Processing table 1 of 3...")
- **Real-time expandable execution plans** - Live updates of planner thinking and task progress
- **Message-specific execution plan history** - Each planner activation creates an expandable "Agents assemble!" message

### Multi-Modal Processing
- Image analysis and chart reading
- PDF document processing
- Text document processing with multi-encoding support
- CSV data analysis with SQL queries
- Table extraction and data visualisation

### File Management
- Intelligent duplicate detection using SHA-256 content hashing
- User-friendly duplicate resolution options:
  - Use existing file (reference previously uploaded)
  - Overwrite existing file with new version
  - Save as new copy with unique filename
  - Cancel upload process
- Automatic unique filename generation for conflict avoidance

### Progressive Answer Templates
- Dynamic answer template generation for structured responses
- Progressive template refinement as tasks complete
- Markdown-based template structure with placeholder filling
- Context-aware template updates based on discovered information
- Work-in-progress template tracking for quality assurance

### Conversation Management
- Persistent conversation history
- Context switching between chat and analysis modes
- Session state management

## Prerequisites

Before running the project, ensure you have the following installed:

### Required
- **Docker & Docker Compose** - For containerised development (recommended)
- **Git** - For version control

### For Manual Development
- **Node.js** - v18.0.0 or higher
- **Python** - v3.11 or higher
- **uv** - Python package manager (`pip install uv`)

### System Requirements
- **Memory**: Minimum 4GB RAM (8GB recommended for LLM operations)
- **Storage**: At least 2GB free space for dependencies and file uploads
- **Network**: Internet connection required for LLM API calls

## Environment Setup

### Environment Variables

Create a `.env.local` file in the backend directory with your API keys:

```bash
# LLM Provider Configuration (choose one or more)
OPENAI_API_KEY=your_openai_key_here
ANTHROPIC_API_KEY=your_anthropic_key_here
GOOGLE_API_KEY=your_google_key_here

# Application Settings
ENVIRONMENT=development
PYTHONPATH=/app/src

# Database (SQLite - no setup required)
# DATABASE_URL=sqlite:///./agent.db  # Default, auto-created
# Schema automatically migrates to V2 on startup

# Optional: For production PostgreSQL
# DATABASE_URL=postgresql://user:pass@localhost:5432/agent_db
```

Create a `.env.local` file in the frontend directory:

```bash
# API Configuration
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000

# Development Settings
NODE_ENV=development
```

### Security Notes
- Never commit `.env.local` files to version control
- Rotate API keys regularly
- Use different keys for development and production

## Quick Start

### Development with Docker Compose

1. **Start all services:**
   ```bash
   docker-compose up
   ```

   This will start:
   - Backend API server on http://localhost:8000
   - Frontend web app on http://localhost:3000
   - PostgreSQL database on localhost:5432

2. **Access the application:**
   - Open http://localhost:3000 in your browser
   - Start chatting with the agent
   - Upload files (images, PDFs, CSVs) for analysis

### Manual Development Setup

#### Backend Setup

1. **Navigate to backend:**
   ```bash
   cd backend
   ```

2. **Install dependencies (using uv):**
   ```bash
   pip install uv
   uv sync
   ```

3. **Run the server:**
   ```bash
   python main.py
   ```

   Server will be available at http://localhost:8000

#### Frontend Setup

1. **Navigate to frontend:**
   ```bash
   cd frontend
   ```

2. **Install dependencies:**
   ```bash
   npm install
   ```

3. **Run the development server:**
   ```bash
   npm run dev
   ```

   Frontend will be available at http://localhost:3000

## API Endpoints

### WebSocket
- `ws://localhost:8000/chat` - Real-time chat communication

### HTTP
- `POST /upload` - File upload endpoint with duplicate detection
- `POST /upload/resolve-duplicate` - Handle duplicate file resolution
- `GET /health` - Health check
- `GET /routers` - Get router history
- `GET /messages/{message_id}/planner-info` - Get planner execution plan for specific message
- `DELETE /routers` - Clear router history

## How It Works

The system automatically switches between simple chat and complex analysis modes:

**Chat Mode**: Direct responses for simple questions  
**Analysis Mode**: Multi-agent processing for file analysis and complex tasks

*For detailed technical architecture, see [ARCHITECTURE.md](ARCHITECTURE.md)*

## Tech Stack

### Backend
- **FastAPI** - Modern Python web framework
- **WebSockets** - Real-time bidirectional communication
- **SQLite** - Lightweight database (can migrate to PostgreSQL)
- **Pydantic** - Data validation and serialization

### Frontend
- **Next.js 14+** - React framework with TypeScript
- **TailwindCSS** - Utility-first CSS framework
- **shadcn/ui** - Accessible UI components (Collapsible for execution plans)
- **Zustand** - Lightweight state management
- **WebSocket API** - Real-time communication

### Development
- **Docker & Docker Compose** - Containerized development
- **uv** - Fast Python package management
- **TypeScript** - Type safety across the stack

## Environment Variables

### Backend
- `PYTHONPATH=/app/src` - Python module path
- `ENVIRONMENT=development` - Runtime environment

### Frontend
- `NODE_ENV=development` - Node environment
- `NEXT_PUBLIC_API_URL=http://localhost:8000` - Backend API URL
- `NEXT_PUBLIC_WS_URL=ws://localhost:8000` - WebSocket URL

## Testing

### Backend Tests

```bash
cd backend

# Install test dependencies
uv sync --dev

# Run all tests
python -m pytest

# Run with coverage
python -m pytest --cov=src/agent --cov-report=html

# Run specific test modules
python -m pytest test/test_agents.py
python -m pytest test/test_file_utils.py
```

### Frontend Tests

```bash
cd frontend

# Install test dependencies
npm install

# Run unit tests
npm test

# Run tests in watch mode
npm test -- --watch

# Run with coverage
npm test -- --coverage
```

### Integration Tests

```bash
# Start services
docker-compose up -d

# Wait for services to be ready
sleep 10

# Run end-to-end tests
cd frontend && npm run test:e2e

# Cleanup
docker-compose down
```

### Test Coverage

The test suite covers:
- **Agent Logic**: PlannerAgent and WorkerAgent functionality
- **File Processing**: Upload, duplicate detection, and resolution
- **API Endpoints**: WebSocket and HTTP endpoint testing
- **Database Operations**: Message persistence and retrieval
- **Frontend Components**: UI component behaviour and integration

## Troubleshooting

### Common Issues

#### Services Won't Start

**Problem**: `docker-compose up` fails
```bash
# Check Docker daemon is running
docker info

# Clear Docker cache
docker system prune -a

# Rebuild containers
docker-compose up --build
```

#### Backend Connection Issues

**Problem**: Frontend can't connect to backend
```bash
# Check backend is running
curl http://localhost:8000/health

# Check WebSocket connection
wscat -c ws://localhost:8000/chat

# Verify environment variables
cd backend && cat .env.local
```

#### File Upload Failures

**Problem**: File uploads return 500 errors
- **Check disk space**: `df -h`
- **Verify upload directory permissions**: `ls -la backend/uploads/`
- **Check backend logs**: `docker-compose logs backend`

#### LLM API Errors

**Problem**: "API key not found" or rate limit errors
- **Verify API keys**: Check `.env.local` files contain valid keys
- **Check API quotas**: Ensure you haven't exceeded rate limits
- **Test API connectivity**: Use curl to test API endpoints directly

```bash
# Test OpenAI API
curl -H "Authorization: Bearer $OPENAI_API_KEY" \
  https://api.openai.com/v1/models

# Test Anthropic API  
curl -H "x-api-key: $ANTHROPIC_API_KEY" \
  https://api.anthropic.com/v1/messages
```

### Performance Issues

#### High Memory Usage
- **Reduce concurrent file processing**: Limit file upload batch sizes
- **Check for memory leaks**: Monitor with `docker stats`
- **Increase system resources**: Ensure minimum 8GB RAM for LLM operations

#### Slow Response Times
- **Check network latency**: Test LLM API response times
- **Monitor database**: Check SQLite file size and query performance
- **Review file sizes**: Large uploads may need chunked processing

### Development Issues

#### Hot Reload Not Working

**Frontend**:
```bash
# Clear Next.js cache
rm -rf frontend/.next
npm run dev
```

**Backend**:
```bash
# Restart with fresh dependencies
cd backend && uv sync && python main.py
```

#### Type Errors

**Shared Types**:
```bash
# Regenerate shared types
cd shared && npm run build
```

### Database Issues

#### SQLite Lock Errors
```bash
# Stop all services
docker-compose down

# Remove database file (development only)
rm backend/agent.db

# Restart services
docker-compose up
```

#### Migration Needed
```bash
# Check current schema version
sqlite3 backend/agent.db ".schema"

# Apply migrations (if any)
cd backend && python -m alembic upgrade head
```

### Getting Help

1. **Check Logs**: Always check service logs first
   ```bash
   docker-compose logs backend
   docker-compose logs frontend
   ```

2. **Search Issues**: Look through existing GitHub issues

3. **Debug Mode**: Set `ENVIRONMENT=debug` for verbose logging

4. **Create Issue**: Include:
   - Error messages and stack traces
   - Steps to reproduce
   - Environment details (OS, Docker version, etc.)
   - Relevant log output

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test with `docker-compose up`
5. Submit a pull request

## License

MIT License