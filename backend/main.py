import asyncio
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import uvicorn
from dotenv import load_dotenv
from fastapi import (
    FastAPI,
    WebSocket,
    WebSocketDisconnect,
    HTTPException,
    UploadFile,
    File,
    Form,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.agent.core.router import RouterAgent
from src.agent.models.agent_database import AgentDatabase
from src.agent.utils.file_utils import calculate_file_hash, generate_unique_filename, sanitise_filename

# Load environment variables
# Load .env first (shared config), then .env.local (secrets) to override
load_dotenv()  # Loads .env
load_dotenv(".env.local")  # Loads .env.local and overrides any duplicates

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Agent System API", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store active connections
active_connections = {}  # conversation_id -> RouterAgent
user_connections = {}  # websocket -> user_session

# Initialize database
db = AgentDatabase()


# Pydantic models for API
class ChatMessage(BaseModel):
    message: str
    conversation_id: str
    files: Optional[List[str]] = []
    model: str = "gpt-4"
    temperature: float = 0.7


class StatusUpdate(BaseModel):
    status: str
    message: str


@app.websocket("/chat")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for chat communication"""
    await websocket.accept()
    logger.info("WebSocket connection established")

    # Store connection with a session ID
    import uuid

    session_id = uuid.uuid4().hex
    user_connections[websocket] = {
        "session_id": session_id,
        "current_conversation": None,
    }

    try:
        # Send initial connection confirmation
        await websocket.send_json(
            {"type": "connection_established", "session_id": session_id}
        )

        while True:
            # Receive message from frontend
            data = await websocket.receive_json()
            await handle_websocket_message(websocket, data)

    except WebSocketDisconnect:
        # Clean up connection
        if websocket in user_connections:
            session_info = user_connections[websocket]
            del user_connections[websocket]
            logger.info(f"Client session {session_info['session_id']} disconnected")


async def handle_websocket_message(websocket: WebSocket, data: dict):
    """Handle incoming WebSocket messages with conversation routing"""
    try:
        message_type = data.get("type", "message")

        if message_type == "load_conversation":
            # Load conversation history
            conversation_id = data.get("conversation_id")
            if conversation_id:
                router = RouterAgent(conversation_id=conversation_id)
                # Update current conversation for this session
                user_connections[websocket]["current_conversation"] = conversation_id

                # Send conversation history
                await websocket.send_json(
                    {
                        "type": "conversation_history",
                        "conversation_id": conversation_id,
                        "messages": router.messages,
                    }
                )

        elif message_type == "message":
            # Regular chat message
            conversation_id = data.get("conversation_id")
            if not conversation_id:
                await websocket.send_json(
                    {"type": "error", "message": "conversation_id is required"}
                )
                return

            # Get or create router for this conversation
            if conversation_id not in active_connections:
                router = RouterAgent(conversation_id=conversation_id)
                await router.connect_websocket(websocket)
                active_connections[conversation_id] = router
                
                # For new conversations, use activate_conversation
                user_message = data.get("message", "")
                files = data.get("files", [])
                await router.activate_conversation(user_message, files)
            else:
                router = active_connections[conversation_id]
                # Update websocket connection for existing router
                router.websocket = websocket

                # Update current conversation for this session
                user_connections[websocket]["current_conversation"] = conversation_id

                # Handle the message for existing conversations
                await router.handle_message(data)

    except Exception as e:
        logger.error(f"Error handling WebSocket message: {str(e)}")
        await websocket.send_json(
            {"type": "error", "message": f"Error processing message: {str(e)}"}
        )


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """Handle file uploads with duplicate detection"""
    try:
        # TODO: Replace 'bryan000' with actual username from user management system
        user_id = "bryan000"
        
        # Read file content
        content = await file.read()
        file_size = len(content)
        
        # Calculate content hash
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(content)
            temp_file_path = temp_file.name
        
        try:
            content_hash = calculate_file_hash(temp_file_path)
        finally:
            # Clean up temp file
            Path(temp_file_path).unlink(missing_ok=True)
        
        # Check for duplicate content
        existing_file = db.get_file_by_hash(content_hash, user_id)
        
        if existing_file:
            # Duplicate found - return duplicate info with options
            return {
                "duplicate_found": True,
                "existing_file": {
                    "file_id": existing_file["file_id"],
                    "original_filename": existing_file["original_filename"],
                    "file_size": existing_file["file_size"],
                    "upload_timestamp": existing_file["upload_timestamp"].isoformat()
                },
                "new_filename": file.filename,
                "options": ["use_existing", "overwrite_existing", "save_as_new_copy", "cancel"]
            }
        
        # No duplicate - save file normally
        upload_dir = Path("/app/files/uploads") / user_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        file_id = uuid.uuid4().hex
        sanitised_filename = sanitise_filename(file.filename)
        
        # Check if sanitised filename already exists and make it unique if needed
        existing_files = [f.name for f in upload_dir.iterdir() if f.is_file()]
        if sanitised_filename in existing_files:
            sanitised_filename = generate_unique_filename(sanitised_filename, existing_files)
        
        file_path = upload_dir / sanitised_filename
        
        with open(file_path, "wb") as buffer:
            buffer.write(content)
        
        # Store file metadata
        db.create_file_metadata(
            file_id=file_id,
            content_hash=content_hash,
            original_filename=sanitised_filename,
            file_path=str(file_path),
            file_size=file_size,
            mime_type=file.content_type,
            user_id=user_id
        )
        
        return {
            "duplicate_found": False,
            "file_id": file_id,
            "filename": sanitised_filename,
            "path": str(file_path),
            "size": file_size
        }

    except Exception as e:
        logger.error(f"Error uploading file: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/upload/resolve-duplicate")
async def resolve_duplicate(
    action: str = Form(...),
    existing_file_id: str = Form(...),
    new_filename: str = Form(...),
    file: UploadFile = File(...)
):
    """Handle duplicate resolution based on user choice"""
    try:
        # TODO: Replace 'bryan000' with actual username from user management system
        user_id = "bryan000"
        
        if action == "cancel":
            return {
                "action": "cancel",
                "files": []  # Empty files array for message handling
            }
        
        existing_file = db.get_file_by_id(existing_file_id)
        if not existing_file:
            raise HTTPException(status_code=404, detail="Existing file not found")
        
        if action == "use_existing":
            # Increment reference count and return existing file
            db.increment_file_reference(existing_file_id)
            return {
                "action": "use_existing",
                "file_id": existing_file["file_id"],
                "filename": existing_file["original_filename"],
                "path": existing_file["file_path"],
                "size": existing_file["file_size"],
                "files": [existing_file["file_path"]]  # For message handling
            }
        
        elif action == "overwrite_existing":
            # Read new file content
            content = await file.read()
            
            # Overwrite existing file
            with open(existing_file["file_path"], "wb") as buffer:
                buffer.write(content)
            
            return {
                "action": "overwrite_existing", 
                "file_id": existing_file["file_id"],
                "filename": new_filename,
                "path": existing_file["file_path"],
                "size": len(content),
                "files": [existing_file["file_path"]]  # For message handling
            }
        
        elif action == "save_as_new_copy":
            # Read new file content
            content = await file.read()
            
            # Create new file with unique filename
            upload_dir = Path("/app/files/uploads") / user_id
            upload_dir.mkdir(parents=True, exist_ok=True)
            
            # Sanitise the new filename
            sanitised_filename = sanitise_filename(new_filename)
            
            # Get list of existing filenames in the directory
            existing_files = [f.name for f in upload_dir.iterdir() if f.is_file()]
            
            unique_filename = generate_unique_filename(sanitised_filename, existing_files)
            file_id = uuid.uuid4().hex
            file_path = upload_dir / unique_filename
            
            with open(file_path, "wb") as buffer:
                buffer.write(content)
            
            # Calculate content hash for new file
            content_hash = calculate_file_hash(file_path)
            
            # Store file metadata with unique filename
            db.create_file_metadata(
                file_id=file_id,
                content_hash=content_hash,
                original_filename=unique_filename,
                file_path=str(file_path),
                file_size=len(content),
                mime_type=file.content_type,
                user_id=user_id
            )
            
            return {
                "action": "save_as_new_copy",
                "file_id": file_id,
                "filename": unique_filename,
                "path": str(file_path),
                "size": len(content),
                "files": [str(file_path)]  # For message handling
            }
        
        else:
            raise HTTPException(status_code=400, detail="Invalid action")
    
    except Exception as e:
        logger.error(f"Error resolving duplicate: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "agent-system"}


@app.get("/conversations")
async def get_conversations():
    """Get all conversations"""
    try:
        from src.agent.models.agent_database import (
            AgentDatabase,
            Conversation,
            RouterMessage,
        )

        db = AgentDatabase()
        with db.SessionLocal() as session:
            conversations = (
                session.query(Conversation)
                .order_by(Conversation.updated_at.desc())
                .all()
            )

            result = []
            for conv in conversations:
                result.append(
                    {
                        "id": conv.id,
                        "title": conv.title,
                        "preview": conv.preview,
                        "timestamp": conv.updated_at.isoformat(),
                    }
                )

        return result
    except Exception as e:
        logger.error(f"Error fetching conversations: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    """Get conversation history"""
    try:
        router = RouterAgent(conversation_id=conversation_id)
        return {"conversation_id": conversation_id, "messages": router.messages}
    except Exception as e:
        logger.error(f"Error fetching conversation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/conversations")
async def create_conversation():
    """Create a new conversation"""
    try:
        import uuid

        conversation_id = uuid.uuid4().hex
        return {"conversation_id": conversation_id}
    except Exception as e:
        logger.error(f"Error creating conversation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/conversations/{conversation_id}/activate")
async def activate_conversation(conversation_id: str, request: dict):
    """Activate a conversation with the first user message"""
    try:
        user_message = request.get("message", "")
        files = request.get("files", [])

        if not user_message:
            raise HTTPException(status_code=400, detail="Message is required")

        # Create or get existing router
        router = RouterAgent(conversation_id=conversation_id)

        # Activate the conversation (this will add system message and process user message)
        await router.activate_conversation(user_message, files)

        # Store the router for WebSocket connections
        active_connections[conversation_id] = router

        # Get the conversation messages to return the assistant's response
        messages = router.messages
        assistant_response = (
            messages[-1]["content"]
            if messages and messages[-1]["role"] == "assistant"
            else ""
        )

        return {
            "status": "activated",
            "conversation_id": conversation_id,
            "response": assistant_response,
        }
    except Exception as e:
        logger.error(f"Error activating conversation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/conversations/{conversation_id}/update-title")
async def update_conversation_title(conversation_id: str):
    """Update conversation title using LLM (async, fire-and-forget)"""
    try:
        # Create RouterAgent and call method directly
        router = RouterAgent(conversation_id=conversation_id)
        asyncio.create_task(router.generate_and_update_title())

        return {"status": "started"}
    except Exception as e:
        logger.error(f"Error starting title update: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/messages/{message_id}/planner-info")
async def get_message_planner_info(message_id: int):
    """Get planner information for a specific message"""
    try:
        # Get planner associated with this specific message
        planner = db.get_planner_by_message(message_id)
        
        if not planner:
            return {
                "has_planner": False,
                "execution_plan": None,
                "status": None,
                "planner_id": None
            }
        
        return {
            "has_planner": True,
            "execution_plan": planner["execution_plan"],
            "status": planner["status"],
            "planner_id": planner["planner_id"],
            "planner_name": planner["planner_name"],
            "user_question": planner["user_question"],
            "message_id": planner["message_id"],
            "router_id": planner["router_id"]
        }
    except Exception as e:
        logger.error(f"Error fetching message planner info: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/usage")
async def get_usage_stats():
    """Get LLM usage statistics by time periods"""
    try:
        from datetime import datetime, timedelta
        from sqlalchemy import create_engine, func
        from sqlalchemy.orm import sessionmaker
        from src.agent.services.llm_service import LLMUsage, Base
        
        # Database setup
        db_path = Path("/app/db/llm_usage.db")
        engine = create_engine(f"sqlite:///{db_path}")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        
        with Session() as session:
            now = datetime.now()
            
            # Calculate time boundaries
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = today_start - timedelta(days=today_start.weekday())
            month_start = today_start.replace(day=1)
            
            # Today's usage
            today_cost = session.query(func.sum(LLMUsage.cost)).filter(
                LLMUsage.timestamp >= today_start
            ).scalar() or 0.0
            
            # This week's usage
            week_cost = session.query(func.sum(LLMUsage.cost)).filter(
                LLMUsage.timestamp >= week_start
            ).scalar() or 0.0
            
            # This month's usage
            month_cost = session.query(func.sum(LLMUsage.cost)).filter(
                LLMUsage.timestamp >= month_start
            ).scalar() or 0.0
            
            # Total usage
            total_cost = session.query(func.sum(LLMUsage.cost)).scalar() or 0.0
            
            return {
                "today": round(today_cost, 4),
                "week": round(week_cost, 4),
                "month": round(month_cost, 4),
                "total": round(total_cost, 4)
            }
    except Exception as e:
        logger.error(f"Error fetching usage stats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


def main():
    """Main entry point"""
    port = int(os.environ["PORT"])
    logger.info(f"Starting server on port {port}")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True, log_level="info")


if __name__ == "__main__":
    main()
