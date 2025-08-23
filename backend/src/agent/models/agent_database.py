from sqlalchemy import Column, String, Text, DateTime, Integer, JSON, create_engine, ForeignKey, Float, Boolean, UniqueConstraint, Index, func, select
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from datetime import datetime
import json
import logging
from typing import Dict, List, Any, Optional, Literal
from pathlib import Path
from ..config.settings import settings

Base = declarative_base()

AgentType = Literal["planner", "worker", "router"]

logger = logging.getLogger(__name__)


class PlannerMessage(Base):
    __tablename__ = 'planner_messages'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String(32), nullable=False, index=True)  # UUID hex string
    role = Column(String(20), nullable=False)  # 'user', 'assistant', 'system', 'developer'
    content = Column(JSON, nullable=False)  # Store as JSON to handle both string and list content
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def to_message_dict(self) -> Dict[str, Any]:
        """Convert database record back to message format"""
        return {
            "role": self.role,
            "content": self.content
        }


class WorkerMessage(Base):
    __tablename__ = 'worker_messages'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String(32), nullable=False, index=True)  # UUID hex string (task_id)
    role = Column(String(20), nullable=False)  # 'user', 'assistant', 'system', 'developer'
    content = Column(JSON, nullable=False)  # Store as JSON to handle both string and list content
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def to_message_dict(self) -> Dict[str, Any]:
        """Convert database record back to message format"""
        return {
            "role": self.role,
            "content": self.content
        }


