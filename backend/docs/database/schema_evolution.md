# Schema Evolution Strategy

## Overview

The Agent State Database implements a hybrid Data Vault approach designed for gradual, safe schema evolution. This document outlines the versioning strategy, migration patterns, and best practices for evolving the database schema over time.

## Core Principles

### 1. Hybrid Architecture Benefits
- **Fixed Columns**: Stable, frequently-queried attributes with optimal performance
- **JSON Metadata**: Flexible extensibility without schema changes
- **Version Tracking**: Granular control over schema transitions
- **Backward Compatibility**: Multiple schema versions coexist during transitions

### 2. Data Vault Concepts Applied
- **Hubs**: Business keys remain immutable (router_id, planner_id, worker_id)
- **Satellites**: Descriptive data with temporal tracking via updated_at
- **Links**: Explicit relationship management (router_planner_links)
- **Flexibility**: JSON fields serve as lightweight satellite alternatives

## Schema Versioning Framework

### Version Management
```python
# Current version tracking
AGENT_DATABASE_SCHEMA_VERSION = 1

# Version checking on startup
def check_schema_version():
    current_version = get_database_schema_version()
    if current_version < AGENT_DATABASE_SCHEMA_VERSION:
        perform_migration(current_version, AGENT_DATABASE_SCHEMA_VERSION)
```

### Version Storage
Each table includes:
- `schema_version INTEGER DEFAULT 1` - Per-record version tracking
- Global version in `settings.AGENT_DATABASE_SCHEMA_VERSION`
- Migration history table (future enhancement)

## Evolution Patterns

### Pattern 1: JSON Attribute Addition
**Use Case**: Adding new optional attributes without downtime

```sql
-- Step 1: Add to JSON metadata (immediate)
UPDATE routers 
SET metadata = JSON_SET(metadata, '$.timeout_seconds', 300)
WHERE schema_version = 1;

-- Step 2: Update application code to read/write new attribute
-- Step 3: Consider promotion to column if usage justifies it
```

**Benefits:**
- Zero downtime
- Immediate availability
- Backward compatible
- Performance cost only for records using feature

### Pattern 2: Column Promotion
**Use Case**: Frequently accessed JSON attribute becomes dedicated column

```sql
-- Phase 1: Add new column with default
ALTER TABLE routers ADD COLUMN timeout_seconds INTEGER DEFAULT 300;

-- Phase 2: Migrate existing data
UPDATE routers 
SET timeout_seconds = CAST(JSON_EXTRACT(metadata, '$.timeout_seconds') AS INTEGER)
WHERE JSON_EXTRACT(metadata, '$.timeout_seconds') IS NOT NULL;

-- Phase 3: Update application to use column
-- Phase 4: Clean up JSON metadata (optional)
UPDATE routers 
SET metadata = JSON_REMOVE(metadata, '$.timeout_seconds');

-- Phase 5: Update schema version
UPDATE routers SET schema_version = 2;
```

**Benefits:**
- Improved query performance
- Type safety and constraints
- Indexing capability
- Maintains data continuity

### Pattern 3: Major Schema Change
**Use Case**: Structural changes requiring careful coordination

```sql
-- Phase 1: Create versioned table structure
CREATE TABLE routers_v2 (
    router_id VARCHAR(32) PRIMARY KEY,
    status VARCHAR(50) NOT NULL,
    -- new/changed columns
    conversation_context TEXT,  -- new field
    timeout_seconds INTEGER DEFAULT 300,  -- promoted from JSON
    -- existing columns
    model VARCHAR(100),
    temperature FLOAT,
    metadata JSON,
    schema_version INTEGER DEFAULT 2,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Phase 2: Migrate data
INSERT INTO routers_v2 SELECT 
    router_id, status, 
    NULL as conversation_context,  -- new field starts empty
    COALESCE(CAST(JSON_EXTRACT(metadata, '$.timeout_seconds') AS INTEGER), 300),
    model, temperature, 
    JSON_REMOVE(metadata, '$.timeout_seconds'),  -- clean metadata
    2 as schema_version,
    created_at, updated_at
FROM routers;

-- Phase 3: Application deployment with dual-read capability
-- Phase 4: Switch to v2 table writes
-- Phase 5: Verify data integrity
-- Phase 6: Drop v1 table
```

