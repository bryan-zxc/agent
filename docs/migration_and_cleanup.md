# Migration and Cleanup Procedures

This document outlines the comprehensive procedures for database migrations, system cleanup, and maintenance operations for the function-based agent system.

## Overview

The system requires regular maintenance procedures to ensure optimal performance and data integrity:

- **Database Migrations**: Schema evolution and data format updates
- **File System Cleanup**: Removing orphaned files and managing storage
- **Task Queue Maintenance**: Cleaning up completed tasks and handling stale tasks
- **Performance Optimization**: Database maintenance and index optimization

## Database Migration Procedures

### Migration Framework

The system uses a version-based migration approach with automatic detection:

```python
class MigrationManager:
    """Manages database schema migrations."""
    
    def __init__(self, db: AgentDatabase):
        self.db = db
        self.current_version = self._get_current_version()
        self.target_version = settings.database_schema_version
    
    def _get_current_version(self) -> int:
        """Get current database schema version."""
        try:
            with self.db.SessionLocal() as session:
                # Check if migration table exists
                result = session.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table' AND name='migrations'")
                ).fetchone()
                
                if not result:
                    # No migration table - assume version 0
                    return 0
                
                # Get latest migration version
                result = session.execute(
                    text("SELECT version FROM migrations ORDER BY version DESC LIMIT 1")
                ).fetchone()
                
                return result[0] if result else 0
                
        except Exception as e:
            logger.error(f"Failed to get current migration version: {e}")
            return 0
    
    def needs_migration(self) -> bool:
        """Check if migration is needed."""
        return self.current_version < self.target_version
    
    def execute_migrations(self) -> bool:
        """Execute all pending migrations."""
        if not self.needs_migration():
            logger.info("Database is up to date")
            return True
        
        logger.info(f"Migrating database from version {self.current_version} to {self.target_version}")
        
        try:
            # Create migrations table if it doesn't exist
            self._create_migrations_table()
            
            # Execute migrations in order
            for version in range(self.current_version + 1, self.target_version + 1):
                migration_func = getattr(self, f"_migrate_to_v{version}", None)
                if migration_func:
                    logger.info(f"Executing migration to version {version}")
                    migration_func()
                    self._record_migration(version)
                else:
                    logger.warning(f"No migration function found for version {version}")
            
            logger.info("All migrations completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            return False
    
    def _create_migrations_table(self):
        """Create migrations tracking table."""
        with self.db.SessionLocal() as session:
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS migrations (
                    version INTEGER PRIMARY KEY,
                    description TEXT,
                    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            session.commit()
    
    def _record_migration(self, version: int, description: str = ""):
        """Record completed migration."""
        with self.db.SessionLocal() as session:
            session.execute(text("""
                INSERT INTO migrations (version, description) 
                VALUES (:version, :description)
            """), {"version": version, "description": description})
            session.commit()
```

### Specific Migration Procedures

#### Migration to Version 1: Task Queue Addition

```python
def _migrate_to_v1(self):
    """Add task queue table and update existing tables."""
    with self.db.SessionLocal() as session:
        # Add task queue table
        session.execute(text("""
            CREATE TABLE task_queue (
                task_id TEXT PRIMARY KEY,
                entity_type TEXT NOT NULL CHECK (entity_type IN ('planner', 'worker')),
                entity_id TEXT NOT NULL,
                function_name TEXT NOT NULL,
                payload JSON,
                status TEXT NOT NULL DEFAULT 'PENDING' 
                    CHECK (status IN ('PENDING', 'IN_PROGRESS', 'COMPLETED', 'FAILED')),
                error_message TEXT,
                retry_count INTEGER NOT NULL DEFAULT 0 CHECK (retry_count >= 0),
                max_retries INTEGER NOT NULL DEFAULT 3 CHECK (max_retries >= 0),
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        
        # Add indexes for performance
        session.execute(text("""
            CREATE INDEX idx_task_queue_status_created 
            ON task_queue(status, created_at)
        """))
        
        session.execute(text("""
            CREATE INDEX idx_task_queue_entity 
            ON task_queue(entity_type, entity_id)
        """))
        
        # Add file path columns to existing tables
        session.execute(text("""
            ALTER TABLE planners 
            ADD COLUMN variable_file_paths JSON DEFAULT '{}'
        """))
        
        session.execute(text("""
            ALTER TABLE planners 
            ADD COLUMN image_file_paths JSON DEFAULT '{}'
        """))
        
        session.execute(text("""
            ALTER TABLE planners 
            ADD COLUMN next_task TEXT
        """))
        
        session.execute(text("""
            ALTER TABLE workers 
            ADD COLUMN input_variable_filepaths JSON DEFAULT '{}'
        """))
        
        session.execute(text("""
            ALTER TABLE workers 
            ADD COLUMN input_image_filepaths JSON DEFAULT '{}'
        """))
        
        session.execute(text("""
            ALTER TABLE workers 
            ADD COLUMN output_variable_filepaths JSON DEFAULT '{}'
        """))
        
        session.execute(text("""
            ALTER TABLE workers 
            ADD COLUMN output_image_filepaths JSON DEFAULT '{}'
        """))
        
        session.commit()
        
    self._record_migration(1, "Added task queue table and file path columns")
```

