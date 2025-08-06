# Performance Guide

## Overview

This guide covers performance considerations for the Agent State Database. The current implementation uses basic indexing with opportunities for optimization as usage patterns become clear.

## Current Indexing

### Existing Indexes (SQLAlchemy)
The current schema includes these indexes:

```python
# Message table agent lookups (automatically created via index=True)
planner_messages.agent_id  # Index for planner message retrieval
worker_messages.agent_id   # Index for worker message retrieval  
router_messages.conversation_id  # Index for conversation message retrieval
```

### Primary Keys (Automatic)
```sql
-- Primary key indexes (created automatically)
conversations.id
routers.router_id
planners.planner_id  
workers.worker_id
router_planner_links.link_id
```

## Query Patterns Analysis

### Current Query Patterns
Based on the TaskManager implementation in planner.py:

```python
# 1. TaskManager.get_current_task() - Find pending tasks by planner
SELECT worker_id FROM workers 
WHERE planner_id = ? AND task_status = 'pending'

# 2. TaskManager.get_completed_task() - Find completed tasks by planner  
SELECT * FROM workers 
WHERE planner_id = ? AND task_status IN ('completed', 'failed_validation')

# 3. Message retrieval by agent
SELECT * FROM planner_messages WHERE agent_id = ? ORDER BY created_at

# 4. Agent state lookups
SELECT * FROM planners WHERE planner_id = ?
```

### Performance Bottlenecks

**Missing Critical Indexes:**
- `workers(planner_id, task_status)` - Most critical for TaskManager operations
- `workers(task_status)` - For global task status queries
- Message timestamp ordering - Currently no index on created_at

## Recommended Index Additions

### High Priority (TaskManager Performance)
```sql
-- Critical for TaskManager operations
CREATE INDEX idx_workers_planner_status ON workers(planner_id, task_status);
CREATE INDEX idx_workers_status ON workers(task_status);

-- Message chronological ordering
CREATE INDEX idx_planner_messages_agent_time ON planner_messages(agent_id, created_at);
CREATE INDEX idx_worker_messages_agent_time ON worker_messages(agent_id, created_at);
CREATE INDEX idx_router_messages_conv_time ON router_messages(conversation_id, created_at);
```

### Medium Priority (General Performance)
```sql
-- Agent status filtering
CREATE INDEX idx_routers_status ON routers(status);
CREATE INDEX idx_planners_status ON planners(status);

-- Router-planner relationships
CREATE INDEX idx_router_planner_links_router ON router_planner_links(router_id);
CREATE INDEX idx_router_planner_links_planner ON router_planner_links(planner_id);
```

## SQLAlchemy Index Implementation

To add the critical indexes to the current models:

```python
# In agent_database.py Worker model
class Worker(Base):
    __tablename__ = 'workers'
    
    worker_id = Column(String(32), primary_key=True)
    planner_id = Column(String(32), ForeignKey('planners.planner_id'), nullable=False, index=True)  # Add index
    task_status = Column(String(50), nullable=False, index=True)  # Add index
    # ... other columns ...

# Composite index (requires separate Index definition)
from sqlalchemy import Index
Index('idx_workers_planner_status', Worker.planner_id, Worker.task_status)

# Message models with timestamp indexes
class PlannerMessage(Base):
    __tablename__ = 'planner_messages'
    
    agent_id = Column(String(32), nullable=False, index=True)  # Existing
    created_at = Column(DateTime, default=datetime.utcnow, index=True)  # Add index
    # ... other columns ...

# Composite index for chronological queries
Index('idx_planner_messages_agent_time', PlannerMessage.agent_id, PlannerMessage.created_at)
```

## Connection Management

### Current SQLAlchemy Setup
```python
# From agent_database.py
class AgentDatabase:
    def __init__(self):
        db_path = Path(settings.agent_database_path)
        self.engine = create_engine(f'sqlite:///{db_path}')
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.ensure_tables_exist()
```

### Performance Optimization Opportunities
```python
# Optimized connection configuration
def create_optimized_engine(db_path: Path):
    return create_engine(
        f'sqlite:///{db_path}',
        pool_pre_ping=True,
        pool_recycle=3600,
        echo=False,  # Disable SQL logging in production
        connect_args={
            "timeout": 30,
            "check_same_thread": False,
        }
    )
```

## SQLite Optimization

### Pragma Settings
```sql
-- Recommended SQLite configuration for agent workload
PRAGMA journal_mode = WAL;          -- Write-Ahead Logging for concurrency
PRAGMA synchronous = NORMAL;        -- Balance safety and performance  
PRAGMA cache_size = 10000;          -- ~40MB cache
PRAGMA temp_store = MEMORY;         -- In-memory temporary tables
```

