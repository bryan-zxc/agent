from pathlib import Path
from typing import Optional, Union, List, Dict, Any
from fastapi import WebSocket
from PIL import Image
from datetime import datetime, timezone
import asyncio
import logging
import uuid
import duckdb
from ..config.settings import settings
from ..models import File, DocumentContext
from ..models.responses import RequireAgent
from ..models.schemas import FileGrouping
from ..models.agent_database import AgentDatabase, AgentType, Router
from ..services.image_service import process_image_file, is_image
from ..services.llm_service import LLM
from ..tasks.task_utils import update_planner_next_task_and_queue
from ..utils.tools import encode_image, decode_image

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
        "If the document(s) do not contain all necessary information, in other words there are still unanswered questions, you can use the search_web_general tool to search the web for information that can answer the user's question.",
        "text": "(No specific instructions)",
    },
    "non_file": {
        # "chilli_request": "You must first use search_web_pdf tool to find annual report and sustainability report and extract the facts as question and answer pairs, as most questions can be answered by these documents. "
        # "Use only the latest version of these documents, for example if today is 2025 then the latest annual report is likely 2024 (as the new year's report may not yet available) or 2025. "
        # "Questions that are still open can be searched on the web using the search_web_general tool.",
        "web_search": "You must use the search_web_general tool or the search_web_pdf tool to search the web for information that can answer the user's question. ",
    },
}


