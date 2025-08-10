# Migration Guide

## Overview

This guide provides step-by-step procedures for safely migrating the Agent State Database schema. All migrations follow a careful, transaction-based approach with comprehensive rollback capabilities.

## Prerequisites

### Development Environment Setup
```bash
# 1. Backup existing database
cp agent_database.db agent_database.db.backup.$(date +%Y%m%d_%H%M%S)

# 2. Test environment preparation
sqlite3 agent_database_test.db < schema_dump.sql

# 3. Migration script validation
python -m pytest tests/test_migrations.py
```

### Required Tools
- SQLite CLI (`sqlite3`)
- Python migration framework
- Database backup utilities
- Verification scripts

## Migration Framework

### Migration Script Template
```python
"""
Migration: [Description]
Version: X.Y -> X.Z
Date: YYYY-MM-DD
"""

import sqlite3
from datetime import datetime
from typing import Dict, Any

class Migration:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("BEGIN TRANSACTION")
    
    def execute(self) -> bool:
        """Execute migration with full rollback on failure"""
        try:
            self.validate_preconditions()
            self.perform_migration()
            self.validate_postconditions() 
            self.update_schema_version()
            self.conn.commit()
            return True
        except Exception as e:
            self.conn.rollback()
            raise MigrationError(f"Migration failed: {e}")
        finally:
            self.conn.close()
    
    def validate_preconditions(self):
        """Verify database state before migration"""
        pass
    
    def perform_migration(self):
        """Actual schema changes"""
        pass
    
    def validate_postconditions(self):
        """Verify migration success"""
        pass
    
    def update_schema_version(self):
        """Update version tracking"""
        pass
```

## Standard Migration Procedures

### 1. JSON Attribute Addition
**Scenario**: Adding optional attributes to existing records

```python
def add_json_attribute_migration():
    """Add timeout_seconds to router metadata"""
    
    # Validation: Check current schema version
    cursor.execute("SELECT schema_version FROM routers LIMIT 1")
    current_version = cursor.fetchone()[0]
    assert current_version == 1, f"Expected version 1, got {current_version}"
    
    # Migration: Add attribute with default value
    cursor.execute("""
        UPDATE routers 
        SET metadata = JSON_SET(
            COALESCE(metadata, '{}'), 
            '$.timeout_seconds', 
            300
        )
        WHERE JSON_EXTRACT(metadata, '$.timeout_seconds') IS NULL
    """)
    
    # Verification: Confirm all records have new attribute
    cursor.execute("""
        SELECT COUNT(*) FROM routers 
        WHERE JSON_EXTRACT(metadata, '$.timeout_seconds') IS NULL
    """)
    assert cursor.fetchone()[0] == 0, "Some records missing timeout_seconds"
    
    print(f"Added timeout_seconds to {cursor.rowcount} router records")
```

### 2. Column Addition
**Scenario**: Adding new fixed columns with defaults

```python
def add_column_migration():
    """Add conversation_context column to planners"""
    
    # Pre-check: Verify column doesn't exist
    cursor.execute("PRAGMA table_info(planners)")
    columns = [col[1] for col in cursor.fetchall()]
    assert 'conversation_context' not in columns, "Column already exists"
    
    # Migration: Add column with default
    cursor.execute("""
        ALTER TABLE planners 
        ADD COLUMN conversation_context TEXT DEFAULT NULL
    """)
    
    # Verification: Confirm column exists
    cursor.execute("PRAGMA table_info(planners)")
    columns = [col[1] for col in cursor.fetchall()]
    assert 'conversation_context' in columns, "Column addition failed"
    
    print("Added conversation_context column to planners table")
```

### 3. Column Promotion
**Scenario**: Moving frequently accessed JSON attribute to dedicated column

