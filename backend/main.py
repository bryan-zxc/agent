import asyncio
import json
import logging
import os
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
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.agent.core.router import RouterAgent

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
            else:
                router = active_connections[conversation_id]
                # Update websocket connection for existing router
                router.websocket = websocket

            # Update current conversation for this session
            user_connections[websocket]["current_conversation"] = conversation_id

            # Handle the message
            await router.handle_message(data)

    except Exception as e:
        logger.error(f"Error handling WebSocket message: {str(e)}")
        await websocket.send_json(
            {"type": "error", "message": f"Error processing message: {str(e)}"}
        )


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """Handle file uploads"""
    try:
        # Create uploads directory if it doesn't exist
        upload_dir = Path("uploads")
        upload_dir.mkdir(exist_ok=True)

        # Save uploaded file
        file_path = upload_dir / file.filename
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)

        return {"filename": file.filename, "path": str(file_path)}

    except Exception as e:
        logger.error(f"Error uploading file: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "agent-system"}


@app.get("/conversations")
async def get_conversations():
    """Get all conversations"""
    try:
        from src.agent.models.message_db import (
            MessageDatabase,
            Conversation,
            RouterMessage,
        )

        db = MessageDatabase()
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


def main():
    """Main entry point"""
    port = int(os.environ["PORT"])
    logger.info(f"Starting server on port {port}")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True, log_level="info")


if __name__ == "__main__":
    main()
