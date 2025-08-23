# Agent System Backend Tests

Comprehensive two-tier test suite combining lightweight unit tests for rapid feedback with thorough integration tests for end-to-end validation.

## Test Structure

```
backend/tests/
├── unit/                           # Lightweight unit tests (<30s total)
│   ├── test_async_validation.py    # Async/await compliance tests
│   ├── test_import_structure.py    # Import and dependency tests
│   ├── test_database_operations.py # Database functionality tests
│   ├── test_router_agent.py       # RouterAgent ephemeral architecture
│   ├── test_task_execution.py     # Task pipeline and functions
│   ├── test_file_manager.py       # File storage and retrieval
│   ├── test_websocket_communication.py # WebSocket functionality
│   ├── test_api_endpoints.py      # FastAPI endpoint tests
│   └── __init__.py
├── integration/                    # Comprehensive integration tests
│   ├── test_background_processor_efficiency.py # Performance validation
│   ├── test_concurrent_planner_execution.py    # Concurrency testing
│   ├── test_multiple_conversations_concurrent.py # Multi-router isolation
│   ├── test_fastapi_immediate_response.py      # API response validation
│   ├── test_file_storage.py                    # File operations end-to-end
│   └── test_websocket_updates_execution.py     # WebSocket workflows
├── experimental/                   # Test data and experimental files
│   ├── test.ipynb                  # Jupyter notebook experiments
│   ├── Annual-Report-2023.pdf      # Test document
│   ├── img_03.png                  # Test image
│   └── *.pdf                       # Various test documents
├── run_tests.py                    # Main test runner (simplified interface)
├── run_all_tests.py               # Combined test orchestrator
├── run_unit_tests.py              # Unit test runner
├── run_integration_tests.py       # Integration test runner
└── README.md                      # This file
```

## Quick Start

### Daily Development Workflow

```bash
# Quick unit tests after code changes (recommended default)
docker-compose exec backend uv run python tests/run_tests.py

# Run all tests before major releases
docker-compose exec backend uv run python tests/run_tests.py --all

# Run integration tests for performance validation
docker-compose exec backend uv run python tests/run_tests.py --integration
```

### Specific Test Runners

```bash
# Unit tests only (rapid feedback)
docker-compose exec backend uv run python tests/run_unit_tests.py

# Integration tests only (comprehensive validation)
docker-compose exec backend uv run python tests/run_integration_tests.py

# Combined orchestrator with advanced options
docker-compose exec backend uv run python tests/run_all_tests.py
```

### Run Specific Test Suites

```bash
# Unit test suites
docker-compose exec backend uv run python tests/run_unit_tests.py --suite async_validation
docker-compose exec backend uv run python tests/run_unit_tests.py --suite database_operations

# Integration test suites  
docker-compose exec backend uv run python tests/run_integration_tests.py --suite background_processor_efficiency
docker-compose exec backend uv run python tests/run_integration_tests.py --suite concurrent_planner_execution
```

### Verbose Output and Options

```bash
# Verbose output
docker-compose exec backend uv run python tests/run_tests.py --verbose

# Stop on first failure
docker-compose exec backend uv run python tests/run_tests.py --fail-fast

# Combined options
docker-compose exec backend uv run python tests/run_tests.py --all --verbose --fail-fast
```

## Test Categories

### 1. Async/Await Validation (`test_async_validation.py`)
**Purpose:** Catch missing `await` keywords that break coroutines

**Tests:**
- RouterAgent async methods (activate_conversation, handle_message, etc.)
- AgentDatabase async operations (all `a_*` methods)
- Background Processor task execution
- LLM Service async inference calls
- Concurrent async operations
- Error handling in async context

**Performance Target:** <5 seconds

### 2. Import Structure (`test_import_structure.py`)
**Purpose:** Ensure all modules import correctly without circular dependencies

**Tests:**
- Core module imports (RouterAgent, BaseAgent)
- Model exports from `models/__init__.py`
- Service layer imports (LLM, document, image services)
- Task function imports and registry validation
- Circular dependency detection
- Import speed validation (<1 second per module)

**Performance Target:** <1 second

### 3. Database Operations (`test_database_operations.py`)
**Purpose:** Validate core async database functionality

**Tests:**
- Async connection establishment with aiosqlite
- Router, Planner, Worker CRUD operations
- JSON column operations for file paths
- Task queue CRUD operations
- Message-planner linking (Schema V2)
- Concurrent entity isolation
- Schema migration validation

**Performance Target:** <3 seconds

### 4. RouterAgent (`test_router_agent.py`)
**Purpose:** Validate ephemeral router lifecycle and operations

**Tests:**
- Ephemeral architecture (creation, state loading, cleanup)
- Message routing (simple chat vs complex request)
- WebSocket communication (all send methods require WebSocket)
- Database persistence
- File processing integration
- Title generation
- Concurrent router operations

**Performance Target:** <5 seconds

### 5. Task Execution (`test_task_execution.py`)
**Purpose:** Validate function-based task system

**Tests:**
- Planner tasks: execute_initial_planning, execute_task_creation, execute_synthesis
- Worker tasks: worker_initialisation, execute_standard_worker, execute_sql_worker
- Task queue integration and status transitions
- Early completion optimisation
- Concurrent task execution
- Error handling in task pipeline

**Performance Target:** <5 seconds

### 6. File Manager (`test_file_manager.py`)
**Purpose:** Test file storage and retrieval operations

**Tests:**
- Variable storage with collision avoidance
- Image storage with name cleaning
- Answer template operations (create, update, WIP management)
- Worker message history management
- Lazy loading behaviour
- Cleanup operations
- Concurrent file operations

**Performance Target:** <5 seconds

