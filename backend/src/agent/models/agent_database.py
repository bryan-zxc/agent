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
from sqlalchemy.orm import declarative_base
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool
from datetime import datetime, timezone
import json
import logging
from typing import Dict, List, Any, Optional, Literal
from pathlib import Path
from ..config.settings import settings

Base = declarative_base()

AgentType = Literal["planner", "worker", "router"]

logger = logging.getLogger(__name__)


class PlannerMessage(Base):
    __tablename__ = "planner_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String(32), nullable=False, index=True)  # UUID hex string
    role = Column(
        String(20), nullable=False
    )  # 'user', 'assistant'
    # content column REMOVED - now stored in PlannerMessageContent
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class WorkerMessage(Base):
    __tablename__ = "worker_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(
        String(32), nullable=False, index=True
    )  # UUID hex string (task_id)
    role = Column(
        String(20), nullable=False
    )  # 'user', 'assistant'
    # content column REMOVED - now stored in WorkerMessageContent
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class RouterMessage(Base):
    __tablename__ = "router_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    router_id = Column(
        String(32), ForeignKey("routers.router_id"), nullable=False, index=True
    )
    role = Column(String(20), nullable=False)  # 'user', 'assistant'
    # content column REMOVED - now stored in RouterMessageContent
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Add composite index for message history queries
    __table_args__ = (Index("idx_router_created", "router_id", "created_at"),)


# Satellite Tables for Message Content


class PlannerMessageContent(Base):
    __tablename__ = "planner_message_content"

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(Integer, ForeignKey("planner_messages.id"), nullable=False)
    content = Column(JSON, nullable=False)  # Single dictionary expected
    display_text = Column(Text, nullable=False)  # For frontend rendering
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (Index("idx_planner_content_lookup", "message_id"),)


class WorkerMessageContent(Base):
    __tablename__ = "worker_message_content"

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(Integer, ForeignKey("worker_messages.id"), nullable=False)
    content = Column(JSON, nullable=False)  # Single dictionary expected
    display_text = Column(Text, nullable=False)  # For frontend rendering
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (Index("idx_worker_content_lookup", "message_id"),)


class RouterMessageContent(Base):
    __tablename__ = "router_message_content"

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(Integer, ForeignKey("router_messages.id"), nullable=False)
    content = Column(JSON, nullable=False)  # Single dictionary expected
    display_text = Column(Text, nullable=False)  # For frontend rendering
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

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
    execution_plan_model = Column(JSON, default=lambda: {})  # ExecutionPlanModel structure
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

    agent_metadata = Column(JSON, default=lambda: {})  # Future extensibility
    schema_version = Column(Integer, default=1)  # Schema evolution tracking
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class Planner(Base):
    __tablename__ = "planners"

    planner_id = Column(String(32), primary_key=True)  # UUID hex string
    planner_name = Column(String(255))  # Human readable planner name
    user_question = Column(Text, nullable=False)  # Original user request
    instruction = Column(Text)  # Processing instructions
    execution_plan = Column(Text)  # Markdown formatted execution plan
    model = Column(String(100))  # LLM model used
    temperature = Column(Float)  # LLM temperature setting
    failed_task_limit = Column(Integer)  # Max failed tasks allowed
    status = Column(
        String(50), nullable=False, index=True
    )  # planning, executing, completed, failed - ADDED INDEX
    user_response = Column(Text)  # Final response generated for user when completed

    # New fields for function-based task queue system
    next_task = Column(String(100))  # Next function name to execute for resumability
    variable_file_paths = Column(
        JSON, default=lambda: {}
    )  # File paths for variables {key: file_path}
    image_file_paths = Column(
        JSON, default=lambda: {}
    )  # File paths for images {key: file_path}

    agent_metadata = Column(JSON, default=lambda: {})  # Future extensibility
    schema_version = Column(Integer, default=1)  # Schema evolution tracking
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
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
    acceptance_criteria = Column(JSON)  # List of success criteria
    user_request = Column(Text)  # Original user request or question
    wip_answer_template = Column(Text)  # Work-in-progress answer template
    task_result = Column(Text)  # Execution outcome
    querying_structured_data = Column(
        Boolean, default=False
    )  # Whether task queries data files
    image_keys = Column(JSON)  # List of relevant image identifiers
    variable_keys = Column(JSON)  # List of relevant variable identifiers
    tools = Column(JSON)  # List of required tools
    input_variable_filepaths = Column(
        JSON, default=lambda: {}
    )  # File paths for input variables {key: file_path}
    input_image_filepaths = Column(
        JSON, default=lambda: {}
    )  # File paths for input images {key: file_path}
    output_variable_filepaths = Column(
        JSON, default=lambda: {}
    )  # File paths for output variables {key: file_path}
    output_image_filepaths = Column(
        JSON, default=lambda: {}
    )  # File paths for output images {key: file_path}
    current_attempt = Column(Integer, default=0)  # Current retry attempt number
    tables = Column(JSON)  # TableMeta objects
    filepaths = Column(JSON)  # List of PDF file paths available for use
    agent_metadata = Column(JSON, default=lambda: {})  # Future extensibility
    schema_version = Column(Integer, default=1)  # Schema evolution tracking
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class RouterSystemInstructions(Base):
    """System instructions for router agents"""

    __tablename__ = "router_system_instructions"

    instruction_id = Column(Integer, primary_key=True, autoincrement=True)
    router_id = Column(
        String(32), ForeignKey("routers.router_id"), nullable=False, index=True
    )
    system_instruction_type = Column(
        String(50), nullable=False, default="default"
    )  # default, custom, etc.
    system_instruction = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("router_id", "system_instruction_type"),
        Index("idx_router_instruction_type", "router_id", "system_instruction_type"),
    )


