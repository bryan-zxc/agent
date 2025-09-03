# Agent System Backend Tests

Multi-layer async/await validation test suite ensuring runtime correctness through static analysis, runtime warnings, pre-commit hooks, and comprehensive integration testing.

## 🔍 Async/Await Correctness Strategy

This test suite implements a **six-layer approach** to prevent async/await bugs from reaching production:

1. **Static Analysis** (0.1-5 sec) - Ruff + MyPy catch missing awaits immediately
2. **Runtime Warning Tests** (5-15 sec) - Unit tests detect unawaited coroutines  
3. **Hybrid Mocking** (2-3 sec) - Real async execution with selective mocking
4. **Pre-commit Hooks** (30-60 sec) - Block commits containing async issues
5. **Integration Tests** (<2 min) - System-level async execution validation
6. **End-to-End Validation** (<3 min) - Complete multi-layer effectiveness validation

**Key Innovation**: Unlike traditional testing, our approach catches async bugs **during development** rather than during manual testing or production.

## Test Structure

```
backend/tests/
├── async_test_utils.py             # 🧪 Async testing utilities & mixins
├── unit/                           # Lightweight unit tests (<30s total)
│   ├── test_async_validation.py    # ⚡ Runtime async/await compliance tests
│   ├── test_hybrid_async_execution.py # 🚀 Advanced hybrid mocking + performance
│   ├── test_import_structure.py    # Import and dependency tests
│   ├── test_database_operations.py # Database functionality tests
│   ├── test_router_operations.py  # Router operations functional tests
│   ├── test_router_operations_simple.py # Simple router operations tests
│   ├── test_async_error_utils.py  # Async error handling utilities tests
│   ├── test_task_execution.py     # 🔄 Enhanced with async warning capture
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
│   ├── test_websocket_updates_execution.py     # WebSocket workflows
│   │
│   │ ⚡ Phase 4: Enhanced Integration Testing for Real Async Execution
│   ├── test_lightweight_async_flows.py         # Critical async paths (30s)
│   ├── test_agent_activation_e2e.py            # Agent activation E2E (35s)
│   ├── test_concurrent_async_operations.py     # Concurrent async validation (45s)
│   └── test_websocket_async_communication.py   # WebSocket async flows (40s)
├── validation/                     # ⭐ Phase 6: End-to-End Validation & Performance Optimization
│   └── test_end_to_end_async_prevention.py     # Complete multi-layer validation (60s)
├── experimental/                   # Test data and experimental files
│   ├── test.ipynb                  # Jupyter notebook experiments
│   ├── Annual-Report-2023.pdf      # Test document
│   ├── img_03.png                  # Test image
│   └── *.pdf                       # Various test documents
├── async_test_utils.py            # Async testing utilities & mixins
└── README.md                      # This file

🔧 Async/Await Tools (in backend root):
├── check_async.py                  # ⚡ Quick async validation (3-5 sec)
├── setup_hooks.py                  # 🪝 Pre-commit hook installer
├── ruff.toml                       # Static analysis config
├── mypy.ini                        # Type checking config
├── .pre-commit-config.yaml         # Git hook configuration
└── docs/async_testing_strategy.md   # Complete strategy guide
```

## 🚀 Quick Start

### Running Tests with Docker (Recommended)

```bash
# Run all tests
docker-compose exec backend uv run python -m pytest tests/

# Run unit tests only
docker-compose exec backend uv run python -m pytest tests/unit/

# Run integration tests only
docker-compose exec backend uv run python -m pytest tests/integration/

# Run with verbose output
docker-compose exec backend uv run python -m pytest tests/ -v

# Stop on first failure
docker-compose exec backend uv run python -m pytest tests/ -x

# Run specific test file
docker-compose exec backend uv run python -m pytest tests/unit/test_router_operations.py

# Quick async check while coding (3-5 seconds)
python check_async.py  # Catches missing awaits immediately

# 3. Run unit tests with async warnings (5-15 seconds)  
docker-compose exec backend uv run python -m pytest tests/unit/

# 4. Commit (hooks run automatically - blocks if async issues)
git commit -m "Your changes"  # Automatic validation
```

## ⚠️ IMPORTANT: MCP Integration Test Isolation

**The LLM integration tests with MCP tools MUST be run individually**, not together.

### Why Test Isolation is Required

The MCP (Model Context Protocol) filesystem server uses stdio (stdin/stdout) communication via an npx subprocess. When pytest runs multiple tests sequentially:
- The stdio subprocess connection is lost between tests
- Subsequent tests fail with "Client is not connected" errors
- This is a **test-specific issue** that does NOT affect production

