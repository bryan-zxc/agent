# Task Functions

The tasks module implements the function-based task execution system that replaced the class-based agent architecture. This system provides async task functions for planner and worker execution, along with comprehensive file management capabilities.

## Architecture Overview

The function-based system operates through a background processor that executes queued tasks asynchronously:

- **Task Queue**: SQLite-based queue with task status tracking
- **Background Processor**: Continuous 1-second polling for task execution  
- **Function Registry**: Maps function names to executable async functions
- **Entity Isolation**: Sequential task execution per entity (planner/worker)
- **Concurrent Processing**: Multiple entities can execute tasks simultaneously

## Module Structure

```
tasks/
├── planner_tasks.py      # Planner execution functions
├── worker_tasks.py       # Worker execution functions  
├── file_manager.py       # File storage and retrieval
├── task_utils.py         # Queue management utilities
└── README.md            # This documentation
```

## Core Functions

### Planner Functions (`planner_tasks.py`)

#### `execute_initial_planning(task_data: Dict[str, Any])`
Creates execution plan from user request and queues task creation.

**Parameters:**
- `task_data`: Contains `user_question`, `instruction`, `files`, `planner_name`, `router_id`

**Process:**
1. Creates planner record in database with user question and instructions
2. Generates execution plan using LLM with file processing instructions
3. Saves execution plan model to filesystem and database
4. Queues `execute_task_creation` for next step

**Key Features:**
- File type detection and instruction generation
- Execution plan validation and storage
- Automatic progression to task creation phase

#### `execute_task_creation(task_data: Dict[str, Any])`
Breaks down execution plan into individual worker tasks.

**Parameters:**
- `task_data`: Contains planner context and execution plan

**Process:**
1. Loads execution plan model from filesystem
2. Analyses plan and generates individual worker tasks
3. Creates worker records in database for each task
4. Queues `worker_initialisation` for each worker
5. Queues `execute_synthesis` when all workers are created

**Key Features:**
- Dynamic task generation based on plan complexity
- Worker task distribution and queuing
- Parallel worker initialisation

#### `execute_synthesis(task_data: Dict[str, Any])`
Processes worker results and generates final user response.

**Parameters:**
- `task_data`: Contains planner context and worker results

**Process:**
1. Checks if all workers have completed successfully
2. Collects worker results and execution context
3. Generates final user response using LLM synthesis
4. Updates planner status to completed
5. Triggers cleanup of planner files
6. Notifies router of completion for WebSocket delivery

**Key Features:**
- Worker result aggregation
- Final response generation
- Automatic file cleanup
- Router notification for real-time delivery

### Worker Functions (`worker_tasks.py`)

#### `worker_initialisation(task_data: Dict[str, Any])`
Initialises worker with task context and prepares for execution.

**Parameters:**
- `task_data`: Contains worker ID and task description

**Process:**
1. Loads task context and planner variables/images
2. Prepares execution environment with available tools
3. Validates task requirements and prerequisites  
4. Queues appropriate execution function based on task type
5. Updates worker status to ready for execution

**Key Features:**
- Context loading from planner state
- Tool availability validation
- Task type detection for routing

#### `execute_standard_worker(task_data: Dict[str, Any])`
Executes general worker tasks with code generation and validation.

**Parameters:**
- `task_data`: Contains worker context and task details

**Process:**
1. Generates Python code for task execution
2. Executes code in sandboxed environment
3. Validates results against acceptance criteria
4. Saves output variables and images to filesystem
5. Updates worker status and task results

**Key Features:**
- Safe code execution with security guardrails
- Result validation and quality checks
- Variable/image persistence with collision avoidance

#### `execute_sql_worker(task_data: Dict[str, Any])`
Specialised worker for database queries and data analysis.

**Parameters:**
- `task_data`: Contains SQL task context and data files

**Process:**
1. Loads CSV/data files into DuckDB
2. Generates SQL queries for data analysis
3. Executes queries with result validation
4. Formats results for user presentation
5. Saves analysis results to planner variables

**Key Features:**
- DuckDB integration for efficient data processing
- SQL query generation and validation
- Structured result formatting

## File Management (`file_manager.py`)

### Variable Storage

Variables are serialised using pickle and stored with collision avoidance:

```python
# Save complex data with automatic collision handling
file_path, final_key = save_planner_variable(
    planner_id="abc123",
    key="analysis_results", 
    value={"insights": [...], "metrics": {...}},
    check_existing=True  # Enables hex suffix collision avoidance
)

# Lazy load when needed - only reads from disk when called
data = get_planner_variable("abc123", "analysis_results")
```

### Image Storage

Images are stored as base64 text files with name cleaning and collision avoidance:

