from pathlib import Path
from fastapi import WebSocket
from ..core.base import BaseAgent
from ..agents.planner import PlannerAgent
from ..models import (
    PDFType,
    PDFFull,
    File,
)
from ..services.document_service import (
    extract_document_content,
    create_document_meta_summary,
)
from ..services.image_service import process_image_file
import uuid

INSTRUCTION_LIBRARY = {
    "data": {
        "csv": "When querying a data file such as csv, you must do so via SQL query. "
        "If required, create intermediate queries such as those that give you precise values in a field to apply an accurate filter on. "
        "You must not ever make up table names, column names, or values in tables. "
        "If you don't know, use intermediate queries to get the information you need. "
    },
    "image": {
        "chart": "Breakdown the task as follows:\n"
        "  1. If the image has 3 or more elements such as charts, tables, diagrams, text blocks (any combination of 3 such as 3 charts or two charts and a table), then crop the image to isolate the chart(s) of relevance. "
        "Otherwise, skip this step.\n"
        "  2. Use the provided tool get_chart_readings_from_image to extract the chart readings as text. This must be a standalone task.\n"
        "  3. If the user's question is a composite question requiring multiple pieces of information to be read from the chart, split the questions into atomic questions that can be answered by a single fact. "
        "Answer each question that is aiming to extract facts from the chart individually, and ignore analytical questions.\n"
        "  4. Compose a comprehensive answer to address the user's question.\n",
        "table": "Breakdown the task as follows:\n"
        "  1. Using the provided tool get_text_and_table_json_from_image, read the table contents as a JSON string. This must be the first standalone task.\n"
        "  2. If the user's question is a composite question requiring multiple pieces of information to be read from the table, split the questions into atomic questions that can be answered by a single fact. "
        "Answer each question that is aiming to extract facts from the table individually, and ignore analytical questions.\n"
        "  3. Compose a comprehensive answer to address the user's question.",
        "diagram": "Breakdown the task as follows:\n"
        "  1. Read the diagram and its contents as mermaid code."
        "  2. If the user's question is a composite question requiring multiple pieces of information to be read from the diagram, split the questions into atomic questions that can be answered by a single fact. "
        "Answer each question that is aiming to extract facts from the diagram individually, and ignore analytical questions."
        "  3. Compose a comprehensive answer to address the user's question.",
        "text": "Breakdown the task as follows:\n"
        "  1. Using the provided tool get_text_and_table_json_from_image, read the table contents as a JSON string. This must be the first standalone task.\n"
        "  2. If the user's question is a composite question requiring multiple pieces of information to be read from the text, split the questions into atomic questions that can be answered by a single fact. "
        "Answer each question that is aiming to extract facts from the text individually, and ignore analytical questions.\n"
        "  3. Compose a comprehensive answer to address the user's question.",
    },
}


class RouterAgent(BaseAgent):
    def __init__(self, conversation_id: str = None):
        super().__init__(id=conversation_id or uuid.uuid4().hex, agent_type="router")
        self.conversation_id = self.id
        self.websocket = None
        self.model = "gpt-4.1-nano"
        self.temperature = 0.0
        self.add_message(
            role="system",
            content="Your name is Bandit Heeler, your main role is to have a conversation with the user and for complex requests activate agents."
            "Otherwise, you are a fictional character from the show Bluey.",
        )

    async def connect_websocket(self, websocket: WebSocket):
        """Connect WebSocket for real-time communication"""
        await websocket.accept()
        self.websocket = websocket

        # Send conversation history to frontend
        await self.send_conversation_history()

    async def handle_message(self, message_data: dict):
        """Main message handler - processes user messages"""
        user_message = message_data.get("message", "")
        files = message_data.get("files", [])

        # Store user message
        self.add_message("user", user_message)

        try:
            # Send processing status
            await self.send_status("Processing...")

            # Determine response type
            if files or self.needs_planner(user_message):
                response = await self.handle_complex_request(user_message, files)
            else:
                response = await self.handle_simple_chat(user_message)

            # Store and send response
            self.add_message("assistant", response)
            await self.send_response(response)

        except Exception as e:
            await self.send_error(f"Error: {str(e)}")

    async def handle_simple_chat(self, user_message: str) -> str:
        """Handle simple conversational messages"""
        conversation_messages = self.messages  # From database via BaseAgent
        response = await self.llm.a_get_response(
            messages=conversation_messages,
            model=self.model,
            temperature=self.temperature,
        )
        return response.content

    async def handle_complex_request(self, user_message: str, files: list) -> str:
        """Handle complex requests requiring planner"""
        processed_files = await self.process_files(files)

        # Create planner with processed files
        planner = PlannerAgent(
            user_question=user_message,
            files=processed_files,
            model=self.model,
            temperature=self.temperature,
        )

        await planner.invoke()
        return await planner.get_response_to_user()

    def needs_planner(self, message: str) -> bool:
        """Check if message requires planner activation"""
        triggers = [
            "analyze",
            "process",
            "generate",
            "report",
            "chart",
            "table",
            "data",
        ]
        return any(trigger in message.lower() for trigger in triggers)

    async def process_files(self, file_paths: list) -> list:
        """Process uploaded files into File objects"""
        processed_files = []

        for file_path in file_paths:
            file_obj = Path(file_path)

            if file_obj.suffix == ".csv":
                processed_files.append(
                    File(filepath=file_path, file_type="data", data_context="csv")
                )
            elif file_obj.suffix == ".pdf":
                # Process PDF
                content = extract_document_content(file_path)
                meta = create_document_meta_summary(content)
                is_image_pdf = await self.llm.a_get_response(
                    messages=[
                        {
                            "role": "developer",
                            "content": f"Based on the following document metadata, is the document likely an image based pdf?\n\n```json\n{meta.model_dump_json(indent=2)}\n```",
                        }
                    ],
                    response_format=PDFType,
                )
                processed_files.append(
                    File(
                        filepath=file_path,
                        file_type="document",
                        document_context=PDFFull(
                            filename=file_obj.stem,
                            is_image_based=is_image_pdf.is_image_based,
                            content=content,
                            meta=meta,
                        ),
                    )
                )
            elif file_obj.suffix.lower() in [".png", ".jpg", ".jpeg"]:
                # Process image
                breakdown, error = process_image_file(file_path)
                if not error:
                    processed_files.append(
                        File(
                            filepath=file_path,
                            file_type="image",
                            image_context=breakdown.elements,
                        )
                    )

        return processed_files

    # WebSocket communication methods
    async def send_message(self, role: str, content: str):
        """Send message to frontend"""
        if self.websocket:
            await self.websocket.send_json(
                {
                    "type": "message",
                    "role": role,
                    "content": content,
                    "conversation_id": self.conversation_id,
                }
            )

    async def send_status(self, status: str):
        """Send status update to frontend"""
        if self.websocket:
            await self.websocket.send_json({"type": "status", "message": status})

    async def send_response(self, content: str):
        """Send response message to frontend"""
        if self.websocket:
            await self.websocket.send_json({"type": "response", "message": content})

    async def send_error(self, error: str):
        """Send error message to frontend"""
        if self.websocket:
            await self.websocket.send_json({"type": "error", "message": error})

    async def send_conversation_history(self):
        """Send conversation history to frontend on connect"""
        if self.websocket:
            await self.websocket.send_json(
                {
                    "type": "conversation_history",
                    "messages": self.messages,
                    "conversation_id": self.conversation_id,
                }
            )
