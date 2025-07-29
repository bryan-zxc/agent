# Agent System Architecture

## Overview
Implementation of a conversational AI agent system with real-time frontend interface. The system features a conversational router that handles normal chat interactions and automatically activates the planner agent when specific triggers are detected (e.g., image analysis, complex tasks).

## System Architecture

```
┌─────────────────┐    WebSocket        ┌──────────────────┐    ┌─────────────┐
│   Next.js       │ ←─────────────────→ │   FastAPI        │───→│   SQLite    │
│   Frontend      │                     │   Server         │    │  Database   │
│   - Chat UI     │                     │   - RouterAgent  │    │ - Conversations
│   - File upload │   /chat/{conv_id}   │   - PlannerAgent │    │ - Messages  │
│   - History     │                     │   - WorkerAgents │    │ - Persistence
└─────────────────┘                     └──────────────────┘    └─────────────┘
```

## Core Components

### Frontend (Next.js)
- **Technology**: Next.js 15 with App Router, TypeScript
- **UI Framework**: shadcn/ui components with Tailwind CSS
- **Architecture**: 
  - Modular component design (6 focused components vs monolithic)
  - Error boundaries for fault tolerance
  - Mobile-first responsive design
  - Accessibility-first approach with ARIA labels
- **Features**: 
  - Real-time chat interface with semantic HTML
  - File upload with drag-and-drop capability
  - WebSocket connection for bidirectional communication
  - Conversation history and persistence
  - Auto-resizing input with keyboard shortcuts
  - Status indicators and loading states
- **State Management**: Zustand with TypeScript
- **Styling**: 
  - shadcn/ui component library
  - Tailwind CSS with CSS variables for theming
  - Dark/light mode support
  - Design token system

### Backend (FastAPI Server)
- **Technology**: FastAPI with WebSocket support
- **Core Agents**:
  - **RouterAgent**: WebSocket-enabled chat interface with intelligent routing
  - **PlannerAgent**: Activated automatically for complex tasks requiring multi-step execution
  - **WorkerAgents**: Execute individual tasks (general and SQL-specialized)

### Database
- **Technology**: SQLite with conversation-based persistence
- **Schema**: Conversations, RouterMessage, PlannerMessage, WorkerMessage tables
- **Purpose**: Store conversation history, message threading, and agent state
- **Scalability**: Can migrate to PostgreSQL for multi-user production deployment

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

## Communication Protocols

### WebSocket (Primary)
- **Endpoint**: `/chat/{conversation_id}`
- **Purpose**: Real-time bidirectional communication
- **Features**: 
  - Instant messaging with conversation persistence
  - Status updates during processing
  - Automatic conversation history on connect
  - File-based analysis triggering

### HTTP REST (Secondary)
- **Purpose**: File uploads and conversation management
- **Endpoints**: 
  - `POST /upload` - File uploads
  - `GET /conversations/{id}` - Conversation history
  - `GET /health` - Service status

## Key Features

### Intelligent Routing
- Automatic detection of simple chat vs complex analysis needs
- Seamless switching between conversational and analysis modes
- Status updates during processing ("Analyzing image...", "Processing table 1 of 3...")

### Multi-Modal Processing
- Image analysis and chart reading
- PDF document processing with text/image extraction
- CSV data analysis with SQL queries
- Table extraction and data visualization

### Conversation Management
- Persistent conversation history with SQLite database
- Thread-based conversation organization
- Full message history retrieval on reconnection
- Cross-session state management

## Development Structure (Monorepo)

```
agent/
├── backend/
│   ├── src/agent/          # Agent system library
│   │   ├── agents/         # PlannerAgent, WorkerAgents
│   │   ├── core/           # RouterAgent, BaseAgent
│   │   ├── models/         # Pydantic schemas and database models
│   │   └── services/       # LLM, document, image services
│   ├── main.py             # FastAPI server entry point
│   ├── pyproject.toml      # uv-managed dependencies
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── app/            # Next.js App Router
│   │   ├── components/     # Modular React components
│   │   │   ├── ChatInterface.tsx    # Main orchestrator (70 lines)
│   │   │   ├── ChatHeader.tsx       # Header with connection status
│   │   │   ├── MessageList.tsx      # Message display and scrolling
│   │   │   ├── MessageInput.tsx     # Input with auto-resize
│   │   │   ├── FileAttachment.tsx   # File upload handling
│   │   │   └── ErrorBoundary.tsx    # Error handling component
│   │   ├── hooks/          # WebSocket and state hooks
│   │   ├── lib/            # Utility functions (cn helper)
│   │   └── stores/         # Zustand state management
│   ├── components.json     # shadcn/ui configuration
│   ├── tailwind.config.ts  # Tailwind with design tokens
│   ├── package.json
│   └── Dockerfile
├── shared/
│   └── types/              # Shared type definitions
├── docker-compose.yml      # Local development setup
└── README.md
```

## Technical Benefits

### Clean Architecture
- Unified RouterAgent eliminates unnecessary complexity
- Direct WebSocket integration without extra layers
- Database-first approach for reliable persistence
- Component-based frontend with separation of concerns
- Error boundaries prevent cascade failures

### Scalability
- Monorepo for coordinated development
- Independent scaling of frontend/backend
- Database migration path (SQLite → PostgreSQL)
- Conversation-based architecture supports multi-user scenarios

### Developer Experience
- Type safety across frontend/backend with shared types
- WebSocket-native development with FastAPI
- Component-driven development with shadcn/ui
- Accessibility-first design patterns
- Hot reload and development tools
- Container-ready deployment
- uv-based dependency management for fast builds
- Modern React patterns (hooks, error boundaries)

## Deployment Options

### Development
- `docker-compose up` for full stack
- Independent service development

### Production
- Container orchestration (Docker Swarm/Kubernetes)
- Separate database hosting if needed
- CDN for frontend static assets

## Future Enhancements

- Multi-user support with PostgreSQL migration
- Advanced conversation analytics
- Plugin system for additional agent capabilities
- Mobile-responsive PWA features