### 7. WebSocket Communication (`test_websocket_communication.py`)
**Purpose:** Validate real-time WebSocket communication

**Tests:**
- Connection establishment and message history
- Status updates and message delivery
- Input lock/unlock operations
- Error handling and connection resilience
- Message ordering and timestamps
- Concurrent messaging
- Large message handling

**Performance Target:** <5 seconds

### 8. API Endpoints (`test_api_endpoints.py`)
**Purpose:** Ensure FastAPI endpoints work correctly

**Tests:**
- File upload with duplicate detection
- Duplicate resolution options
- Router management endpoints
- Health checks and usage statistics
- Error handling and input validation
- Concurrent API requests

**Performance Target:** <5 seconds

## Performance Targets

- **Total execution time:** <30 seconds
- **Individual test file:** <5 seconds
- **Database tests:** <3 seconds per file
- **Import tests:** <1 second total

The test runner provides performance warnings when targets are exceeded.

## Design Principles

### Lightweight Focus
- Mock external dependencies (LLM APIs, file I/O, WebSocket connections)
- Use in-memory databases for speed
- Focus on vanilla flow testing, not comprehensive edge cases
- Rapid execution for immediate feedback

### Error Detection Priority
✅ Missing `await` keywords  
✅ Import errors and circular dependencies  
✅ Database connection failures  
✅ WebSocket communication breaks  
✅ Task execution failures  
✅ File processing errors  
✅ API integration issues  

### Test Patterns
- `unittest.IsolatedAsyncioTestCase` for async support
- Extensive use of `AsyncMock` for async components
- Temporary directories and in-memory databases for isolation
- Proper setup/teardown with resource cleanup

## Two-Tier Testing Strategy

The test suite implements a two-tier approach balancing speed and comprehensiveness:

### Tier 1: Unit Tests (Rapid Feedback)
- **Purpose:** Catch common errors quickly during development
- **Target:** <30 seconds total execution time
- **When to run:** After every code change, before commits
- **Focus:** Missing awaits, import failures, basic functionality

### Tier 2: Integration Tests (Comprehensive Validation)
- **Purpose:** End-to-end validation, performance analysis, concurrency testing
- **Target:** No strict time limits (typically 2-5 minutes)
- **When to run:** Before releases, for thorough validation
- **Focus:** System integration, performance characteristics, real-world scenarios

### Integration Test Suites
- `test_background_processor_efficiency.py` - Performance and efficiency validation
- `test_concurrent_planner_execution.py` - Complex concurrency scenarios  
- `test_multiple_conversations_concurrent.py` - Multi-router isolation testing
- `test_fastapi_immediate_response.py` - API endpoint integration
- `test_file_storage.py` - End-to-end file operations
- `test_websocket_updates_execution.py` - Full WebSocket workflows

## Running Tests in CI/CD

```bash
# Fast CI pipeline (unit tests only)
docker-compose exec backend uv run python tests/run_tests.py --fail-fast

# Comprehensive CI pipeline (all tests)
docker-compose exec backend uv run python tests/run_tests.py --all --fail-fast

# Check exit code
if [ $? -eq 0 ]; then
    echo "✅ All tests passed"
else
    echo "❌ Tests failed"
    exit 1
fi

# Example GitHub Actions workflow
name: Test Suite
on: [push, pull_request]
jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run unit tests
        run: docker-compose exec backend uv run python tests/run_tests.py --fail-fast
  
  integration-tests:
    runs-on: ubuntu-latest
    needs: unit-tests
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v3
      - name: Run integration tests
        run: docker-compose exec backend uv run python tests/run_tests.py --integration --fail-fast
```

## Adding New Tests

### When to Add Unit Tests
- New async functions (add to `test_async_validation.py`)
- New modules (add to `test_import_structure.py`)
- New database operations (add to `test_database_operations.py`)
- New API endpoints (add to `test_api_endpoints.py`)

### Test Naming Convention
```python
async def test_new_feature_awaits_correctly(self):
    """Test that new feature properly awaits async operations."""
    # Test implementation
```

### Mock Patterns
```python
# Database mocking
with patch('src.agent.models.agent_database.AgentDatabase') as MockDB:
    mock_db = AsyncMock()
    MockDB.return_value = mock_db
    mock_db.some_method.return_value = expected_value

# LLM service mocking  
with patch('src.agent.services.llm_service.LLM.a_get_response', new_callable=AsyncMock) as mock_llm:
    mock_llm.return_value = "Test response"

# WebSocket mocking
mock_websocket = AsyncMock()
await router.send_status("Test", mock_websocket)
mock_websocket.send_json.assert_awaited_once()
```

## Troubleshooting

### Common Issues

**Import Errors:**
```bash
# Ensure Python path is correct
export PYTHONPATH=/app/src
docker-compose exec backend uv run python tests/run_unit_tests.py
```

**Slow Tests:**
```bash
# Run with performance warnings
docker-compose exec backend uv run python tests/run_unit_tests.py --verbose
```

**Test Failures:**
```bash
# Run specific failing test
docker-compose exec backend uv run python tests/run_unit_tests.py --suite async_validation --verbose
```

### Debug Mode
```python
# Add to test for debugging
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Maintenance Guidelines

1. **Add tests for new async functions immediately**
2. **Keep tests lightweight - mock heavy operations**
3. **Focus on catching breaking changes, not perfection**
4. **Run after every code change before manual testing**
5. **Update when architecture changes occur**

## Performance Monitoring

The test runner tracks:
- Total execution time vs target (<30s)
- Individual test file performance
- Slow test identification
- Performance trend monitoring

Use this data to optimise test efficiency and maintain rapid feedback loops.