### Running MCP Integration Tests Correctly

```bash
# ✅ CORRECT: Run each test individually
docker-compose exec backend uv run python -m pytest tests/integration/test_llm_service_integration.py::TestLLMServiceIntegration::test_anthropic_mixed_tools -xvs

docker-compose exec backend uv run python -m pytest tests/integration/test_llm_service_integration.py::TestLLMServiceIntegration::test_google_mcp_tools_only -xvs

docker-compose exec backend uv run python -m pytest tests/integration/test_llm_service_integration.py::TestLLMServiceIntegration::test_openai_mcp_tools_only -xvs

# ❌ INCORRECT: Running all together will cause failures
docker-compose exec backend uv run python -m pytest tests/integration/test_llm_service_integration.py -m llm_live
```

### Production Safety

This isolation requirement does NOT affect production because:
- The MCP manager is a singleton that persists between API requests
- The stdio subprocess stays alive for the entire application lifetime
- Concurrent production requests successfully share the same MCP connection

### Traditional Development Workflow

```bash
# Quick unit tests after code changes (recommended default)
docker-compose exec backend uv run python -m pytest tests/unit/

# Run all tests before major releases
docker-compose exec backend uv run python -m pytest tests/

# Run integration tests for performance validation
docker-compose exec backend uv run python -m pytest tests/integration/
```

### Async-Specific Commands

```bash
# Quick async validation (development iteration)
python check_async.py --file src/agent/tasks/worker_tasks.py  # Specific file
python check_async.py --module tasks                          # Specific module  
python check_async.py --quiet                                 # Minimal output

# Test async validation specifically
docker-compose exec backend uv run python -m pytest tests/unit/test_async_validation.py -v

# Test advanced hybrid async execution  
docker-compose exec backend uv run python -m pytest tests/unit/test_hybrid_async_execution.py -v

# Check if pre-commit hooks are working
git commit --allow-empty -m "test hooks"  # Should run validation
```

### Test Execution Options

```bash
# Show test durations (find slow tests)
docker-compose exec backend uv run python -m pytest tests/ --durations=10

# Run tests matching a pattern
docker-compose exec backend uv run python -m pytest tests/ -k "router"

# Run with coverage report
docker-compose exec backend uv run python -m pytest tests/ --cov=src/agent
```

### Run Specific Test Files

```bash
# Unit test files
docker-compose exec backend uv run python -m pytest tests/unit/test_async_validation.py
docker-compose exec backend uv run python -m pytest tests/unit/test_hybrid_async_execution.py
docker-compose exec backend uv run python -m pytest tests/unit/test_database_operations.py

# Integration test files  
docker-compose exec backend uv run python -m pytest tests/integration/test_background_processor_efficiency.py
docker-compose exec backend uv run python -m pytest tests/integration/test_concurrent_planner_execution.py

# Phase 4: Enhanced Integration Testing for Real Async Execution
docker-compose exec backend uv run python -m pytest tests/integration/test_lightweight_async_flows.py
docker-compose exec backend uv run python -m pytest tests/integration/test_agent_activation_e2e.py
docker-compose exec backend uv run python -m pytest tests/integration/test_concurrent_async_operations.py
docker-compose exec backend uv run python -m pytest tests/integration/test_websocket_async_communication.py

# Phase 6: End-to-End Validation & Performance Optimization
docker-compose exec backend uv run python -m pytest tests/validation/test_end_to_end_async_prevention.py -v
```

### Verbose Output and Options

```bash
# Verbose output
docker-compose exec backend uv run python -m pytest tests/ -v

# Stop on first failure
docker-compose exec backend uv run python -m pytest tests/ -x

# Combined options
docker-compose exec backend uv run python -m pytest tests/ -vx --tb=short
```

## Test Categories

### 1. Async/Await Validation (`test_async_validation.py`) ⭐ NEW
**Purpose:** Runtime detection of missing `await` keywords and async execution correctness

**Four-Layer Strategy:**
1. **Static Analysis**: `python check_async.py` - Immediate feedback (3-5 sec)
2. **Runtime Warnings**: Test execution with warning capture
3. **Pre-commit Hooks**: Automatic validation on `git commit`
4. **Integration Tests**: End-to-end async execution flows

**Key Tests:**
- `TestUpdatePlannerNextTaskAndQueue` - Critical async function validation
- `TestTaskFunctionAsyncCorrectness` - Task execution with real database
- `TestAsyncContextManagerCorrectness` - Async context manager validation
- `TestConcurrentAsyncOperations` - Concurrent execution correctness

