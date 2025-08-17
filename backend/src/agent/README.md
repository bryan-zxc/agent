# Agent Library

A comprehensive AI agent system for processing various file types and executing complex tasks using large language models.

## Architecture Overview

This library implements a function-based task queue system that processes documents, images, and data files to answer user questions and execute complex tasks. The system uses a router-background processor architecture where the RouterAgent handles immediate responses and queues background tasks for a function-based execution engine.

## Directory Structure

```
agent/
├── config/          # Configuration and settings
├── core/            # RouterAgent and base routing logic
├── models/          # Pydantic models, database schemas, and API responses
├── security/        # Security and safety guardrails
├── services/        # External service integrations and background processor
├── tasks/           # Function-based task implementations and file management
└── utils/           # Utility functions and tools
```

## Key Components

### Core (`core/`)
- **RouterAgent**: WebSocket-enabled chat interface with immediate response capability
- **Task routing**: Automatic detection of simple chat vs complex analysis needs

### Tasks (`tasks/`)
- **Planner Functions**: `execute_initial_planning`, `execute_task_creation`, `execute_synthesis`
- **Worker Functions**: `worker_initialisation`, `execute_standard_worker`, `execute_sql_worker`
- **File Manager**: Variable/image storage with collision avoidance and lazy loading
- **Task Utilities**: Queue management and background task coordination

### Services (`services/`)
- **Background Processor**: Continuous async task execution with 1-second polling
- **LLM Service**: Unified interface for multiple language models (OpenAI, Anthropic, Google)
- **Image Service**: Image analysis and content recognition

### Models (`models/`)
- **Agent Database**: SQLite-based storage with JSON columns for file paths
- **Task Models**: Define task structure and execution flow
- **Response Models**: Structure API responses and validations
- **Schema Models**: Data models for files, images, and documents

## Getting Started

### WebSocket Integration (Recommended)
```python
from agent.core.router import RouterAgent
from agent.services.background_processor import start_background_processor
from fastapi import FastAPI, WebSocket

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    # Start background processor for task execution
    await start_background_processor()

@app.websocket("/chat")
async def websocket_endpoint(websocket: WebSocket):
    router = RouterAgent()
    await router.connect_websocket(websocket)
    
    # Handle messages with immediate response + background processing
    while True:
        data = await websocket.receive_json()
        await router.handle_message(data)  # Returns immediately, tasks run in background
```

### Function-Based Task Usage
```python
from agent.tasks.file_manager import save_planner_variable, get_planner_variable
from agent.tasks.task_utils import update_planner_next_task_and_queue

# Save complex data structures with collision avoidance
analysis_results = {"insights": [...], "metrics": {...}}
file_path, final_key = save_planner_variable(
    planner_id="abc123", 
    key="analysis_results", 
    value=analysis_results,
    check_existing=True
)

# Lazy load when needed
data = get_planner_variable("abc123", "analysis_results")

# Queue background tasks
success = update_planner_next_task_and_queue(
    planner_id="abc123",
    function_name="execute_initial_planning",
    payload={"user_question": "Analyze the data", "instruction": "Use charts"}
)
```

## Features

- **Function-Based Architecture**: Immediate HTTP responses with background task processing
- **Real-time Communication**: WebSocket-based chat interface with router persistence
- **Intelligent Routing**: Automatically switches between simple chat and complex analysis
- **Background Processing**: Async task queue with 1-second polling for scalable execution
- **Multi-modal Processing**: Handles text, images, charts, tables, and data files
- **Task Planning**: Function-based planning with `execute_initial_planning`, `execute_task_creation`, `execute_synthesis`
- **Worker Execution**: Concurrent worker functions for individual task execution
- **Code Execution**: Safe sandboxed Python code execution
- **SQL Queries**: DuckDB integration for data analysis
- **Image Analysis**: Chart reading, table extraction, and visual content analysis
- **Document Processing**: PDF parsing and text document processing with multi-encoding support
- **Database Persistence**: SQLite-based storage with JSON columns for file paths
- **File Storage System**: Organised file management with lazy loading and collision avoidance
- **Concurrent Processing**: Multiple conversations and planners execute simultaneously
- **Safety**: Built-in security guardrails and code validation

## File Storage System

The agent system implements a sophisticated file storage mechanism that handles both intermediate processing variables and images generated during task execution. This system provides organised file management, lazy loading, and collision avoidance to ensure reliable and efficient data persistence.

### Architecture Overview

The file storage system operates on a hybrid approach combining database references with filesystem storage:

- **Database Storage**: File paths and metadata are stored in SQLite database JSON columns
- **Filesystem Storage**: Actual file content is stored in organised directory structures
- **Lazy Loading**: Files are only loaded from disk when explicitly requested
- **Collision Avoidance**: Automatic handling of naming conflicts with hex suffix generation

### Directory Structure

Files are organised in a hierarchical structure under the configured base path:

