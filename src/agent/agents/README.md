# Agents Module

Core agent implementations that handle task planning and execution in the AI agent system.

## Modules

### `planner.py`
Main planning agent that orchestrates task execution and manages the overall workflow.

#### Classes

**`TaskQueue`**
- Manages task lifecycle from planning to completion
- **Methods:**
  - `load_plan(tasks, duck_conn)`: Load and initialize task execution plan
  - `load_task(task)`: Load individual task for execution
  - `execute_task(task)`: Execute task using appropriate worker agent

**`PlannerAgent(BaseAgent)`**
- Orchestrates complex multi-step task execution
- Breaks down user requests into manageable subtasks
- **Key Methods:**
  - `__init__(user_question, instruction, files, model, temperature, failed_task_limit)`: Initialize planner with request context
  - `invoke()`: Main execution loop for task planning and validation
  - `load_image(image, encoded_image, image_name)`: Load images for task context
  - `assess_completion()`: Validate task completion and handle failures
  - `get_table_metadata(table_name)`: Extract metadata from database tables

#### Functions

**`clean_table_name(input_string)`**
- Sanitizes strings to create valid SQL table names
- Handles special characters and ensures SQL compliance

**`clean_column_name(input_string, i, all_cols)`**
- Sanitizes strings to create valid SQL column names
- Prevents naming conflicts and ensures uniqueness

### `worker.py`
Worker agents that execute individual tasks with different specializations.

#### Classes

**`BaseWorkerAgent(BaseAgent)`**
- Abstract base class for all worker agents
- **Methods:**
  - `_validate_result()`: Validate task completion against acceptance criteria

**`WorkerAgent(BaseWorkerAgent)`**
- General-purpose worker for Python code execution and task completion
- **Key Methods:**
  - `__init__(task, max_retry, model, temperature)`: Initialize with task configuration
  - `invoke()`: Main execution loop with retry logic
  - `_process_image_variable(image, variable_name)`: Handle image outputs
  - `_process_variable(variable, variable_name)`: Handle general variable outputs

**`WorkerAgentSQL(BaseWorkerAgent)`**
- Specialized worker for SQL query execution and data analysis
- **Key Methods:**
  - `__init__(task, duck_conn, max_retry, model, temperature)`: Initialize with database connection
  - `invoke()`: Execute SQL-based tasks with error handling

#### Functions

**`convert_result_to_str(result)`**
- Convert TaskResult objects to formatted strings for display

## Usage Patterns

### Planning and Execution
```python
from agent.agents.planner import PlannerAgent
from agent.models.schemas import File

planner = PlannerAgent(
    user_question="Analyze sales data",
    files=[File(filepath="sales.csv", file_type="data")],
    model="gemini-2.5-pro"
)
await planner.invoke()
```

### Direct Task Execution
```python
from agent.agents.worker import WorkerAgent

worker = WorkerAgent(task=full_task, max_retry=3)
await worker.invoke()
```

## Task Flow

1. **PlannerAgent** receives user request and files
2. Analyzes request and breaks into atomic tasks
3. **TaskQueue** manages task execution order
4. **WorkerAgent** or **WorkerAgentSQL** executes individual tasks
5. Results are validated and consolidated
6. Final response is generated

## Error Handling

- Automatic retry logic with exponential backoff
- Task validation against acceptance criteria
- Graceful failure handling with detailed error reporting
- Protection against infinite loops through failure limits