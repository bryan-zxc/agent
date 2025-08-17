# Agent System Architecture

## Overview
Implementation of an AI agent system with real-time frontend interface using a modern function-based task queue architecture. The system features a router that handles normal chat interactions and automatically queues background agent tasks when complex processing is required (e.g., image analysis, multi-step tasks).

## System Architecture

```mermaid
graph LR
    A[Next.js Frontend<br/>- Chat UI<br/>- File upload<br/>- Real-time updates] 
    B[FastAPI Server<br/>- RouterAgent<br/>- Immediate responses<br/>- WebSocket updates]
    C[Background Processor<br/>- Async task execution<br/>- Function-based tasks<br/>- Concurrent processing]
    D[Task Queue<br/>- Planner tasks<br/>- Worker tasks<br/>- Status tracking]
    E[SQLite Database<br/>- Routers & Messages<br/>- Task queue<br/>- File paths<br/>- Agent state]
    
    A <-->|"WebSocket /chat"| B
    B --> D
    C --> D
    C --> E
    B --> E
    C -.->|"Completion updates"| B
    B -.->|"Real-time status"| A
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
  - Intelligent file upload with duplicate detection
  - Drag-and-drop file capability with resolution dialogs
  - WebSocket connection for bidirectional communication
  - Router history and persistence
  - Auto-resizing input with keyboard shortcuts
  - Status indicators and loading states
- **State Management**: Zustand with TypeScript
- **Styling**: 
  - shadcn/ui component library
  - Tailwind CSS with CSS variables for theming
  - Dark/light mode support
  - Design token system

### Backend (FastAPI Server)
- **Technology**: FastAPI with WebSocket support and async task queue
- **Core Components**:
  - **RouterAgent**: WebSocket-enabled chat interface with immediate response capability
  - **Background Processor**: Continuous task processor that executes queued functions
  - **Task Queue System**: Database-backed queue for async function execution
  - **Function-Based Tasks**: 
    - Planner functions (planning, task creation, synthesis)
    - Worker functions (initialisation, execution, validation)
  - **File Storage System**: Organised file management with collision avoidance

### Database
- **Technology**: SQLite with comprehensive agent state management
- **Core Tables**: 
  - **Routers**: Conversation state and metadata
  - **Messages**: Router, planner, and worker message history
  - **Planners**: Planning agent state and execution plans
  - **Workers**: Worker agent state and task results
  - **TaskQueue**: Async function execution queue with status tracking
- **Advanced Features**:
  - JSON columns for file path storage (variable_file_paths, image_file_paths)
  - Task queue with entity-based organization
  - Collision avoidance for file naming
  - Agent state persistence and recovery
- **Scalability**: Can migrate to PostgreSQL for multi-user production deployment

## Agent Flow

### Simple Chat Mode (Default)
1. User sends message via WebSocket
2. RouterAgent processes immediately and responds
3. WebSocket delivers instant response
4. No background processing required
5. Maintains router history in database

### Complex Processing Mode (Triggered)
1. RouterAgent detects complex requirements:
   - File uploads (images, PDFs, CSVs)
   - Agent assistance needed (web search, analysis)
   - Multi-step processing requests
2. RouterAgent queues background task and responds "Agents assemble!"
3. Background processor picks up queued planner task
4. Function-based execution:
   - `execute_initial_planning`: Creates execution plan from user request
   - `execute_task_creation`: Generates worker tasks from plan
   - `execute_synthesis`: Processes worker results and updates plan
5. Worker functions execute individual tasks concurrently
6. Planner synthesis generates final user response
7. Router receives completion notification and delivers final response

## Task Queue Flow Diagrams

### Complete Task Execution Flow

```mermaid
graph TD
    A[User Message] --> B{RouterAgent Assessment}
    B -->|Simple Chat| C[Direct LLM Response]
    B -->|Complex Request| D[Queue Initial Planning]
    
    C --> E[WebSocket Response]
    
    D --> F[Background Processor]
    F --> G[Execute Initial Planning]
    G --> H[Create Execution Plan]
    H --> I[Queue Task Creation]
    
    I --> J[Execute Task Creation]
    J --> K[Generate Worker Tasks]
    K --> L[Queue Worker Tasks]
    
    L --> M[Execute Worker Tasks Concurrently]
    M --> N[Worker Results]
    N --> O[Queue Synthesis]
    
    O --> P[Execute Synthesis]
    P --> Q[Process Results & Update Plan]
    Q --> R{More Tasks Needed?}
    
    R -->|Yes| I
    R -->|No| S[Generate Final Response]
    S --> T[Mark Planner Complete]
    T --> U[Notify Router]
    U --> V[WebSocket Final Response]
    
    style D fill:#e1f5fe
    style F fill:#f3e5f5
    style G fill:#e8f5e8
    style J fill:#e8f5e8
    style M fill:#fff3e0
    style P fill:#e8f5e8