## Migration Procedures

### 1. Pre-Migration Checklist
- [ ] Database backup created
- [ ] Migration script tested on development data
- [ ] Rollback procedure prepared and tested
- [ ] Application compatibility verified
- [ ] Performance impact assessed

### 2. Migration Execution
```python
def perform_migration(from_version: int, to_version: int):
    """Execute schema migration with full transaction support"""
    
    with database.transaction():
        # Version validation
        current_version = get_schema_version()
        if current_version != from_version:
            raise MigrationError(f"Version mismatch: expected {from_version}, got {current_version}")
        
        # Execute version-specific migrations
        for version in range(from_version + 1, to_version + 1):
            migration_function = get_migration_function(version)
            migration_function()
            
        # Update global version
        update_schema_version(to_version)
        
        # Verification
        verify_migration_success(to_version)
```

### 3. Post-Migration Validation
- Record count verification
- Data integrity checks
- Performance benchmarking
- Application functionality testing

## Safe Evolution Practices

### Do's ✅
- **Always use transactions** for multi-step migrations
- **Test on production data copies** before live deployment
- **Maintain backward compatibility** during transition periods
- **Document all changes** with business justification
- **Monitor performance impact** of JSON vs column access
- **Use JSON for optional/experimental features** initially

### Don'ts ❌
- **Never drop columns immediately** - deprecate gradually
- **Don't skip version numbers** - maintain sequential versioning  
- **Avoid complex migrations during peak hours**
- **Don't forget to update schema_version** after changes
- **Never migrate without backup** and rollback plan
- **Don't ignore application layer compatibility**

## JSON Field Management

### Best Practices
```python
# Reading JSON attributes with fallback
timeout = json_extract(metadata, '$.timeout_seconds', default=300)

# Writing JSON attributes safely
metadata = json_set(metadata, '$.timeout_seconds', 300)

# Querying JSON attributes (performance consideration)
SELECT * FROM routers 
WHERE JSON_EXTRACT(metadata, '$.feature_flag') = 'enabled';
```

### Performance Considerations
- **Index JSON extracts** for frequent queries:
  ```sql
  CREATE INDEX idx_router_timeout 
  ON routers(CAST(JSON_EXTRACT(metadata, '$.timeout_seconds') AS INTEGER));
  ```
- **Monitor query performance** on JSON fields
- **Consider column promotion** when JSON queries become frequent

## Future Enhancement Planning

### Event-Driven Architecture
Future consideration for further decoupling:
```python
# Current: Database-centric coordination
task_manager.execute_current_task()

# Future: Event-driven coordination  
event_bus.publish(TaskQueued(task_id, planner_id))
event_bus.subscribe(TaskCompleted, planner.handle_task_completion)
```

### Potential Schema Enhancements
- **Audit trails**: Complete change history tracking
- **Soft deletes**: Retention policies for archived data
- **Partitioning**: Time-based table partitioning for scale
- **Replication**: Multi-instance data synchronisation

## Rollback Procedures

### Emergency Rollback
```sql
-- Quick rollback to previous version
BEGIN TRANSACTION;

-- Restore from backup if available
-- OR revert schema changes manually

-- Reset schema version
UPDATE routers SET schema_version = 1;
UPDATE planners SET schema_version = 1; 
UPDATE workers SET schema_version = 1;

-- Verify application compatibility
COMMIT;
```

### Data Recovery
- **Point-in-time recovery** from SQLite backups
- **Selective rollback** of specific migrations
- **Data reconstruction** from application logs if needed

---

**Schema Version**: 1.0  
**Last Updated**: 2025-08-06  
**Next Review**: After first production migration