#### Migration to Version 2: Enhanced Constraints

```python
def _migrate_to_v2(self):
    """Add enhanced constraints and triggers."""
    with self.db.SessionLocal() as session:
        # Add trigger for automatic timestamp updates
        session.execute(text("""
            CREATE TRIGGER task_queue_updated_at 
                AFTER UPDATE ON task_queue
                FOR EACH ROW
                WHEN NEW.updated_at = OLD.updated_at
            BEGIN
                UPDATE task_queue 
                SET updated_at = CURRENT_TIMESTAMP 
                WHERE task_id = NEW.task_id;
            END
        """))
        
        # Add additional indexes for monitoring
        session.execute(text("""
            CREATE INDEX idx_task_queue_status_updated 
            ON task_queue(status, updated_at)
        """))
        
        session.execute(text("""
            CREATE INDEX idx_task_queue_function 
            ON task_queue(function_name)
        """))
        
        # Add retry_after column for future exponential backoff
        session.execute(text("""
            ALTER TABLE task_queue 
            ADD COLUMN retry_after TIMESTAMP
        """))
        
        session.commit()
        
    self._record_migration(2, "Added triggers, indexes, and retry scheduling support")
```

### Data Migration Procedures

#### Migrate Legacy Agent Data

```python
def migrate_legacy_agent_data():
    """Migrate data from old class-based agent system."""
    logger.info("Starting legacy agent data migration")
    
    try:
        with SessionLocal() as session:
            # Find planners with old execution plan format
            planners = session.query(Planner).filter(
                Planner.execution_plan.isnot(None),
                Planner.status == "completed"
            ).all()
            
            migrated_count = 0
            
            for planner in planners:
                try:
                    # Convert old execution plan to new format
                    if isinstance(planner.execution_plan, str):
                        # Parse markdown execution plan
                        execution_plan_model = parse_legacy_execution_plan(planner.execution_plan)
                        
                        # Save as JSON file
                        success = save_execution_plan_model(planner.planner_id, execution_plan_model)
                        if success:
                            migrated_count += 1
                            logger.debug(f"Migrated execution plan for planner {planner.planner_id}")
                
                except Exception as e:
                    logger.error(f"Failed to migrate planner {planner.planner_id}: {e}")
            
            logger.info(f"Successfully migrated {migrated_count} planner execution plans")
            
    except Exception as e:
        logger.error(f"Legacy data migration failed: {e}")
        raise e

def parse_legacy_execution_plan(markdown_plan: str) -> ExecutionPlanModel:
    """Convert legacy markdown execution plan to Pydantic model."""
    # Implementation depends on legacy format
    # This is a simplified example
    
    lines = markdown_plan.split('\n')
    tasks = []
    
    for line in lines:
        if line.startswith('- '):
            task_desc = line[2:].strip()
            task = Task(
                task_description=task_desc,
                acceptance_criteria=["Task completed successfully"],
                task_context=TaskContext(
                    user_request="Legacy migration",
                    context="Migrated from old format",
                    previous_outputs=""
                )
            )
            tasks.append(task)
    
    return ExecutionPlanModel(
        user_question="Legacy plan",
        overall_plan=markdown_plan,
        tasks=tasks
    )
```

