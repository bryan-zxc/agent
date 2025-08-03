# Agent System

A conversational AI agent system with real-time frontend interface. The system features a conversational router that handles normal chat interactions and automatically activates the planner agent when specific triggers are detected (e.g., image analysis, complex tasks).

## Architecture

```
┌─────────────────┐    WebSocket/HTTP    ┌──────────────────┐    ┌─────────────┐
│   Next.js       │ ←─────────────────→ │   FastAPI        │───→│   SQLite    │
│   Frontend      │                     │   Server         │    │  Database   │
│   - Chat UI     │                     │   - RouterAgent  │    │             │
│   - Real-time   │                     │   - PlannerAgent │    └─────────────┘
│   - File upload │                     │   - WorkerAgents │
└─────────────────┘                     └──────────────────┘
```

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

### Multi-Modal Processing
- Image analysis and chart reading
- PDF document processing
- CSV data analysis with SQL queries
- Table extraction and data visualization

### Conversation Management
- Persistent conversation history
- Context switching between chat and analysis modes
- Session state management

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
- `POST /upload` - File upload endpoint
- `GET /health` - Health check
- `GET /conversations` - Get conversation history
- `DELETE /conversations` - Clear conversation history

## Agent Flow

### Conversational Mode (Default)
1. User sends message via WebSocket
2. RouterAgent processes in conversational context
3. Responds directly for simple queries
4. Maintains conversation history

### Analysis Mode (Triggered)
1. RouterAgent detects triggers:
   - File uploads (images, PDFs, CSVs)
   - Keywords: "analyze", "process", "generate report"
   - Complex multi-step requests
2. RouterAgent activates PlannerAgent
3. PlannerAgent breaks down task into subtasks
4. WorkerAgents execute individual tasks
5. Results consolidated and returned to user

## Tech Stack

### Backend
- **FastAPI** - Modern Python web framework
- **WebSockets** - Real-time bidirectional communication
- **SQLite** - Lightweight database (can migrate to PostgreSQL)
- **Pydantic** - Data validation and serialization

### Frontend
- **Next.js 14+** - React framework with TypeScript
- **TailwindCSS** - Utility-first CSS framework
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

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test with `docker-compose up`
5. Submit a pull request

## License

MIT License