```python
def promote_json_to_column_migration():
    """Promote timeout_seconds from JSON to column"""
    
    # Phase 1: Add column
    cursor.execute("""
        ALTER TABLE routers 
        ADD COLUMN timeout_seconds INTEGER DEFAULT 300
    """)
    
    # Phase 2: Migrate existing data
    cursor.execute("""
        UPDATE routers 
        SET timeout_seconds = CAST(
            JSON_EXTRACT(metadata, '$.timeout_seconds') AS INTEGER
        )
        WHERE JSON_EXTRACT(metadata, '$.timeout_seconds') IS NOT NULL
    """)
    
    # Phase 3: Clean up JSON metadata
    cursor.execute("""
        UPDATE routers 
        SET metadata = JSON_REMOVE(metadata, '$.timeout_seconds')
        WHERE JSON_EXTRACT(metadata, '$.timeout_seconds') IS NOT NULL
    """)
    
    # Phase 4: Update schema version
    cursor.execute("UPDATE routers SET schema_version = 2")
    
    # Verification
    cursor.execute("""
        SELECT COUNT(*) FROM routers 
        WHERE timeout_seconds IS NULL 
        OR JSON_EXTRACT(metadata, '$.timeout_seconds') IS NOT NULL
    """)
    assert cursor.fetchone()[0] == 0, "Migration incomplete"
    
    print("Promoted timeout_seconds from JSON to column")
```

### 4. Table Restructure
**Scenario**: Major schema changes requiring new table version

```python
def table_restructure_migration():
    """Restructure workers table with new fields"""
    
    # Phase 1: Create new table structure
    cursor.execute("""
        CREATE TABLE workers_v2 (
            worker_id VARCHAR(32) PRIMARY KEY,
            planner_id VARCHAR(32) NOT NULL,
            task_status VARCHAR(50) NOT NULL,
            -- New fields
            priority INTEGER DEFAULT 0,
            retry_count INTEGER DEFAULT 0,
            -- Existing fields
            task_description TEXT,
            acceptance_criteria JSON,
            task_context JSON,
            task_result TEXT,
            querying_structured_data BOOLEAN DEFAULT FALSE,
            image_keys JSON,
            variable_keys JSON,
            tools JSON,
            input_images JSON,
            input_variables JSON,
            output_images JSON,
            output_variables JSON,
            tables JSON,
            metadata JSON,
            schema_version INTEGER DEFAULT 2,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (planner_id) REFERENCES planners(planner_id)
        )
    """)
    
    # Phase 2: Migrate existing data
    cursor.execute("""
        INSERT INTO workers_v2 SELECT 
            worker_id, planner_id, task_status,
            0 as priority,  -- new field default
            0 as retry_count,  -- new field default
            task_description, acceptance_criteria, task_context,
            task_result, querying_structured_data, image_keys, variable_keys,
            tools, input_images, input_variables, output_images,
            output_variables, tables, metadata,
            2 as schema_version,  -- updated version
            created_at, updated_at
        FROM workers
    """)
    
    # Phase 3: Verify migration
    cursor.execute("SELECT COUNT(*) FROM workers")
    old_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM workers_v2")
    new_count = cursor.fetchone()[0]
    assert old_count == new_count, f"Record count mismatch: {old_count} vs {new_count}"
    
    # Phase 4: Atomic table swap
    cursor.execute("ALTER TABLE workers RENAME TO workers_v1_backup")
    cursor.execute("ALTER TABLE workers_v2 RENAME TO workers")
    
    print(f"Migrated {new_count} worker records to new schema")
```

## Production Migration Checklist

### Pre-Migration Steps
- [ ] **Database Backup**: Full backup with timestamp
- [ ] **Test Environment**: Migration tested on production copy
- [ ] **Application Compatibility**: Code supports both old/new schema
- [ ] **Performance Baseline**: Current query performance metrics
- [ ] **Rollback Plan**: Tested rollback procedure prepared
- [ ] **Monitoring**: Database monitoring alerts configured
- [ ] **Maintenance Window**: Low-traffic period scheduled

### Migration Execution
```bash
#!/bin/bash
# production_migration.sh

set -e  # Exit on any error

BACKUP_DIR="/backups/agent_db"
DB_PATH="/data/agent_database.db"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# 1. Pre-migration backup
echo "Creating backup..."
cp "$DB_PATH" "$BACKUP_DIR/agent_database_${TIMESTAMP}.db"

# 2. Verify backup integrity
echo "Verifying backup..."
sqlite3 "$BACKUP_DIR/agent_database_${TIMESTAMP}.db" "PRAGMA integrity_check;"

# 3. Execute migration
echo "Starting migration..."
python scripts/migrate_schema.py --target-version 2 --verify

# 4. Post-migration verification
echo "Verifying migration..."
python scripts/verify_migration.py --version 2

# 5. Performance check
echo "Performance validation..."
python scripts/performance_check.py --compare-baseline

echo "Migration completed successfully!"
```

