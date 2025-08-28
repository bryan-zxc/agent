import asyncio
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
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

from sqlalchemy import text
from src.agent.core import router_operations
from src.agent.models.agent_database import AgentDatabase
from src.agent.utils.file_utils import (
    calculate_file_hash,
    generate_unique_filename,
    sanitise_filename,
)
from src.agent.services.background_processor import start_background_processor
from src.agent.utils.async_error_utils import AsyncErrorLogger

# Load environment variables
# Load .env first (shared config), then .env.local (secrets) to override
load_dotenv()  # Loads .env
load_dotenv(".env.local")  # Loads .env.local and overrides any duplicates

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database will be initialized in lifespan context
db = None


# Create lifespan handler before FastAPI app
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage FastAPI application lifespan - startup and shutdown"""
    # Startup: Initialize database with factory method
    global db
    logger.info("Initializing database...")
    db = await AgentDatabase.create()
    logger.info("Database initialized successfully")

    logger.info("Starting background processor...")

    # Clear task queue on startup to prevent stale tasks from previous runs
    logger.info("Clearing task queue...")
    cleared_count = await db.clear_task_queue()
    logger.info(f"Cleared {cleared_count} tasks from task queue")

    await start_background_processor()
    logger.info("Background processor started successfully")

    yield

    # Shutdown (if needed in future)
    logger.info("Application shutdown")


app = FastAPI(title="Agent System API", version="1.0.0", lifespan=lifespan)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# PHASE 3: Ephemeral router architecture - removed active_connections
# Simple session tracking only
websocket_sessions = {}  # websocket -> {session_id, user_info}


# Pydantic models for API
class ChatMessage(BaseModel):
    message: str
    router_id: str
    files: Optional[List[str]] = []
    model: str = "gpt-4"
    temperature: float = 0.7


class StatusUpdate(BaseModel):
    status: str
    message: str


@app.websocket("/chat")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for chat communication with enhanced tracking"""
    await websocket.accept()

    # Enhanced connection logging
    connection_info = {
        "websocket_id": id(websocket),
        "websocket_type": type(websocket).__name__,
        "remote_address": websocket.scope.get("client", "unknown"),
        "path": websocket.scope.get("path", "unknown"),
    }

    if hasattr(websocket, "client_state"):
        connection_info["client_state"] = str(websocket.client_state)

    logger.info(f"WebSocket connection established: {connection_info}")

    # PHASE 3: Simplified session tracking
    import uuid

    session_id = uuid.uuid4().hex
    websocket_sessions[websocket] = {
        "session_id": session_id,
        "connection_info": connection_info,
    }

    try:
        # Send initial connection confirmation
        await websocket.send_json(
            {"type": "connection_established", "session_id": session_id}
        )
        logger.info(f"Sent connection confirmation to session {session_id}")

        while True:
            # Receive message from frontend
            data = await websocket.receive_json()
            logger.info(
                f"Received WebSocket message from session {session_id}: {data.get('type', 'unknown')}"
            )
            asyncio.create_task(handle_websocket_message(websocket, data))

    except WebSocketDisconnect:
        # PHASE 3: Simple session cleanup
        if websocket in websocket_sessions:
            session_info = websocket_sessions[websocket]
            del websocket_sessions[websocket]
            logger.info(
                f"Client session {session_info['session_id']} disconnected - connection info: {session_info.get('connection_info', {})}"
            )
        # No router cleanup needed - routers are ephemeral