class PlannerSystemInstructions(Base):
    """System instructions for planner agents"""

    __tablename__ = "planner_system_instructions"

    instruction_id = Column(Integer, primary_key=True, autoincrement=True)
    planner_id = Column(
        String(32), ForeignKey("planners.planner_id"), nullable=False, index=True
    )
    system_instruction_type = Column(
        String(50), nullable=False, default="default"
    )  # default, custom, etc.
    system_instruction = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("planner_id", "system_instruction_type"),
        Index("idx_planner_instruction_type", "planner_id", "system_instruction_type"),
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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("worker_id", "system_instruction_type"),
        Index("idx_worker_instruction_type", "worker_id", "system_instruction_type"),
    )


class RouterPlannerLink(Base):
    """Legacy table - kept for migration purposes, will be deprecated"""

    __tablename__ = "router_planner_links"

    link_id = Column(Integer, primary_key=True, autoincrement=True)
    router_id = Column(String(32), ForeignKey("routers.router_id"), nullable=False)
    planner_id = Column(String(32), ForeignKey("planners.planner_id"), nullable=False)
    relationship_type = Column(
        String(50), nullable=False
    )  # initiated, continued, forked
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (UniqueConstraint("router_id", "planner_id"),)


class RouterMessagePlannerLink(Base):
    """Links router messages to their associated planners - Schema Version 2"""

    __tablename__ = "router_message_planner_links"

    link_id = Column(Integer, primary_key=True, autoincrement=True)
    router_id = Column(String(32), ForeignKey("routers.router_id"), nullable=False)
    message_id = Column(
        Integer, ForeignKey("router_messages.id"), nullable=False, index=True
    )
    planner_id = Column(
        String(32), ForeignKey("planners.planner_id"), nullable=False, index=True
    )  # ADDED INDEX
    relationship_type = Column(
        String(50), nullable=False
    )  # initiated, continued, forked
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("message_id", "planner_id"),  # One planner per message
        Index("idx_router_message", "router_id", "message_id"),  # Fast lookups
    )