```

### Task Queue Database Operations

```mermaid
sequenceDiagram
    participant R as RouterAgent
    participant DB as Task Queue DB
    participant BP as Background Processor
    participant PF as Planner Function
    participant WF as Worker Function
    
    R->>DB: enqueue_task(planner_id, "execute_initial_planning")
    R->>R: Send "Agents assemble!" to WebSocket
    
    loop Every 1 Second
        BP->>DB: get_pending_tasks()
        DB-->>BP: [pending_tasks]
        
        alt Tasks Available
            BP->>DB: update_task_status(task_id, "IN_PROGRESS")
            BP->>PF: execute_initial_planning(task_data)
            
            alt Planning Success
                PF->>DB: create_planner(planner_id, execution_plan)
                PF->>DB: enqueue_task(planner_id, "execute_task_creation")
                BP->>DB: update_task_status(task_id, "COMPLETED")
            else Planning Failure
                BP->>DB: update_task_status(task_id, "FAILED", error_msg)
            end
            
            BP->>DB: get_pending_tasks()
            BP->>PF: execute_task_creation(task_data)
            
            PF->>DB: create_worker(worker_id, task_description)
            PF->>DB: enqueue_task(worker_id, "worker_initialisation")
            
            BP->>WF: worker_initialisation(task_data)
            WF->>DB: enqueue_task(worker_id, "execute_standard_worker")
            
            BP->>WF: execute_standard_worker(task_data)
            WF->>DB: update_worker(worker_id, task_result)
            
            alt All Workers Complete
                BP->>PF: execute_synthesis(task_data)
                PF->>DB: update_planner(planner_id, user_response, "completed")
                PF->>R: notify_planner_completion(planner_id)
            end
        end
    end
```

### Concurrent Task Processing

```mermaid
graph LR
    subgraph "Task Queue Database"
        Q[(TaskQueue Table)]
    end
    
    subgraph "Background Processor"
        BP[Background Processor<br/>Scans every 1s]
    end
    
    subgraph "Concurrent Execution"
        P1[Planner 1<br/>execute_initial_planning]
        P2[Planner 2<br/>execute_task_creation] 
        W1[Worker 1<br/>execute_standard_worker]
        W2[Worker 2<br/>execute_sql_worker]
        W3[Worker 3<br/>execute_standard_worker]
    end
    
    subgraph "Entity Isolation"
        E1[Entity: planner_123<br/>Tasks execute sequentially]
        E2[Entity: planner_456<br/>Tasks execute sequentially]
        E3[Entity: worker_789<br/>Tasks execute sequentially]
    end
    
    Q --> BP
    BP --> P1
    BP --> P2
    BP --> W1
    BP --> W2
    BP --> W3
    
    P1 --> E1
    P2 --> E2
    W1 --> E1
    W2 --> E2
    W3 --> E3
    
    style Q fill:#e1f5fe
    style BP fill:#f3e5f5
    style E1 fill:#e8f5e8
    style E2 fill:#e8f5e8
    style E3 fill:#e8f5e8
```

### Task State Transitions

```mermaid
stateDiagram-v2
    [*] --> PENDING: Task Queued
    PENDING --> IN_PROGRESS: Background Processor Picks Up
    IN_PROGRESS --> COMPLETED: Function Executes Successfully
    IN_PROGRESS --> FAILED: Function Throws Exception
    
    COMPLETED --> [*]: Task Done
    FAILED --> PENDING: Retry Logic (Future)
    FAILED --> [*]: Max Retries Reached
    
    note right of PENDING
        Task sits in queue waiting
        for background processor
    end note
    
    note right of IN_PROGRESS
        Function execution active
        Database status updated
    end note
    
    note right of COMPLETED
        Task finished successfully
        Next task may be queued
    end note
    
    note right of FAILED
        Error logged to database
        Task marked as failed
    end note