async def handle_websocket_message(websocket: WebSocket, data: dict):
    """PHASE 3: Ephemeral router message handling - create router on-demand"""
    try:
        message_type = data.get("type", "message")

        if message_type == "load_router":
            # Load router history - create ephemeral router instance
            router_id = data.get("router_id")
            if router_id:
                logger.info(f"Loading router history for {router_id}")
                router_state = await router_operations.create_router(
                    router_id=router_id
                )

                # Send message history using WebSocket parameter
                await router_operations.send_message_history(
                    router_state=router_state, websocket=websocket
                )
                logger.info(f"Sent message history for router {router_id}")
                # Router state discarded after use

        elif message_type == "update_mode":
            # Update router mode
            router_id = data.get("router_id")
            mode = data.get("mode", "auto")
            if router_id:
                logger.info(f"Updating router {router_id} mode to {mode}")
                # Update mode in database
                agent_db = await AgentDatabase.create()
                await agent_db.update_router(router_id=router_id, mode=mode)
                # Send confirmation
                await websocket.send_json({
                    "type": "mode_updated",
                    "router_id": router_id,
                    "mode": mode
                })
                logger.info(f"Router {router_id} mode updated to {mode}")
        
        elif message_type == "message":
            # Regular chat message - ephemeral router creation
            router_id = data.get("router_id")
            is_new_conversation = not router_id

            if is_new_conversation:
                # Brand new conversation - activate_conversation creates router internally
                logger.info(f"Creating new ephemeral router for new conversation")

                # For new conversations, use activate_conversation with WebSocket
                user_message = data.get("message", "")
                files = data.get("files", [])
                mode = data.get("mode", "auto")  # Get mode from frontend, default to auto
                router_state = await router_operations.activate_conversation(
                    user_message=user_message, files=files, websocket=websocket, mode=mode
                )
                router_id = router_state[
                    "id"
                ]  # Get the generated ID from returned state
                logger.info(f"Generated new router_id: {router_id}")

            else:
                # Existing conversation - create ephemeral router from database
                logger.info(
                    f"Creating ephemeral router for existing conversation {router_id}"
                )
                router_state = await router_operations.create_router(
                    router_id=router_id
                )  # Load state from database

                # Handle message with WebSocket parameter
                await router_operations.handle_message(
                    router_state=router_state, message_data=data, websocket=websocket
                )

            logger.info(
                f"Message processed by ephemeral router {router_id} - state discarded"
            )
            # Router state automatically discarded after handling

    except Exception as e:
        # Log detailed error information for WebSocket message handling
        error_logger = AsyncErrorLogger("websocket_message_handler")
        error_logger.log_detailed_exception(e, "WebSocket message processing")

        # Only try to send error if WebSocket is still open
        try:
            await websocket.send_json(
                {"type": "error", "message": f"Error processing message: {str(e)}"}
            )
        except RuntimeError as ws_error:
            if "close message has been sent" in str(ws_error):
                logger.warning(f"WebSocket closed while sending error response: {ws_error}")
            else:
                raise


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
        existing_file = await db.get_file_by_hash(content_hash, user_id)

        if existing_file:
            # Duplicate found - return duplicate info with options
            return {
                "duplicate_found": True,
                "existing_file": {
                    "file_id": existing_file["file_id"],
                    "original_filename": existing_file["original_filename"],
                    "file_size": existing_file["file_size"],
                    "upload_timestamp": existing_file["upload_timestamp"].isoformat(),
                },
                "new_filename": file.filename,
                "options": [
                    "use_existing",
                    "overwrite_existing",
                    "save_as_new_copy",
                    "cancel",
                ],
            }

        # No duplicate - save file normally
        upload_dir = Path("/app/files/uploads") / user_id
        upload_dir.mkdir(parents=True, exist_ok=True)

        file_id = uuid.uuid4().hex
        sanitised_filename = sanitise_filename(file.filename)

        # Check if sanitised filename already exists and make it unique if needed
        existing_files = [f.name for f in upload_dir.iterdir() if f.is_file()]
        if sanitised_filename in existing_files:
            sanitised_filename = generate_unique_filename(
                sanitised_filename, existing_files
            )

        file_path = upload_dir / sanitised_filename

        with open(file_path, "wb") as buffer:
            buffer.write(content)

        # Store file metadata
        await db.create_file_metadata(
            file_id=file_id,
            content_hash=content_hash,
            original_filename=sanitised_filename,
            file_path=str(file_path),
            file_size=file_size,
            mime_type=file.content_type,
            user_id=user_id,
        )

        return {
            "duplicate_found": False,
            "file_id": file_id,
            "filename": sanitised_filename,
            "path": str(file_path),
            "size": file_size,
        }

    except Exception as e:
        logger.error(f"Error uploading file: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/upload/resolve-duplicate")