## File System Cleanup Procedures

### Orphaned File Detection

```python
class FileSystemCleaner:
    """Manages file system cleanup operations."""
    
    def __init__(self, base_path: str = None):
        self.base_path = Path(base_path or settings.collaterals_base_path)
        self.db = AgentDatabase()
    
    def detect_orphaned_files(self) -> dict:
        """Detect files that exist on filesystem but not in database."""
        orphaned_files = {
            "orphaned_directories": [],
            "orphaned_variables": [],
            "orphaned_images": [],
            "orphaned_json_files": []
        }
        
        try:
            # Get all planner IDs from database
            with self.db.SessionLocal() as session:
                planners = session.query(Planner.planner_id).all()
                active_planner_ids = {p.planner_id for p in planners}
            
            # Scan filesystem for directories
            if self.base_path.exists():
                for planner_dir in self.base_path.iterdir():
                    if planner_dir.is_dir():
                        planner_id = planner_dir.name
                        
                        if planner_id not in active_planner_ids:
                            # Entire directory is orphaned
                            orphaned_files["orphaned_directories"].append(str(planner_dir))
                        else:
                            # Check individual files within valid directories
                            self._check_files_in_directory(planner_id, planner_dir, orphaned_files)
            
            return orphaned_files
            
        except Exception as e:
            logger.error(f"Failed to detect orphaned files: {e}")
            return orphaned_files
    
    def _check_files_in_directory(self, planner_id: str, planner_dir: Path, orphaned_files: dict):
        """Check for orphaned files within a planner directory."""
        try:
            # Get file paths from database
            planner = self.db.get_planner(planner_id)
            if not planner:
                return
            
            db_variable_paths = set((planner.get("variable_file_paths") or {}).values())
            db_image_paths = set((planner.get("image_file_paths") or {}).values())
            
            # Check variables directory
            variables_dir = planner_dir / "variables"
            if variables_dir.exists():
                for var_file in variables_dir.glob("*.pkl"):
                    if str(var_file) not in db_variable_paths:
                        orphaned_files["orphaned_variables"].append(str(var_file))
            
            # Check images directory
            images_dir = planner_dir / "images"
            if images_dir.exists():
                for img_file in images_dir.glob("*.b64"):
                    if str(img_file) not in db_image_paths:
                        orphaned_files["orphaned_images"].append(str(img_file))
            
            # Check for orphaned JSON files
            for json_file in planner_dir.glob("*.json"):
                expected_files = {
                    settings.execution_plan_model_filename,
                    settings.current_task_filename
                }
                if json_file.name not in expected_files:
                    orphaned_files["orphaned_json_files"].append(str(json_file))
        
        except Exception as e:
            logger.error(f"Failed to check files in directory {planner_dir}: {e}")
    
    def cleanup_orphaned_files(self, orphaned_files: dict, dry_run: bool = True) -> dict:
        """Clean up orphaned files and directories."""
        cleanup_report = {
            "removed_directories": [],
            "removed_files": [],
            "errors": [],
            "total_space_freed": 0
        }
        
        try:
            # Remove orphaned directories
            for dir_path in orphaned_files["orphaned_directories"]:
                try:
                    dir_size = self._get_directory_size(Path(dir_path))
                    
                    if not dry_run:
                        shutil.rmtree(dir_path)
                    
                    cleanup_report["removed_directories"].append({
                        "path": dir_path,
                        "size_bytes": dir_size
                    })
                    cleanup_report["total_space_freed"] += dir_size
                    
                except Exception as e:
                    cleanup_report["errors"].append(f"Failed to remove directory {dir_path}: {e}")
            
            # Remove individual orphaned files
            all_orphaned_files = (
                orphaned_files["orphaned_variables"] +
                orphaned_files["orphaned_images"] +
                orphaned_files["orphaned_json_files"]
            )
            
            for file_path in all_orphaned_files:
                try:
                    file_size = Path(file_path).stat().st_size if Path(file_path).exists() else 0
                    
                    if not dry_run:
                        Path(file_path).unlink()
                    
                    cleanup_report["removed_files"].append({
                        "path": file_path,
                        "size_bytes": file_size
                    })
                    cleanup_report["total_space_freed"] += file_size
                    
                except Exception as e:
                    cleanup_report["errors"].append(f"Failed to remove file {file_path}: {e}")
            
            if dry_run:
                logger.info(f"DRY RUN: Would free {cleanup_report['total_space_freed']} bytes")
            else:
                logger.info(f"Cleaned up {len(cleanup_report['removed_directories'])} directories and {len(cleanup_report['removed_files'])} files, freed {cleanup_report['total_space_freed']} bytes")
            
            return cleanup_report
            
        except Exception as e:
            logger.error(f"Cleanup operation failed: {e}")
            cleanup_report["errors"].append(str(e))
            return cleanup_report
    
    def _get_directory_size(self, directory: Path) -> int:
        """Calculate total size of directory and contents."""
        total_size = 0
        try:
            for file_path in directory.rglob("*"):
                if file_path.is_file():
                    total_size += file_path.stat().st_size
        except Exception as e:
            logger.error(f"Failed to calculate size for {directory}: {e}")
        return total_size
```