```

### Router-Level Task Locking

```mermaid
graph TD
    subgraph "Router 1"
        R1[Router ABC123]
        R1 --> R1_P1[Planner Task 1]
        R1_P1 --> R1_P2[Planner Task 2]
        R1_P2 --> R1_P3[Planner Task 3]
    end
    
    subgraph "Router 2"
        R2[Router DEF456]
        R2 --> R2_P1[Planner Task 1]
        R2_P1 --> R2_P2[Planner Task 2]
    end
    
    subgraph "Workers (Can Run Concurrently)"
        W1[Worker Task A]
        W2[Worker Task B]
        W3[Worker Task C]
        W4[Worker Task D]
    end
    
    subgraph "Background Processor"
        BP[Concurrent Execution<br/>One Task Per Router<br/>Multiple Workers]
    end
    
    R1_P1 --> BP
    R1_P2 --> BP
    R1_P3 --> BP
    R2_P1 --> BP
    R2_P2 --> BP
    
    W1 --> BP
    W2 --> BP
    W3 --> BP
    W4 --> BP
    
    style R1 fill:#e3f2fd
    style R2 fill:#f3e5f5
    style BP fill:#e8f5e8
    
    note1[Router-level locking ensures<br/>only one task per conversation<br/>executes at a time]
    note2[Multiple routers can have<br/>tasks executing concurrently]
    note3[Worker tasks from different<br/>planners execute concurrently]
```

## Communication Protocols

### WebSocket (Primary)
- **Endpoint**: `/chat`
- **Purpose**: Real-time bidirectional communication
- **Features**: 
  - Instant messaging with router persistence
  - Status updates during processing
  - Automatic router history on connect
  - File-based analysis triggering

### HTTP REST (Secondary)
- **Purpose**: File uploads and router management
- **Endpoints**: 
  - `POST /upload` - File uploads
  - `GET /routers/{id}` - Router history
  - `GET /health` - Service status

## Key Features

### Function-Based Task Architecture
- Immediate HTTP responses with background processing
- Async task queue for scalable agent execution
- Concurrent processing of multiple agents and conversations
- Function-based design for improved maintainability and testability

### Intelligent Routing
- Automatic detection of simple chat vs complex analysis needs
- Immediate responses for simple queries
- Background task queueing for complex processing
- Real-time WebSocket status updates during background execution

### Multi-Modal Processing
- Image analysis and chart reading with file storage
- PDF document processing with text/image extraction
- CSV data analysis with SQL queries and DuckDB integration
- Organised file management with collision avoidance

### Advanced State Management
- Persistent router and agent state with SQLite database
- File path storage with JSON columns
- Task queue with status tracking and error handling
- Recovery mechanisms for failed tasks
- Cross-session state persistence and restoration

## Development Structure (Monorepo)

```
agent/
├── backend/
│   ├── src/agent/          # Agent system library
│   │   ├── core/           # RouterAgent (function-based)
│   │   ├── tasks/          # Async task functions
│   │   │   ├── planner_tasks.py    # Planning function library
│   │   │   ├── worker_tasks.py     # Worker function library
│   │   │   ├── file_manager.py     # File storage operations
│   │   │   └── task_utils.py       # Task queue utilities
│   │   ├── services/       # Background processor and LLM services
│   │   │   ├── background_processor.py  # Async task processor
│   │   │   ├── llm_service.py           # LLM integration
│   │   │   └── image_service.py         # Image processing
│   │   ├── models/         # Pydantic schemas and database models
│   │   │   ├── agent_database.py       # Database models and operations
│   │   │   ├── tasks.py                # Task-related models
│   │   │   └── responses.py            # Response models
│   │   ├── config/         # Configuration and settings
│   │   ├── utils/          # Utility functions and tools
│   │   └── security/       # Security and validation
│   ├── tests/              # Comprehensive test suite
│   │   ├── test_*.py       # Function-based testing
│   │   └── ...             # Organised by functionality
│   ├── main.py             # FastAPI server entry point
│   ├── pyproject.toml      # uv-managed dependencies
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── app/            # Next.js App Router
│   │   ├── components/     # Modular React components
│   │   │   ├── ChatInterface.tsx    # Main orchestrator
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
├── ARCHITECTURE.md         # This file
└── README.md
```

## Technical Benefits

### Function-Based Architecture
- Immediate HTTP responses improve user experience
- Background task processing enables concurrent operations
- Function-based design improves testability and maintainability
- Async task queue supports scalable processing
- Separation of concerns between routing and processing

### Performance & Responsiveness
- Sub-100ms response times for simple chat interactions
- Non-blocking background processing for complex tasks
- Concurrent execution of multiple conversations
- Efficient task queue with database persistence
- Real-time WebSocket updates during background execution

### Scalability & Reliability
- Task queue enables horizontal scaling of background processors
- Database-backed state management ensures reliability
- Error handling and recovery mechanisms for failed tasks
- File storage system with collision avoidance
- Comprehensive test suite ensures system stability

### Developer Experience
- Function-based design simplifies testing and debugging
- Clear separation between immediate and background operations
- Type safety across frontend/backend with shared types
- Comprehensive test coverage for all major components
- Container-ready deployment with Docker
- uv-based dependency management for fast builds
- Modern development patterns throughout the stack

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
- Advanced router analytics
- Plugin system for additional agent capabilities
- Mobile-responsive PWA features