async def resolve_duplicate(
    action: str = Form(...),
    existing_file_id: str = Form(...),
    new_filename: str = Form(...),
    file: UploadFile = File(...),
):
    """Handle duplicate resolution based on user choice"""
    try:
        # TODO: Replace 'bryan000' with actual username from user management system
        user_id = "bryan000"

        if action == "cancel":
            return {
                "action": "cancel",
                "files": [],  # Empty files array for message handling
            }

        existing_file = await db.get_file_by_id(existing_file_id)
        if not existing_file:
            raise HTTPException(status_code=404, detail="Existing file not found")

        if action == "use_existing":
            # Increment reference count and return existing file
            await db.increment_file_reference(existing_file_id)
            return {
                "action": "use_existing",
                "file_id": existing_file["file_id"],
                "filename": existing_file["original_filename"],
                "path": existing_file["file_path"],
                "size": existing_file["file_size"],
                "files": [existing_file["file_path"]],  # For message handling
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
                "files": [existing_file["file_path"]],  # For message handling
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

            unique_filename = generate_unique_filename(
                sanitised_filename, existing_files
            )
            file_id = uuid.uuid4().hex
            file_path = upload_dir / unique_filename

            with open(file_path, "wb") as buffer:
                buffer.write(content)

            # Calculate content hash for new file
            content_hash = calculate_file_hash(file_path)

            # Store file metadata with unique filename
            await db.create_file_metadata(
                file_id=file_id,
                content_hash=content_hash,
                original_filename=unique_filename,
                file_path=str(file_path),
                file_size=len(content),
                mime_type=file.content_type,
                user_id=user_id,
            )

            return {
                "action": "save_as_new_copy",
                "file_id": file_id,
                "filename": unique_filename,
                "path": str(file_path),
                "size": len(content),
                "files": [str(file_path)],  # For message handling
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


@app.get("/routers")
async def get_routers():
    """Get all routers"""
    try:
        # Use the global db instance
        routers = await db.get_all_routers()

        # Transform to match expected API format
        return [
            {
                "id": router["router_id"],
                "title": router["title"],
                "preview": router["preview"],
                "timestamp": (
                    router["updated_at"].isoformat() if router["updated_at"] else None
                ),
            }
            for router in routers
        ]
    except Exception as e:
        logger.error(f"Error fetching routers: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/routers/{router_id}")
async def get_router(router_id: str):
    """Get router history"""
    try:
        router_state = await router_operations.create_router(router_id=router_id)
        # Get messages through MessageManager
        messages = await router_state["message_manager"].get_messages()
        return {"router_id": router_id, "messages": messages}
    except Exception as e:
        logger.error(f"Error fetching router: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# NOTE: Router activation happens through WebSocket (/chat) endpoint
# All user interactions for starting conversations go through WebSocket
# There is no HTTP-based activation endpoint as it's not needed

# NOTE: Title generation happens automatically via WebSocket flow
# No separate HTTP endpoint needed as titles are generated after conversation activation


@app.get("/messages/{message_id}/planner-info")
async def get_message_planner_info(message_id: int):
    """Get planner information for a specific message"""
    try:
        # Get planner associated with this specific message (now async)
        planner = await db.get_planner_by_message(message_id)

        if not planner:
            return {
                "has_planner": False,
                "execution_plan": None,
                "status": None,
                "planner_id": None,
            }

        return {
            "has_planner": True,
            "execution_plan": planner["execution_plan"],
            "status": planner["status"],
            "planner_id": planner["planner_id"],
            "planner_name": planner["planner_name"],
            "user_question": planner["user_question"],
            "message_id": planner["message_id"],
            "router_id": planner["router_id"],
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

        # Database setup with WAL mode optimisations (same as LLM service)
        db_path = Path("/app/db/llm_usage.db")
        engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={
                "check_same_thread": False,
                "timeout": 30,
            },
        )

        # Configure WAL mode for this connection
        with engine.connect() as conn:
            conn.execute(text("PRAGMA journal_mode=WAL"))
            conn.execute(text("PRAGMA busy_timeout=5000"))
            conn.commit()

        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)

        with Session() as session:
            now = datetime.now()

            # Calculate time boundaries
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = today_start - timedelta(days=today_start.weekday())
            month_start = today_start.replace(day=1)

            # Today's usage
            today_cost = (
                session.query(func.sum(LLMUsage.cost))
                .filter(LLMUsage.timestamp >= today_start)
                .scalar()
                or 0.0
            )

            # This week's usage
            week_cost = (
                session.query(func.sum(LLMUsage.cost))
                .filter(LLMUsage.timestamp >= week_start)
                .scalar()
                or 0.0
            )

            # This month's usage
            month_cost = (
                session.query(func.sum(LLMUsage.cost))
                .filter(LLMUsage.timestamp >= month_start)
                .scalar()
                or 0.0
            )

            # Total usage
            total_cost = session.query(func.sum(LLMUsage.cost)).scalar() or 0.0

            return {
                "today": round(today_cost, 4),
                "week": round(week_cost, 4),
                "month": round(month_cost, 4),
                "total": round(total_cost, 4),
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