class TaskQueue(Base):
    """Task queue for async execution of planner and worker functions"""

    __tablename__ = "task_queue"

    task_id = Column(String(32), primary_key=True)  # UUID hex string
    entity_type = Column(
        String(20), nullable=False, index=True
    )  # 'planner' or 'worker'
    entity_id = Column(
        String(32), nullable=False, index=True
    )  # planner_id or worker_id
    function_name = Column(String(100), nullable=False)  # async function to execute
    status = Column(
        String(20), nullable=False, default="PENDING", index=True
    )  # PENDING, IN_PROGRESS, COMPLETED, FAILED
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    error_message = Column(Text)  # Store error details for failed tasks
    payload = Column(JSON, nullable=True)  # JSON payload for additional task parameters

    __table_args__ = (
        Index("idx_entity_status", "entity_id", "status"),
        Index("idx_status_created", "status", "created_at"),
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
    upload_timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    reference_count = Column(Integer, default=1)  # Number of times referenced


class LLMUsage(Base):
    """Track LLM API usage and costs."""
    __tablename__ = "llm_usage"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    model = Column(String(100), nullable=False)
    input_tokens = Column(Integer, nullable=False)
    output_tokens = Column(Integer, nullable=False)
    cost = Column(Float, nullable=False)
    request_type = Column(String(20), nullable=False)  # text, tools, structured, json_object, pdf_processing, web_search
    caller = Column(String(100), nullable=False, index=True)
    
    # Indexes for performance
    __table_args__ = (
        Index("idx_llm_usage_caller_timestamp", "caller", "timestamp"),
    )


class AgentDatabase:
    """Database service for managing agent messages and state.

    This class uses a factory pattern to ensure proper async initialisation.
    Use AgentDatabase.create() to instantiate, not direct __init__.
    """

    def __init__(
        self, database_path: str = settings.database_path, _internal_init: bool = False
    ):
        """Private initialiser - use AgentDatabase.create() instead.

        Args:
            database_path: Path to the SQLite database file
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

        # Store database path for schema operations
        self.database_path = database_path

        # Async engine for all database operations with improved concurrency settings
        async_database_url = f"sqlite+aiosqlite:///{database_path}"
        
        # Different configuration for in-memory vs file-based databases
        if database_path == ":memory:":
            # In-memory databases use StaticPool, which doesn't support pool_size/max_overflow
            self.async_engine = create_async_engine(
                async_database_url,
                echo=False,
                connect_args={
                    "timeout": 30,  # Connection timeout
                    "check_same_thread": False,  # Allow cross-thread access for better concurrency
                },
                pool_pre_ping=True,  # Verify connections before use to avoid stale connections
                poolclass=StaticPool,  # Use StaticPool for in-memory databases
            )
        else:
            # File-based databases can use normal pooling
            self.async_engine = create_async_engine(
                async_database_url,
                echo=False,
                connect_args={
                    "timeout": 30,  # Connection timeout
                    "check_same_thread": False,  # Allow cross-thread access for better concurrency
                },
                pool_size=20,  # Increase from default 5 to handle concurrent requests
                max_overflow=10,  # Allow 10 additional connections beyond pool_size
                pool_pre_ping=True,  # Verify connections before use to avoid stale connections
                pool_recycle=3600,  # Recycle connections every hour to prevent issues
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
    async def create(
        cls, database_path: str = settings.database_path
    ) -> "AgentDatabase":
        """Factory method to create and properly initialise an AgentDatabase instance.

        This method ensures all async initialisation is completed before returning
        the database instance, preventing issues with uninitialised connections.

        Args:
            database_path: Path to the SQLite database file

        Returns:
            Fully initialised AgentDatabase instance

        Example:
            db = await AgentDatabase.create()
        """
        # Ensure directory exists
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)

        # Create instance using internal flag
        instance = cls(database_path=database_path, _internal_init=True)

        # Perform all async initialisation
        await instance._initialise_database_async()
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

    async def _configure_async_sqlite_optimisations(self):
        """Configure SQLite pragmas for async connections"""
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
            await conn.execute(text("PRAGMA wal_autocheckpoint=1000"))  # Checkpoint every 1000 pages
            await conn.execute(text("PRAGMA mmap_size=268435456"))  # 256MB memory-mapped I/O
            logger.info("SQLite WAL mode and optimisations enabled for agent database")

    # Removed initialise_async() - now handled automatically in create()

    async def _get_last_message(
        self, agent_type: AgentType, agent_id: str
    ) -> Optional[Any]:
        """Get the most recent message for an agent.
        
        Args:
            agent_type: Type of agent ('planner', 'worker', 'router')
            agent_id: Agent identifier (router_id for router type)
            
        Returns:
            The last message object or None if no messages exist
        """
        async with self.AsyncSessionLocal() as session:
            if agent_type == "planner":
                result = await session.execute(
                    select(PlannerMessage)
                    .where(PlannerMessage.agent_id == agent_id)
                    .order_by(PlannerMessage.created_at.desc())
                    .limit(1)
                )
            elif agent_type == "worker":
                result = await session.execute(
                    select(WorkerMessage)
                    .where(WorkerMessage.agent_id == agent_id)
                    .order_by(WorkerMessage.created_at.desc())
                    .limit(1)
                )
            else:  # router
                result = await session.execute(
                    select(RouterMessage)
                    .where(RouterMessage.router_id == agent_id)
                    .order_by(RouterMessage.created_at.desc())
                    .limit(1)
                )
            
            return result.scalar_one_or_none()

    async def add_message(
        self, agent_type: AgentType, agent_id: str, role: str, content: Any
    ) -> Dict[str, Any]:
        """Add a message and its content to appropriate satellite table.
        
        If the last message has the same role, content will be appended to it
        instead of creating a new message, ensuring alternating user/assistant pattern.
        
        Args:
            agent_type: Type of agent ('planner', 'worker', 'router')
            agent_id: Agent identifier (router_id for router type)
            role: Message role ('user', 'assistant')
            content: Either a string or list of dictionaries
        
        Raises:
            ValueError: If content is not string or list of dictionaries
        
        Returns:
            Dictionary containing:
            - message_id: Message ID (either new or existing if combined)
            - display_texts: List of newly added display texts
        """
        async with self.AsyncSessionLocal() as session:
            # Determine the ContentClass based on agent type
            if agent_type == "planner":
                ContentClass = PlannerMessageContent
            elif agent_type == "worker":
                ContentClass = WorkerMessageContent
            else:  # router
                ContentClass = RouterMessageContent
            
            # Check if we should combine with the last message
            last_message = await self._get_last_message(agent_type, agent_id)
            
            # Determine the message_id to use
            if last_message and last_message.role == role:
                # Use existing message ID - combining with last message
                message_id = last_message.id
            else:
                # Create new message record
                if agent_type == "planner":
                    message = PlannerMessage(agent_id=agent_id, role=role)
                elif agent_type == "worker":
                    message = WorkerMessage(agent_id=agent_id, role=role)
                else:  # router
                    message = RouterMessage(router_id=agent_id, role=role)
                
                session.add(message)
                await session.flush()  # Flush to get the message ID
                message_id = message.id
            
            # Now process content and add to satellite table
            new_display_texts = []
            
            if isinstance(content, str):
                # Single text content
                display_text = content
                content_entry = ContentClass(
                    message_id=message_id,
                    content={"type": "text", "text": content},
                    display_text=display_text
                )
                session.add(content_entry)
                new_display_texts.append(display_text)
                # Log role and display text
                logger.info(f"[{role}] {display_text}")
            
            elif isinstance(content, list):
                # Multiple content parts - must be list of dictionaries
                for part in content:
                    if not isinstance(part, dict):
                        raise ValueError(f"List content must contain dictionaries, got {type(part)}")
                    
                    display_text = part.get("text", "")
                    content_entry = ContentClass(
                        message_id=message_id,
                        content=part,
                        display_text=display_text
                    )
                    session.add(content_entry)
                    new_display_texts.append(display_text)
                    # Log role and display text if not empty
                    if display_text:
                        logger.info(f"[{role}] {display_text}")
            
            elif isinstance(content, dict):
                # Single dictionary content
                display_text = content.get("text", "")
                content_entry = ContentClass(
                    message_id=message_id,
                    content=content,
                    display_text=display_text
                )
                session.add(content_entry)
                new_display_texts.append(display_text)
                # Log role and display text if not empty
                if display_text:
                    logger.info(f"[{role}] {display_text}")
            
            else:
                raise ValueError(f"Content must be string, dict, or list of dictionaries, got {type(content)}")
            
            await session.commit()
            # Filter out empty display texts before returning
            return {
                "message_id": message_id,
                "display_texts": [text for text in new_display_texts if text]
            }


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
        """Retrieve messages with content from appropriate satellite table"""
        async with self.AsyncSessionLocal() as session:
            # Select appropriate tables based on agent type
            if agent_type == "planner":
                MessageClass = PlannerMessage
                ContentClass = PlannerMessageContent
                query = select(MessageClass).where(MessageClass.agent_id == agent_id)
            elif agent_type == "worker":
                MessageClass = WorkerMessage
                ContentClass = WorkerMessageContent
                query = select(MessageClass).where(MessageClass.agent_id == agent_id)
            else:  # router
                MessageClass = RouterMessage
                ContentClass = RouterMessageContent
                query = select(MessageClass).where(MessageClass.router_id == agent_id)
            
            # Get messages ordered by creation time
            result = await session.execute(query.order_by(MessageClass.created_at))
            messages = result.scalars().all()
            
            # Build message list with content from satellite table
            message_list = []
            for msg in messages:
                # Get content parts from satellite table
                content_result = await session.execute(
                    select(ContentClass)
                    .where(ContentClass.message_id == msg.id)
                    .order_by(ContentClass.id)  # Order by ID to maintain insertion order
                )
                content_parts = content_result.scalars().all()
                
                # Reconstruct content
                if len(content_parts) == 0:
                    raise ValueError(f"Message {msg.id} has no content in satellite table")
                
                # Always return as list of content dictionaries
                content = [part.content for part in content_parts]
                
                message_list.append({
                    "role": msg.role,
                    "content": content
                })
            
            return message_list

    async def get_messages_for_display(
        self, agent_type: AgentType, agent_id: str
    ) -> List[Dict[str, Any]]:
        """
        Retrieve messages formatted for frontend display.
        Returns messages with display_text for each content part.
        Empty or blank display_text entries are filtered out completely.
        """
        async with self.AsyncSessionLocal() as session:
            # Select appropriate tables based on agent type
            if agent_type == "planner":
                MessageClass = PlannerMessage
                ContentClass = PlannerMessageContent
                query = select(MessageClass).where(MessageClass.agent_id == agent_id)
            elif agent_type == "worker":
                MessageClass = WorkerMessage
                ContentClass = WorkerMessageContent
                query = select(MessageClass).where(MessageClass.agent_id == agent_id)
            else:  # router
                MessageClass = RouterMessage
                ContentClass = RouterMessageContent
                query = select(MessageClass).where(MessageClass.router_id == agent_id)
            
            # Get messages ordered by creation time
            result = await session.execute(query.order_by(MessageClass.created_at))
            messages = result.scalars().all()
            
            # Build message list formatted for display
            display_messages = []
            for msg in messages:
                # Get content parts from satellite table
                content_result = await session.execute(
                    select(ContentClass)
                    .where(ContentClass.message_id == msg.id)
                    .order_by(ContentClass.id)  # Order by ID to maintain insertion order
                )
                content_parts = content_result.scalars().all()
                
                if len(content_parts) == 0:
                    continue  # Skip messages with no content
                
                # Return each content part with its display_text
                # Frontend will render each as a separate message
                # Filter out empty or blank display_text
                for part in content_parts:
                    if part.display_text and part.display_text.strip():
                        display_messages.append({
                            "role": msg.role,
                            "content": part.display_text,  # Use display_text as content for frontend
                            "message_id": msg.id
                        })
            
            return display_messages

    async def clear_messages(self, agent_type: AgentType, agent_id: str) -> None:
        """Clear all messages and their content for an agent"""
        async with self.AsyncSessionLocal() as session:
            if agent_type == "planner":
                # Delete content first (foreign key constraint)
                subquery = select(PlannerMessage.id).where(PlannerMessage.agent_id == agent_id)
                await session.execute(
                    delete(PlannerMessageContent).where(PlannerMessageContent.message_id.in_(subquery))
                )
                # Then delete messages
                await session.execute(
                    delete(PlannerMessage).where(PlannerMessage.agent_id == agent_id)
                )
            elif agent_type == "worker":
                # Delete content first
                subquery = select(WorkerMessage.id).where(WorkerMessage.agent_id == agent_id)
                await session.execute(
                    delete(WorkerMessageContent).where(WorkerMessageContent.message_id.in_(subquery))
                )
                # Then delete messages
                await session.execute(
                    delete(WorkerMessage).where(WorkerMessage.agent_id == agent_id)
                )
            else:  # router
                # Delete content first
                subquery = select(RouterMessage.id).where(RouterMessage.router_id == agent_id)
                await session.execute(
                    delete(RouterMessageContent).where(RouterMessageContent.message_id.in_(subquery))
                )
                # Then delete messages
                await session.execute(
                    delete(RouterMessage).where(RouterMessage.router_id == agent_id)
                )

            await session.commit()

    async def get_message_display_texts(self, agent_type: AgentType, message_id: int) -> List[str]:
        """Get all display texts for a message as separate entries
        
        Args:
            agent_type: Type of agent ('planner', 'worker', 'router')
            message_id: ID of the message
            
        Returns:
            List of display texts in the order they were created
        """
        async with self.AsyncSessionLocal() as session:
            # Select appropriate content table
            if agent_type == "planner":
                ContentClass = PlannerMessageContent
            elif agent_type == "worker":
                ContentClass = WorkerMessageContent
            else:  # router
                ContentClass = RouterMessageContent
            
            # Get all content parts ordered by ID
            result = await session.execute(
                select(ContentClass.display_text)
                .where(ContentClass.message_id == message_id)
                .order_by(ContentClass.id)
            )
            # Filter out empty display texts
            display_texts = [row[0] for row in result if row[0]]
            
            # Note: We don't raise an error if all display_texts are empty
            # This can happen with non-text content like images
            return display_texts
    

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
                    "title": router.title,
                    "preview": router.preview,
                    "agent_metadata": router.agent_metadata,
                    "schema_version": router.schema_version,
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

    async def create_planner(
        self,
        planner_id: str,
        user_question: str,
        instruction: str = None,
        execution_plan: str = None,
        model: str = None,
        temperature: float = None,
        failed_task_limit: int = None,
        status: str = "planning",
        planner_name: str = None,
        next_task: str = None,
    ) -> None:
        """Create a new planner state record"""
        async with self.AsyncSessionLocal() as session:
            planner = Planner(
                planner_id=planner_id,
                planner_name=planner_name,
                user_question=user_question,
                instruction=instruction,
                execution_plan=execution_plan,
                model=model,
                temperature=temperature,
                failed_task_limit=failed_task_limit,
                status=status,
                next_task=next_task,
            )
            session.add(planner)
            await session.commit()

    async def get_planner(self, planner_id: str) -> Optional[Dict[str, Any]]:
        """Get planner state by ID"""
        async with self.AsyncSessionLocal() as session:
            result = await session.execute(
                select(Planner).where(Planner.planner_id == planner_id)
            )
            planner = result.scalar_one_or_none()
            if planner:
                return {
                    "planner_id": planner.planner_id,
                    "planner_name": planner.planner_name,
                    "user_question": planner.user_question,
                    "instruction": planner.instruction,
                    "execution_plan": planner.execution_plan,
                    "model": planner.model,
                    "temperature": planner.temperature,
                    "failed_task_limit": planner.failed_task_limit,
                    "status": planner.status,
                    "agent_metadata": planner.agent_metadata,
                    "schema_version": planner.schema_version,
                    "user_response": planner.user_response,
                    "created_at": planner.created_at,
                    "updated_at": planner.updated_at,
                }
            return None

    async def create_worker(
        self,
        worker_id: str,
        router_id: str,
        worker_name: str,
        task_status: str,
        task_description: str,
        acceptance_criteria: list,
        user_request: str,
        wip_answer_template: str,
        task_result: str,
        querying_structured_data: bool,
        image_keys: list,
        variable_keys: list,
        tools: list,
        input_variable_filepaths: dict,
        input_image_filepaths: dict,
        tables: list,
        filepaths: list,
    ) -> None:
        """Create a new worker/task state record"""
        async with self.AsyncSessionLocal() as session:
            worker = Worker(
                worker_id=worker_id,
                worker_name=worker_name,
                router_id=router_id,
                task_status=task_status,
                task_description=task_description,
                acceptance_criteria=acceptance_criteria,
                user_request=user_request,
                wip_answer_template=wip_answer_template,
                task_result=task_result,
                querying_structured_data=querying_structured_data,
                image_keys=image_keys,
                variable_keys=variable_keys,
                tools=tools,
                input_variable_filepaths=input_variable_filepaths,
                input_image_filepaths=input_image_filepaths,
                output_variable_filepaths={},  # Empty initially
                output_image_filepaths={},  # Empty initially
                current_attempt=0,  # Initialise to 0
                tables=tables,
                filepaths=filepaths,
            )
            session.add(worker)
            await session.commit()

    async def update_worker(self, worker_id: str, **kwargs) -> bool:
        """Update worker fields with arbitrary keyword arguments"""
        async with self.AsyncSessionLocal() as session:
            result = await session.execute(
                select(Worker).where(Worker.worker_id == worker_id)
            )
            worker = result.scalar_one_or_none()
            if worker:
                for key, value in kwargs.items():
                    if hasattr(worker, key):
                        setattr(worker, key, value)
                worker.updated_at = datetime.now(timezone.utc)
                await session.commit()
                return True
            return False

    async def update_planner(self, planner_id: str, **kwargs) -> bool:
        """Update planner fields with arbitrary keyword arguments"""
        async with self.AsyncSessionLocal() as session:
            result = await session.execute(
                select(Planner).where(Planner.planner_id == planner_id)
            )
            planner = result.scalar_one_or_none()
            if planner:
                for key, value in kwargs.items():
                    if hasattr(planner, key):
                        setattr(planner, key, value)
                planner.updated_at = datetime.now(timezone.utc)
                await session.commit()
                return True
            return False

    async def get_worker(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """Get worker state by ID"""
        async with self.AsyncSessionLocal() as session:
            result = await session.execute(
                select(Worker).where(Worker.worker_id == worker_id)
            )
            worker = result.scalar_one_or_none()
            if worker:
                return {
                    "worker_id": worker.worker_id,
                    "worker_name": worker.worker_name,
                    "router_id": worker.router_id,
                    "task_status": worker.task_status,
                    "task_description": worker.task_description,
                    "acceptance_criteria": worker.acceptance_criteria,
                    "user_request": worker.user_request,
                    "wip_answer_template": worker.wip_answer_template,
                    "task_result": worker.task_result,
                    "querying_structured_data": worker.querying_structured_data,
                    "image_keys": worker.image_keys,
                    "variable_keys": worker.variable_keys,
                    "tools": worker.tools,
                    "input_image_filepaths": worker.input_image_filepaths,
                    "input_variable_filepaths": worker.input_variable_filepaths,
                    "output_image_filepaths": worker.output_image_filepaths,
                    "output_variable_filepaths": worker.output_variable_filepaths,
                    "tables": worker.tables,
                    "agent_metadata": worker.agent_metadata,
                    "schema_version": worker.schema_version,
                    "created_at": worker.created_at,
                    "updated_at": worker.updated_at,
                }
            return None

    async def get_workers_by_router(self, router_id: str) -> List[Dict[str, Any]]:
        """Get all workers for a router"""
        async with self.AsyncSessionLocal() as session:
            result = await session.execute(
                select(Worker)
                .where(Worker.router_id == router_id)
                .order_by(Worker.created_at)
            )
            workers = result.scalars().all()
            return [
                {
                    "worker_id": worker.worker_id,
                    "worker_name": worker.worker_name,
                    "router_id": worker.router_id,
                    "task_status": worker.task_status,
                    "task_description": worker.task_description,
                    "acceptance_criteria": worker.acceptance_criteria,
                    "user_request": worker.user_request,
                    "wip_answer_template": worker.wip_answer_template,
                    "task_result": worker.task_result,
                    "querying_structured_data": worker.querying_structured_data,
                    "image_keys": worker.image_keys,
                    "variable_keys": worker.variable_keys,
                    "tools": worker.tools,
                    "input_image_filepaths": worker.input_image_filepaths,
                    "input_variable_filepaths": worker.input_variable_filepaths,
                    "output_image_filepaths": worker.output_image_filepaths,
                    "output_variable_filepaths": worker.output_variable_filepaths,
                    "tables": worker.tables,
                    "filepaths": worker.filepaths,
                    "agent_metadata": worker.agent_metadata,
                    "schema_version": worker.schema_version,
                    "created_at": worker.created_at,
                    "updated_at": worker.updated_at,
                }
                for worker in workers
            ]

    async def link_router_planner(
        self, router_id: str, planner_id: str, relationship_type: str = "initiated"
    ) -> None:
        """Legacy method - create a link between router and planner (V1 compatibility)"""
        async with self.AsyncSessionLocal() as session:
            # Check if link already exists
            result = await session.execute(
                select(RouterPlannerLink).where(
                    RouterPlannerLink.router_id == router_id,
                    RouterPlannerLink.planner_id == planner_id,
                )
            )
            existing_link = result.scalar_one_or_none()

            if not existing_link:
                link = RouterPlannerLink(
                    router_id=router_id,
                    planner_id=planner_id,
                    relationship_type=relationship_type,
                )
                session.add(link)
                await session.commit()

    async def link_message_planner(
        self,
        router_id: str,
        message_id: int,
        planner_id: str,
        relationship_type: str = "initiated",
    ) -> None:
        """Create a link between router message and planner (V2)"""
        async with self.AsyncSessionLocal() as session:
            # Check if link already exists
            result = await session.execute(
                select(RouterMessagePlannerLink).where(
                    RouterMessagePlannerLink.message_id == message_id,
                    RouterMessagePlannerLink.planner_id == planner_id,
                )
            )
            existing_link = result.scalar_one_or_none()

            if not existing_link:
                link = RouterMessagePlannerLink(
                    router_id=router_id,
                    message_id=message_id,
                    planner_id=planner_id,
                    relationship_type=relationship_type,
                )
                session.add(link)
                await session.commit()

    async def get_planners_by_router(self, router_id: str) -> List[Dict[str, Any]]:
        """Get all planners linked to a router (legacy V1 method)"""
        async with self.AsyncSessionLocal() as session:
            # Try V2 first (RouterMessagePlannerLink)
            v2_result = await session.execute(
                select(RouterMessagePlannerLink)
                .where(RouterMessagePlannerLink.router_id == router_id)
                .order_by(RouterMessagePlannerLink.created_at)
            )
            v2_links = v2_result.scalars().all()

            if v2_links:
                # V2 data available - use message-specific links
                planners = []
                for link in v2_links:
                    planner_result = await session.execute(
                        select(Planner).where(Planner.planner_id == link.planner_id)
                    )
                    planner = planner_result.scalar_one_or_none()
                    if planner:
                        planners.append(
                            {
                                "planner_id": planner.planner_id,
                                "planner_name": planner.planner_name,
                                "user_question": planner.user_question,
                                "instruction": planner.instruction,
                                "execution_plan": planner.execution_plan,
                                "model": planner.model,
                                "temperature": planner.temperature,
                                "failed_task_limit": planner.failed_task_limit,
                                "status": planner.status,
                                "agent_metadata": planner.agent_metadata,
                                "schema_version": planner.schema_version,
                                "created_at": planner.created_at,
                                "updated_at": planner.updated_at,
                                "relationship_type": link.relationship_type,
                                "message_id": link.message_id,  # V2 addition
                            }
                        )
                return planners
            else:
                # Fallback to V1 data
                v1_result = await session.execute(
                    select(RouterPlannerLink)
                    .where(RouterPlannerLink.router_id == router_id)
                    .order_by(RouterPlannerLink.created_at)
                )
                v1_links = v1_result.scalars().all()

                planners = []
                for link in v1_links:
                    planner_result = await session.execute(
                        select(Planner).where(Planner.planner_id == link.planner_id)
                    )
                    planner = planner_result.scalar_one_or_none()
                    if planner:
                        planners.append(
                            {
                                "planner_id": planner.planner_id,
                                "planner_name": planner.planner_name,
                                "user_question": planner.user_question,
                                "instruction": planner.instruction,
                                "execution_plan": planner.execution_plan,
                                "model": planner.model,
                                "temperature": planner.temperature,
                                "failed_task_limit": planner.failed_task_limit,
                                "status": planner.status,
                                "agent_metadata": planner.agent_metadata,
                                "schema_version": planner.schema_version,
                                "created_at": planner.created_at,
                                "updated_at": planner.updated_at,
                                "relationship_type": link.relationship_type,
                                "message_id": None,  # V1 compatibility
                            }
                        )
                return planners

    async def get_planner_by_message(self, message_id: int) -> Optional[Dict[str, Any]]:
        """Get planner associated with a specific message (V2) - Optimised for read-only polling
        
        This method is heavily used by frontend polling and is optimised to minimise blocking.
        Uses a single query with JOIN to reduce round trips and avoid lock contention.
        """
        async with self.AsyncSessionLocal() as session:
            # Single optimised query with JOIN to get both link and planner data
            result = await session.execute(
                select(Planner, RouterMessagePlannerLink)
                .join(RouterMessagePlannerLink, Planner.planner_id == RouterMessagePlannerLink.planner_id)
                .where(RouterMessagePlannerLink.message_id == message_id)
            )
            row = result.first()

            if not row:
                return None

            planner, link = row

            return {
                "planner_id": planner.planner_id,
                "planner_name": planner.planner_name,
                "user_question": planner.user_question,
                "instruction": planner.instruction,
                "execution_plan": planner.execution_plan,
                "model": planner.model,
                "temperature": planner.temperature,
                "failed_task_limit": planner.failed_task_limit,
                "status": planner.status,
                "agent_metadata": planner.agent_metadata,
                "schema_version": planner.schema_version,
                "created_at": planner.created_at,
                "updated_at": planner.updated_at,
                "relationship_type": link.relationship_type,
                "message_id": link.message_id,
                "router_id": link.router_id,
            }

    async def get_message_by_planner(self, planner_id: str) -> Optional[int]:
        """Get message ID associated with a specific planner (V2)"""
        async with self.AsyncSessionLocal() as session:
            result = await session.execute(
                select(RouterMessagePlannerLink).where(
                    RouterMessagePlannerLink.planner_id == planner_id
                )
            )
            link = result.scalar_one_or_none()

            return link.message_id if link else None

    # Database Schema Management

    # Removed sync _initialise_database() - now using async _initialise_database_async()

    async def _check_and_migrate_schema_async(self) -> None:
        """Check current schema version and perform migrations if needed"""
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
            # Continue with current schema for now

    async def _get_database_schema_version_async(self) -> int:
        """Get the current database schema version"""
        async with self.AsyncSessionLocal() as session:
            try:
                # Check if we have any versioned tables by looking for schema_version column
                result = await session.execute(
                    text("SELECT schema_version FROM routers LIMIT 1")
                )
                result.fetchone()
                return 1  # If routers table exists with schema_version, we're at v1
            except Exception:
                # If routers table doesn't exist or doesn't have schema_version,
                # check if we have old message tables
                try:
                    await session.execute(text("SELECT 1 FROM routers LIMIT 1"))
                    return 1  # We have message tables, assume v1
                except Exception:
                    return 0  # Fresh database

    async def _migrate_schema_async(self, from_version: int, to_version: int) -> None:
        """Perform schema migration from one version to another"""
        logger.info(
            f"Performing schema migration from v{from_version} to v{to_version}"
        )

        if from_version == 0 and to_version >= 1:
            # Fresh install - tables created by Base.metadata.create_all()
            logger.info("Schema migration completed: Fresh database initialised")
        else:
            logger.warning(
                f"Migration from v{from_version} to v{to_version} not implemented"
            )

    async def get_schema_info(self) -> Dict[str, Any]:
        """Get database schema information for debugging"""
        return {
            "database_path": self.database_path,
            "current_schema_version": await self._get_database_schema_version_async(),
            "target_schema_version": settings.database_schema_version,
            "auto_migrate_enabled": settings.database_auto_migrate,
        }

    # File Metadata Operations

    async def create_file_metadata(
        self,
        file_id: str,
        content_hash: str,
        original_filename: str,
        file_path: str,
        file_size: int,
        mime_type: str,
    ) -> None:
        """Create a new file metadata record"""
        async with self.AsyncSessionLocal() as session:
            file_metadata = FileMetadata(
                file_id=file_id,
                content_hash=content_hash,
                original_filename=original_filename,
                file_path=file_path,
                file_size=file_size,
                mime_type=mime_type,
            )
            session.add(file_metadata)
            await session.commit()

    async def get_file_by_hash(
        self, content_hash: str
    ) -> Optional[Dict[str, Any]]:
        """Find existing file by content hash"""
        async with self.AsyncSessionLocal() as session:
            result = await session.execute(
                select(FileMetadata).where(
                    FileMetadata.content_hash == content_hash
                )
            )
            file_record = result.scalars().first()

            if file_record:
                return {
                    "file_id": file_record.file_id,
                    "content_hash": file_record.content_hash,
                    "original_filename": file_record.original_filename,
                    "file_path": file_record.file_path,
                    "file_size": file_record.file_size,
                    "mime_type": file_record.mime_type,
                    "upload_timestamp": file_record.upload_timestamp,
                    "reference_count": file_record.reference_count,
                }
            return None

    async def get_file_by_id(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Get file metadata by file ID"""
        async with self.AsyncSessionLocal() as session:
            result = await session.execute(
                select(FileMetadata).where(FileMetadata.file_id == file_id)
            )
            file_record = result.scalars().first()

            if file_record:
                return {
                    "file_id": file_record.file_id,
                    "content_hash": file_record.content_hash,
                    "original_filename": file_record.original_filename,
                    "file_path": file_record.file_path,
                    "file_size": file_record.file_size,
                    "mime_type": file_record.mime_type,
                    "upload_timestamp": file_record.upload_timestamp,
                    "reference_count": file_record.reference_count,
                }
            return None

    async def increment_file_reference(self, file_id: str) -> None:
        """Increment reference count for a file"""
        async with self.AsyncSessionLocal() as session:
            result = await session.execute(
                select(FileMetadata).where(FileMetadata.file_id == file_id)
            )
            file_record = result.scalars().first()
            if file_record:
                file_record.reference_count += 1
                await session.commit()

    async def get_files_by_filename(
        self, filename: str, user_id: str
    ) -> List[Dict[str, Any]]:
        """Get all files with the same original filename for a user"""
        async with self.AsyncSessionLocal() as session:
            result = await session.execute(
                select(FileMetadata)
                .where(
                    FileMetadata.original_filename == filename,
                    FileMetadata.user_id == user_id,
                )
                .order_by(FileMetadata.upload_timestamp.desc())
            )
            file_records = result.scalars().all()

            return [
                {
                    "file_id": record.file_id,
                    "content_hash": record.content_hash,
                    "original_filename": record.original_filename,
                    "file_path": record.file_path,
                    "file_size": record.file_size,
                    "mime_type": record.mime_type,
                    "upload_timestamp": record.upload_timestamp,
                    "user_id": record.user_id,
                    "reference_count": record.reference_count,
                }
                for record in file_records
            ]

    # Task Queue Management Methods

    async def enqueue_task(
        self,
        task_id: str,
        entity_type: str,
        entity_id: str,
        function_name: str,
        payload: dict = None,
    ) -> bool:
        """Add a task to the queue"""
        async with self.AsyncSessionLocal() as session:
            # Create new task
            task = TaskQueue(
                task_id=task_id,
                entity_type=entity_type,
                entity_id=entity_id,
                function_name=function_name,
                payload=payload,
            )

            session.add(task)
            await session.commit()
            logger.info(f"Enqueued task {task_id} for {entity_type} {entity_id}")
            return True

    async def get_pending_tasks(self) -> List[Dict[str, Any]]:
        """Get all pending tasks ordered by creation time"""
        async with self.AsyncSessionLocal() as session:
            result = await session.execute(
                select(TaskQueue)
                .where(TaskQueue.status == "PENDING")
                .order_by(TaskQueue.created_at)
            )
            tasks = result.scalars().all()

            return [
                {
                    "task_id": task.task_id,
                    "entity_type": task.entity_type,
                    "entity_id": task.entity_id,
                    "function_name": task.function_name,
                    "created_at": task.created_at,
                    "payload": task.payload,
                }
                for task in tasks
            ]

    async def update_task_status(
        self, task_id: str, status: str, error_message: str = None
    ) -> bool:
        """Update task status with timestamps"""
        async with self.AsyncSessionLocal() as session:
            result = await session.execute(
                select(TaskQueue).where(TaskQueue.task_id == task_id)
            )
            task = result.scalar_one_or_none()
            if not task:
                logger.error(f"Task {task_id} not found")
                return False

            task.status = status
            if status == "IN_PROGRESS":
                task.started_at = datetime.now(timezone.utc)
            elif status in ["COMPLETED", "FAILED"]:
                task.completed_at = datetime.now(timezone.utc)
                if status == "FAILED":
                    task.error_message = error_message

            await session.commit()
            return True

    # Planner Task Management Methods

    async def get_planner_next_task(self, planner_id: str) -> Optional[str]:
        """Get the next task function name for a planner"""
        async with self.AsyncSessionLocal() as session:
            result = await session.execute(
                select(Planner).where(Planner.planner_id == planner_id)
            )
            planner = result.scalar_one_or_none()
            return planner.next_task if planner else None

    async def get_router_id_for_planner(self, planner_id: str) -> Optional[str]:
        """Get router ID for a planner via router-message-planner links"""
        async with self.AsyncSessionLocal() as session:
            result = await session.execute(
                select(RouterMessagePlannerLink).where(
                    RouterMessagePlannerLink.planner_id == planner_id
                )
            )
            link = result.scalar_one_or_none()
            return link.router_id if link else None

    async def get_pending_task_for_entity(
        self, entity_id: str, function_name: str
    ) -> Optional[Dict[str, Any]]:
        """Check if a specific function is already queued for an entity"""
        async with self.AsyncSessionLocal() as session:
            result = await session.execute(
                select(TaskQueue).where(
                    TaskQueue.entity_id == entity_id,
                    TaskQueue.function_name == function_name,
                    TaskQueue.status.in_(["PENDING", "IN_PROGRESS"]),
                )
            )
            task = result.scalar_one_or_none()

            if task:
                return {
                    "task_id": task.task_id,
                    "function_name": task.function_name,
                    "status": task.status,
                }
            return None

    async def clear_task_queue(self) -> int:
        """Clear all tasks from the task queue on startup and return count of cleared tasks"""
        async with self.AsyncSessionLocal() as session:
            # Get count of tasks to be cleared for logging
            count_result = await session.execute(
                select(func.count()).select_from(TaskQueue)
            )
            task_count = count_result.scalar()

            # Delete all tasks in the queue
            await session.execute(delete(TaskQueue))
            await session.commit()

            logger.info(f"Cleared {task_count} tasks from task queue on startup")
            return task_count

    # System Instruction Management Methods

    async def set_router_system_instruction(
        self,
        router_id: str,
        system_instruction: str,
        instruction_type: str = "default",
    ) -> None:
        """Set or update system instruction for a router"""
        async with self.AsyncSessionLocal() as session:
            # Check if instruction already exists
            result = await session.execute(
                select(RouterSystemInstructions).where(
                    RouterSystemInstructions.router_id == router_id,
                    RouterSystemInstructions.system_instruction_type == instruction_type,
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                # Update existing instruction
                existing.system_instruction = system_instruction
                existing.updated_at = datetime.now(timezone.utc)
            else:
                # Create new instruction
                instruction = RouterSystemInstructions(
                    router_id=router_id,
                    system_instruction_type=instruction_type,
                    system_instruction=system_instruction,
                )
                session.add(instruction)

            await session.commit()

    async def get_router_system_instruction(
        self, router_id: str, instruction_type: str = "default"
    ) -> Optional[str]:
        """Get system instruction for a router"""
        async with self.AsyncSessionLocal() as session:
            result = await session.execute(
                select(RouterSystemInstructions).where(
                    RouterSystemInstructions.router_id == router_id,
                    RouterSystemInstructions.system_instruction_type == instruction_type,
                )
            )
            instruction = result.scalar_one_or_none()
            return instruction.system_instruction if instruction else None

    async def set_planner_system_instruction(
        self,
        planner_id: str,
        system_instruction: str,
        instruction_type: str = "default",
    ) -> None:
        """Set or update system instruction for a planner"""
        async with self.AsyncSessionLocal() as session:
            # Check if instruction already exists
            result = await session.execute(
                select(PlannerSystemInstructions).where(
                    PlannerSystemInstructions.planner_id == planner_id,
                    PlannerSystemInstructions.system_instruction_type == instruction_type,
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                # Update existing instruction
                existing.system_instruction = system_instruction
                existing.updated_at = datetime.now(timezone.utc)
            else:
                # Create new instruction
                instruction = PlannerSystemInstructions(
                    planner_id=planner_id,
                    system_instruction_type=instruction_type,
                    system_instruction=system_instruction,
                )
                session.add(instruction)

            await session.commit()

    async def get_planner_system_instruction(
        self, planner_id: str, instruction_type: str = "default"
    ) -> Optional[str]:
        """Get system instruction for a planner"""
        async with self.AsyncSessionLocal() as session:
            result = await session.execute(
                select(PlannerSystemInstructions).where(
                    PlannerSystemInstructions.planner_id == planner_id,
                    PlannerSystemInstructions.system_instruction_type == instruction_type,
                )
            )
            instruction = result.scalar_one_or_none()
            return instruction.system_instruction if instruction else None

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
                    WorkerSystemInstructions.system_instruction_type == instruction_type,
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

    async def get_worker_system_instruction(
        self, worker_id: str, instruction_type: str = "default"
    ) -> Optional[str]:
        """Get system instruction for a worker"""
        async with self.AsyncSessionLocal() as session:
            result = await session.execute(
                select(WorkerSystemInstructions).where(
                    WorkerSystemInstructions.worker_id == worker_id,
                    WorkerSystemInstructions.system_instruction_type == instruction_type,
                )
            )
            instruction = result.scalar_one_or_none()
            return instruction.system_instruction if instruction else None
