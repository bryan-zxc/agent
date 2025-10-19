from sqlalchemy import (
    Column,
    String,
    Text,
    DateTime,
    Integer,
    JSON,
    ForeignKey,
    Float,
    Boolean,
    UniqueConstraint,
    Index,
    func,
    select,
    delete,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.exc import OperationalError, IntegrityError
from datetime import datetime, timezone
import json
import logging
import os
from typing import Dict, List, Any, Optional, Literal
from pathlib import Path
from ..config.settings import settings

Base = declarative_base()

AgentType = Literal["planner", "worker", "router"]

logger = logging.getLogger(__name__)


# Detect database type from environment or settings
def get_database_type() -> str:
    """Detect whether we're using PostgreSQL or SQLite."""
    # Check if we have PostgreSQL configuration
    if hasattr(settings, "postgres_host") and settings.postgres_host:
        return "postgresql"
    return "sqlite"


# Select appropriate JSON type based on database
DB_TYPE = get_database_type()
json_column_type = JSONB if DB_TYPE == "postgresql" else JSON


class WorkerMessage(Base):
    __tablename__ = "worker_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(
        String(32), nullable=False, index=True
    )  # UUID hex string (task_id)

    # New columns for native API format storage
    technical_message = Column(json_column_type, nullable=False)  # Native API format (for LLM)
    display_message = Column(Text, nullable=True)  # Human-readable text (for UI) - NULL means don't display
    message_from = Column(String(10), nullable=False)  # "Bandit" or "Me" - for frontend rendering

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class RouterMessage(Base):
    __tablename__ = "router_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    router_id = Column(
        String(32), ForeignKey("routers.router_id"), nullable=False, index=True
    )

    # New columns for native API format storage
    technical_message = Column(json_column_type, nullable=False)  # Native API format (for LLM)
    display_message = Column(Text, nullable=True)  # Human-readable text (for UI) - NULL means don't display
    message_from = Column(String(10), nullable=False)  # "Bandit" or "Me" - for frontend rendering

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Add composite index for message history queries
    __table_args__ = (Index("idx_router_created", "router_id", "created_at"),)


# Satellite Tables for Message Content


class WorkerMessageContent(Base):
    __tablename__ = "worker_message_content"

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(Integer, ForeignKey("worker_messages.id"), nullable=False)
    content = Column(json_column_type, nullable=False)  # Single dictionary expected
    display_text = Column(Text, nullable=False)  # For frontend rendering
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (Index("idx_worker_content_lookup", "message_id"),)


class RouterMessageContent(Base):
    __tablename__ = "router_message_content"

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(Integer, ForeignKey("router_messages.id"), nullable=False)
    content = Column(json_column_type, nullable=False)  # Single dictionary expected
    display_text = Column(Text, nullable=False)  # For frontend rendering
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (Index("idx_router_content_lookup", "message_id"),)


# Agent State Tables