### Implementation in AgentDatabase
```python
def optimize_connection(self):
    """Apply performance optimizations to SQLite"""
    with self.engine.connect() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL") 
        conn.execute("PRAGMA cache_size = 10000")
        conn.execute("PRAGMA temp_store = MEMORY")
```

## Performance Monitoring

### Simple Query Time Monitoring
```python
import time
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)

@contextmanager
def monitor_query(operation_name: str):
    """Basic query time monitoring"""
    start = time.perf_counter()
    try:
        yield
    finally:
        duration = time.perf_counter() - start
        if duration > 0.1:  # Log queries over 100ms
            logger.warning(f"Slow query {operation_name}: {duration:.3f}s")

# Usage in TaskManager
async def get_current_task(self) -> Optional[str]:
    with monitor_query("get_current_task"):
        workers = self.agent_db.get_workers_by_planner(self.planner_id)
        # ... rest of method
```

### Database Size Monitoring
```python
def check_database_size():
    """Monitor database growth"""
    db_path = Path(settings.agent_database_path)
    if db_path.exists():
        size_mb = db_path.stat().st_size / (1024 * 1024)
        if size_mb > 100:  # Alert if over 100MB
            logger.warning(f"Database size: {size_mb:.1f}MB")
        return size_mb
    return 0
```

## JSON Field Performance

### Current JSON Usage
The schema uses JSON fields for:
- `workers.acceptance_criteria`, `task_context`, `input_images`, etc.
- `metadata` fields in all agent tables

### JSON Query Considerations
```python
# Efficient: Filter by fixed columns first, process JSON in Python
workers = session.query(Worker).filter(
    Worker.planner_id == planner_id,
    Worker.task_status == 'completed'
).all()

# Then process JSON fields in Python
for worker in workers:
    context = json.loads(worker.task_context) if worker.task_context else {}
    
# Inefficient: JSON queries in SQL (SQLite JSON support limited)
# Avoid complex JSON WHERE clauses until performance testing proves necessity
```

## Common Performance Issues

### Issue 1: Slow TaskManager Operations
**Problem**: `get_current_task()` and `get_completed_task()` scan all workers

**Current Code:**
```python
# Inefficient: No index on planner_id + task_status
workers = self.agent_db.get_workers_by_planner(self.planner_id)
for worker in workers:
    if worker['task_status'] == 'pending':
        return worker['worker_id']
```

**Solution**: Add composite index on `(planner_id, task_status)`

### Issue 2: Message Retrieval Without Ordering
**Problem**: Message chronological order not optimized

**Solution**: Add index on `(agent_id, created_at)` for all message tables

### Issue 3: Growing Database Size
**Problem**: No cleanup mechanism for old data

**Solution**: Implement retention policies
```python
def cleanup_old_records():
    """Clean up completed tasks older than 30 days"""
    cutoff = datetime.utcnow() - timedelta(days=30)
    
    session.query(Worker).filter(
        Worker.task_status == 'recorded',
        Worker.updated_at < cutoff
    ).delete()
    session.commit()
```

## Performance Testing

### Basic Load Testing
```python
def test_task_manager_performance():
    """Test TaskManager operations under load"""
    
    # Create test data
    planner_id = "test_planner_123"
    for i in range(1000):
        create_test_worker(planner_id, status='pending' if i < 100 else 'completed')
    
    # Measure critical operations
    start = time.perf_counter()
    current_task = task_manager.get_current_task()
    get_current_duration = time.perf_counter() - start
    
    start = time.perf_counter()  
    completed_task = task_manager.get_completed_task()
    get_completed_duration = time.perf_counter() - start
    
    # Assert performance requirements
    assert get_current_duration < 0.05, f"get_current_task too slow: {get_current_duration:.3f}s"
    assert get_completed_duration < 0.05, f"get_completed_task too slow: {get_completed_duration:.3f}s"
```

## Immediate Action Items

### Critical Performance Improvements
1. **Add composite index** on `workers(planner_id, task_status)`
2. **Add timestamp indexes** on all message tables
3. **Implement SQLite pragma optimizations**
4. **Add basic query time monitoring**

### Implementation Priority
1. **High**: TaskManager query optimization (affects core functionality)  
2. **Medium**: Message retrieval optimization (affects conversation loading)
3. **Low**: General status filtering (nice-to-have for admin queries)

---

**Current Performance Baseline**: No comprehensive benchmarks exist  
**Recommended Next Steps**: Implement critical indexes and establish performance baselines  
**Last Updated**: 2025-08-06