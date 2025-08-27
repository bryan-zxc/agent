# Task Functions

The tasks module implements the function-based task execution system that replaced the class-based agent architecture. This system provides async task functions for planner and worker execution, along with comprehensive file management capabilities.

## Architecture Overview

The function-based system operates through a background processor that executes queued tasks asynchronously:

- **Task Queue**: Async SQLite-based queue with task status tracking using aiosqlite
- **Background Processor**: Continuous 1-second polling for task execution  
- **Function Registry**: Maps function names to executable async functions
- **Entity Isolation**: Sequential task execution per entity (planner/worker)
- **Concurrent Processing**: Multiple entities can execute tasks simultaneously
- **Database Operations**: All database interactions use async/await patterns for optimal performance

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
2. Processes uploaded files (images, CSV, PDF, text) into planner context
3. Generates execution plan using LLM with file processing instructions
4. Creates initial answer template structure for progressive refinement
5. Saves execution plan model and answer templates to filesystem
6. Queues `execute_task_creation` for next step

**Key Features:**
- File type detection and instruction generation
- Initial answer template creation with placeholder structure
- Execution plan validation and storage
- Answer template file persistence (.md format)
- Automatic progression to task creation phase

#### `execute_task_creation(task_data: Dict[str, Any])`
Breaks down execution plan into individual worker tasks with historical context.

**Parameters:**
- `task_data`: Contains planner context and execution plan

**Process:**
1. Loads execution plan model from filesystem
2. Loads worker message history for context (last 10 completed tasks)
3. Analyses plan and generates individual worker tasks with historical context
4. Creates worker records in database for each task
5. Queues `worker_initialisation` for each worker
6. Queues `execute_synthesis` when all workers are created

**Key Features:**
- Dynamic task generation based on plan complexity
- Worker context from previous task completions
- Worker task distribution and queuing
- Parallel worker initialisation

#### `execute_synthesis(task_data: Dict[str, Any])`
Processes worker results, appends to message history, and generates final user response.

**Parameters:**
- `task_data`: Contains planner context and worker results

**Process:**
1. Processes completed worker results and updates execution plan
2. Updates answer template with new information from worker outputs
3. Appends completed worker responses to message history for future context
4. **Early completion check**: If no open todos remain after task completion, triggers immediate planner completion
5. Updates execution plan using LLM for remaining open tasks
6. Checks if all tasks are complete for final response generation
7. Uses filled answer template as primary source for final user response
8. Updates planner status to completed and triggers file cleanup

**Key Features:**
- **Early completion optimisation**: Skips unnecessary LLM processing when no work remains
- Progressive answer template refinement after each worker completion
- Answer template-based final response generation
- Worker result aggregation and execution plan updates
- Worker message history persistence for future tasks
- Template-driven structured response formatting
- Automatic file cleanup and completion handling

#### `_complete_planner_execution(planner_id, execution_plan_model, worker_id, planner_data, db)`
Internal helper function that handles planner completion logic to avoid code duplication.

**Parameters:**
- `planner_id`: The planner ID
- `execution_plan_model`: The execution plan model to save
- `worker_id`: The current worker ID to mark as recorded
- `planner_data`: Planner data from database
- `db`: Database connection

**Process:**
1. Loads final work-in-progress answer template
2. Generates final user response using LLM with template completion prompts
3. Saves execution plan and updates planner status to completed
4. Marks worker as recorded and performs file cleanup
5. Logs completion status

**Usage:**
- Called by early completion check when no open todos remain
- Called by standard completion logic after LLM execution plan updates
- Ensures consistent completion behaviour across both paths

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

### Answer Template Management

Answer templates provide structured response formatting with progressive refinement:

```python
# Save initial template structure
save_answer_template(
    planner_id="abc123",
    template_content="# Analysis Results\n\n## Overview\n[Summary]\n\n## Key Findings\n- [Finding 1]\n- [Finding 2]"
)

# Save work-in-progress template with partial fills
save_wip_answer_template(
    planner_id="abc123", 
    template_content="# Analysis Results\n\n## Overview\nSales data shows Q3 decline\n\n## Key Findings\n- [Finding 1]\n- [Finding 2]"
)

# Load templates for updates
current_template = load_answer_template("abc123")
wip_template = load_wip_answer_template("abc123")
```

**Template Lifecycle:**
1. **Initial Creation**: Basic markdown structure with placeholders during planning
2. **Progressive Filling**: Updated after each worker completion with new information
3. **Final Completion**: Used as primary source for final user response
4. **File Storage**: Stored as `.md` files with template and WIP versions

### Worker Message History Functions

#### `save_worker_message_history(planner_id, task_responses) -> bool`
Save complete list of worker task responses to JSON file.

#### `load_worker_message_history(planner_id) -> List[TaskResponseModel]`
Load all worker task responses from JSON file, returns empty list if file doesn't exist.

#### `append_to_worker_message_history(planner_id, task_response) -> bool`
Append single task response to existing history, automatically loads and saves complete file.

```python
# Example usage in planner synthesis
from agent.models import TaskResponseModel
from agent.tasks.file_manager import append_to_worker_message_history

task_response = TaskResponseModel(
    task_id="worker_123",
    task_description="Generate sales report with charts", 
    task_status="completed",
    assistance_responses="Created 3 charts showing revenue trends..."
)

success = append_to_worker_message_history("planner_456", task_response)
```

### Collision Avoidance System

The system automatically handles naming conflicts using hex suffixes:

- **Original**: `analysis_results.pkl`
- **First collision**: `analysis_results_a3f.pkl`  
- **Second collision**: `analysis_results_b72.pkl`

This ensures data integrity whilst maintaining predictable naming patterns.

### Worker Message History

The system maintains a persistent history of completed worker tasks to provide context for future workers:

```python
# Save worker message history (automatic during synthesis)
task_response = TaskResponseModel(
    task_id=worker_id,
    task_description="Analyse sales data trends",
    task_status="completed", 
    assistance_responses="Worker generated detailed analysis..."
)
append_to_worker_message_history(planner_id, task_response)

# Load history for context (automatic during task creation)
task_responses = load_worker_message_history(planner_id)
latest_responses = task_responses[-10:]  # Last 10 workers
```

**Storage Format:**
- **File**: `worker_message_history.json` in planner directory
- **Structure**: Array of TaskResponseModel objects
- **Retention**: Last 10 completed tasks (configurable)
- **Context**: Provided to future workers during task creation

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
success = await db.enqueue_task(
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

### System Recovery

- **Persistent Queue**: Tasks survive application restarts
- **Resumable Execution**: Background processor picks up pending tasks on startup
- **State Preservation**: Database maintains complete execution state

This function-based architecture provides a robust, scalable foundation for complex multi-modal AI task execution whilst maintaining simplicity and performance.