class RouterAgent:
    def __init__(self, router_id: str = None):
        # Use "router" as the caller for LLM usage tracking
        self.llm = LLM(caller="router")

        # Initialize database connection first
        self.agent_type = "router"
        self._agent_db = AgentDatabase()
        self.websocket = None

        if router_id:
            self.id = router_id
            # Load existing router from database
            self._load_existing_state()
        else:
            self.id = uuid.uuid4().hex
            # Note: For new routers, initialization happens in activate_conversation()

    def _load_existing_state(self):
        """Load router-specific state from database"""
        state = self._agent_db.get_router(self.id)
        if state:
            self._model = state["model"]
            self._temperature = state["temperature"]
            self._status = state["status"]
        else:
            raise ValueError(f"Router {self.id} not found in database")

    # Common agent properties with database sync

    @property
    def model(self):
        return getattr(self, "_model", None)

    @model.setter
    def model(self, value):
        self._model = value
        self.update_agent_state(model=value)

    @property
    def temperature(self):
        return getattr(self, "_temperature", None)

    @temperature.setter
    def temperature(self, value):
        self._temperature = value
        self.update_agent_state(temperature=value)

    @property
    def messages(self) -> List[Dict[str, Any]]:
        """Get messages from database for this agent"""
        return self._agent_db.get_messages(self.agent_type, self.id)

    @messages.setter
    def messages(self, value: List[Dict[str, Any]]):
        """Set messages (for backward compatibility, though we prefer database storage)"""
        # Clear existing messages and add new ones
        self._agent_db.clear_messages(self.agent_type, self.id)
        for msg in value:
            self._agent_db.add_message(
                self.agent_type, self.id, msg["role"], msg["content"]
            )

    def add_message(
        self,
        role: str,
        content: str,
        image: Union[str, Path, Image.Image] = None,
        verbose=True,
    ) -> Optional[int]:
        """
        Adds a message to the message history.

        :param role: The role of the message sender (e.g., 'user', 'assistant').
        :param content: The content of the message.
        :return: A list of messages including the new message.
        """
        if image:
            if content:
                if isinstance(content, str):
                    content = [
                        {"type": "text", "text": content},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{encode_image(image)}"
                            },
                        },
                    ]
                else:
                    content.append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{encode_image(image)}"
                            },
                        }
                    )
            else:
                content = [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{encode_image(image)}"
                        },
                    }
                ]

        if isinstance(content, str):
            if verbose:
                logger.info(content)
            else:
                logger.debug(content)
        elif isinstance(content, list):
            for c in content:
                if c.get("type") == "text":
                    if verbose:
                        logger.info(c["text"])
                    else:
                        logger.debug(c["text"])
                else:
                    if verbose:
                        decode_image(
                            c["image_url"]["url"].replace("data:image/png;base64,", "")
                        ).show()

        # Store in database and return message ID
        return self._agent_db.add_message(self.agent_type, self.id, role, content)

    # Agent State Management

    def update_agent_state(self, **kwargs):
        """Update any agent state fields dynamically"""
        if not kwargs:
            return

        # Always update the updated_at timestamp
        kwargs["updated_at"] = datetime.now(timezone.utc)

        # Build dynamic update query
        with self._agent_db.SessionLocal() as session:
            # Get the router record
            record = session.query(Router).filter(Router.router_id == self.id).first()

            if record:
                # Update all provided fields
                for field, value in kwargs.items():
                    if hasattr(record, field):
                        setattr(record, field, value)

                session.commit()

    # Router-specific properties

    @property
    def status(self):
        return getattr(self, "_status", None)

    @status.setter
    def status(self, value):
        self._status = value
        self.update_agent_state(status=value)

    async def activate_conversation(self, user_message: str, files: list = None):
        """Activate a new router with system message and process first user message"""
        # Create default title (truncated if over 30 chars) and preview
        title = user_message[:30] if len(user_message) > 30 else user_message
        preview = user_message[:37] + "..." if len(user_message) > 40 else user_message

        # Create router with complete initialization in database
        self._agent_db.create_router(
            router_id=self.id,
            status="active",
            model=settings.router_model,
            temperature=0.0,
            title=title,
            preview=preview,
        )

        # Set instance variables after DB creation
        self._model = settings.router_model
        self._temperature = 0.0
        self._status = "active"

        # Add system message to database
        self.add_message(
            role="system",
            content="Your name is Bandit Heeler, your main role is to have a conversation with the user and for complex requests activate agents."
            "Otherwise, you are a fictional character from the show Bluey.",
        )

        # Note: User message is already displayed on frontend from sendMessage()
        # No need to send_user_message() here to avoid duplication

        # Prepare message data for processing
        message_data = {"message": user_message, "files": files or []}

        logger.info(f"DEBUG: activate_conversation called with files: {files}")
        logger.info(f"DEBUG: message_data prepared: {message_data}")

        # Process the main message
        await self.handle_message(message_data)

    async def generate_and_update_title(self):
        """Generate LLM title using existing message chain and update database"""
        try:
            # Get the first user message to check length
            user_messages = [msg for msg in self.messages if msg.get("role") == "user"]
            if not user_messages or len(user_messages[0]["content"]) <= 30:
                return

            # Use the entire message history to generate a title
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
            self._agent_db.update_router_title(self.id, llm_title)
            logger.info(f"Updated title for router {self.id}: {llm_title}")

        except Exception as e:
            # Log error but don't fail
            logger.error(f"Failed to generate LLM title for {self.id}: {e}")

    async def connect_websocket(self, websocket: WebSocket):
        """Connect WebSocket for real-time communication with enhanced tracking"""
        # Log WebSocket connection details
        websocket_info = {
            "websocket_id": id(websocket),
            "websocket_type": type(websocket).__name__,
            "router_id": self.id,
        }

        if hasattr(websocket, "client_state"):
            websocket_info["client_state"] = str(websocket.client_state)
        if hasattr(websocket, "scope"):
            websocket_info["scope_path"] = websocket.scope.get("path", "unknown")
            websocket_info["scope_client"] = websocket.scope.get("client", "unknown")

        logger.info(f"Connecting WebSocket to router {self.id}: {websocket_info}")

        self.websocket = websocket

        # Send message history to frontend
        await self.send_message_history()

    async def handle_message(self, message_data: dict):
        """Main message handler - processes user messages"""
        # Lock input for this router immediately
        await self.send_input_lock()

        user_message = message_data.get("message", "")
        files = message_data.get("files", [])

        logger.info(f"DEBUG: handle_message called with files: {files}")
        logger.info(
            f"DEBUG: files type: {type(files)}, length: {len(files) if files else 'None'}"
        )

        # Store user message
        self.add_message("user", user_message)

        try:
            # Send processing status
            await self.send_status("Thinking")

            # Determine response type
            logger.info(
                f"DEBUG: Checking if files exist - files: {files}, bool(files): {bool(files)}"
            )
            if files:
                logger.info(f"DEBUG: Taking complex request path with files: {files}")
                await self.handle_complex_request(files=files)
                # Complex request handles its own messaging - no response to send
            else:
                logger.info(f"DEBUG: Taking simple chat path - no files provided")
                # Run assessment and simple chat concurrently to reduce wait time
                async with asyncio.TaskGroup() as tg:
                    assessment_task = tg.create_task(self.assess_agent_requirements())
                    simple_chat_task = tg.create_task(self.handle_simple_chat())

                agent_requirements = assessment_task.result()
                logger.info(
                    f"Agent requirements assessed for router {self.id}: {agent_requirements.model_dump_json(indent=2)}"
                )

                # Check if agent is needed by looping through all boolean fields
                boolean_requirements = [
                    getattr(agent_requirements, field_name)
                    for field_name, field_info in agent_requirements.__class__.model_fields.items()
                    if field_info.annotation == bool
                    and hasattr(agent_requirements, field_name)
                ]
                if any(boolean_requirements):
                    # We need complex handling - simple chat result is discarded
                    await self.handle_complex_request(
                        agent_requirements=agent_requirements
                    )
                    # Complex request handles its own messaging - no response to send
                else:
                    # Use the already completed simple chat response
                    response = simple_chat_task.result()
                    logger.info(f"Response generated in router:\n{response}")
                    # Store and send response for simple chat only
                    self.add_message("assistant", response)
                    await self.send_assistant_message(response)

        except Exception as e:
            logger.error(
                f"Error handling message in router {self.id}: {str(e)}", exc_info=True
            )
            await self.send_error(f"Error: {str(e)}")
        finally:
            # Always unlock input for this router, even if processing failed
            await self.send_input_unlock()

    async def handle_simple_chat(self) -> str:
        """Handle simple conversational messages"""
        response = await self.llm.a_get_response(
            messages=self.messages,
            model=self.model,
            temperature=self.temperature,
        )
        return response.content

    async def assess_agent_requirements(self) -> RequireAgent:
        """Use LLM to assess what type of agent assistance is needed based on message history"""
        assessment_messages = self.messages + [
            {
                "role": "user",
                "content": "Based on the conversation, are there any indicators that the user request requires agent assistance?",
            }
        ]

        response = await self.llm.a_get_response(
            messages=assessment_messages,
            model=self.model,
            temperature=0.0,
            response_format=RequireAgent,
        )

        return response

    async def handle_complex_request(
        self, files: list = None, agent_requirements: RequireAgent = None
    ):
        """Handle complex requests requiring planner - runs asynchronously in background"""
        logger.info(
            f"DEBUG: handle_complex_request called with files: {files}, agent_requirements: {agent_requirements}"
        )

        # Validate that either files or agent requirements exist
        if not files and not agent_requirements:
            logger.error(
                "DEBUG: Neither files nor agent requirements provided - raising ValueError"
            )
            raise ValueError(
                "Either files must be provided or agent requirements must be specified"
            )

        # Determine user question and generate instructions
        instructions = []
        logger.info(
            f"DEBUG: Checking agent_requirements path - agent_requirements: {agent_requirements}"
        )
        if agent_requirements:
            # Generate non-file instructions based on agent requirements
            # if agent_requirements.chilli_request:
            #     instructions.append(
            #         f"# Instructions for Chilli request:\n\n{INSTRUCTION_LIBRARY.get('non_file').get('chilli_request', '')}"
            #     )
            if agent_requirements.web_search_required:
                instructions.append(
                    f"# Instructions for web search:\n\n{INSTRUCTION_LIBRARY.get('non_file').get('web_search', '')}"
                )
            user_question = agent_requirements.context_rich_agent_request
        else:
            logger.info(
                f"DEBUG: Taking files-only path - calling LLM to summarise message history"
            )
            # Create a fresh message context for summarisation without the Bandit Heeler system message
            user_messages = [
                msg for msg in self.messages if msg.get("role") != "system"
            ]
            summary_messages = [
                {
                    "role": "system",
                    "content": "Your sole job is to summarise the conversation into a context-rich request for the downstream agent. "
                    "Use the latest message from the user as the basis and enrich the context directly associated with the question using the conversation history. "
                    "Return only the context-rich request for the agent, do not include any other information such as prefixes or suffixes, do not ask for more information from the user.",
                },
                *user_messages,
            ]
            response = await self.llm.a_get_response(
                messages=summary_messages,
                model=self.model,
                temperature=self.temperature,
            )
            user_question = response.content
            logger.info(f"DEBUG: LLM summarised user question: {user_question}")

        # Check if files list is not empty before processing
        logger.info(
            f"DEBUG: About to check files - files: {files}, bool(files): {bool(files)}"
        )
        if files:
            logger.info(f"DEBUG: Files found - processing files: {files}")
            # Determine file groups
            file_groups = await self.determine_file_groups(user_question, files)
            logger.info(f"DEBUG: File groups determined: {file_groups}")

            # Process each file group sequentially
            for i, file_group in enumerate(file_groups, 1):
                if len(file_groups) > 1:
                    await self.send_status(f"Processing file group {i}/{len(file_groups)}: {', '.join(file_group)}")
                else:
                    logger.info(f"DEBUG: Processing single file group with files: {file_group}")

                # Start background task for this file group - no return value, runs asynchronously
                await self._invoke_single(
                    file_group, user_question, instructions, agent_requirements
                )
                logger.info(
                    f"DEBUG: File group {i} planner queued for background processing"
                )

            # All file groups processed sequentially - no return value needed
            logger.info(f"Queued sequential processing of all {len(file_groups)} file groups.")

        else:
            logger.info(f"DEBUG: No files - using _invoke_single with empty files list")
            # No files, use _invoke_single with empty files list
            await self._invoke_single(
                [], user_question, instructions, agent_requirements
            )

    async def process_files(self, file_paths: list) -> tuple[list, list]:
        """Process uploaded files into File objects and return (processed_files, errors)"""
        logger.info(f"DEBUG: process_files called with file_paths: {file_paths}")
        processed_files = []
        errors = []
        image_types = []
        data_types = []
        document_types = []

        for file_path in file_paths:
            logger.info(f"DEBUG: Processing file: {file_path}")
            file_obj = Path(file_path)

            # Check CSV files first
            if file_obj.suffix == ".csv":
                logger.info(f"DEBUG: Processing CSV file: {file_path}")
                # Test CSV file readability before adding to file_list
                try:
                    duckdb.sql(
                        f"SELECT * FROM read_csv('{file_path}', strict_mode=false, all_varchar=true) LIMIT 100000"
                    )
                    processed_files.append(
                        File(filepath=file_path, file_type="data", data_context="csv")
                    )
                    data_types.append("csv")
                    logger.info(f"CSV file {file_path} validated successfully")
                except Exception as e:
                    logger.error(f"CSV file {file_path} cannot be read: {e}")
                    errors.append(
                        f"The CSV file `{file_obj.name}` cannot be processed due to format issues. "
                        f"Error: {str(e)[:250]}..."
                    )
                continue

            # Check PDF files
            if file_obj.suffix == ".pdf":
                logger.info(f"DEBUG: Processing PDF file: {file_path}")
                # Process PDF - create simplified DocumentContext for now
                processed_files.append(
                    File(
                        filepath=file_path,
                        file_type="document",
                        document_context=DocumentContext(file_type="pdf"),
                    )
                )
                document_types.append("pdf")
                logger.info(f"DEBUG: document_types: {document_types}")
                continue

            # Try to read as text file with multiple encodings
            encodings_to_try = ["utf-8", "utf-16", "windows-1252"]
            text_processed = False
            for encoding in encodings_to_try:
                try:
                    Path(file_path).read_text(encoding=encoding)
                    logger.info(
                        f"DEBUG: Processing text file: {file_path} with encoding: {encoding}"
                    )
                    processed_files.append(
                        File(
                            filepath=file_path,
                            file_type="document",
                            document_context=DocumentContext(
                                file_type="text",
                                encoding=encoding,
                            ),
                        )
                    )
                    document_types.append("text")
                    text_processed = True
                    break  # Successfully read, exit the encoding loop
                except (UnicodeDecodeError, UnicodeError):
                    continue  # Try next encoding
                except OSError:
                    break  # File system error, don't try other encodings

            if text_processed:
                continue

            # Check if it's an image file
            if is_image(file_path)[0]:
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
                continue

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

        logger.info(
            f"DEBUG: process_files completed - processed_files: {len(processed_files)}, errors: {len(errors)}, instructions: {len(instructions)}"
        )
        return processed_files, errors, instructions

    async def determine_file_groups(self, user_question: str, files: list) -> list[list[str]]:
        """Determine how files should be grouped for processing"""
        if not files:
            return []
        elif len(files) == 1:
            return [files]  # Single group with all files
        else:
            # Use LLM to determine file groupings
            file_grouping_response = await self.llm.a_get_response(
                messages=[
                    {
                        "role": "user",
                        "content": f"User question/request:\n\n{user_question}\n\nFiles: {', '.join(files)}",
                    },
                    {
                        "role": "developer",
                        "content": "Restructure the files to a list of groups of files that need to be processed one by one. "
                        "By default, in case of doubt, there should only be one group with all the files in it. "
                        "If the user's question indicates that they want to process files independently from each other, looking for one response per file (as opposed to a single response using all files), "
                        "then by default, each group should contain only one file unless there is evidence to suggest otherwise. "
                        "In the case where the user specifically instructs to repeatedly use a particular file (for example) when processing other files one by one, the groups should reflect that and have the file repeat across groups.",
                    },
                ],
                model=self.model,
                temperature=0.0,
                response_format=FileGrouping,
            )
            return file_grouping_response.file_groups

    async def _invoke_single(
        self,
        files: list,
        user_question: str,
        instructions: list,
        agent_requirements: RequireAgent = None,
    ):
        """Invoke planner for single file, combined, or non-file processing - runs asynchronously in background"""
        logger.info(
            f"DEBUG: _invoke_single called with files: {files}, user_question: {user_question[:100]}..."
        )

        # Handle file processing if files are provided
        if files:
            logger.info(f"DEBUG: Processing files in _invoke_single: {files}")
            processed_files, errors, file_instructions = await self.process_files(files)
            logger.info(
                f"DEBUG: process_files returned - processed_files: {processed_files}, errors: {errors}"
            )

            if not processed_files:
                logger.error(
                    f"DEBUG: No processed files found, returning error message"
                )
                return "Unable to process any files. Errors encountered:\n" + "\n".join(
                    f"• {error}" for error in errors
                )

            logger.info(
                f"DEBUG: Combining instructions - base: {len(instructions)}, file: {len(file_instructions)}"
            )
            # Combine instructions
            all_instructions = instructions + file_instructions
        else:
            logger.info(f"DEBUG: No files case - using base instructions only")
            # No files case
            processed_files = None
            all_instructions = instructions

        logger.info(
            f"Conversation ID: {self.id}\nUser question: {user_question}\nInstructions: {"\n\n---\n\n".join(all_instructions)}"
        )

        logger.info(
            f"DEBUG: About to determine planner name - agent_requirements: {agent_requirements}"
        )
        # Determine planner name based on agent requirements
        planner_name = None
        if agent_requirements and agent_requirements.chilli_request:
            planner_name = "Chilli"
            logger.info(f"DEBUG: Set planner_name to Chilli")
        else:
            logger.info(f"DEBUG: Using default planner (no special name)")

        # Send "Agents assemble!" message first and capture its ID
        agents_assemble_message_id = self.add_message("assistant", "Agents assemble!")
        await self.send_assistant_message(
            "Agents assemble!", agents_assemble_message_id
        )

        logger.info(
            f"DEBUG: Creating planner using function-based approach with processed_files: {processed_files}"
        )

        # Create planner using function-based task queue system
        planner_id = uuid.uuid4().hex
        logger.info(f"DEBUG: Generated planner_id: {planner_id}")

        # Queue initial planning task with complete payload
        payload = {
            "user_question": user_question,
            "instruction": "\n\n---\n\n".join(all_instructions),
            "files": [
                f.model_dump() if hasattr(f, "model_dump") else f
                for f in processed_files
            ],
            "planner_name": planner_name,
            "message_id": agents_assemble_message_id,
            "router_id": self.id,
        }

        logger.info(f"DEBUG: Queuing initial planning task for planner {planner_id}")
        task_id = uuid.uuid4().hex
        success = self._agent_db.enqueue_task(
            task_id=task_id,
            entity_type="planner",
            entity_id=planner_id,
            function_name="execute_initial_planning",
            payload=payload,
        )

        if not success:
            logger.error(
                f"Failed to queue initial planning task for planner {planner_id}"
            )
            return

        logger.info(
            f"DEBUG: Successfully queued initial planning task for planner {planner_id}"
        )

        # Note: Planner execution now handled asynchronously by background processor
        # Frontend will poll for completion and call completion handler
        # No return value - planner runs in background

    # WebSocket communication methods
    async def send_user_message(self, content: str):
        """Send user message to frontend"""
        if self.websocket:
            await self.websocket.send_json(
                {
                    "type": "message",
                    "role": "user",
                    "content": content,
                    "router_id": self.id,
                }
            )

    async def send_status(self, status: str):
        """Send status update to frontend"""
        if self.websocket:
            await self.websocket.send_json(
                {"type": "status", "message": status, "router_id": self.id}
            )

    async def send_assistant_message(
        self, content: str, message_id: Optional[int] = None
    ):
        """Send assistant message to frontend"""
        if self.websocket:
            response_data = {
                "type": "response",
                "message": content,
                "router_id": self.id,
            }
            if message_id is not None:
                response_data["message_id"] = message_id
            await self.websocket.send_json(response_data)

    async def send_error(self, error: str):
        """Send error message to frontend"""
        if self.websocket:
            await self.websocket.send_json(
                {"type": "error", "message": error, "router_id": self.id}
            )

    async def send_message_history(self):
        """Send message history to frontend on connect"""
        if self.websocket:
            # Only send history if there are actual messages (excluding system messages)
            router_messages = [
                msg for msg in self.messages if msg.get("role") != "system"
            ]
            await self.websocket.send_json(
                {
                    "type": "message_history",
                    "messages": router_messages,
                    "router_id": self.id,
                }
            )

    async def send_input_lock(self):
        """Lock input for this specific router"""
        # Update router status to processing
        self.status = "processing"

        if self.websocket:
            await self.websocket.send_json(
                {
                    "type": "input_lock",
                    "router_id": self.id,
                }
            )

    async def send_input_unlock(self):
        """Unlock input for this specific router"""
        # Update router status back to active
        self.status = "active"

        if self.websocket:
            await self.websocket.send_json(
                {
                    "type": "input_unlock",
                    "router_id": self.id,
                }
            )

    async def handle_planner_completion(self, planner_id: str):
        """Handle completed planner - add response to message chain and send to frontend"""
        logger.info(f"Handling planner completion for planner {planner_id}")

        try:
            # Get planner data
            planner = self._agent_db.get_planner(planner_id)
            if not planner:
                logger.error(f"Planner {planner_id} not found")
                return

            user_response = planner.get("user_response")
            if not user_response:
                logger.error(
                    f"No user response found for completed planner {planner_id}"
                )
                return

            # Add to router's message chain
            self.add_message("assistant", user_response)

            # Send to frontend via WebSocket (if connected) - no message_id needed for final response
            if self.websocket:
                await self.send_assistant_message(user_response)
                logger.info(f"Sent planner completion response to frontend")
            else:
                logger.warning(
                    f"No WebSocket connection for router {self.id} - response not sent"
                )

            # Update router status back to active
            self.status = "active"

            logger.info(
                f"Successfully handled planner completion for planner {planner_id}"
            )

        except Exception as e:
            logger.error(
                f"Error handling planner completion for planner {planner_id}: {e}"
            )
            raise