```python
# Save image with automatic name cleaning
file_path, final_name = save_planner_image(
    planner_id="abc123",
    raw_image_name="sales chart (2024).png",  # Cleaned to: sales_chart_2024
    encoded_image=base64_string,
    check_existing=True
)

# Lazy load for LLM processing
chart_data = get_planner_image("abc123", "sales_chart_2024")
```

### Collision Avoidance System

The system automatically handles naming conflicts using hex suffixes:

- **Original**: `analysis_results.pkl`
- **First collision**: `analysis_results_a3f.pkl`  
- **Second collision**: `analysis_results_b72.pkl`

This ensures data integrity whilst maintaining predictable naming patterns.

### File Cleanup

Automatic cleanup is integrated into the planner lifecycle:

```python
# Called automatically during execute_synthesis completion
cleanup_success = cleanup_planner_files(planner_id)
```

## Task Queue Management (`task_utils.py`)

### Queue Operations

#### `update_planner_next_task_and_queue(planner_id, function_name)`
Queues a new task for background execution with no payload data.

**Parameters:**
- `planner_id`: Entity identifier for task isolation
- `function_name`: Name of function to execute (must be in background processor registry)

**Returns:**
- `bool`: Success status of queue operation

### Database Schema

Tasks are stored in the `task_queue` table with the following structure:

```sql
CREATE TABLE task_queue (
    task_id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,    -- 'planner' or 'worker'
    entity_id TEXT NOT NULL,      -- Links to planners/workers table
    function_name TEXT NOT NULL,  -- Function to execute
    payload JSON,                 -- Function parameters
    status TEXT NOT NULL,         -- 'PENDING', 'IN_PROGRESS', 'COMPLETED', 'FAILED'
    error_message TEXT,           -- Error details if failed
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Usage Patterns

### Direct Function Execution (Testing)

```python
# For testing individual functions
from agent.tasks.planner_tasks import execute_initial_planning

task_data = {
    "task_id": "test_task_123",
    "entity_id": "planner_456", 
    "payload": {
        "user_question": "Analyse sales data",
        "instruction": "Create charts and insights",
        "files": []
    }
}

await execute_initial_planning(task_data)
```

### Background Queue Integration

```python
# Task chaining (no payload needed)
from agent.tasks.task_utils import update_planner_next_task_and_queue

success = update_planner_next_task_and_queue(
    planner_id="planner_456",
    function_name="execute_task_creation"
)

# Initial task with payload (use direct database enqueue)
from agent.models.agent_database import AgentDatabase
import uuid

db = AgentDatabase()
task_id = uuid.uuid4().hex
success = db.enqueue_task(
    task_id=task_id,
    entity_type="planner",
    entity_id="planner_456",
    function_name="execute_initial_planning",
    payload={
        "user_question": "Analyse sales data",
        "instruction": "Create charts and insights", 
        "files": []
    }
)
```

### Error Handling

All task functions implement comprehensive error handling:

```python
try:
    # Function execution
    result = await some_task_function(task_data)
except Exception as e:
    # Background processor catches exceptions and:
    # 1. Updates task status to 'FAILED'
    # 2. Stores error message in database
    # 3. Logs error details
    # 4. Optionally implements retry logic
    pass
```

## Performance Characteristics

### Execution Model

- **Sequential per Entity**: Tasks for the same planner/worker execute sequentially
- **Concurrent across Entities**: Multiple planners can execute simultaneously  
- **Background Processing**: All execution happens asynchronously
- **Immediate Response**: Router responds instantly while tasks queue

### Scalability Features

- **Database Queue**: Persistent task storage survives restarts
- **Function Registry**: Easy addition of new task types
- **Concurrent Execution**: Scales with number of entities
- **Resource Management**: Automatic file cleanup prevents accumulation

### Memory Efficiency

- **Lazy Loading**: Files only loaded when specifically requested
- **Filesystem Storage**: Large data stored outside database
- **Cleanup Integration**: Automatic removal of completed planner files
- **JSON Metadata**: Efficient database storage of file paths

## Error Recovery

The system provides robust error handling and recovery:

### Task Failure Handling

1. **Exception Capture**: All function exceptions caught by background processor
2. **Status Updates**: Failed tasks marked in database with error details
3. **Logging**: Comprehensive error logging for debugging
4. **Isolation**: Failed tasks don't affect other entities

### Retry Logic (Future Enhancement)

The database schema supports retry logic:

- `retry_count`: Tracks number of retry attempts
- `max_retries`: Configurable retry limit per task
- `error_message`: Stores failure details for analysis

### System Recovery

- **Persistent Queue**: Tasks survive application restarts
- **Resumable Execution**: Background processor picks up pending tasks on startup
- **State Preservation**: Database maintains complete execution state

This function-based architecture provides a robust, scalable foundation for complex multi-modal AI task execution whilst maintaining simplicity and performance.