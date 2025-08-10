from sqlalchemy import Column, String, Text, DateTime, Integer, JSON, create_engine, ForeignKey, Float, Boolean, UniqueConstraint, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
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


class Conversation(Base):
    __tablename__ = 'conversations'
    
    id = Column(String(32), primary_key=True)
    title = Column(String(255), nullable=False, default="New Conversation")
    preview = Column(String(255), nullable=False, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RouterMessage(Base):
    __tablename__ = 'router_messages'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(String(32), ForeignKey('conversations.id'), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # 'user', 'assistant'
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    def to_message_dict(self) -> Dict[str, Any]:
        """Convert database record back to message format"""
        return {
            "role": self.role,
            "content": self.content
        }


# Agent State Tables

class Router(Base):
    __tablename__ = 'routers'
    
    router_id = Column(String(32), primary_key=True)  # UUID hex string (conversation_id)
    status = Column(String(50), nullable=False)  # active, completed, failed, archived
    model = Column(String(100))  # LLM model used
    temperature = Column(Float)  # LLM temperature setting
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
    status = Column(String(50), nullable=False)  # planning, executing, completed, failed
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
    task_description = Column(Text)  # Detailed task description
    acceptance_criteria = Column(JSON)  # List of success criteria
    task_context = Column(JSON)  # TaskContext pydantic model as JSON
    task_result = Column(Text)  # Execution outcome
    querying_structured_data = Column(Boolean, default=False)  # Whether task queries data files
    image_keys = Column(JSON)  # List of relevant image identifiers
    variable_keys = Column(JSON)  # List of relevant variable identifiers
    tools = Column(JSON)  # List of required tools
    input_images = Column(JSON)  # Input image data
    input_variables = Column(JSON)  # Input variables
    output_images = Column(JSON)  # Output image data
    output_variables = Column(JSON)  # Output variables
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
    planner_id = Column(String(32), ForeignKey('planners.planner_id'), nullable=False)
    relationship_type = Column(String(50), nullable=False)  # initiated, continued, forked
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint('message_id', 'planner_id'),  # One planner per message
        Index('idx_router_message', 'router_id', 'message_id'),  # Fast lookups
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
        
        database_url = f"sqlite:///{database_path}"
        self.engine = create_engine(database_url)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        
        # Initialize database with schema version checking
        self._initialize_database()
    
    def add_message(self, agent_type: AgentType, agent_id: str, role: str, content: Any) -> Optional[int]:
        """Add a message to the appropriate agent messages table"""
        with self.SessionLocal() as session:
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
                # For router, agent_id is the conversation_id
                # Conversation should already exist (created via activate_conversation)
                
                message = RouterMessage(
                    conversation_id=agent_id,
                    role=role,
                    content=content
                )
            
            session.add(message)
            session.flush()  # Flush to get the ID before commit
            message_id = message.id
            session.commit()
            return message_id
    
    def create_conversation_with_details(self, conversation_id: str, title: str, preview: str) -> None:
        """Create a conversation with title and preview"""
        with self.SessionLocal() as session:
            conversation = Conversation(
                id=conversation_id,
                title=title,
                preview=preview
            )
            session.add(conversation)
            session.commit()
    
    def update_conversation_title(self, conversation_id: str, title: str) -> None:
        """Update the title of an existing conversation"""
        with self.SessionLocal() as session:
            conversation = session.query(Conversation).filter(
                Conversation.id == conversation_id
            ).first()
            if conversation:
                conversation.title = title
                conversation.updated_at = datetime.utcnow()
                session.commit()
    
    def get_messages(self, agent_type: AgentType, agent_id: str) -> List[Dict[str, Any]]:
        """Retrieve all messages for an agent"""
        with self.SessionLocal() as session:
            if agent_type == "planner":
                messages = session.query(PlannerMessage).filter(
                    PlannerMessage.agent_id == agent_id
                ).order_by(PlannerMessage.created_at).all()
            elif agent_type == "worker":
                messages = session.query(WorkerMessage).filter(
                    WorkerMessage.agent_id == agent_id
                ).order_by(WorkerMessage.created_at).all()
            else:  # router
                messages = session.query(RouterMessage).filter(
                    RouterMessage.conversation_id == agent_id
                ).order_by(RouterMessage.created_at).all()
            
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
                    RouterMessage.conversation_id == agent_id
                ).delete()
            
            session.commit()
    
    # Agent State Operations
    
    def create_router(self, router_id: str, status: str, model: str = None, temperature: float = None) -> None:
        """Create a new router state record"""
        with self.SessionLocal() as session:
            router = Router(
                router_id=router_id,
                status=status,
                model=model,
                temperature=temperature
            )
            session.add(router)
            session.commit()
    
    def update_router_status(self, router_id: str, status: str) -> None:
        """Update router status"""
        with self.SessionLocal() as session:
            router = session.query(Router).filter(Router.router_id == router_id).first()
            if router:
                router.status = status
                router.updated_at = datetime.utcnow()
                session.commit()
    
    def get_router(self, router_id: str) -> Optional[Dict[str, Any]]:
        """Get router state by ID"""
        with self.SessionLocal() as session:
            router = session.query(Router).filter(Router.router_id == router_id).first()
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
    
    def create_planner(self, planner_id: str, user_question: str, instruction: str = None, 
                      execution_plan: str = None, model: str = None, temperature: float = None,
                      failed_task_limit: int = None, status: str = "planning", planner_name: str = None) -> None:
        """Create a new planner state record"""
        with self.SessionLocal() as session:
            planner = Planner(
                planner_id=planner_id,
                planner_name=planner_name,
                user_question=user_question,
                instruction=instruction,
                execution_plan=execution_plan,
                model=model,
                temperature=temperature,
                failed_task_limit=failed_task_limit,
                status=status
            )
            session.add(planner)
            session.commit()
    
    def update_planner_status(self, planner_id: str, status: str) -> None:
        """Update planner status"""
        with self.SessionLocal() as session:
            planner = session.query(Planner).filter(Planner.planner_id == planner_id).first()
            if planner:
                planner.status = status
                planner.updated_at = datetime.utcnow()
                session.commit()
    
    def update_planner_execution_plan(self, planner_id: str, execution_plan: str) -> None:
        """Update planner execution plan"""
        with self.SessionLocal() as session:
            planner = session.query(Planner).filter(Planner.planner_id == planner_id).first()
            if planner:
                planner.execution_plan = execution_plan
                planner.updated_at = datetime.utcnow()
                session.commit()
    
    def get_planner(self, planner_id: str) -> Optional[Dict[str, Any]]:
        """Get planner state by ID"""
        with self.SessionLocal() as session:
            planner = session.query(Planner).filter(Planner.planner_id == planner_id).first()
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
                    'updated_at': planner.updated_at
                }
            return None
    
    def create_worker(self, worker_id: str, planner_id: str, task_data, worker_name: str = None) -> None:
        """Create a new worker/task state record"""
        with self.SessionLocal() as session:
            worker = Worker(
                worker_id=worker_id,
                worker_name=worker_name,
                planner_id=planner_id,
                task_status=task_data.task_status,
                task_description=task_data.task_description,
                acceptance_criteria=task_data.acceptance_criteria,
                task_context=task_data.task_context.model_dump(),
                task_result=task_data.task_result,
                querying_structured_data=task_data.querying_structured_data,
                image_keys=task_data.image_keys,
                variable_keys=task_data.variable_keys,
                tools=task_data.tools,
                input_images=task_data.input_images,
                input_variables=task_data.input_variables,
                output_images=task_data.output_images,
                output_variables=task_data.output_variables,
                tables=[table.model_dump() for table in task_data.tables],
                filepaths=task_data.filepaths
            )
            session.add(worker)
            session.commit()
    
    def update_worker_status(self, worker_id: str, status: str, result: str = None) -> None:
        """Update worker task status and result"""
        with self.SessionLocal() as session:
            worker = session.query(Worker).filter(Worker.worker_id == worker_id).first()
            if worker:
                worker.task_status = status
                if result is not None:
                    worker.task_result = result
                worker.updated_at = datetime.utcnow()
                session.commit()
    
    def update_worker_outputs(self, worker_id: str, output_images: Dict = None, 
                             output_variables: Dict = None) -> None:
        """Update worker output data"""
        with self.SessionLocal() as session:
            worker = session.query(Worker).filter(Worker.worker_id == worker_id).first()
            if worker:
                if output_images is not None:
                    worker.output_images = output_images
                if output_variables is not None:
                    worker.output_variables = output_variables
                worker.updated_at = datetime.utcnow()
                session.commit()
    
    def get_worker(self, worker_id: str) -> Optional[Dict[str, Any]]:
        """Get worker state by ID"""
        with self.SessionLocal() as session:
            worker = session.query(Worker).filter(Worker.worker_id == worker_id).first()
            if worker:
                return {
                    'worker_id': worker.worker_id,
                    'worker_name': worker.worker_name,
                    'planner_id': worker.planner_id,
                    'task_status': worker.task_status,
                    'task_description': worker.task_description,
                    'acceptance_criteria': worker.acceptance_criteria,
                    'task_context': worker.task_context,
                    'task_result': worker.task_result,
                    'querying_structured_data': worker.querying_structured_data,
                    'image_keys': worker.image_keys,
                    'variable_keys': worker.variable_keys,
                    'tools': worker.tools,
                    'input_images': worker.input_images,
                    'input_variables': worker.input_variables,
                    'output_images': worker.output_images,
                    'output_variables': worker.output_variables,
                    'tables': worker.tables,
                    'agent_metadata': worker.agent_metadata,
                    'schema_version': worker.schema_version,
                    'created_at': worker.created_at,
                    'updated_at': worker.updated_at
                }
            return None
    
    def get_workers_by_planner(self, planner_id: str) -> List[Dict[str, Any]]:
        """Get all workers for a planner"""
        with self.SessionLocal() as session:
            workers = session.query(Worker).filter(Worker.planner_id == planner_id).order_by(Worker.created_at).all()
            return [
                {
                    'worker_id': worker.worker_id,
                    'worker_name': worker.worker_name,
                    'planner_id': worker.planner_id,
                    'task_status': worker.task_status,
                    'task_description': worker.task_description,
                    'acceptance_criteria': worker.acceptance_criteria,
                    'task_context': worker.task_context,
                    'task_result': worker.task_result,
                    'querying_structured_data': worker.querying_structured_data,
                    'image_keys': worker.image_keys,
                    'variable_keys': worker.variable_keys,
                    'tools': worker.tools,
                    'input_images': worker.input_images,
                    'input_variables': worker.input_variables,
                    'output_images': worker.output_images,
                    'output_variables': worker.output_variables,
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
    
    def link_message_planner(self, router_id: str, message_id: int, planner_id: str, relationship_type: str = "initiated") -> None:
        """Create a link between router message and planner (V2)"""
        with self.SessionLocal() as session:
            # Check if link already exists
            existing_link = session.query(RouterMessagePlannerLink).filter(
                RouterMessagePlannerLink.message_id == message_id,
                RouterMessagePlannerLink.planner_id == planner_id
            ).first()
            
            if not existing_link:
                link = RouterMessagePlannerLink(
                    router_id=router_id,
                    message_id=message_id,
                    planner_id=planner_id,
                    relationship_type=relationship_type
                )
                session.add(link)
                session.commit()
    
    def get_planners_by_router(self, router_id: str) -> List[Dict[str, Any]]:
        """Get all planners linked to a router (legacy V1 method)"""
        with self.SessionLocal() as session:
            # Try V2 first (RouterMessagePlannerLink)
            v2_links = session.query(RouterMessagePlannerLink).filter(
                RouterMessagePlannerLink.router_id == router_id
            ).order_by(RouterMessagePlannerLink.created_at).all()
            
            if v2_links:
                # V2 data available - use message-specific links
                planners = []
                for link in v2_links:
                    planner = session.query(Planner).filter(
                        Planner.planner_id == link.planner_id
                    ).first()
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
                v1_links = session.query(RouterPlannerLink).filter(
                    RouterPlannerLink.router_id == router_id
                ).order_by(RouterPlannerLink.created_at).all()
                
                planners = []
                for link in v1_links:
                    planner = session.query(Planner).filter(
                        Planner.planner_id == link.planner_id
                    ).first()
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
    
    def get_planner_by_message(self, message_id: int) -> Optional[Dict[str, Any]]:
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
    
    # Database Schema Management
    
    def _initialize_database(self) -> None:
        """Initialize database with schema version checking and migration"""
        # Create tables if they don't exist
        Base.metadata.create_all(bind=self.engine)
        
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
                    session.execute("SELECT 1 FROM conversations LIMIT 1")
                    return 1  # We have message tables, assume v1
                except Exception:
                    return 0  # Fresh database
    
    def _migrate_schema(self, from_version: int, to_version: int) -> None:
        """Perform schema migration from one version to another"""
        logger.info(f"Performing schema migration from v{from_version} to v{to_version}")
        
        if from_version == 0 and to_version >= 1:
            # Fresh install - tables created by Base.metadata.create_all()
            logger.info("Schema migration completed: Fresh database initialized")
        elif from_version == 1 and to_version == 2:
            # V1 -> V2: Add RouterMessagePlannerLink table and migrate data
            self._migrate_v1_to_v2()
            logger.info("Schema migration completed: V1 -> V2 migration successful")
        else:
            logger.warning(f"Migration from v{from_version} to v{to_version} not implemented")
    
    def _migrate_v1_to_v2(self) -> None:
        """Migrate from Schema V1 to V2: RouterPlannerLink -> RouterMessagePlannerLink"""
        with self.SessionLocal() as session:
            try:
                # Create the new table (RouterMessagePlannerLink)
                # Note: Base.metadata.create_all() should have already created it
                
                # Get all existing RouterPlannerLink records
                old_links = session.query(RouterPlannerLink).all()
                logger.info(f"Found {len(old_links)} existing router-planner links to migrate")
                
                # For each old link, we need to find the most recent user message 
                # that would have triggered this planner activation
                migrated_count = 0
                for old_link in old_links:
                    # Find the most recent user message in this conversation before the planner was created
                    recent_user_message = session.query(RouterMessage).filter(
                        RouterMessage.conversation_id == old_link.router_id,
                        RouterMessage.role == 'user',
                        RouterMessage.created_at <= old_link.created_at
                    ).order_by(RouterMessage.created_at.desc()).first()
                    
                    if recent_user_message:
                        # Create new link with message association
                        new_link = RouterMessagePlannerLink(
                            router_id=old_link.router_id,
                            message_id=recent_user_message.id,
                            planner_id=old_link.planner_id,
                            relationship_type=old_link.relationship_type,
                            created_at=old_link.created_at
                        )
                        session.add(new_link)
                        migrated_count += 1
                    else:
                        logger.warning(f"Could not find user message for planner {old_link.planner_id} in router {old_link.router_id}")
                
                # Commit the new links
                session.commit()
                logger.info(f"Successfully migrated {migrated_count} router-planner links to message-specific links")
                
                # Note: Keep old table for potential rollback, don't drop yet
                
            except Exception as e:
                session.rollback()
                logger.error(f"V1->V2 migration failed: {e}")
                raise
    
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