### Automated Cleanup Scheduling

```python
def schedule_cleanup_tasks():
    """Schedule regular cleanup tasks."""
    
    def daily_cleanup():
        """Daily cleanup routine."""
        logger.info("Starting daily cleanup routine")
        
        # Clean up completed tasks older than 7 days
        cleanup_completed_tasks(retention_days=7)
        
        # Clean up failed tasks older than 30 days
        cleanup_failed_tasks(retention_days=30)
        
        # Detect and report orphaned files (dry run)
        cleaner = FileSystemCleaner()
        orphaned_files = cleaner.detect_orphaned_files()
        
        if any(orphaned_files.values()):
            logger.warning(f"Found orphaned files: {sum(len(v) for v in orphaned_files.values())} items")
            # Could trigger alert or cleanup based on configuration
    
    def weekly_cleanup():
        """Weekly deep cleanup routine."""
        logger.info("Starting weekly deep cleanup routine")
        
        # Clean up orphaned files (actual cleanup)
        cleaner = FileSystemCleaner()
        orphaned_files = cleaner.detect_orphaned_files()
        cleanup_report = cleaner.cleanup_orphaned_files(orphaned_files, dry_run=False)
        
        # Database maintenance
        optimize_database()
        
        # Generate cleanup report
        generate_cleanup_report(cleanup_report)
    
    # In production, these would be scheduled with a job scheduler
    # For example, using APScheduler:
    # scheduler.add_job(daily_cleanup, 'cron', hour=2)
    # scheduler.add_job(weekly_cleanup, 'cron', day_of_week=0, hour=3)
```

## Task Queue Maintenance

### Stale Task Detection and Recovery

```python
def detect_and_recover_stale_tasks(threshold_minutes: int = 30):
    """Detect and recover tasks stuck in IN_PROGRESS state."""
    logger.info(f"Detecting stale tasks (threshold: {threshold_minutes} minutes)")
    
    threshold_time = datetime.utcnow() - timedelta(minutes=threshold_minutes)
    
    try:
        with SessionLocal() as session:
            # Find stale tasks
            stale_tasks = session.query(TaskQueue).filter(
                TaskQueue.status == "IN_PROGRESS",
                TaskQueue.updated_at < threshold_time
            ).all()
            
            if not stale_tasks:
                logger.info("No stale tasks found")
                return
            
            logger.warning(f"Found {len(stale_tasks)} stale tasks")
            
            # Reset stale tasks to PENDING
            for task in stale_tasks:
                logger.info(f"Resetting stale task {task.task_id} (function: {task.function_name})")
                
                task.status = "PENDING"
                task.error_message = f"Task timed out after {threshold_minutes} minutes and was reset"
                task.updated_at = datetime.utcnow()
                
                # Don't increment retry count for timeouts - may not be task's fault
            
            session.commit()
            logger.info(f"Reset {len(stale_tasks)} stale tasks to PENDING")
            
    except Exception as e:
        logger.error(f"Failed to detect/recover stale tasks: {e}")

def cleanup_completed_tasks(retention_days: int = 7) -> int:
    """Remove completed tasks older than retention period."""
    cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
    
    try:
        with SessionLocal() as session:
            deleted_count = session.query(TaskQueue).filter(
                TaskQueue.status == "COMPLETED",
                TaskQueue.updated_at < cutoff_date
            ).delete()
            
            session.commit()
            logger.info(f"Cleaned up {deleted_count} completed tasks older than {retention_days} days")
            return deleted_count
            
    except Exception as e:
        logger.error(f"Failed to cleanup completed tasks: {e}")
        return 0

def cleanup_failed_tasks(retention_days: int = 30) -> int:
    """Remove failed tasks older than retention period."""
    cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
    
    try:
        with SessionLocal() as session:
            # Only clean up failed tasks that have exceeded max retries
            deleted_count = session.query(TaskQueue).filter(
                TaskQueue.status == "FAILED",
                TaskQueue.retry_count >= TaskQueue.max_retries,
                TaskQueue.updated_at < cutoff_date
            ).delete()
            
            session.commit()
            logger.info(f"Cleaned up {deleted_count} failed tasks older than {retention_days} days")
            return deleted_count
            
    except Exception as e:
        logger.error(f"Failed to cleanup failed tasks: {e}")
        return 0
```

