from pathlib import Path
from fastapi import WebSocket
from ..core.base import BaseAgent
import asyncio
import logging
from ..agents.planner import PlannerAgent
from ..config.settings import settings
from ..models import File
from ..models.responses import RequireAgent
from ..models.schemas import SinglevsMultiRequest
from ..services.image_service import process_image_file, is_image
import uuid

logger = logging.getLogger(__name__)

INSTRUCTION_LIBRARY = {
    "data": {
        "csv": "When querying a data file such as csv, you must do so via SQL query. "
        "If required, create intermediate queries such as those that give you precise values in a field to apply an accurate filter on. "
        "You must not ever make up table names, column names, or values in tables. "
        "If you don't know, use intermediate queries to get the information you need. "
    },
    "image": {
        "chart": "You must use the provided tool get_chart_readings_from_image to extract the chart readings as text first before performing further actions. "
        "This must be a standalone task.",
        "table": "You must use the provided tool get_text_and_table_json_from_image, read the table contents as a JSON string first before performing further actions. "
        "This must be a standalone task.",
        "diagram": "You must convert the diagram into mermaid code first before performing further actions.",
        "text": "You must use the provided tool get_text_and_table_json_from_image, read the text content as a JSON string first before performing further actions. "
        "This must be a standalone task.",
    },
    "document": {
        "pdf": "You must first use the provided tool get_facts_from_pdf to extract relevant facts in the form of question answer pairs from each document until there are no longer any unanswered questions (ie missing facts to answer the user's original question). "
        "Extracting from each file must be a standalone task.\n"
        "When compiling the final response, you must aggressively use in-line citations, and your answer should be in markdown format."
    },
    "non_file": {
        "company_query": "You must first use search_web_pdf tool to find annual report and sustainability report, as most questions can be answered by these documents."
        "If pdf documents are found, you must use the get_facts_from_pdf tool to extract relevant facts in the form of question answer pairs from each document until either there are no longer any unanswered questions (ie missing facts to answer the user's original question), or if there are no more documents. "
        "Questions that are still open can be searched on the web using the search_web_general tool.",
        "web_search": "You must use the search_web_general tool or the search_web_pdf tool to search the web for information that can answer the user's question. "
        "If pdf documents are found, you must use the get_facts_from_pdf tool to extract relevant facts in the form of question answer pairs from each document until either there are no longer any unanswered questions (ie missing facts to answer the user's original question), or if there are no more documents. ",
    },
}


