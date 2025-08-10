# Agents Module

Core agent implementations that handle task planning and execution in the AI agent system with database persistence.

## Modules

### `planner.py`
Main planning agent that orchestrates task execution using a database-driven task management system.

#### Classes

**`TaskManager`**
- Manages task lifecycle using database persistence
- **Methods:**
  - `__init__(planner_id, agent_db)`: Initialize with planner ID and database connection
  - `queue_single_task(task)`: Queue a FullTask to database and return worker_id
  - `get_current_task()`: Get worker_id of current pending task
  - `execute_current_task(duck_conn)`: Execute the current pending task
  - `get_completed_task()`: Get a completed task that needs recording
  - `mark_task_recorded(task_id)`: Mark task as recorded after planner processes it
  - `has_pending_tasks()`: Check if there are any pending tasks
  - `recover_from_restart()`: Recover any in-progress task from previous session

**`PlannerAgent(BaseAgent)`**
- Database-persisted planner that orchestrates complex multi-step task execution
- Supports both new planning and resumption from database state
- **Key Methods:**
  - `__init__(id, user_question, instruction, files, model, temperature, failed_task_limit)`: Initialize planner with database persistence
  - `invoke()`: Main execution loop with restart recovery and database-driven task management
  - `load_image(image, encoded_image, image_name)`: Load images for task context
  - `assess_completion()`: Validate task completion using LLM assessment
  - `task_result_synthesis()`: Process completed tasks and update execution plan
  - `get_table_metadata(table_name)`: Extract metadata from database tables with column cleaning

#### Functions

**`clean_table_name(input_string)`**
- Sanitises strings to create valid SQL table names
- Handles special characters and ensures DuckDB compliance
- Returns fallback name if cleaning fails

**`clean_column_name(input_string, i, all_cols)`**
- Sanitises strings to create valid SQL column names
- Prevents naming conflicts and ensures uniqueness
- Handles special cases like percentage symbols

### `worker.py`
Database-persisted worker agents that execute individual tasks with different specialisations.

#### Classes

**`BaseWorkerAgent(BaseAgent)`**
- Abstract base class for all worker agents with database persistence
- Supports both new task execution and resumption from database state
- **Key Methods:**
  - `__init__(task, id, planner_id, max_retry, model, temperature)`: Initialize with database support
  - `_load_existing_state(state)`: Load worker state from database
  - `_create_new_worker(task, planner_id, max_retry, model, temperature)`: Create new worker with database record
  - `_setup_worker_messages()`: Configure initial system messages for new workers

**`WorkerAgent(BaseWorkerAgent)`**
- General-purpose worker for Python code execution using sandboxed environment
- **Key Methods:**
  - `invoke()`: Main execution loop with retry logic and validation
  - `_validate_task_result(artefact, code_result)`: Validate task completion against acceptance criteria
  - `_process_outputs(artefact, code_result)`: Handle image and variable outputs from code execution

**`WorkerAgentSQL(BaseWorkerAgent)`**
- Specialised worker for SQL query execution using DuckDB
- **Key Methods:**
  - `invoke()`: Execute SQL-based tasks with comprehensive error handling
  - Direct SQL execution with proper error reporting and validation

#### Functions

**`convert_result_to_str(result)`**
- Convert TaskResult objects to formatted strings for display

## Usage Patterns

### Planning and Execution (New Conversation)
```python
from agent.agents.planner import PlannerAgent
from agent.models.schemas import File

planner = PlannerAgent(
    user_question="Analyse sales data",
    instruction="Generate comprehensive insights",
    files=[File(filepath="sales.csv", file_type="data")],
    model="gemini-2.5-pro"
)
await planner.invoke()
```

### Resuming Existing Planner
```python
from agent.agents.planner import PlannerAgent

# Resume from database state
planner = PlannerAgent(id="existing-planner-id")
await planner.invoke()  # Continues from where it left off
```

### Direct Worker Execution (New Task)
```python
from agent.agents.worker import WorkerAgent, WorkerAgentSQL
from agent.models.tasks import FullTask

# General Python worker
worker = WorkerAgent(task=full_task, planner_id="planner-123")
await worker.invoke()

# SQL-specialised worker
sql_worker = WorkerAgentSQL(task=sql_task, planner_id="planner-123")
await sql_worker.invoke()
```

### Resuming Existing Worker
```python
from agent.agents.worker import WorkerAgent

# Resume from database state
worker = WorkerAgent(id="existing-worker-id", planner_id="planner-123")
await worker.invoke()  # Continues task execution
```

## Task Flow

1. **RouterAgent** determines if PlannerAgent activation is needed
2. **PlannerAgent** creates execution plan and queues first task via **TaskManager**
3. **TaskManager** stores tasks in database and manages execution order
4. **WorkerAgent** or **WorkerAgentSQL** executes individual tasks with database persistence
5. **PlannerAgent** processes completed tasks via `task_result_synthesis()`
6. Execution plan is updated and next task is generated until completion
7. Final **RequestResponse** is generated for the user

## Database Integration

### Agent State Management
- All agents persist state to SQLite database
- Support for interruption and resumption
- Message history maintained per agent type
- Automatic state synchronisation during execution

### Task Persistence
- Tasks stored in database with status tracking
- Worker agents can be resumed after interruption
- Task results and outputs preserved across sessions
- Comprehensive audit trail for debugging

## Error Handling

- **Restart Recovery**: Automatic detection and resumption of interrupted tasks
- **Database Consistency**: Proper state management during failures
- **Task Validation**: Acceptance criteria checking with LLM assessment
- **Retry Logic**: Configurable retry limits with failure tracking
- **Graceful Degradation**: Detailed error reporting without system crashes
- **Loop Protection**: Failed task limits prevent infinite loops