### Task Queue Statistics and Monitoring

```python
def get_task_queue_statistics() -> dict:
    """Get comprehensive task queue statistics."""
    stats = {
        "total_tasks": 0,
        "by_status": {},
        "by_function": {},
        "by_entity_type": {},
        "oldest_pending": None,
        "avg_completion_time": None,
        "stale_tasks": 0
    }
    
    try:
        with SessionLocal() as session:
            # Total tasks
            stats["total_tasks"] = session.query(TaskQueue).count()
            
            # Tasks by status
            status_counts = session.query(
                TaskQueue.status, 
                func.count(TaskQueue.task_id)
            ).group_by(TaskQueue.status).all()
            
            stats["by_status"] = {status: count for status, count in status_counts}
            
            # Tasks by function
            function_counts = session.query(
                TaskQueue.function_name, 
                func.count(TaskQueue.task_id)
            ).group_by(TaskQueue.function_name).all()
            
            stats["by_function"] = {func_name: count for func_name, count in function_counts}
            
            # Tasks by entity type
            entity_counts = session.query(
                TaskQueue.entity_type, 
                func.count(TaskQueue.task_id)
            ).group_by(TaskQueue.entity_type).all()
            
            stats["by_entity_type"] = {entity_type: count for entity_type, count in entity_counts}
            
            # Oldest pending task
            oldest_pending = session.query(TaskQueue).filter(
                TaskQueue.status == "PENDING"
            ).order_by(TaskQueue.created_at).first()
            
            if oldest_pending:
                stats["oldest_pending"] = {
                    "task_id": oldest_pending.task_id,
                    "created_at": oldest_pending.created_at.isoformat(),
                    "age_minutes": (datetime.utcnow() - oldest_pending.created_at).total_seconds() / 60
                }
            
            # Average completion time for completed tasks in last 24 hours
            day_ago = datetime.utcnow() - timedelta(days=1)
            completed_tasks = session.query(TaskQueue).filter(
                TaskQueue.status == "COMPLETED",
                TaskQueue.created_at > day_ago
            ).all()
            
            if completed_tasks:
                completion_times = [
                    (task.updated_at - task.created_at).total_seconds()
                    for task in completed_tasks
                ]
                stats["avg_completion_time"] = sum(completion_times) / len(completion_times)
            
            # Stale tasks count
            threshold_time = datetime.utcnow() - timedelta(minutes=30)
            stats["stale_tasks"] = session.query(TaskQueue).filter(
                TaskQueue.status == "IN_PROGRESS",
                TaskQueue.updated_at < threshold_time
            ).count()
        
        return stats
        
    except Exception as e:
        logger.error(f"Failed to get task queue statistics: {e}")
        return stats
```

## Database Optimization Procedures

### Index Optimization