class RouterMessage(Base):
    __tablename__ = 'router_messages'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    router_id = Column(String(32), ForeignKey('routers.router_id'), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # 'user', 'assistant'
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Add composite index for message history queries
    __table_args__ = (
        Index('idx_router_created', 'router_id', 'created_at'),
    )
    
    def to_message_dict(self) -> Dict[str, Any]:
        """Convert database record back to message format"""
        return {
            "role": self.role,
            "content": self.content,
            "message_id": self.id  # Include database message ID for frontend
        }


# Agent State Tables

class Router(Base):
    __tablename__ = 'routers'
    
    router_id = Column(String(32), primary_key=True)  # UUID hex string (same as router_id)
    status = Column(String(50), nullable=False)  # active, completed, failed, archived
    model = Column(String(100))  # LLM model used
    temperature = Column(Float)  # LLM temperature setting
    title = Column(String(255), nullable=False, default="New conversation")
    preview = Column(String(255), nullable=False, default="")
    agent_metadata = Column(JSON, default=lambda: {})  # Future extensibility
    schema_version = Column(Integer, default=1)  # Schema evolution tracking
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Planner(Base):
    __tablename__ = 'planners'
    
    planner_id = Column(String(32), primary_key=True)  # UUID hex string
    planner_name = Column(String(255))  # Human readable planner name
    user_question = Column(Text, nullable=False)  # Original user request
    instruction = Column(Text)  # Processing instructions
    execution_plan = Column(Text)  # Markdown formatted execution plan
    model = Column(String(100))  # LLM model used
    temperature = Column(Float)  # LLM temperature setting
    failed_task_limit = Column(Integer)  # Max failed tasks allowed
    status = Column(String(50), nullable=False, index=True)  # planning, executing, completed, failed - ADDED INDEX
    user_response = Column(Text)  # Final response generated for user when completed
    
    # New fields for function-based task queue system
    next_task = Column(String(100))  # Next function name to execute for resumability
    variable_file_paths = Column(JSON, default=lambda: {})  # File paths for variables {key: file_path}
    image_file_paths = Column(JSON, default=lambda: {})  # File paths for images {key: file_path}
    
    agent_metadata = Column(JSON, default=lambda: {})  # Future extensibility
    schema_version = Column(Integer, default=1)  # Schema evolution tracking
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Worker(Base):
    __tablename__ = 'workers'
    
    worker_id = Column(String(32), primary_key=True)  # UUID hex string (links to worker_messages)
    worker_name = Column(String(255))  # Human readable worker name
    planner_id = Column(String(32), ForeignKey('planners.planner_id'), nullable=False, index=True)  # Direct relationship to planner
    task_status = Column(String(50), nullable=False, index=True)  # pending, in_progress, completed, failed_validation, recorded
    next_task = Column(String(100))  # Next async function to execute
    task_description = Column(Text)  # Detailed task description
    acceptance_criteria = Column(JSON)  # List of success criteria
    user_request = Column(Text)  # Original user request or question
    wip_answer_template = Column(Text)  # Work-in-progress answer template
    task_result = Column(Text)  # Execution outcome
    querying_structured_data = Column(Boolean, default=False)  # Whether task queries data files
    image_keys = Column(JSON)  # List of relevant image identifiers
    variable_keys = Column(JSON)  # List of relevant variable identifiers
    tools = Column(JSON)  # List of required tools
    input_variable_filepaths = Column(JSON, default=lambda: {})  # File paths for input variables {key: file_path}
    input_image_filepaths = Column(JSON, default=lambda: {})  # File paths for input images {key: file_path}
    output_variable_filepaths = Column(JSON, default=lambda: {})  # File paths for output variables {key: file_path}
    output_image_filepaths = Column(JSON, default=lambda: {})  # File paths for output images {key: file_path}
    current_attempt = Column(Integer, default=0)  # Current retry attempt number
    tables = Column(JSON)  # TableMeta objects
    filepaths = Column(JSON)  # List of PDF file paths available for use
    agent_metadata = Column(JSON, default=lambda: {})  # Future extensibility
    schema_version = Column(Integer, default=1)  # Schema evolution tracking
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RouterPlannerLink(Base):
    """Legacy table - kept for migration purposes, will be deprecated"""
    __tablename__ = 'router_planner_links'
    
    link_id = Column(Integer, primary_key=True, autoincrement=True)
    router_id = Column(String(32), ForeignKey('routers.router_id'), nullable=False)
    planner_id = Column(String(32), ForeignKey('planners.planner_id'), nullable=False)
    relationship_type = Column(String(50), nullable=False)  # initiated, continued, forked
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (UniqueConstraint('router_id', 'planner_id'),)


class RouterMessagePlannerLink(Base):
    """Links router messages to their associated planners - Schema Version 2"""
    __tablename__ = 'router_message_planner_links'
    
    link_id = Column(Integer, primary_key=True, autoincrement=True)
    router_id = Column(String(32), ForeignKey('routers.router_id'), nullable=False)
    message_id = Column(Integer, ForeignKey('router_messages.id'), nullable=False, index=True)
    planner_id = Column(String(32), ForeignKey('planners.planner_id'), nullable=False, index=True)  # ADDED INDEX
    relationship_type = Column(String(50), nullable=False)  # initiated, continued, forked
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint('message_id', 'planner_id'),  # One planner per message
        Index('idx_router_message', 'router_id', 'message_id'),  # Fast lookups
    )


class TaskQueue(Base):
    """Task queue for async execution of planner and worker functions"""
    __tablename__ = 'task_queue'
    
    task_id = Column(String(32), primary_key=True)  # UUID hex string
    entity_type = Column(String(20), nullable=False, index=True)  # 'planner' or 'worker'
    entity_id = Column(String(32), nullable=False, index=True)  # planner_id or worker_id
    function_name = Column(String(100), nullable=False)  # async function to execute
    status = Column(String(20), nullable=False, default='PENDING', index=True)  # PENDING, IN_PROGRESS, COMPLETED, FAILED
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    error_message = Column(Text)  # Store error details for failed tasks
    payload = Column(JSON, nullable=True)  # JSON payload for additional task parameters
    
    __table_args__ = (
        Index('idx_entity_status', 'entity_id', 'status'),
        Index('idx_status_created', 'status', 'created_at'),
    )