**Enhanced Unit Tests:**
- `test_task_execution.py` - Now includes `AsyncWarningCaptureMixin`
- Automatic detection via `@async_warning_test` decorator
- Real database operations (in-memory) instead of mocks for critical paths

**Performance Target:** <15 seconds (includes real async execution)

### 2. Hybrid Async Execution (`test_hybrid_async_execution.py`) ⭐ NEW  
**Purpose:** Advanced async testing with hybrid mocking strategy and performance analysis

**Hybrid Mocking Strategy:**
- **Mock**: External services (LLM API calls, file I/O operations)  
- **Real**: Internal async functions, database operations, task queueing
- **Result**: Test real async execution paths while avoiding external dependencies

**Key Tests:**
- `TestHybridPlannerAsyncExecution` - Real planner function execution with mocked externals
- `TestHybridWorkerAsyncExecution` - Worker task execution with real async flow  
- `TestAsyncPerformanceAnalysis` - Performance benchmarking and concurrency analysis

**Advanced Features:**
- Performance measurement with `measure_async_performance()`
- Concurrent execution overhead analysis  
- Real database operations with temporary files
- Comprehensive async warning detection across complex execution paths

**Performance Target:** <3 seconds (optimised for rapid execution)

### 3. Import Structure (`test_import_structure.py`)
**Purpose:** Ensure all modules import correctly without circular dependencies

**Tests:**
- Core module imports (router_operations, BaseAgent)
- Model exports from `models/__init__.py`
- Service layer imports (LLM, document, image services)
- Task function imports and registry validation
- Circular dependency detection
- Import speed validation (<1 second per module)

**Performance Target:** <1 second

### 4. Database Operations (`test_database_operations.py`)
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

### 5. Router Operations (`test_router_operations.py` and `test_router_operations_simple.py`)
**Purpose:** Validate router operations functional architecture

**Tests:**
- Ephemeral architecture (creation, state loading, cleanup)
- Message routing (simple chat vs complex request)
- WebSocket communication (all send methods require WebSocket)
- Database persistence
- File processing integration
- Title generation
- Concurrent router operations

**Performance Target:** <5 seconds

### 6. Task Execution (`test_task_execution.py`)
**Purpose:** Validate function-based task system

**Tests:**
- Planner tasks: execute_initial_planning, execute_task_creation, execute_synthesis
- Worker tasks: worker_initialisation, execute_standard_worker, execute_sql_worker
- Task queue integration and status transitions
- Early completion optimisation
- Concurrent task execution
- Error handling in task pipeline

**Performance Target:** <5 seconds

### 7. File Manager (`test_file_manager.py`)
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

### 8. WebSocket Communication (`test_websocket_communication.py`)
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

### 9. API Endpoints (`test_api_endpoints.py`)
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

## 🧪 Async Testing Utilities (`async_test_utils.py`)

### Core Components

**`AsyncWarningCaptureMixin`**
```python  
class MyTest(unittest.IsolatedAsyncioTestCase, AsyncWarningCaptureMixin):
    @async_warning_test  # Automatic async warning detection
    async def test_my_function(self):
        result = await my_async_function()  # Will fail if warnings detected
        self.assertTrue(result)
```

**Manual Warning Capture**
```python
async with self.capture_async_warnings() as warnings_list:
    coroutine = my_function()  # Missing await - intentional for testing
    coroutine.close()
    
self.assert_has_unawaited_coroutines(warnings_list)  # Verify warnings captured
```

**Utility Functions**
- `run_with_warning_check()` - Quick async function validation
- `@async_warning_test` - Decorator for automatic warning detection
- `AsyncTestCase` - Combined async testing with warning capture

### Integration Strategy

**For New Tests:**
```python
from tests.async_test_utils import AsyncWarningCaptureMixin, async_warning_test

class TestMyAsyncFeature(unittest.IsolatedAsyncioTestCase, AsyncWarningCaptureMixin):
    @async_warning_test
    async def test_feature_async_correctness(self):
        # Test will automatically fail if async warnings detected
        pass
```

**For Existing Tests:**
- Add `AsyncWarningCaptureMixin` to test classes
- Use `@async_warning_test` decorator on critical async tests
- Replace heavy database mocks with in-memory databases for async paths

## Design Principles

### Async-First Testing (NEW)
- **Static Analysis First**: Catch issues before execution
- **Runtime Warning Detection**: Validate real async execution  
- **Selective Mocking**: Mock external services, use real internal async functions
- **Pre-commit Protection**: Block commits with async issues

