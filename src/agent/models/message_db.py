from sqlalchemy import Column, String, Text, DateTime, Integer, JSON, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import json
from typing import Dict, List, Any, Optional, Literal
from pathlib import Path

Base = declarative_base()

AgentType = Literal["planner", "worker"]


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


class MessageDatabase:
    """Database service for managing agent messages"""
    
    def __init__(self, database_path: str = "/Users/bryanye/agent/db/agent_messages.db"):
        # Ensure directory exists
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        
        database_url = f"sqlite:///{database_path}"
        self.engine = create_engine(database_url)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        
        # Create tables if they don't exist
        Base.metadata.create_all(bind=self.engine)
    
    def add_message(self, agent_type: AgentType, agent_id: str, role: str, content: Any) -> None:
        """Add a message to the appropriate agent messages table"""
        with self.SessionLocal() as session:
            if agent_type == "planner":
                message = PlannerMessage(
                    agent_id=agent_id,
                    role=role,
                    content=content
                )
            else:  # worker
                message = WorkerMessage(
                    agent_id=agent_id,
                    role=role,
                    content=content
                )
            
            session.add(message)
            session.commit()
    
    def get_messages(self, agent_type: AgentType, agent_id: str) -> List[Dict[str, Any]]:
        """Retrieve all messages for an agent"""
        with self.SessionLocal() as session:
            if agent_type == "planner":
                messages = session.query(PlannerMessage).filter(
                    PlannerMessage.agent_id == agent_id
                ).order_by(PlannerMessage.created_at).all()
            else:  # worker
                messages = session.query(WorkerMessage).filter(
                    WorkerMessage.agent_id == agent_id
                ).order_by(WorkerMessage.created_at).all()
            
            return [msg.to_message_dict() for msg in messages]
    
    def clear_messages(self, agent_type: AgentType, agent_id: str) -> None:
        """Clear all messages for an agent"""
        with self.SessionLocal() as session:
            if agent_type == "planner":
                session.query(PlannerMessage).filter(
                    PlannerMessage.agent_id == agent_id
                ).delete()
            else:  # worker
                session.query(WorkerMessage).filter(
                    WorkerMessage.agent_id == agent_id
                ).delete()
            
            session.commit()