class FileMetadata(Base):
    __tablename__ = 'file_metadata'
    
    file_id = Column(String(32), primary_key=True)  # UUID hex string
    content_hash = Column(String(64), nullable=False, index=True)  # SHA-256 hash
    original_filename = Column(String(512), nullable=False)  # Original filename from user
    file_path = Column(String(1024), nullable=False)  # Actual storage path
    file_size = Column(Integer, nullable=False)  # File size in bytes
    mime_type = Column(String(255))  # MIME type
    upload_timestamp = Column(DateTime, default=datetime.utcnow)
    user_id = Column(String(255), nullable=False, index=True)  # User identifier
    reference_count = Column(Integer, default=1)  # Number of times referenced
    
    __table_args__ = (
        Index('idx_content_hash_user', 'content_hash', 'user_id'),
        Index('idx_filename_user', 'original_filename', 'user_id'),
    )


class AgentDatabase:
    """Database service for managing agent messages and state"""
    
    def __init__(self, database_path: str = settings.database_path):
        # Ensure directory exists
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Store database path for schema operations
        self.database_path = database_path
        
        # Synchronous engine for setup operations
        sync_database_url = f"sqlite:///{database_path}"
        self.sync_engine = create_engine(
            sync_database_url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=3600,
            connect_args={
                "check_same_thread": False,
                "timeout": 30,
            },
            echo=False
        )
        
        # Async engine for database operations
        async_database_url = f"sqlite+aiosqlite:///{database_path}"
        self.async_engine = create_async_engine(
            async_database_url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=False
        )
        
        # Configure WAL mode and other SQLite optimisations
        self._configure_sqlite_optimisations()
        
        # Session factories
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.sync_engine)
        self.AsyncSessionLocal = async_sessionmaker(
            bind=self.async_engine,
            class_=AsyncSession,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False
        )
        
        # Initialize database with schema version checking
        self._initialize_database()
    
    def _configure_sqlite_optimisations(self):
        """Configure SQLite for optimal concurrent performance"""
        with self.sync_engine.connect() as conn:
            from sqlalchemy import text
            # Enable WAL mode for concurrent readers and writers
            conn.execute(text("PRAGMA journal_mode=WAL"))
            
            # Set busy timeout to handle lock contention gracefully
            conn.execute(text("PRAGMA busy_timeout=5000"))  # 5 second timeout
            
            # Enable synchronous mode for durability while maintaining performance
            conn.execute(text("PRAGMA synchronous=NORMAL"))  # Balance safety vs performance
            
            # Set cache size for better performance (negative value = KB)
            conn.execute(text("PRAGMA cache_size=-64000"))  # 64MB cache
            
            # Enable foreign key constraints
            conn.execute(text("PRAGMA foreign_keys=ON"))
            
            # Optimize temp storage
            conn.execute(text("PRAGMA temp_store=MEMORY"))
            
            conn.commit()
            logger.info("SQLite WAL mode and optimisations enabled for agent database")
    
    async def add_message(self, agent_type: AgentType, agent_id: str, role: str, content: Any) -> Optional[int]:
        """Add a message to the appropriate agent messages table"""
        async with self.AsyncSessionLocal() as session:
            if agent_type == "planner":
                message = PlannerMessage(
                    agent_id=agent_id,
                    role=role,
                    content=content
                )
            elif agent_type == "worker":
                message = WorkerMessage(
                    agent_id=agent_id,
                    role=role,
                    content=content
                )
            else:  # router
                # For router, agent_id is the router_id
                # Router should already exist (created via activate_conversation)
                
                message = RouterMessage(
                    router_id=agent_id,
                    role=role,
                    content=content
                )
            
            session.add(message)
            await session.flush()  # Flush to get the ID before commit
            message_id = message.id
            await session.commit()
            return message_id
    
    async def update_router_title(self, router_id: str, title: str) -> None:
        """Update the title of an existing router"""
        async with self.AsyncSessionLocal() as session:
            result = await session.execute(
                select(Router).where(Router.router_id == router_id)
            )
            router_record = result.scalar_one_or_none()
            if router_record:
                router_record.title = title
                router_record.updated_at = datetime.utcnow()
                await session.commit()
    
    async def get_messages(self, agent_type: AgentType, agent_id: str) -> List[Dict[str, Any]]:
        """Retrieve all messages for an agent"""
        async with self.AsyncSessionLocal() as session:
            if agent_type == "planner":
                result = await session.execute(
                    select(PlannerMessage)
                    .where(PlannerMessage.agent_id == agent_id)
                    .order_by(PlannerMessage.created_at)
                )
                messages = result.scalars().all()
            elif agent_type == "worker":
                result = await session.execute(
                    select(WorkerMessage)
                    .where(WorkerMessage.agent_id == agent_id)
                    .order_by(WorkerMessage.created_at)
                )
                messages = result.scalars().all()
            else:  # router
                result = await session.execute(
                    select(RouterMessage)
                    .where(RouterMessage.router_id == agent_id)
                    .order_by(RouterMessage.created_at)
                )
                messages = result.scalars().all()
            
            return [msg.to_message_dict() for msg in messages]
    
    def clear_messages(self, agent_type: AgentType, agent_id: str) -> None:
        """Clear all messages for an agent"""
        with self.SessionLocal() as session:
            if agent_type == "planner":
                session.query(PlannerMessage).filter(
                    PlannerMessage.agent_id == agent_id
                ).delete()
            elif agent_type == "worker":
                session.query(WorkerMessage).filter(
                    WorkerMessage.agent_id == agent_id
                ).delete()
            else:  # router
                session.query(RouterMessage).filter(
                    RouterMessage.router_id == agent_id
                ).delete()
            
            session.commit()
    
    # Agent State Operations
    
    async def create_router(self, router_id: str, status: str, model: str = None, temperature: float = None, title: str = None, preview: str = None) -> None:
        """Create a new router record"""
        async with self.AsyncSessionLocal() as session:
            router = Router(
                router_id=router_id,
                status=status,
                model=model or settings.router_model,
                temperature=temperature or 0.0,
                title=title or "New conversation",
                preview=preview or ""
            )
            session.add(router)
            await session.commit()
    
    def update_router_status(self, router_id: str, status: str) -> None:
        """Update router status"""
        with self.SessionLocal() as session:
            router = session.query(Router).filter(Router.router_id == router_id).first()
            if router:
                router.status = status
                router.updated_at = datetime.utcnow()
                session.commit()
    
    async def get_router(self, router_id: str) -> Optional[Dict[str, Any]]:
        """Get router state by ID"""
        async with self.AsyncSessionLocal() as session:
            result = await session.execute(
                select(Router).where(Router.router_id == router_id)
            )
            router = result.scalar_one_or_none()
            if router:
                return {
                    'router_id': router.router_id,
                    'status': router.status,
                    'model': router.model,
                    'temperature': router.temperature,
                    'agent_metadata': router.agent_metadata,
                    'schema_version': router.schema_version,
                    'created_at': router.created_at,
                    'updated_at': router.updated_at
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
                    'router_id': router.router_id,
                    'title': router.title,
                    'preview': router.preview,
                    'status': router.status,
                    'created_at': router.created_at,
                    'updated_at': router.updated_at
                }
                for router in routers
            ]
    
    async def create_planner(self, planner_id: str, user_question: str, instruction: str = None, 
                      execution_plan: str = None, model: str = None, temperature: float = None,
                      failed_task_limit: int = None, status: str = "planning", planner_name: str = None,
                      next_task: str = None) -> None:
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
                next_task=next_task
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
                    'planner_id': planner.planner_id,
                    'planner_name': planner.planner_name,
                    'user_question': planner.user_question,
                    'instruction': planner.instruction,
                    'execution_plan': planner.execution_plan,
                    'model': planner.model,
                    'temperature': planner.temperature,
                    'failed_task_limit': planner.failed_task_limit,
                    'status': planner.status,
                    'agent_metadata': planner.agent_metadata,
                    'schema_version': planner.schema_version,
                    'user_response': planner.user_response,
                    'created_at': planner.created_at,
                    'updated_at': planner.updated_at
                }
            return None
    
    async def create_worker(self, worker_id: str, planner_id: str, worker_name: str,
                     task_status: str, task_description: str, acceptance_criteria: list,
                     user_request: str, wip_answer_template: str, task_result: str, querying_structured_data: bool,
                     image_keys: list, variable_keys: list, tools: list,
                     input_variable_filepaths: dict, input_image_filepaths: dict,
                     tables: list, filepaths: list) -> None:
        """Create a new worker/task state record"""
        async with self.AsyncSessionLocal() as session:
            worker = Worker(
                worker_id=worker_id,
                worker_name=worker_name,
                planner_id=planner_id,
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
                output_image_filepaths={},    # Empty initially
                current_attempt=0,  # Initialize to 0
                tables=tables,
                filepaths=filepaths
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
                worker.updated_at = datetime.utcnow()
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
                planner.updated_at = datetime.utcnow()
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
                    'worker_id': worker.worker_id,
                    'worker_name': worker.worker_name,
                    'planner_id': worker.planner_id,
                    'task_status': worker.task_status,
                    'task_description': worker.task_description,
                    'acceptance_criteria': worker.acceptance_criteria,
                    'user_request': worker.user_request,
                    'wip_answer_template': worker.wip_answer_template,
                    'task_result': worker.task_result,
                    'querying_structured_data': worker.querying_structured_data,
                    'image_keys': worker.image_keys,
                    'variable_keys': worker.variable_keys,
                    'tools': worker.tools,
                    'input_image_filepaths': worker.input_image_filepaths,
                    'input_variable_filepaths': worker.input_variable_filepaths,
                    'output_image_filepaths': worker.output_image_filepaths,
                    'output_variable_filepaths': worker.output_variable_filepaths,
                    'tables': worker.tables,
                    'agent_metadata': worker.agent_metadata,
                    'schema_version': worker.schema_version,
                    'created_at': worker.created_at,
                    'updated_at': worker.updated_at
                }
            return None
    
    async def get_workers_by_planner(self, planner_id: str) -> List[Dict[str, Any]]:
        """Get all workers for a planner"""
        async with self.AsyncSessionLocal() as session:
            result = await session.execute(
                select(Worker)
                .where(Worker.planner_id == planner_id)
                .order_by(Worker.created_at)
            )
            workers = result.scalars().all()
            return [
                {
                    'worker_id': worker.worker_id,
                    'worker_name': worker.worker_name,
                    'planner_id': worker.planner_id,
                    'task_status': worker.task_status,
                    'task_description': worker.task_description,
                    'acceptance_criteria': worker.acceptance_criteria,
                    'user_request': worker.user_request,
                    'wip_answer_template': worker.wip_answer_template,
                    'task_result': worker.task_result,
                    'querying_structured_data': worker.querying_structured_data,
                    'image_keys': worker.image_keys,
                    'variable_keys': worker.variable_keys,
                    'tools': worker.tools,
                    'input_image_filepaths': worker.input_image_filepaths,
                    'input_variable_filepaths': worker.input_variable_filepaths,
                    'output_image_filepaths': worker.output_image_filepaths,
                    'output_variable_filepaths': worker.output_variable_filepaths,
                    'tables': worker.tables,
                    'filepaths': worker.filepaths,
                    'agent_metadata': worker.agent_metadata,
                    'schema_version': worker.schema_version,
                    'created_at': worker.created_at,
                    'updated_at': worker.updated_at
                }
                for worker in workers
            ]
    
    def link_router_planner(self, router_id: str, planner_id: str, relationship_type: str = "initiated") -> None:
        """Legacy method - create a link between router and planner (V1 compatibility)"""
        with self.SessionLocal() as session:
            # Check if link already exists
            existing_link = session.query(RouterPlannerLink).filter(
                RouterPlannerLink.router_id == router_id,
                RouterPlannerLink.planner_id == planner_id
            ).first()
            
            if not existing_link:
                link = RouterPlannerLink(
                    router_id=router_id,
                    planner_id=planner_id,
                    relationship_type=relationship_type
                )
                session.add(link)
                session.commit()
    
    async def link_message_planner(self, router_id: str, message_id: int, planner_id: str, relationship_type: str = "initiated") -> None:
        """Create a link between router message and planner (V2)"""
        async with self.AsyncSessionLocal() as session:
            # Check if link already exists
            result = await session.execute(
                select(RouterMessagePlannerLink).where(
                    RouterMessagePlannerLink.message_id == message_id,
                    RouterMessagePlannerLink.planner_id == planner_id
                )
            )
            existing_link = result.scalar_one_or_none()
            
            if not existing_link:
                link = RouterMessagePlannerLink(
                    router_id=router_id,
                    message_id=message_id,
                    planner_id=planner_id,
                    relationship_type=relationship_type
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
                        planners.append({
                            'planner_id': planner.planner_id,
                            'planner_name': planner.planner_name,
                            'user_question': planner.user_question,
                            'instruction': planner.instruction,
                            'execution_plan': planner.execution_plan,
                            'model': planner.model,
                            'temperature': planner.temperature,
                            'failed_task_limit': planner.failed_task_limit,
                            'status': planner.status,
                            'agent_metadata': planner.agent_metadata,
                            'schema_version': planner.schema_version,
                            'created_at': planner.created_at,
                            'updated_at': planner.updated_at,
                            'relationship_type': link.relationship_type,
                            'message_id': link.message_id  # V2 addition
                        })
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
                        planners.append({
                            'planner_id': planner.planner_id,
                            'planner_name': planner.planner_name,
                            'user_question': planner.user_question,
                            'instruction': planner.instruction,
                            'execution_plan': planner.execution_plan,
                            'model': planner.model,
                            'temperature': planner.temperature,
                            'failed_task_limit': planner.failed_task_limit,
                            'status': planner.status,
                            'agent_metadata': planner.agent_metadata,
                            'schema_version': planner.schema_version,
                            'created_at': planner.created_at,
                            'updated_at': planner.updated_at,
                            'relationship_type': link.relationship_type,
                            'message_id': None  # V1 compatibility
                        })
                return planners
    
    async def get_planner_by_message(self, message_id: int) -> Optional[Dict[str, Any]]:
        """Get planner associated with a specific message (V2)"""
        with self.SessionLocal() as session:
            link = session.query(RouterMessagePlannerLink).filter(
                RouterMessagePlannerLink.message_id == message_id
            ).first()
            
            if not link:
                return None
                
            planner = session.query(Planner).filter(
                Planner.planner_id == link.planner_id
            ).first()
            
            if planner:
                return {
                    'planner_id': planner.planner_id,
                    'planner_name': planner.planner_name,
                    'user_question': planner.user_question,
                    'instruction': planner.instruction,
                    'execution_plan': planner.execution_plan,
                    'model': planner.model,
                    'temperature': planner.temperature,
                    'failed_task_limit': planner.failed_task_limit,
                    'status': planner.status,
                    'agent_metadata': planner.agent_metadata,
                    'schema_version': planner.schema_version,
                    'created_at': planner.created_at,
                    'updated_at': planner.updated_at,
                    'relationship_type': link.relationship_type,
                    'message_id': link.message_id,
                    'router_id': link.router_id
                }
            return None
    
    def get_message_by_planner(self, planner_id: str) -> Optional[int]:
        """Get message ID associated with a specific planner (V2)"""
        with self.SessionLocal() as session:
            link = session.query(RouterMessagePlannerLink).filter(
                RouterMessagePlannerLink.planner_id == planner_id
            ).first()
            
            return link.message_id if link else None
    
    # Database Schema Management
    
    def _initialize_database(self) -> None:
        """Initialize database with schema version checking and migration"""
        # Create tables if they don't exist
        Base.metadata.create_all(bind=self.sync_engine)
        
        # Check schema version and migrate if needed
        if settings.database_auto_migrate:
            self._check_and_migrate_schema()
        else:
            logger.info(f"Database initialized. Auto-migration disabled.")
    
    def _check_and_migrate_schema(self) -> None:
        """Check current schema version and perform migrations if needed"""
        try:
            current_version = self._get_database_schema_version()
            target_version = settings.database_schema_version
            
            if current_version == target_version:
                logger.info(f"Database schema is up to date (version {current_version})")
                return
            
            if current_version < target_version:
                logger.info(f"Migrating database schema from version {current_version} to {target_version}")
                self._migrate_schema(current_version, target_version)
            else:
                logger.warning(f"Database schema version {current_version} is newer than expected {target_version}")
                
        except Exception as e:
            logger.error(f"Schema version check failed: {e}")
            # Continue with current schema for now
    
    def _get_database_schema_version(self) -> int:
        """Get the current database schema version"""
        with self.SessionLocal() as session:
            try:
                # Check if we have any versioned tables by looking for schema_version column
                result = session.execute(
                    "SELECT schema_version FROM routers LIMIT 1"
                ).fetchone()
                return 1  # If routers table exists with schema_version, we're at v1
            except Exception:
                # If routers table doesn't exist or doesn't have schema_version, 
                # check if we have old message tables
                try:
                    session.execute("SELECT 1 FROM routers LIMIT 1")
                    return 1  # We have message tables, assume v1
                except Exception:
                    return 0  # Fresh database
    
    def _migrate_schema(self, from_version: int, to_version: int) -> None:
        """Perform schema migration from one version to another"""
        logger.info(f"Performing schema migration from v{from_version} to v{to_version}")
        
        if from_version == 0 and to_version >= 1:
            # Fresh install - tables created by Base.metadata.create_all()
            logger.info("Schema migration completed: Fresh database initialized")
        else:
            logger.warning(f"Migration from v{from_version} to v{to_version} not implemented")
    
    
    def get_schema_info(self) -> Dict[str, Any]:
        """Get database schema information for debugging"""
        return {
            'database_path': self.database_path,
            'current_schema_version': self._get_database_schema_version(),
            'target_schema_version': settings.database_schema_version,
            'auto_migrate_enabled': settings.database_auto_migrate
        }
    
    # File Metadata Operations
    
    def create_file_metadata(self, file_id: str, content_hash: str, original_filename: str, 
                           file_path: str, file_size: int, mime_type: str, user_id: str) -> None:
        """Create a new file metadata record"""
        with self.SessionLocal() as session:
            file_metadata = FileMetadata(
                file_id=file_id,
                content_hash=content_hash,
                original_filename=original_filename,
                file_path=file_path,
                file_size=file_size,
                mime_type=mime_type,
                user_id=user_id
            )
            session.add(file_metadata)
            session.commit()
    
    def get_file_by_hash(self, content_hash: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Find existing file by content hash for a specific user"""
        with self.SessionLocal() as session:
            file_record = session.query(FileMetadata).filter(
                FileMetadata.content_hash == content_hash,
                FileMetadata.user_id == user_id
            ).first()
            
            if file_record:
                return {
                    'file_id': file_record.file_id,
                    'content_hash': file_record.content_hash,
                    'original_filename': file_record.original_filename,
                    'file_path': file_record.file_path,
                    'file_size': file_record.file_size,
                    'mime_type': file_record.mime_type,
                    'upload_timestamp': file_record.upload_timestamp,
                    'user_id': file_record.user_id,
                    'reference_count': file_record.reference_count
                }
            return None
    
    def get_file_by_id(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Get file metadata by file ID"""
        with self.SessionLocal() as session:
            file_record = session.query(FileMetadata).filter(
                FileMetadata.file_id == file_id
            ).first()
            
            if file_record:
                return {
                    'file_id': file_record.file_id,
                    'content_hash': file_record.content_hash,
                    'original_filename': file_record.original_filename,
                    'file_path': file_record.file_path,
                    'file_size': file_record.file_size,
                    'mime_type': file_record.mime_type,
                    'upload_timestamp': file_record.upload_timestamp,
                    'user_id': file_record.user_id,
                    'reference_count': file_record.reference_count
                }
            return None
    
    def increment_file_reference(self, file_id: str) -> None:
        """Increment reference count for a file"""
        with self.SessionLocal() as session:
            file_record = session.query(FileMetadata).filter(
                FileMetadata.file_id == file_id
            ).first()
            if file_record:
                file_record.reference_count += 1
                session.commit()
    
    def get_files_by_filename(self, filename: str, user_id: str) -> List[Dict[str, Any]]:
        """Get all files with the same original filename for a user"""
        with self.SessionLocal() as session:
            file_records = session.query(FileMetadata).filter(
                FileMetadata.original_filename == filename,
                FileMetadata.user_id == user_id
            ).order_by(FileMetadata.upload_timestamp.desc()).all()
            
            return [
                {
                    'file_id': record.file_id,
                    'content_hash': record.content_hash,
                    'original_filename': record.original_filename,
                    'file_path': record.file_path,
                    'file_size': record.file_size,
                    'mime_type': record.mime_type,
                    'upload_timestamp': record.upload_timestamp,
                    'user_id': record.user_id,
                    'reference_count': record.reference_count
                }
                for record in file_records
            ]

    # Task Queue Management Methods
    
    async def enqueue_task(self, task_id: str, entity_type: str, entity_id: str, 
                    function_name: str, payload: dict = None) -> bool:
        """Add a task to the queue"""
        async with self.AsyncSessionLocal() as session:
            # Create new task
            task = TaskQueue(
                task_id=task_id,
                entity_type=entity_type,
                entity_id=entity_id,
                function_name=function_name,
                payload=payload
            )
            
            session.add(task)
            await session.commit()
            logger.info(f"Enqueued task {task_id} for {entity_type} {entity_id}")
            return True
    
    async def get_pending_tasks(self) -> List[Dict[str, Any]]:
        """Get all pending tasks ordered by creation time"""
        with self.SessionLocal() as session:
            tasks = session.query(TaskQueue).filter(
                TaskQueue.status == 'PENDING'
            ).order_by(TaskQueue.created_at).all()
            
            return [
                {
                    'task_id': task.task_id,
                    'entity_type': task.entity_type,
                    'entity_id': task.entity_id,
                    'function_name': task.function_name,
                    'created_at': task.created_at,
                    'payload': task.payload
                }
                for task in tasks
            ]
    
    async def update_task_status(self, task_id: str, status: str, error_message: str = None) -> bool:
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
            if status == 'IN_PROGRESS':
                task.started_at = datetime.utcnow()
            elif status in ['COMPLETED', 'FAILED']:
                task.completed_at = datetime.utcnow()
                if status == 'FAILED':
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
    
    async def get_pending_task_for_entity(self, entity_id: str, function_name: str) -> Optional[Dict[str, Any]]:
        """Check if a specific function is already queued for an entity"""
        async with self.AsyncSessionLocal() as session:
            result = await session.execute(
                select(TaskQueue).where(
                    TaskQueue.entity_id == entity_id,
                    TaskQueue.function_name == function_name,
                    TaskQueue.status.in_(['PENDING', 'IN_PROGRESS'])
                )
            )
            task = result.scalar_one_or_none()
            
            if task:
                return {
                    'task_id': task.task_id,
                    'function_name': task.function_name,
                    'status': task.status
                }
            return None
    
    def clear_task_queue(self) -> int:
        """Clear all tasks from the task queue on startup and return count of cleared tasks"""
        with self.SessionLocal() as session:
            # Get count of tasks to be cleared for logging
            task_count = session.query(TaskQueue).count()
            
            # Delete all tasks in the queue
            session.query(TaskQueue).delete()
            session.commit()
            
            logger.info(f"Cleared {task_count} tasks from task queue on startup")
            return task_count