```
/app/files/agent_collaterals/
└── {planner_id}/
    ├── variables/
    │   ├── variable_name.pkl
    │   ├── complex_data_abc.pkl  # Collision-avoided with hex suffix
    │   └── analysis_results.pkl
    ├── images/
    │   ├── chart_analysis.b64
    │   ├── processed_image_def.b64  # Collision-avoided with hex suffix
    │   └── generated_plot.b64
    ├── execution_plan_model.json  # Pydantic model serialisation
    └── current_task.json          # Current task state
```

### Core Functions

#### Variable Storage (`tasks/file_manager.py`)

**`save_planner_variable(planner_id, key, value, check_existing=False)`**
- Serialises Python objects using pickle format
- Stores file path in database `variable_file_paths` JSON column
- Supports collision avoidance with hex suffix generation
- Returns tuple of (file_path, final_key_used)

**`get_planner_variable(planner_id, key)`**
- Lazy loads variables only when requested
- Retrieves file path from database, then loads from filesystem
- Returns deserialised Python object or None if not found

#### Image Storage (`tasks/file_manager.py`)

**`save_planner_image(planner_id, raw_image_name, encoded_image, check_existing=False)`**
- Stores base64 encoded images as text files (.b64 extension)
- Performs name cleaning (alphanumeric + underscores only)
- Handles duplicate names with counter system
- Supports collision avoidance with hex suffix generation
- Updates database `image_file_paths` JSON column

**`get_planner_image(planner_id, key)`**
- Lazy loads images only when requested
- Returns base64 encoded string for direct use in LLM calls
- Provides efficient memory usage by avoiding loading all images

#### Collision Avoidance System

The system implements intelligent collision avoidance using hex suffixes:

```python
# Original: "analysis_results"
# If collision detected: "analysis_results_a3f"
# If still collision: "analysis_results_b72"
```

**Variable Path Generation:**
- Generates 3-character hex suffixes using `secrets.token_hex(3)`
- Checks filesystem for existing files before finalising path
- Updates database with final key name used

**Image Name Cleaning:**
- Removes non-alphanumeric characters (except underscores)
- Eliminates repeated underscores
- Strips leading/trailing underscores
- Falls back to "image" if name becomes empty after cleaning

### Database Integration

File paths are stored in the database using JSON columns for efficient querying:

**Planner Table Schema (`models/agent_database.py:103-104`):**
```python
variable_file_paths = Column(JSON, default=lambda: {})  # {key: file_path}
image_file_paths = Column(JSON, default=lambda: {})     # {key: file_path}
```

**Storage Pattern:**
```json
{
  "variable_file_paths": {
    "analysis_results": "/app/files/agent_collaterals/planner123/variables/analysis_results.pkl",
    "user_data": "/app/files/agent_collaterals/planner123/variables/user_data_a3f.pkl"
  },
  "image_file_paths": {
    "chart_analysis": "/app/files/agent_collaterals/planner123/images/chart_analysis.b64",
    "processed_chart": "/app/files/agent_collaterals/planner123/images/processed_chart_def.b64"
  }
}
```

### Cleanup Mechanisms

**Automatic Cleanup (`tasks/file_manager.py:363`):**
- `cleanup_planner_files(planner_id)` removes entire planner directory
- Called automatically during planner completion synthesis
- Integrated into planner lifecycle for memory management
- Handles permission errors gracefully with logging

**Manual Cleanup:**
- Individual file removal through filesystem operations
- Database path cleanup through JSON column updates

### Usage Patterns

#### Saving Complex Data
```python
from agent.tasks.file_manager import save_planner_variable

# Save analysis results
analysis_data = {"insights": [...], "metrics": {...}}
file_path, final_key = save_planner_variable(
    planner_id="abc123", 
    key="analysis_results", 
    value=analysis_data,
    check_existing=True  # Enable collision avoidance
)
```

#### Loading Data with Lazy Loading
```python
from agent.tasks.file_manager import get_planner_variable

# Only loads from disk when called
analysis_data = get_planner_variable("abc123", "analysis_results")
if analysis_data:
    insights = analysis_data["insights"]
```

#### Working with Images
```python
from agent.tasks.file_manager import save_planner_image, get_planner_image

# Save generated chart
save_planner_image(
    planner_id="abc123",
    raw_image_name="sales_chart.png", 
    encoded_image=base64_string,
    check_existing=True
)

# Lazy load for LLM processing
chart_data = get_planner_image("abc123", "sales_chart")
```

### Performance Characteristics

**Memory Efficiency:**
- Lazy loading prevents loading unnecessary files into memory
- Large datasets stored on filesystem, only metadata in database
- Images stored as text files for efficient base64 handling

**I/O Optimisation:**
- Single database query retrieves all file paths
- Individual file loading only when specifically requested
- Pickle serialisation for efficient Python object storage

**Scalability:**
- Directory-per-planner structure prevents filesystem bottlenecks
- JSON columns enable efficient path queries
- Automatic cleanup prevents storage accumulation

## Dependencies

- **LLM Providers**: OpenAI, Anthropic Claude, Google Gemini
- **Data Processing**: pandas, DuckDB, pypdf
- **Image Processing**: PIL, base64 encoding
- **Validation**: Pydantic models
- **Execution**: Sandboxed Python environment