### Post-Migration Verification
```python
def verify_migration_success(target_version: int):
    """Comprehensive post-migration verification"""
    
    # 1. Schema version check
    versions = []
    for table in ['routers', 'planners', 'workers']:
        cursor.execute(f"SELECT DISTINCT schema_version FROM {table}")
        versions.extend([row[0] for row in cursor.fetchall()])
    
    assert all(v == target_version for v in versions), f"Version mismatch: {versions}"
    
    # 2. Data integrity check
    cursor.execute("PRAGMA integrity_check")
    integrity = cursor.fetchone()[0]
    assert integrity == "ok", f"Integrity check failed: {integrity}"
    
    # 3. Record count verification
    cursor.execute("""
        SELECT 
            (SELECT COUNT(*) FROM routers) as router_count,
            (SELECT COUNT(*) FROM planners) as planner_count,
            (SELECT COUNT(*) FROM workers) as worker_count
    """)
    counts = cursor.fetchone()
    print(f"Post-migration counts: {dict(zip(['routers', 'planners', 'workers'], counts))}")
    
    # 4. Application compatibility test
    from agent.models.agent_database import AgentDatabase
    db = AgentDatabase()
    test_router_id = db.get_routers()[0]['router_id'] if db.get_routers() else None
    if test_router_id:
        router_data = db.get_router(test_router_id)
        assert router_data is not None, "Router retrieval failed"
    
    print("Migration verification completed successfully")
```

## Rollback Procedures

### Immediate Rollback
```bash
#!/bin/bash
# emergency_rollback.sh

set -e

DB_PATH="/data/agent_database.db"
BACKUP_PATH="/backups/agent_db/agent_database_${1}.db"  # Timestamp argument

if [ ! -f "$BACKUP_PATH" ]; then
    echo "Error: Backup file $BACKUP_PATH not found"
    exit 1
fi

echo "Rolling back to backup: $BACKUP_PATH"

# 1. Stop application services
systemctl stop agent-service

# 2. Replace database
cp "$BACKUP_PATH" "$DB_PATH"

# 3. Verify rollback
sqlite3 "$DB_PATH" "PRAGMA integrity_check;"

# 4. Restart services
systemctl start agent-service

echo "Rollback completed"
```

### Partial Rollback
```python
def rollback_specific_migration(target_version: int):
    """Rollback to specific schema version"""
    
    current_versions = get_current_schema_versions()
    
    if target_version == 1:
        # Rollback column promotion
        cursor.execute("ALTER TABLE routers DROP COLUMN timeout_seconds")
        cursor.execute("""
            UPDATE routers 
            SET metadata = JSON_SET(metadata, '$.timeout_seconds', 300)
        """)
        cursor.execute("UPDATE routers SET schema_version = 1")
    
    print(f"Rolled back to schema version {target_version}")
```

## Common Migration Issues

### Issue 1: Foreign Key Constraint Violations
```python
# Temporarily disable foreign keys during migration
cursor.execute("PRAGMA foreign_keys = OFF")
# ... perform migration ...
cursor.execute("PRAGMA foreign_keys = ON")
```

### Issue 2: JSON Parsing Errors
```python
# Handle malformed JSON gracefully
cursor.execute("""
    UPDATE routers 
    SET metadata = '{}' 
    WHERE metadata IS NULL OR NOT JSON_VALID(metadata)
""")
```

### Issue 3: Performance Degradation
```python
# Add indexes after large data migrations
cursor.execute("CREATE INDEX idx_workers_status ON workers(task_status)")
cursor.execute("CREATE INDEX idx_workers_planner ON workers(planner_id)")
```

## Best Practices

### Migration Design
- **Atomic Operations**: Use transactions for all changes
- **Backward Compatibility**: Support N-1 version during transitions
- **Incremental Changes**: Small, focused migrations over large rewrites
- **Documentation**: Detailed change logs with business justification

### Testing Strategy
- **Unit Tests**: Individual migration function testing
- **Integration Tests**: End-to-end migration scenarios
- **Load Testing**: Performance impact assessment
- **Rollback Testing**: Verify rollback procedures work

### Monitoring
- **Migration Logs**: Comprehensive logging of all changes
- **Performance Metrics**: Before/after query performance
- **Error Tracking**: Detailed error reporting and recovery
- **Audit Trail**: Complete change history

---

**Last Updated**: 2025-08-06  
**Migration Framework Version**: 1.0