class RouterAgent(BaseAgent):
    def __init__(self, conversation_id: str = None):
        super().__init__(id=conversation_id or uuid.uuid4().hex, agent_type="router")
        self.conversation_id = self.id
        self.websocket = None
        self.model = settings.router_model
        self.temperature = 0.0

    async def activate_conversation(self, user_message: str, files: list = None):
        """Activate a new conversation with system message and process first user message"""
        # Create default title (truncated if over 30 chars) and preview
        title = user_message[:30] if len(user_message) > 30 else user_message
        preview = user_message[:37] + "..." if len(user_message) > 40 else user_message

        # Create conversation with default title and preview in database first
        self._message_db.create_conversation_with_details(self.id, title, preview)

        # Add system message to database
        self.add_message(
            role="system",
            content="Your name is Bandit Heeler, your main role is to have a conversation with the user and for complex requests activate agents."
            "Otherwise, you are a fictional character from the show Bluey.",
        )

        # Prepare message data for processing
        message_data = {"message": user_message, "files": files or []}

        # Process the main message
        await self.handle_message(message_data)

    async def generate_and_update_title(self):
        """Generate LLM title using existing message chain and update database"""
        try:
            # Get the first user message to check length
            user_messages = [msg for msg in self.messages if msg.get("role") == "user"]
            if not user_messages or len(user_messages[0]["content"]) <= 30:
                return

            # Use the entire conversation to generate a title
            title_messages = self.messages + [
                {
                    "role": "user",
                    "content": "Create a succinct title for this conversation. "
                    "In the response, only provide the title and nothing else. "
                    "Keep the title under 30 characters.",
                }
            ]

            response = await self.llm.a_get_response(
                messages=title_messages,
                model=self.model,
                temperature=self.temperature,
            )
            llm_title = response.content.strip()

            # Update title in database
            self._message_db.update_conversation_title(self.id, llm_title)
            logger.info(f"Updated title for conversation {self.id}: {llm_title}")

        except Exception as e:
            # Log error but don't fail
            logger.error(f"Failed to generate LLM title for {self.id}: {e}")

    async def connect_websocket(self, websocket: WebSocket):
        """Connect WebSocket for real-time communication"""
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
            await self.send_status("Thinking...")

            # Determine response type
            if files:
                response = await self.handle_complex_request(files=files)
            else:
                # Run assessment and simple chat concurrently to reduce wait time
                async with asyncio.TaskGroup() as tg:
                    assessment_task = tg.create_task(self.assess_agent_requirements())
                    simple_chat_task = tg.create_task(self.handle_simple_chat())
                
                agent_requirements = assessment_task.result()
                
                # Check if agent is needed
                if any([
                    agent_requirements.calculation_required,
                    agent_requirements.web_search_required,
                    agent_requirements.company_query,
                    agent_requirements.complex_question,
                ]):
                    # We need complex handling - simple chat result is discarded
                    response = await self.handle_complex_request(agent_requirements=agent_requirements)
                else:
                    # Use the already completed simple chat response
                    response = simple_chat_task.result()

            # Store and send response
            self.add_message("assistant", response)
            await self.send_response(response)

        except Exception as e:
            await self.send_error(f"Error: {str(e)}")

    async def handle_simple_chat(self) -> str:
        """Handle simple conversational messages"""
        response = await self.llm.a_get_response(
            messages=self.messages,
            model=self.model,
            temperature=self.temperature,
        )
        return response.content

    async def assess_agent_requirements(self) -> RequireAgent:
        """Use LLM to assess what type of agent assistance is needed based on conversation history"""
        assessment_messages = self.messages + [
            {
                "role": "user",
                "content": "Based on the conversation, what type of assistance is needed? Return RequireAgent with appropriate flags.",
            }
        ]

        response = await self.llm.a_get_response(
            messages=assessment_messages,
            model=self.model,
            temperature=0.0,
            response_format=RequireAgent,
        )

        return response.parsed

    async def handle_complex_request(
        self, files: list = None, agent_requirements: RequireAgent = None
    ) -> str:
        """Handle complex requests requiring planner"""
        # Validate that either files or agent requirements exist
        if not files and not agent_requirements:
            raise ValueError(
                "Either files must be provided or agent requirements must be specified"
            )

        # Determine user question and generate instructions
        instructions = []
        if agent_requirements:
            # Generate non-file instructions based on agent requirements
            if agent_requirements.company_query:
                instructions.append(
                    f"# Instructions for company query:\n\n{INSTRUCTION_LIBRARY.get('non_file').get('company_query', '')}"
                )
            if agent_requirements.web_search_required:
                instructions.append(
                    f"# Instructions for web search:\n\n{INSTRUCTION_LIBRARY.get('non_file').get('web_search', '')}"
                )
            user_question = agent_requirements.context_rich_agent_request
        else:
            response = await self.llm.a_get_response(
                messages=self.messages
                + [
                    {
                        "role": "developer",
                        "content": "Summarise the conversation into a context-rich request for the agent.",
                    }
                ],
                model=self.model,
                temperature=self.temperature,
            )
            user_question = response.content

        # Check if files list is not empty before processing
        if files:
            # Determine question type
            question_type = await self.determine_question_type(user_question, files)
            
            if question_type == "multiple":
                # Process each file separately
                responses = []
                for file in files:
                    response = await self._invoke_single([file], user_question, instructions)
                    responses.append(f"**File: {file}**\n\n{response}")
                return "\n\n---\n\n".join(responses)
            else:
                # Process all files together
                return await self._invoke_single(files, user_question, instructions)

        else:
            processed_files = None

        # Create planner with processed files
        planner = PlannerAgent(
            user_question=user_question,
            instruction="\n\n---\n\n".join(instructions),
            files=processed_files,
            model=self.model,
            temperature=self.temperature,
            failed_task_limit=settings.failed_task_limit,
        )

        await planner.invoke()
        return await planner.get_response_to_user()

    async def process_files(self, file_paths: list) -> tuple[list, list]:
        """Process uploaded files into File objects and return (processed_files, errors)"""
        processed_files = []
        errors = []
        image_types = []
        data_types = []
        document_types = []

        for file_path in file_paths:
            file_obj = Path(file_path)

            if file_obj.suffix == ".csv":
                processed_files.append(
                    File(filepath=file_path, file_type="data", data_context="csv")
                )
                data_types.append("csv")
            elif file_obj.suffix == ".pdf":
                # Process PDF
                processed_files.append(
                    File(
                        filepath=file_path, file_type="document", document_context="pdf"
                    )
                )
                document_types.append("pdf")
            elif is_image(file_path)[0]:
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
                    image_types.extend(
                        [element.element_type for element in breakdown.elements]
                    )
                else:
                    errors.append(f"Error processing image '{file_obj.name}': {error}")
            else:
                # Unsupported file type
                errors.append(
                    f"Unsupported file type '{file_obj.suffix}' for file '{file_obj.name}'"
                )
        # Remove duplicates
        image_types = list(set(image_types))
        data_types = list(set(data_types))
        document_types = list(set(document_types))

        instructions = []

        # Add image instructions
        if image_types:
            instructions.extend(
                [
                    f"# Instructions for handling - {element_type} image:\n\n{INSTRUCTION_LIBRARY.get('image').get(element_type, '')}"
                    for element_type in image_types
                ]
            )

        # Add data instructions
        if data_types:
            instructions.extend(
                [
                    f"# Instructions for handling - {data_type} data:\n\n{INSTRUCTION_LIBRARY.get('data').get(data_type, '')}"
                    for data_type in data_types
                ]
            )

        # Add document instructions
        if document_types:
            instructions.extend(
                [
                    f"# Instructions for handling - {doc_type} document:\n\n{INSTRUCTION_LIBRARY.get('document').get(doc_type, '')}"
                    for doc_type in document_types
                ]
            )

        return processed_files, errors, instructions

    async def determine_question_type(self, user_question: str, files: list) -> str:
        """Determine if user wants single response or multiple responses for files"""
        if len(files) == 1:
            return "single"
        else:
            response = await self.llm.a_get_response(
                messages=[
                    {
                        "role": "user",
                        "content": f"{user_question}\n\nFiles: {','.join(files)}",
                    },
                    {
                        "role": "developer",
                        "content": "Is the user looking for a single response or multiple responses - one for each file?",
                    },
                ],
                model=self.model,
                temperature=0.0,
                response_format=SinglevsMultiRequest,
            )
            return response.parsed.request_type

    async def _invoke_single(self, files: list, user_question: str, instructions: list) -> str:
        """Invoke planner for single file or combined processing"""
        processed_files, errors, file_instructions = await self.process_files(files)
        
        if not processed_files:
            return "Unable to process any files. Errors encountered:\n" + "\n".join(
                f"• {error}" for error in errors
            )
        
        # Combine instructions
        all_instructions = instructions + file_instructions
        
        # Create planner with processed files
        planner = PlannerAgent(
            user_question=user_question,
            instruction="\n\n---\n\n".join(all_instructions),
            files=processed_files,
            model=self.model,
            temperature=self.temperature,
            failed_task_limit=settings.failed_task_limit,
        )

        await planner.invoke()
        return await planner.get_response_to_user()

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
            # Only send history if there are actual messages (excluding system messages)
            conversation_messages = [
                msg for msg in self.messages if msg.get("role") != "system"
            ]
            await self.websocket.send_json(
                {
                    "type": "conversation_history",
                    "messages": conversation_messages,
                    "conversation_id": self.conversation_id,
                }
            )
