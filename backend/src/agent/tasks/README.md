# Task Functions

The tasks module implements worker task execution and file management for the agent system. With the new frontend-orchestrated architecture, planner functions are deprecated and the router handles execution plans directly through MCP tools.

## Architecture Overview

The system now uses synchronous execution controlled by the frontend:

- **No Task Queue**: All execution is immediate and synchronous
- **No Background Processor**: Frontend orchestrates execution via WebSocket
- **MCP Tools**: Execute Python, SQL, and store plans directly
- **Worker Functions**: Still used for structured task execution
- **File Management**: Comprehensive storage and retrieval system

## Module Structure

```
tasks/
├── worker_tasks.py       # Worker execution functions
├── file_manager.py       # File storage and retrieval
├── planner_tasks.py      # DEPRECATED - Planner functions (commented out)
└── README.md            # This documentation
```

## Core Functions

### Worker Functions (`worker_tasks.py`)

#### `worker_initialisation(task_data: Dict[str, Any])`
Initialises worker with task context and prepares for execution.

**Parameters:**
- `task_data`: Contains worker ID, task description, and context

**Process:**
1. Creates worker record in database
2. Sets up worker message history
3. Prepares execution environment
4. Returns ready status for execution

#### `execute_standard_worker(task_data: Dict[str, Any])`
Executes general-purpose worker tasks using available tools.

**Parameters:**
- `task_data`: Contains task description, tools, and context

**Process:**
1. Loads task context and available tools
2. Executes task using LLM with tool capabilities
3. Stores results in worker variables
4. Updates worker status and messages
5. Returns execution results

#### `execute_sql_worker(task_data: Dict[str, Any])`
Specialised worker for SQL query execution on data.

**Parameters:**
- `task_data`: Contains SQL context, database connection, and query requirements

**Process:**
1. Connects to data source (DuckDB, SQLite, etc.)
2. Executes SQL queries with validation
3. Processes query results
4. Stores results for later use
5. Returns formatted query outputs

### File Manager (`file_manager.py`)

#### Storage Functions

##### `save_worker_variable(worker_id: str, key: str, value: Any, check_existing: bool = False)`
Saves worker execution results with collision avoidance.

**Returns:** `(file_path, final_key)` tuple

**Features:**
- JSON serialisation for complex data
- Collision detection and key renaming
- Lazy loading support
- Filesystem-based persistence

##### `get_worker_variable(worker_id: str, key: str) -> Any`
Retrieves stored worker variables with lazy loading.

**Features:**
- Automatic deserialisation
- Error handling for missing keys
- Memory-efficient loading

##### `save_worker_image(worker_id: str, key: str, image_data: str, check_existing: bool = False)`
Stores base64-encoded images from worker execution.

**Features:**
- Base64 decoding and validation
- Image format detection
- Collision avoidance
- Path generation

#### Utility Functions

##### `list_worker_variables(worker_id: str) -> List[str]`
Lists all stored variables for a worker.

##### `delete_worker_variables(worker_id: str)`
Cleans up all worker files after completion.

##### `get_worker_directory(worker_id: str) -> Path`
Returns the filesystem path for worker storage.

### Deprecated Functions (`planner_tasks.py`)

The following functions are commented out and no longer used:

- ~~`execute_initial_planning`~~ - Router handles plans via MCP tools
- ~~`execute_task_creation`~~ - Frontend orchestrates task creation
- ~~`execute_synthesis`~~ - Results processed synchronously

## Migration from Planner to Router

### Before (Planner-based)
```python
# Old approach - background task queue
await update_planner_next_task_and_queue(
    planner_id="abc123",
    function_name="execute_initial_planning",
    payload={"user_question": "..."}
)
```

### After (Router-based)
```python
# New approach - direct MCP tool execution
await mcp_manager.execute_tool(
    "agent_tools__set_plan_and_answer",
    {
        "router_id": "abc123",
        "execution_plan": "...",
        "answer": "..."
    }
)
```

## File Organisation

### Directory Structure
```
/app/files/collaterals/
├── workers/
│   ├── {worker_id}/
│   │   ├── variables/
│   │   │   ├── {key}.json
│   │   │   └── ...
│   │   └── images/
│   │       ├── {key}.png
│   │       └── ...
└── routers/
    └── {router_id}/
        └── execution_plan.json
```

### File Naming Convention
- Variables: `{key}.json` or `{key}_{n}.json` for collisions
- Images: `{key}.png` or `{key}_{n}.png` for collisions
- Plans: Stored in router database, not filesystem

## Best Practices

1. **Worker Isolation**: Each worker has its own storage directory
2. **Collision Handling**: Always use `check_existing=True` for safety
3. **Cleanup**: Delete worker files after task completion
4. **Error Handling**: Wrap file operations in try-catch blocks
5. **Lazy Loading**: Only load variables when needed

## Performance Considerations

- File I/O is synchronous (no async file operations)
- JSON serialisation for all variable types
- Images stored as files, not in database
- Worker directories created on demand
- Automatic cleanup prevents storage bloat

## Testing

```bash
# Test worker functions
pytest tests/unit/test_worker_tasks.py

# Test file manager
pytest tests/unit/test_file_manager.py
```

## Future Enhancements

- Async file I/O for better performance
- S3/cloud storage support
- File compression for large data
- Caching layer for frequently accessed files
- File versioning and history