```python
def optimize_database():
    """Perform database optimization operations."""
    logger.info("Starting database optimization")
    
    try:
        with SessionLocal() as session:
            # Analyze tables to update query planner statistics
            session.execute(text("ANALYZE"))
            
            # Vacuum to reclaim space
            session.execute(text("VACUUM"))
            
            # Reindex to rebuild indexes
            session.execute(text("REINDEX"))
            
            session.commit()
            logger.info("Database optimization completed")
            
    except Exception as e:
        logger.error(f"Database optimization failed: {e}")

def check_database_integrity():
    """Check database integrity and report issues."""
    logger.info("Checking database integrity")
    
    integrity_report = {
        "pragma_checks": {},
        "foreign_key_violations": [],
        "constraint_violations": []
    }
    
    try:
        with SessionLocal() as session:
            # PRAGMA integrity check
            result = session.execute(text("PRAGMA integrity_check")).fetchone()
            integrity_report["pragma_checks"]["integrity_check"] = result[0] if result else "unknown"
            
            # Foreign key check
            result = session.execute(text("PRAGMA foreign_key_check")).fetchall()
            if result:
                integrity_report["foreign_key_violations"] = [
                    {"table": row[0], "rowid": row[1], "parent": row[2], "fkid": row[3]}
                    for row in result
                ]
            
            # Check for orphaned workers
            orphaned_workers = session.execute(text("""
                SELECT worker_id FROM workers 
                WHERE planner_id NOT IN (SELECT planner_id FROM planners)
            """)).fetchall()
            
            if orphaned_workers:
                integrity_report["constraint_violations"].append({
                    "type": "orphaned_workers",
                    "count": len(orphaned_workers),
                    "worker_ids": [row[0] for row in orphaned_workers]
                })
        
        if integrity_report["pragma_checks"]["integrity_check"] == "ok":
            logger.info("Database integrity check passed")
        else:
            logger.warning(f"Database integrity issues found: {integrity_report}")
        
        return integrity_report
        
    except Exception as e:
        logger.error(f"Database integrity check failed: {e}")
        return integrity_report
```

## Maintenance Scheduling

### Automated Maintenance Runner