class Router(Base):
    __tablename__ = "routers"

    router_id = Column(
        String(32), primary_key=True
    )  # UUID hex string (same as router_id)
    status = Column(
        String(50), nullable=False
    )  # active, plamarinating, plamarinating_awaiting_user, awaiting_approval, executing, processing, completed, failed, archived
    model = Column(String(100))  # LLM model used
    temperature = Column(Float)  # LLM temperature setting
    mode = Column(String(10), nullable=False, default="auto")  # auto, rapid, agent
    agent_phase = Column(
        String(20),
        nullable=True,  # Null when not in agent mode
        default=None,
        comment="Phase when in agent mode: plamarination or execution",
    )
    title = Column(String(255), nullable=False, default="New conversation")
    preview = Column(String(255), nullable=False, default="")

    # Execution-related fields for merged planner-router architecture
    execution_plan = Column(Text)  # Markdown formatted plan from plamarination
    execution_plan_model = Column(
        JSON, default=lambda: {}
    )  # ExecutionPlanModel structure
    current_task = Column(JSON, default=lambda: {})  # Active task being executed
    execution_status = Column(
        String(50), default="idle"
    )  # idle, creating_task, executing_worker, synthesising, complete
    worker_metadata = Column(
        JSON, default=lambda: {}
    )  # {task_id: {description, tools, status, result}}
    variable_file_paths = Column(
        JSON, default=lambda: {}
    )  # File paths for variables {key: file_path}
    image_file_paths = Column(
        JSON, default=lambda: {}
    )  # File paths for images {key: file_path}
    answer_template = Column(Text)  # Template for final answer from plamarination
    wip_answer = Column(Text)  # Work-in-progress answer being filled during execution

    agent_metadata = Column(
        json_column_type, default=lambda: {}
    )  # Future extensibility
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class Worker(Base):
    __tablename__ = "workers"

    worker_id = Column(
        String(32), primary_key=True
    )  # UUID hex string (links to worker_messages)
    worker_name = Column(String(255))  # Human readable worker name
    router_id = Column(
        String(32), ForeignKey("routers.router_id"), nullable=False, index=True
    )  # Direct relationship to router
    task_status = Column(
        String(50), nullable=False, index=True
    )  # pending, in_progress, completed, failed_validation, recorded
    next_task = Column(String(100))  # Next async function to execute
    task_description = Column(Text)  # Detailed task description
    acceptance_criteria = Column(json_column_type)  # List of success criteria
    user_request = Column(Text)  # Original user request or question
    wip_answer_template = Column(Text)  # Work-in-progress answer template
    task_result = Column(Text)  # Execution outcome
    querying_structured_data = Column(
        Boolean, default=False
    )  # Whether task queries data files
    image_keys = Column(json_column_type)  # List of relevant image identifiers
    variable_keys = Column(json_column_type)  # List of relevant variable identifiers
    tools = Column(json_column_type)  # List of required tools
    input_variable_filepaths = Column(
        json_column_type, default=lambda: {}
    )  # File paths for input variables {key: file_path}
    input_image_filepaths = Column(
        json_column_type, default=lambda: {}
    )  # File paths for input images {key: file_path}
    output_variable_filepaths = Column(
        json_column_type, default=lambda: {}
    )  # File paths for output variables {key: file_path}
    output_image_filepaths = Column(
        json_column_type, default=lambda: {}
    )  # File paths for output images {key: file_path}
    current_attempt = Column(Integer, default=0)  # Current retry attempt number
    tables = Column(json_column_type)  # TableMeta objects
    filepaths = Column(json_column_type)  # List of PDF file paths available for use
    agent_metadata = Column(
        json_column_type, default=lambda: {}
    )  # Future extensibility
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class WorkerSystemInstructions(Base):
    """System instructions for worker agents"""

    __tablename__ = "worker_system_instructions"

    instruction_id = Column(Integer, primary_key=True, autoincrement=True)
    worker_id = Column(
        String(32), ForeignKey("workers.worker_id"), nullable=False, index=True
    )
    system_instruction_type = Column(
        String(50), nullable=False, default="default"
    )  # default, custom, etc.
    system_instruction = Column(Text, nullable=False)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("worker_id", "system_instruction_type"),
        Index("idx_worker_instruction_type", "worker_id", "system_instruction_type"),
    )


class FileMetadata(Base):
    __tablename__ = "file_metadata"

    file_id = Column(String(32), primary_key=True)  # UUID hex string
    content_hash = Column(String(64), nullable=False, index=True)  # SHA-256 hash
    original_filename = Column(
        String(512), nullable=False
    )  # Original filename from user
    file_path = Column(String(1024), nullable=False)  # Actual storage path
    file_size = Column(Integer, nullable=False)  # File size in bytes
    mime_type = Column(String(255))  # MIME type
    upload_timestamp = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    reference_count = Column(Integer, default=1)  # Number of times referenced


class LLMUsage(Base):
    """Track LLM API usage and costs."""

    __tablename__ = "llm_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    model = Column(String(100), nullable=False)
    input_tokens = Column(Integer, nullable=False)
    output_tokens = Column(Integer, nullable=False)
    cost = Column(Float, nullable=False)
    request_type = Column(
        String(20), nullable=False
    )  # text, tools, structured, json_object, pdf_processing, web_search
    caller = Column(String(100), nullable=False, index=True)

    # Indexes for performance
    __table_args__ = (Index("idx_llm_usage_caller_timestamp", "caller", "timestamp"),)


class SchemaVersion(Base):
    """Global database schema version tracking.

    This table tracks the current schema version of the entire database,
    providing a single source of truth for migration management.
    Unlike per-record schema_version columns, this represents the
    structural version of the database schema itself.
    """

    __tablename__ = "schema_version"

    version = Column(Integer, primary_key=True)
    applied_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    description = Column(Text)


