import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.agent.core.router import RouterAgent

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

# Pydantic models for API
class ChatMessage(BaseModel):
    message: str
    files: Optional[List[str]] = []
    model: str = "gpt-4"
    temperature: float = 0.7

class StatusUpdate(BaseModel):
    status: str
    message: str

@app.websocket("/chat/{conversation_id}")
async def websocket_endpoint(websocket: WebSocket, conversation_id: str):
    """WebSocket endpoint for chat communication"""
    # Create or get existing router
    router = RouterAgent(conversation_id=conversation_id)
    await router.connect_websocket(websocket)
    active_connections[conversation_id] = router
    
    try:
        while True:
            # Receive message from frontend
            data = await websocket.receive_json()
            await router.handle_message(data)
            
    except WebSocketDisconnect:
        # Clean up connection
        if conversation_id in active_connections:
            del active_connections[conversation_id]
        logger.info(f"Client {conversation_id} disconnected")

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

@app.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    """Get conversation history"""
    try:
        router = RouterAgent(conversation_id=conversation_id)
        return {
            "conversation_id": conversation_id,
            "messages": router.messages
        }
    except Exception as e:
        logger.error(f"Error fetching conversation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

def main():
    """Main entry point"""
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )

if __name__ == "__main__":
    main()