### Multi-Layer Validation
✅ **Missing `await` keywords** (Static + Runtime + Hooks + Integration)
✅ **Import errors and circular dependencies** (Static + Unit)  
✅ **Database connection failures** (Runtime + Integration)  
✅ **WebSocket communication breaks** (Unit + Integration)  
✅ **Task execution failures** (All Layers)  
✅ **File processing errors** (Unit + Integration)  
✅ **API integration issues** (Unit + Integration)

### Enhanced Test Patterns
- `AsyncWarningCaptureMixin` for runtime async validation
- `@async_warning_test` decorator for automatic detection
- **Hybrid mocking**: Mock external services, real internal async functions
- In-memory databases for async execution paths
- Warning capture context managers

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

**Existing Integration Tests:**
- `test_background_processor_efficiency.py` - Performance and efficiency validation
- `test_concurrent_planner_execution.py` - Complex concurrency scenarios  
- `test_multiple_conversations_concurrent.py` - Multi-router isolation testing
- `test_fastapi_immediate_response.py` - API endpoint integration
- `test_file_storage.py` - End-to-end file operations
- `test_websocket_updates_execution.py` - Full WebSocket workflows

**Phase 4: Enhanced Integration Testing for Real Async Execution:**
- `test_lightweight_async_flows.py` (30s) - Critical async paths with real database ops
- `test_agent_activation_e2e.py` (35s) - Complete "Agents assemble!" flow validation
- `test_concurrent_async_operations.py` (45s) - Race condition detection & concurrent validation
- `test_websocket_async_communication.py` (40s) - WebSocket async integrity & performance

**Phase 6: End-to-End Validation & Performance Optimization:**
- `test_end_to_end_async_prevention.py` (60s) - Complete multi-layer validation effectiveness testing

## Running Tests in CI/CD

```bash
# Fast CI pipeline (unit tests only)
docker-compose exec backend uv run python -m pytest tests/unit/ -x

# Comprehensive CI pipeline (all tests)
docker-compose exec backend uv run python -m pytest tests/ -x

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
        run: docker-compose exec backend uv run python -m pytest tests/unit/ -x
  
  integration-tests:
    runs-on: ubuntu-latest
    needs: unit-tests
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v3
      - name: Run integration tests
        run: docker-compose exec backend uv run python -m pytest tests/integration/ -x
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
docker-compose exec backend uv run python -m pytest tests/unit/
```

**Slow Tests:**
```bash
# Run with performance warnings
docker-compose exec backend uv run python -m pytest tests/ --durations=10 -v
```

**Test Failures:**
```bash
# Run specific failing test
docker-compose exec backend uv run python -m pytest tests/unit/test_async_validation.py -v
```

### Debug Mode
```python
# Add to test for debugging
import logging
logging.basicConfig(level=logging.DEBUG)
```

## ⚡ Async Validation Quick Reference

### Essential Commands
```bash
# Daily development
python check_async.py                    # Quick async check (3-5 sec)
python setup_hooks.py                    # One-time hook setup  
git commit -m "changes"                  # Auto-validation

# Debugging async issues
python check_async.py --file worker_tasks.py  # Focus on specific file
python check_async.py --mypy-only             # Type checking only
python check_async.py --ruff-only             # Style checking only

# Testing async validation
docker-compose exec backend uv run python -m pytest tests/unit/test_async_validation.py -v
```

### Error Interpretation
```bash
# MyPy: Missing await
"Maybe you forgot to use 'await'?" → Add await to async call

# Ruff: Blocking call  
"ASYNC251: Blocking sleep in async function" → Use asyncio.sleep()

# Runtime: Unawaited coroutine
"was never awaited" → Function called without await
```

### Files to Know
- `check_async.py` - Quick async validation script
- `setup_hooks.py` - Pre-commit hook installer  
- `async_test_utils.py` - Testing utilities and mixins
- `docs/async_testing_strategy.md` - Complete strategy guide
- `.pre-commit-config.yaml` - Git hook configuration

## Maintenance Guidelines

1. **NEW: Install hooks immediately**: `python setup_hooks.py`
2. **NEW: Run async checks before commits**: `python check_async.py`
3. **Add tests for new async functions with warning capture**
4. **Use hybrid mocking**: Mock external services, real internal async functions
5. **Focus on async correctness as top priority**
6. **Update async tests when architecture changes occur**
7. **Monitor pre-commit hook effectiveness and performance**

## Performance Monitoring

The test runner tracks:
- Total execution time vs target (<30s)
- Individual test file performance
- Slow test identification
- Performance trend monitoring

Use this data to optimise test efficiency and maintain rapid feedback loops.