class AgentDatabase:
    """Database service for managing agent messages and state.

    This class uses a factory pattern to ensure proper async initialisation.
    Use AgentDatabase.create() to instantiate, not direct __init__.
    """

    def __init__(self, database_url: str = None, _internal_init: bool = False):
        """Private initialiser - use AgentDatabase.create() instead.

        Args:
            database_url: Database connection URL (PostgreSQL or SQLite)
            _internal_init: Internal flag to prevent direct instantiation

        Raises:
            RuntimeError: If called directly without using the factory method
        """
        if not _internal_init:
            raise RuntimeError(
                "AgentDatabase must be created using the async factory method.\n"
                "Use: db = await AgentDatabase.create()\n"
                "Not: db = AgentDatabase()"
            )

        # Build database URL from settings if not provided
        if database_url is None:
            # Always use project-specific database for isolation
            from ..database.connection import DatabaseConfig
            config = DatabaseConfig()
            database_url = config.get_database_url()  # Uses settings.project_name

        # Store database URL for schema operations
        self.database_url = database_url

        # Set the async database URL
        async_database_url = database_url

        # Different configuration for PostgreSQL vs SQLite
        if "postgresql" in async_database_url:
            # PostgreSQL configuration
            self.async_engine = create_async_engine(
                async_database_url,
                echo=False,
                pool_size=20,  # Connection pool size
                max_overflow=10,  # Additional connections allowed
                pool_pre_ping=True,  # Verify connections before use
                pool_recycle=3600,  # Recycle connections every hour
            )
        elif ":memory:" in async_database_url:
            # In-memory SQLite databases use StaticPool
            self.async_engine = create_async_engine(
                async_database_url,
                echo=False,
                connect_args={
                    "timeout": 30,  # Connection timeout
                    "check_same_thread": False,  # Allow cross-thread access
                },
                pool_pre_ping=True,
                poolclass=StaticPool,  # Use StaticPool for in-memory databases
            )
        else:
            # File-based SQLite databases
            self.async_engine = create_async_engine(
                async_database_url,
                echo=False,
                connect_args={
                    "timeout": 30,  # Connection timeout
                    "check_same_thread": False,  # Allow cross-thread access
                },
                pool_size=20,  # Increase from default 5 to handle concurrent requests
                max_overflow=10,  # Allow 10 additional connections beyond pool_size
                pool_pre_ping=True,  # Verify connections before use
                pool_recycle=3600,  # Recycle connections every hour
            )

        # Async session factory with optimised settings
        self.AsyncSessionLocal = async_sessionmaker(
            bind=self.async_engine,
            class_=AsyncSession,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )

    @classmethod
    async def create(cls, database_url: str = None) -> "AgentDatabase":
        """Factory method to create and properly initialise an AgentDatabase instance.

        This method ensures all async initialisation is completed before returning
        the database instance, preventing issues with uninitialised connections.

        Args:
            database_url: Database connection URL (PostgreSQL or SQLite)

        Returns:
            Fully initialised AgentDatabase instance

        Example:
            db = await AgentDatabase.create()
        """
        # Create instance using internal flag
        instance = cls(database_url=database_url, _internal_init=True)

        # Perform all async initialisation
        await instance._initialise_database_async()

        # Only configure SQLite optimisations for SQLite databases
        if instance.database_url and "sqlite" in instance.database_url:
            await instance._configure_async_sqlite_optimisations()

        return instance

    async def _initialise_database_async(self) -> None:
        """Initialise database schema using async operations."""
        # Create tables if they don't exist
        async with self.async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Check schema version and migrate if needed
        if settings.database_auto_migrate:
            await self._check_and_migrate_schema_async()
        else:
            logger.info(f"Database initialised. Auto-migration disabled.")

    async def _check_and_migrate_schema_async(self) -> None:
        """Check current schema version and perform migrations if needed."""
        try:
            current_version = await self._get_database_schema_version_async()
            target_version = settings.database_schema_version

            if current_version == target_version:
                logger.info(
                    f"Database schema is up to date (version {current_version})"
                )
                return

            if current_version < target_version:
                logger.info(
                    f"Migrating database schema from version {current_version} to {target_version}"
                )
                await self._migrate_schema_async(current_version, target_version)
            else:
                logger.warning(
                    f"Database schema version {current_version} is newer than expected {target_version}"
                )

        except Exception as e:
            logger.error(f"Schema version check failed: {e}")
            # Continue with current schema - don't block startup on migration errors

    async def _get_database_schema_version_async(self) -> int:
        """Get the current database schema version from SchemaVersion table.

        Returns:
            int: Current schema version, or 0 if SchemaVersion table doesn't exist (fresh database)
        """
        async with self.AsyncSessionLocal() as session:
            try:
                # Try to query the SchemaVersion table
                result = await session.execute(
                    select(SchemaVersion.version).order_by(
                        SchemaVersion.version.desc()
                    )
                )
                version_row = result.first()
                if version_row:
                    return version_row[0]
                else:
                    # Table exists but empty - fresh database
                    return 0
            except Exception:
                # SchemaVersion table doesn't exist - fresh database
                return 0

    async def _migrate_schema_async(self, from_version: int, to_version: int) -> None:
        """Perform schema migration from one version to another.

        Args:
            from_version: Current schema version
            to_version: Target schema version
        """
        logger.info(
            f"Performing schema migration from v{from_version} to v{to_version}"
        )

        async with self.AsyncSessionLocal() as session:
            try:
                if from_version == 0 and to_version == 1:
                    # Fresh database - create initial SchemaVersion record
                    schema_record = SchemaVersion(
                        version=1,
                        description="Initial schema with Router, Worker, and message tables",
                    )
                    session.add(schema_record)
                    await session.commit()
                    logger.info(
                        "Schema migration completed: Fresh database initialised to v1"
                    )
                else:
                    # Future migrations would go here
                    logger.warning(
                        f"Migration from v{from_version} to v{to_version} not implemented"
                    )
            except Exception as e:
                logger.error(f"Migration failed: {e}")
                await session.rollback()
                raise

    async def _configure_async_sqlite_optimisations(self):
        """Configure SQLite pragmas for async connections (SQLite only)"""
        async with self.async_engine.begin() as conn:
            from sqlalchemy import text

            # Apply optimised pragmas for better concurrency
            await conn.execute(text("PRAGMA journal_mode=WAL"))
            await conn.execute(
                text("PRAGMA busy_timeout=30000")
            )  # 30 second timeout to prevent blocking on concurrent access
            await conn.execute(text("PRAGMA synchronous=NORMAL"))
            await conn.execute(text("PRAGMA cache_size=-64000"))  # 64MB cache
            await conn.execute(text("PRAGMA foreign_keys=ON"))
            await conn.execute(text("PRAGMA temp_store=MEMORY"))
            # Additional optimisations for read-heavy workloads
            await conn.execute(
                text("PRAGMA wal_autocheckpoint=1000")
            )  # Checkpoint every 1000 pages
            await conn.execute(
                text("PRAGMA mmap_size=268435456")
            )  # 256MB memory-mapped I/O
            logger.info("SQLite WAL mode and optimisations enabled for agent database")

    # Removed initialise_async() - now handled automatically in create()

    async def add_message(
        self,
        agent_type: AgentType,
        agent_id: str,
        message_from: str,
        technical_message: Dict[str, Any],
        display_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """Add a message using new standardised format.

        Args:
            agent_type: Type of agent ('planner', 'worker', 'router')
            agent_id: Agent identifier (router_id for router type)
            message_from: "Bandit" (from agent) or "Me" (from user)
            technical_message: Native API format dict (JSONB)
            display_message: Human-readable text (None if shouldn't display)

        Returns:
            Dictionary containing message_id
        """
        async with self.AsyncSessionLocal() as session:
            # Create message record
            if agent_type == "worker":
                message = WorkerMessage(
                    agent_id=agent_id,
                    message_from=message_from,
                    technical_message=technical_message,
                    display_message=display_message
                )
            else:  # router
                message = RouterMessage(
                    router_id=agent_id,
                    message_from=message_from,
                    technical_message=technical_message,
                    display_message=display_message
                )

            session.add(message)
            await session.flush()
            message_id = message.id

            # Log for debugging
            if display_message:
                logger.info(f"[{message_from}] {display_message[:100]}")

            await session.commit()
            return {"message_id": message_id}

    async def update_router(self, router_id: str, **kwargs) -> bool:
        """Update router fields with arbitrary keyword arguments"""
        async with self.AsyncSessionLocal() as session:
            result = await session.execute(
                select(Router).where(Router.router_id == router_id)
            )
            router = result.scalar_one_or_none()
            if router:
                for key, value in kwargs.items():
                    if hasattr(router, key):
                        setattr(router, key, value)
                router.updated_at = datetime.now(timezone.utc)
                await session.commit()
                return True
            return False

    async def get_messages(
        self, agent_type: AgentType, agent_id: str
    ) -> List[Dict[str, Any]]:
        """Retrieve messages for LLM API calls.

        Returns list of technical_message dicts in native API format.
        """
        async with self.AsyncSessionLocal() as session:
            # Select appropriate table
            if agent_type == "worker":
                MessageClass = WorkerMessage
                query = select(MessageClass).where(MessageClass.agent_id == agent_id)
            else:  # router
                MessageClass = RouterMessage
                query = select(MessageClass).where(MessageClass.router_id == agent_id)

            # Get messages ordered by creation time
            result = await session.execute(query.order_by(MessageClass.created_at))
            messages = result.scalars().all()

            # Return just the technical_message dicts
            return [msg.technical_message for msg in messages]

    async def get_messages_for_display(
        self, agent_type: AgentType, agent_id: str
    ) -> List[Dict[str, Any]]:
        """Retrieve messages formatted for frontend display.

        Returns messages with message_from ("Bandit"/"Me") and display_message.
        Skips messages where display_message is NULL.
        """
        async with self.AsyncSessionLocal() as session:
            # Select appropriate table
            if agent_type == "worker":
                MessageClass = WorkerMessage
                query = select(MessageClass).where(MessageClass.agent_id == agent_id)
            else:  # router
                MessageClass = RouterMessage
                query = select(MessageClass).where(MessageClass.router_id == agent_id)

            # Get messages ordered by creation time
            result = await session.execute(query.order_by(MessageClass.created_at))
            messages = result.scalars().all()

            # Build display message list (skip NULL display_message)
            display_messages = []
            for msg in messages:
                if msg.display_message is not None:
                    display_messages.append({
                        "message_from": msg.message_from,  # "Bandit" or "Me"
                        "content": msg.display_message,
                        "message_id": msg.id
                    })

            return display_messages

    async def clear_messages(self, agent_type: AgentType, agent_id: str) -> None:
        """Clear all messages for an agent"""
        async with self.AsyncSessionLocal() as session:
            if agent_type == "worker":
                await session.execute(
                    delete(WorkerMessage).where(WorkerMessage.agent_id == agent_id)
                )
            else:  # router
                await session.execute(
                    delete(RouterMessage).where(RouterMessage.router_id == agent_id)
                )

            await session.commit()

    # Agent State Operations

    async def create_router(
        self,
        router_id: str,
        status: str,
        model: str = None,
        temperature: float = None,
        mode: str = None,
        title: str = None,
        preview: str = None,
    ) -> None:
        """Create a new router record"""
        async with self.AsyncSessionLocal() as session:
            router = Router(
                router_id=router_id,
                status=status,
                model=model or settings.router_model,
                temperature=temperature or 0.0,
                mode=mode or "auto",
                title=title or "New conversation",
                preview=preview or "",
            )
            session.add(router)
            await session.commit()

    async def get_router(self, router_id: str) -> Optional[Dict[str, Any]]:
        """Get router state by ID"""
        async with self.AsyncSessionLocal() as session:
            result = await session.execute(
                select(Router).where(Router.router_id == router_id)
            )
            router = result.scalar_one_or_none()
            if router:
                return {
                    "router_id": router.router_id,
                    "status": router.status,
                    "model": router.model,
                    "temperature": router.temperature,
                    "mode": router.mode,
                    "agent_phase": router.agent_phase,
                    "title": router.title,
                    "preview": router.preview,
                    "execution_plan": router.execution_plan,
                    "execution_plan_model": router.execution_plan_model,
                    "answer_template": router.answer_template,
                    "execution_status": router.execution_status,
                    "current_task": router.current_task,
                    "worker_metadata": router.worker_metadata,
                    "variable_file_paths": router.variable_file_paths,
                    "image_file_paths": router.image_file_paths,
                    "wip_answer": router.wip_answer,
                    "agent_metadata": router.agent_metadata,
                    "created_at": router.created_at,
                    "updated_at": router.updated_at,
                }
            return None

    async def get_all_routers(self) -> List[Dict[str, Any]]:
        """Get all routers ordered by updated_at descending"""
        async with self.AsyncSessionLocal() as session:
            result = await session.execute(
                select(Router).order_by(Router.updated_at.desc())
            )
            routers = result.scalars().all()
            return [
                {
                    "router_id": router.router_id,
                    "title": router.title,
                    "preview": router.preview,
                    "status": router.status,
                    "created_at": router.created_at,
                    "updated_at": router.updated_at,
                }
                for router in routers
            ]

    # Planner functions removed - planners are no longer created
    # The router now handles execution plans directly via execution_plan field
    # and the set_plan_and_answer MCP tool

    async def set_worker_system_instruction(
        self,
        worker_id: str,
        system_instruction: str,
        instruction_type: str = "default",
    ) -> None:
        """Set or update system instruction for a worker"""
        async with self.AsyncSessionLocal() as session:
            # Check if instruction already exists
            result = await session.execute(
                select(WorkerSystemInstructions).where(
                    WorkerSystemInstructions.worker_id == worker_id,
                    WorkerSystemInstructions.system_instruction_type
                    == instruction_type,
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                # Update existing instruction
                existing.system_instruction = system_instruction
                existing.updated_at = datetime.now(timezone.utc)
            else:
                # Create new instruction
                instruction = WorkerSystemInstructions(
                    worker_id=worker_id,
                    system_instruction_type=instruction_type,
                    system_instruction=system_instruction,
                )
                session.add(instruction)

            await session.commit()

    async def delete_file_metadata_by_path(self, file_path: str) -> bool:
        """Delete file metadata by file path. Returns True even if no record found."""
        async with self.AsyncSessionLocal() as session:
            result = await session.execute(
                select(FileMetadata).where(FileMetadata.file_path == file_path)
            )
            file_record = result.scalars().first()

            if file_record:
                await session.delete(file_record)
                await session.commit()
                return True

            # Return True even if no record found (for orphaned files)
            return True

    async def get_file_by_hash(self, content_hash: str) -> Optional[Dict]:
        """Get file metadata by content hash for duplicate detection.

        Args:
            content_hash: SHA-256 hash of file content

        Returns:
            Dictionary with file metadata if found, None otherwise
        """
        async with self.AsyncSessionLocal() as session:
            result = await session.execute(
                select(FileMetadata).where(FileMetadata.content_hash == content_hash)
            )
            file_record = result.scalars().first()

            if file_record:
                return {
                    "file_id": file_record.file_id,
                    "original_filename": file_record.original_filename,
                    "file_path": file_record.file_path,
                    "file_size": file_record.file_size,
                    "mime_type": file_record.mime_type,
                    "upload_timestamp": file_record.upload_timestamp,
                    "reference_count": file_record.reference_count,
                }
            return None

    async def get_file_by_id(self, file_id: str) -> Optional[Dict]:
        """Get file metadata by file ID.

        Args:
            file_id: Unique file identifier

        Returns:
            Dictionary with file metadata if found, None otherwise
        """
        async with self.AsyncSessionLocal() as session:
            result = await session.execute(
                select(FileMetadata).where(FileMetadata.file_id == file_id)
            )
            file_record = result.scalars().first()

            if file_record:
                return {
                    "file_id": file_record.file_id,
                    "original_filename": file_record.original_filename,
                    "file_path": file_record.file_path,
                    "file_size": file_record.file_size,
                    "mime_type": file_record.mime_type,
                    "upload_timestamp": file_record.upload_timestamp,
                    "reference_count": file_record.reference_count,
                }
            return None

    async def create_file_metadata(
        self,
        file_id: str,
        content_hash: str,
        original_filename: str,
        file_path: str,
        file_size: int,
        mime_type: Optional[str] = None,
    ) -> None:
        """Create new file metadata record.

        Args:
            file_id: Unique file identifier
            content_hash: SHA-256 hash of file content
            original_filename: Original filename from user
            file_path: Actual storage path
            file_size: File size in bytes
            mime_type: MIME type (optional)
        """
        async with self.AsyncSessionLocal() as session:
            file_metadata = FileMetadata(
                file_id=file_id,
                content_hash=content_hash,
                original_filename=original_filename,
                file_path=file_path,
                file_size=file_size,
                mime_type=mime_type,
                reference_count=1,
            )
            session.add(file_metadata)
            await session.commit()

    async def increment_file_reference(self, file_id: str) -> None:
        """Increment reference count for a file when it's reused.

        Args:
            file_id: Unique file identifier
        """
        async with self.AsyncSessionLocal() as session:
            result = await session.execute(
                select(FileMetadata).where(FileMetadata.file_id == file_id)
            )
            file_record = result.scalars().first()

            if file_record:
                file_record.reference_count += 1
                await session.commit()

    async def get_worker_system_instruction(
        self, worker_id: str, instruction_type: str = "default"
    ) -> Optional[str]:
        """Get system instruction for a worker"""
        async with self.AsyncSessionLocal() as session:
            result = await session.execute(
                select(WorkerSystemInstructions).where(
                    WorkerSystemInstructions.worker_id == worker_id,
                    WorkerSystemInstructions.system_instruction_type
                    == instruction_type,
                )
            )
            instruction = result.scalar_one_or_none()
            return instruction.system_instruction if instruction else None