```python
class MaintenanceScheduler:
    """Manages scheduled maintenance operations."""
    
    def __init__(self):
        self.tasks = {
            "daily": [
                ("cleanup_completed_tasks", lambda: cleanup_completed_tasks(retention_days=7)),
                ("detect_stale_tasks", lambda: detect_and_recover_stale_tasks(threshold_minutes=30)),
                ("task_queue_stats", lambda: self._log_task_queue_stats())
            ],
            "weekly": [
                ("cleanup_orphaned_files", self._weekly_file_cleanup),
                ("database_optimization", optimize_database),
                ("integrity_check", check_database_integrity)
            ],
            "monthly": [
                ("deep_cleanup", lambda: cleanup_failed_tasks(retention_days=90)),
                ("migration_check", self._check_migrations),
                ("performance_analysis", self._analyze_performance)
            ]
        }
    
    def run_daily_maintenance(self):
        """Run daily maintenance tasks."""
        logger.info("Starting daily maintenance")
        self._run_task_group("daily")
    
    def run_weekly_maintenance(self):
        """Run weekly maintenance tasks."""
        logger.info("Starting weekly maintenance")
        self._run_task_group("weekly")
    
    def run_monthly_maintenance(self):
        """Run monthly maintenance tasks."""
        logger.info("Starting monthly maintenance")
        self._run_task_group("monthly")
    
    def _run_task_group(self, group: str):
        """Run a group of maintenance tasks."""
        tasks = self.tasks.get(group, [])
        
        for task_name, task_func in tasks:
            try:
                logger.info(f"Running {group} maintenance task: {task_name}")
                result = task_func()
                logger.info(f"Completed {task_name}: {result}")
            except Exception as e:
                logger.error(f"Failed to run {task_name}: {e}")
    
    def _log_task_queue_stats(self):
        """Log task queue statistics."""
        stats = get_task_queue_statistics()
        logger.info(f"Task Queue Stats: {stats}")
        return stats
    
    def _weekly_file_cleanup(self):
        """Perform weekly file cleanup."""
        cleaner = FileSystemCleaner()
        orphaned_files = cleaner.detect_orphaned_files()
        return cleaner.cleanup_orphaned_files(orphaned_files, dry_run=False)
    
    def _check_migrations(self):
        """Check if migrations are needed."""
        db = AgentDatabase()
        migration_manager = MigrationManager(db)
        
        if migration_manager.needs_migration():
            logger.warning(f"Migration needed: current={migration_manager.current_version}, target={migration_manager.target_version}")
            return {"migration_needed": True, "current": migration_manager.current_version, "target": migration_manager.target_version}
        else:
            logger.info("Database schema is up to date")
            return {"migration_needed": False}
    
    def _analyze_performance(self):
        """Analyze system performance metrics."""
        # This would integrate with monitoring systems
        stats = {
            "task_queue": get_task_queue_statistics(),
            "file_system": self._get_file_system_stats(),
            "database": self._get_database_stats()
        }
        
        logger.info(f"Performance Analysis: {stats}")
        return stats
    
    def _get_file_system_stats(self) -> dict:
        """Get file system usage statistics."""
        base_path = Path(settings.collaterals_base_path)
        
        if not base_path.exists():
            return {"total_size": 0, "file_count": 0, "directory_count": 0}
        
        total_size = 0
        file_count = 0
        directory_count = 0
        
        try:
            for item in base_path.rglob("*"):
                if item.is_file():
                    total_size += item.stat().st_size
                    file_count += 1
                elif item.is_dir():
                    directory_count += 1
        except Exception as e:
            logger.error(f"Failed to get file system stats: {e}")
        
        return {
            "total_size": total_size,
            "file_count": file_count,
            "directory_count": directory_count
        }
    
    def _get_database_stats(self) -> dict:
        """Get database usage statistics."""
        try:
            with SessionLocal() as session:
                # Get table sizes
                table_stats = {}
                tables = ["planners", "workers", "routers", "task_queue", "planner_messages", "worker_messages", "router_messages"]
                
                for table in tables:
                    result = session.execute(text(f"SELECT COUNT(*) FROM {table}")).fetchone()
                    table_stats[table] = result[0] if result else 0
                
                return table_stats
                
        except Exception as e:
            logger.error(f"Failed to get database stats: {e}")
            return {}

# Global maintenance scheduler
maintenance_scheduler = MaintenanceScheduler()
```

## Manual Maintenance Commands

### CLI Interface for Maintenance

```python
def run_maintenance_command(command: str, **kwargs):
    """Run maintenance commands manually."""
    
    commands = {
        "migrate": lambda: MigrationManager(AgentDatabase()).execute_migrations(),
        "cleanup-tasks": lambda: cleanup_completed_tasks(kwargs.get("retention_days", 7)),
        "cleanup-files": lambda: _manual_file_cleanup(kwargs.get("dry_run", True)),
        "detect-stale": lambda: detect_and_recover_stale_tasks(kwargs.get("threshold_minutes", 30)),
        "optimize-db": optimize_database,
        "check-integrity": check_database_integrity,
        "stats": get_task_queue_statistics,
        "daily": maintenance_scheduler.run_daily_maintenance,
        "weekly": maintenance_scheduler.run_weekly_maintenance,
        "monthly": maintenance_scheduler.run_monthly_maintenance
    }
    
    if command not in commands:
        logger.error(f"Unknown maintenance command: {command}")
        return {"error": f"Unknown command: {command}"}
    
    try:
        result = commands[command]()
        logger.info(f"Maintenance command '{command}' completed successfully")
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"Maintenance command '{command}' failed: {e}")
        return {"success": False, "error": str(e)}

def _manual_file_cleanup(dry_run: bool = True):
    """Manual file cleanup with dry run option."""
    cleaner = FileSystemCleaner()
    orphaned_files = cleaner.detect_orphaned_files()
    return cleaner.cleanup_orphaned_files(orphaned_files, dry_run=dry_run)

# Example usage:
# run_maintenance_command("cleanup-tasks", retention_days=14)
# run_maintenance_command("cleanup-files", dry_run=False)
# run_maintenance_command("migrate")
```

This comprehensive migration and cleanup documentation provides the foundation for maintaining a healthy, performant function-based agent system throughout its operational lifecycle.