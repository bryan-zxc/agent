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
from ..models.schemas import FileGrouping, RouterMode
from ..models.agent_database import AgentDatabase, AgentType, Router
from sqlalchemy import select, update
from ..services.image_service import process_image_file, is_image
from ..services.llm_service import LLM
from ..tasks.task_utils import update_planner_next_task_and_queue
from ..tasks.message_manager import MessageManager
from ..utils.tools import encode_image, decode_image

logger = logging.getLogger(__name__)

# ========== STANDALONE FUNCTIONS (REFACTORED FROM RouterAgent) ==========


async def create_router(router_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Create or initialise a router instance.

    Args:
        router_id: Optional existing router ID to load. If None, creates new router.

    Returns:
        Dictionary containing router state:
        - id: Router ID
        - llm: LLM instance for this router
        - model: Model configuration
        - temperature: Temperature setting
        - agent_db: Database connection
        - message_manager: MessageManager instance (for existing routers only)
    """
    # Initialise LLM with "router" caller for tracking
    llm = LLM(caller="router")

    # Create database connection
    agent_db = await AgentDatabase.create()

    if router_id:
        # Load existing router state from database
        loaded_state = await load_existing_router_state(
            router_id=router_id, agent_db=agent_db
        )

        # Create MessageManager for existing router
        message_manager = MessageManager(
            db=agent_db, agent_type="router", agent_id=router_id
        )

        return {
            "id": router_id,
            "llm": llm,
            "model": loaded_state["model"],
            "temperature": loaded_state["temperature"],
            "mode": loaded_state.get("mode", "auto"),
            "agent_db": agent_db,
            "message_manager": message_manager,
        }
    else:
        # Create new router with UUID
        new_id = uuid.uuid4().hex
        return {
            "id": new_id,
            "llm": llm,
            "model": settings.router_model,
            "temperature": 0.0,
            "agent_db": agent_db,
            # MessageManager created in activate_conversation for new routers
        }


async def load_existing_router_state(
    router_id: str, agent_db: AgentDatabase
) -> Dict[str, Any]:
    """
    Load existing router state from database.

    Args:
        router_id: Router ID to load
        agent_db: Database connection

    Returns:
        Dictionary with loaded router configuration
    """
    state = await agent_db.get_router(router_id=router_id)
    if not state:
        raise ValueError(
            f"Router {router_id} not found in database - cannot load state"
        )

    # Extract configuration from database
    model = state.get("model") or settings.router_model
    temperature = (
        state.get("temperature") if state.get("temperature") is not None else 0.0
    )
    status = state.get("status")

    # Validate and set defaults if needed
    if status is None:
        logger.warning(
            f"Router {router_id} loaded with null status - setting to active"
        )
        await agent_db.update_router(router_id=router_id, status="active")
        status = "active"

    logger.info(
        f"Router {router_id} state loaded - model: {model}, temp: {temperature}, status: {status}"
    )

    return {"model": model, "temperature": temperature, "status": status}


def encode_image_content(
    content: Union[str, List], image: Union[str, Path, Image.Image]
) -> Union[str, List]:
    """
    Handle image encoding for message content.

    Args:
        content: Original content (string or list)
        image: Image to encode (path, PIL Image, or base64 string)

    Returns:
        Content with encoded image data
    """
    from ..utils.tools import encode_image

    image_data = {
        "type": "image_url",
        "image_url": {"url": f"data:image/png;base64,{encode_image(image)}"},
    }

    if content:
        if isinstance(content, str):
            # Convert string content to list format with text and image
            return [{"type": "text", "text": content}, image_data]
        else:
            # Append image to existing list content
            content.append(image_data)
            return content
    else:
        # No text content, just image
        return [image_data]


async def activate_conversation(
    user_message: str,
    websocket: WebSocket,
    files: Optional[List[str]] = None,
    mode: str = "auto",
) -> Dict[str, Any]:
    """
    Create and activate a new conversation.
    Combines router creation with initial message processing.

    Args:
        user_message: The user's initial message
        websocket: WebSocket connection for real-time communication
        files: Optional list of file paths to process
        mode: Router mode (auto, rapid, agent) - defaults to auto

    Returns:
        Router state dictionary from create_router
    """
    # Create new router
    router_state = await create_router()
    router_id = router_state["id"]
    agent_db = router_state["agent_db"]

    # Create title and preview from user message
    title = user_message[:30] if len(user_message) > 30 else user_message
    preview = user_message[:37] + "..." if len(user_message) > 40 else user_message

    # Create router record in database
    await agent_db.create_router(
        router_id=router_id,
        status="active",
        model=router_state["model"],
        temperature=router_state["temperature"],
        mode=mode,
        title=title,
        preview=preview,
    )

    # Create MessageManager for this new router
    message_manager = MessageManager(
        db=agent_db, agent_type="router", agent_id=router_id
    )
    router_state["message_manager"] = message_manager
    router_state["mode"] = mode

    # Store system instruction in satellite table
    system_instruction = (
        "Your name is Bandit Heeler, your main role is to have a conversation with the user and for complex requests activate agents. "
        "Now you maybe forced to be operating on rapid mode, in which case you will need to answer more complex questions yourself without agents. "
        "In such situations where you sense the question is complex, or requiring information that you don't have, remember to warn the user that your answers is not validated against any files or external sources, and may be incorrect. "
        "If they want a proper answer, they should either switch to auto or agent mode (note web searches, amongst other things) all need to be performed under agent mode). "
        "IMPORTANT: under rapid mode you CANNOT activate agent yourself, so you should ask the user to switch the toggle themselves, but be careful of the wording and don't make it sound like you can activate agent yourself. "
        "The toggle for mode switching is located just above the send button. "
        "By the way, you are a fictional character from the show Bluey."
    )
    await agent_db.set_router_system_instruction(
        router_id=router_id,
        system_instruction=system_instruction,
        instruction_type="default"
    )

    # Process the initial message
    message_data = {"message": user_message, "files": files or []}
    logger.info(f"DEBUG: activate_conversation called with files: {files}")
    logger.info(f"DEBUG: message_data prepared: {message_data}")

    # Handle the message
    await handle_message(
        router_state=router_state, message_data=message_data, websocket=websocket
    )

    return router_state


# Keep INSTRUCTION_LIBRARY as is
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


async def handle_message(
    router_state: Dict[str, Any], message_data: dict, websocket: WebSocket
):
    """
    Main message handler - processes user messages.

    Args:
        router_state: Router state dictionary from create_router
        message_data: Message data containing 'message' and optional 'files'
        websocket: WebSocket connection for real-time communication
    """
    router_id = router_state["id"]
    message_manager = router_state["message_manager"]

    # Lock input immediately
    await send_input_lock(
        router_id=router_id, agent_db=router_state["agent_db"], websocket=websocket
    )

    user_message = message_data.get("message", "")
    files = message_data.get("files", [])

    logger.info(f"DEBUG: handle_message called with files: {files}")
    logger.info(
        f"DEBUG: files type: {type(files)}, length: {len(files) if files else 'None'}"
    )

    # Store user message
    await message_manager.add_message(role="user", content=user_message)

    try:
        # Send processing status
        await send_status(status="Thinking", router_id=router_id, websocket=websocket)

        # Get router mode
        router_mode = router_state.get("mode", "auto")
        logger.info(f"Router {router_id} handling message in {router_mode} mode")

        # Determine response type based on mode
        if router_mode == "rapid":
            # RAPID mode: Always use simple chat, skip assessment
            logger.info(f"RAPID mode: Using simple chat only")
            response = await handle_simple_chat(router_state=router_state)
            await message_manager.add_message(role="assistant", content=response)
            await send_assistant_message(
                content=response, router_id=router_id, websocket=websocket
            )
        elif router_mode == "agent":
            # AGENT mode: Always use complex handling
            logger.info(f"AGENT mode: Forcing complex request handling")
            # First assess requirements even without files
            if not files:
                agent_requirements = await assess_agent_requirements(
                    router_state=router_state
                )
                # Force at least one requirement to be true to trigger complex handling
                agent_requirements.require_agent = True
            else:
                agent_requirements = None

            await handle_complex_request(
                router_state=router_state,
                websocket=websocket,
                files=files,
                agent_requirements=agent_requirements,
            )
        else:
            # AUTO mode: Original behaviour
            logger.info(
                f"AUTO mode: Checking if files exist - files: {files}, bool(files): {bool(files)}"
            )
            if files:
                logger.info(
                    f"AUTO mode: Taking complex request path with files: {files}"
                )
                await handle_complex_request(
                    router_state=router_state, websocket=websocket, files=files
                )
                # Complex request handles its own messaging - no response to send
            else:
                logger.info(f"AUTO mode: Taking simple chat path - no files provided")
                # Run assessment and simple chat concurrently to reduce wait time
                async with asyncio.TaskGroup() as tg:
                    assessment_task = tg.create_task(
                        assess_agent_requirements(router_state=router_state)
                    )
                    simple_chat_task = tg.create_task(
                        handle_simple_chat(router_state=router_state)
                    )

                agent_requirements = assessment_task.result()
                logger.info(
                    f"Agent requirements assessed for router {router_id}: {agent_requirements.model_dump_json(indent=2)}"
                )

                # Check if agent is needed
                boolean_requirements = [
                    getattr(agent_requirements, field_name)
                    for field_name, field_info in agent_requirements.__class__.model_fields.items()
                    if field_info.annotation == bool
                    and hasattr(agent_requirements, field_name)
                ]
                if any(boolean_requirements):
                    # We need complex handling - simple chat result is discarded
                    await handle_complex_request(
                        router_state=router_state,
                        websocket=websocket,
                        agent_requirements=agent_requirements,
                    )
                    # Complex request handles its own messaging
                else:
                    # Use the already completed simple chat response
                    response = simple_chat_task.result()
                    logger.info(f"Response generated in router:\n{response}")
                    # Store and send response for simple chat only
                    await message_manager.add_message(
                        role="assistant", content=response
                    )
                    await send_assistant_message(
                        content=response, router_id=router_id, websocket=websocket
                    )

    except Exception as e:
        logger.error(
            f"Error handling message in router {router_id}: {str(e)}", exc_info=True
        )
        await send_error(
            error=f"Error: {str(e)}", router_id=router_id, websocket=websocket
        )
    finally:
        # Always unlock input, even if processing failed
        await send_input_unlock(
            router_id=router_id, agent_db=router_state["agent_db"], websocket=websocket
        )


async def handle_simple_chat(router_state: Dict[str, Any]) -> str:
    """
    Handle simple conversational messages.

    Args:
        router_state: Router state dictionary containing llm, model, temperature, message_manager

    Returns:
        The LLM response content
    """
    message_manager = router_state["message_manager"]
    router_mode = router_state.get("mode", "auto")
    messages = await message_manager.get_messages()
    
    # Fetch system instruction from database
    agent_db = router_state["agent_db"]
    router_id = router_state["id"]
    system_instruction = await agent_db.get_router_system_instruction(
        router_id=router_id,
        instruction_type="default"
    )

    response = await router_state["llm"].a_get_response(
        messages=messages
        + [
            {
                "role": "user",
                "content": f"You are currently operating in {router_mode} mode.",
            }
        ],
        model=router_state["model"],
        temperature=router_state["temperature"],
        system_instruction=system_instruction,
    )
    return response.content


async def assess_agent_requirements(router_state: Dict[str, Any]) -> RequireAgent:
    """
    Use LLM to assess what type of agent assistance is needed.

    Args:
        router_state: Router state dictionary containing llm, model, message_manager

    Returns:
        RequireAgent object with assessment results
    """
    message_manager = router_state["message_manager"]
    messages = await message_manager.get_messages()
    
    # Fetch system instruction from database
    agent_db = router_state["agent_db"]
    router_id = router_state["id"]
    system_instruction = await agent_db.get_router_system_instruction(
        router_id=router_id,
        instruction_type="default"
    )

    assessment_messages = messages + [
        {
            "role": "user",
            "content": "Based on the conversation, are there any indicators that the user request requires agent assistance?",
        }
    ]

    response = await router_state["llm"].a_get_response(
        messages=assessment_messages,
        model=router_state["model"],
        temperature=0.0,
        response_format=RequireAgent,
        system_instruction=system_instruction,
    )

    return response


# ========== WEBSOCKET COMMUNICATION FUNCTIONS ==========


async def send_user_message(content: str, router_id: str, websocket: WebSocket):
    """Send user message to frontend"""
    if websocket:
        try:
            await websocket.send_json(
                {
                    "type": "message",
                    "role": "user",
                    "content": content,
                    "router_id": router_id,
                }
            )
        except RuntimeError as e:
            if "close message has been sent" in str(e):
                logger.warning(f"WebSocket closed while sending user message: {e}")
            else:
                raise


async def send_status(status: str, router_id: str, websocket: WebSocket):
    """Send status update to frontend"""
    if websocket:
        try:
            await websocket.send_json(
                {"type": "status", "message": status, "router_id": router_id}
            )
        except RuntimeError as e:
            if "close message has been sent" in str(e):
                logger.warning(f"WebSocket closed while sending status: {e}")
            else:
                raise


async def send_assistant_message(
    content: str, router_id: str, websocket: WebSocket, message_id: Optional[int] = None
):
    """Send assistant message to frontend"""
    # Debug logging for Agents assemble messages
    if content == "Agents assemble!":
        logger.info(
            f"DEBUG: send_assistant_message called with websocket={websocket is not None}, message_id={message_id}"
        )

    if websocket:
        response_data = {
            "type": "response",
            "message": content,
            "router_id": router_id,
        }
        if message_id is not None:
            response_data["message_id"] = message_id

        # Debug logging for Agents assemble messages
        if content == "Agents assemble!":
            logger.info(
                f"DEBUG: Sending Agents assemble WebSocket message: {response_data}"
            )

        try:
            await websocket.send_json(response_data)
        except RuntimeError as e:
            if "close message has been sent" in str(e):
                logger.warning(
                    f"WebSocket closed while sending assistant response: {e}"
                )
            else:
                raise
    else:
        # Debug logging when websocket is None
        if content == "Agents assemble!":
            logger.warning(
                f"DEBUG: Cannot send Agents assemble message - WebSocket is None!"
            )


async def send_error(error: str, router_id: str, websocket: WebSocket):
    """Send error message to frontend"""
    if websocket:
        try:
            await websocket.send_json(
                {"type": "error", "message": error, "router_id": router_id}
            )
        except RuntimeError as e:
            if "close message has been sent" in str(e):
                logger.warning(f"WebSocket closed while sending error: {e}")
            else:
                raise


async def send_message_history(router_state: Dict[str, Any], websocket: WebSocket):
    """Send message history to frontend on connect"""
    if websocket:
        message_manager = router_state["message_manager"]
        messages = await message_manager.get_messages()
        # Only send non-system messages
        router_messages = [msg for msg in messages if msg.get("role") != "system"]
        try:
            await websocket.send_json(
                {
                    "type": "message_history",
                    "messages": router_messages,
                    "router_id": router_state["id"],
                }
            )
        except RuntimeError as e:
            if "close message has been sent" in str(e):
                logger.warning(f"WebSocket closed while sending message history: {e}")
            else:
                raise


async def send_input_lock(
    router_id: str, agent_db: AgentDatabase, websocket: WebSocket
):
    """Lock input for this specific router"""
    # Update router status to processing
    await agent_db.update_router(router_id=router_id, status="processing")

    if websocket:
        try:
            await websocket.send_json(
                {
                    "type": "input_lock",
                    "router_id": router_id,
                }
            )
        except RuntimeError as e:
            if "close message has been sent" in str(e):
                logger.warning(f"WebSocket closed while sending input lock: {e}")
            else:
                raise


async def send_input_unlock(
    router_id: str, agent_db: AgentDatabase, websocket: WebSocket
):
    """Unlock input for this specific router"""
    # Update router status back to active
    await agent_db.update_router(router_id=router_id, status="active")

    if websocket:
        try:
            await websocket.send_json(
                {
                    "type": "input_unlock",
                    "router_id": router_id,
                }
            )
        except RuntimeError as e:
            if "close message has been sent" in str(e):
                logger.warning(f"WebSocket closed while sending input unlock: {e}")
            else:
                raise


async def handle_complex_request(
    router_state: Dict[str, Any],
    websocket: WebSocket,
    files: Optional[List[str]] = None,
    agent_requirements: Optional[RequireAgent] = None,
):
    """
    Handle complex requests requiring planner - runs asynchronously in background.

    Args:
        router_state: Router state dictionary
        websocket: WebSocket connection
        files: Optional list of file paths
        agent_requirements: Optional agent requirements from assessment
    """
    router_id = router_state["id"]
    message_manager = router_state["message_manager"]

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
        if agent_requirements.web_search_required:
            instructions.append(
                f"# Instructions for web search:\n\n{INSTRUCTION_LIBRARY.get('non_file').get('web_search', '')}"
            )
        user_question = agent_requirements.context_rich_agent_request
    else:
        logger.info(
            "DEBUG: Taking files-only path - calling LLM to summarise message history"
        )
        # Create a fresh message context for summarisation
        messages = await message_manager.get_messages()
        user_messages = [msg for msg in messages if msg.get("role") != "system"]
        
        # Use specialised system instruction for summarisation
        summarisation_instruction = (
            "Your sole job is to summarise the conversation into a context-rich request for the downstream agent. "
            "Use the latest message from the user as the basis and enrich the context directly associated with the question using the conversation history. "
            "Return only the context-rich request for the agent, do not include any other information such as prefixes or suffixes, do not ask for more information from the user."
        )
        
        response = await router_state["llm"].a_get_response(
            messages=user_messages,
            model=router_state["model"],
            temperature=router_state["temperature"],
            system_instruction=summarisation_instruction,
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
        file_groups = await determine_file_groups(
            router_state=router_state, user_question=user_question, files=files
        )
        logger.info(f"DEBUG: File groups determined: {file_groups}")

        # Process each file group sequentially
        for i, file_group in enumerate(file_groups, 1):
            if len(file_groups) > 1:
                await send_status(
                    f"Processing file group {i}/{len(file_groups)}: {', '.join(file_group)}",
                    router_id,
                    websocket,
                )
            else:
                logger.info(
                    f"DEBUG: Processing single file group with files: {file_group}"
                )

            # Start background task for this file group
            await invoke_single(
                router_state=router_state,
                files=file_group,
                user_question=user_question,
                instructions=instructions,
                websocket=websocket,
                agent_requirements=agent_requirements,
            )
            logger.info(
                f"DEBUG: File group {i} planner queued for background processing"
            )

        # All file groups processed sequentially
        logger.info(
            f"Queued sequential processing of all {len(file_groups)} file groups."
        )
    else:
        logger.info("DEBUG: No files - using invoke_single with empty files list")
        # No files, use invoke_single with empty files list
        await invoke_single(
            router_state=router_state,
            files=[],
            user_question=user_question,
            instructions=instructions,
            websocket=websocket,
            agent_requirements=agent_requirements,
        )


# ========== UTILITY FUNCTIONS ==========


async def process_files(
    file_paths: List[str],
) -> tuple[List[File], List[str], List[str]]:
    """
    Process uploaded files into File objects.

    Args:
        file_paths: List of file paths to process

    Returns:
        Tuple of (processed_files, errors, instructions)
    """
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
            # Test CSV file readability before adding
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


async def determine_file_groups(
    router_state: Dict[str, Any], user_question: str, files: List[str]
) -> List[List[str]]:
    """
    Determine how files should be grouped for processing.

    Args:
        router_state: Router state dictionary
        user_question: User's question
        files: List of file paths

    Returns:
        List of file groups
    """
    if not files:
        return []
    elif len(files) == 1:
        return [files]  # Single group with all files
    else:
        # Use LLM to determine file groupings
        # Fetch router's system instruction for context
        agent_db = router_state["agent_db"]
        router_id = router_state["id"]
        base_system_instruction = await agent_db.get_router_system_instruction(
            router_id=router_id,
            instruction_type="default"
        )
        
        file_grouping_response = await router_state["llm"].a_get_response(
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
            model=router_state["model"],
            temperature=0.0,
            response_format=FileGrouping,
            system_instruction=base_system_instruction,
        )
        return file_grouping_response.file_groups


async def invoke_single(
    router_state: Dict[str, Any],
    files: List[str],
    user_question: str,
    instructions: List[str],
    websocket: WebSocket,
    agent_requirements: Optional[RequireAgent] = None,
):
    """
    Invoke planner for single file, combined, or non-file processing.

    Args:
        router_state: Router state dictionary
        files: List of file paths
        user_question: User's question
        instructions: Processing instructions
        websocket: WebSocket connection
        agent_requirements: Optional agent requirements
    """
    router_id = router_state["id"]
    message_manager = router_state["message_manager"]
    agent_db = router_state["agent_db"]

    logger.info(
        f"DEBUG: invoke_single called with files: {files}, user_question: {user_question[:100]}..."
    )

    # Handle file processing if files are provided
    if files:
        logger.info(f"DEBUG: Processing files in invoke_single: {files}")
        processed_files, errors, file_instructions = await process_files(files)
        logger.info(
            f"DEBUG: process_files returned - processed_files: {processed_files}, errors: {errors}"
        )

        if not processed_files:
            logger.error("DEBUG: No processed files found, returning error message")
            return "Unable to process any files. Errors encountered:\n" + "\n".join(
                f"• {error}" for error in errors
            )

        logger.info(
            f"DEBUG: Combining instructions - base: {len(instructions)}, file: {len(file_instructions)}"
        )
        # Combine instructions
        all_instructions = instructions + file_instructions
    else:
        logger.info("DEBUG: No files case - using base instructions only")
        processed_files = None
        all_instructions = instructions

    logger.info(
        f"Conversation ID: {router_id}\nUser question: {user_question}\nInstructions: {'\n\n---\n\n'.join(all_instructions)}"
    )

    logger.info(
        f"DEBUG: About to determine planner name - agent_requirements: {agent_requirements}"
    )
    # Determine planner name based on agent requirements
    planner_name = None
    if agent_requirements and agent_requirements.chilli_request:
        planner_name = "Chilli"
        logger.info("DEBUG: Set planner_name to Chilli")
    else:
        logger.info("DEBUG: Using default planner (no special name)")

    # Send "Agents assemble!" message first and capture its ID
    result = await message_manager.add_message(
        role="assistant", content="Agents assemble!", need_message_id=True
    )
    agents_assemble_message_id = result["message_id"]
    logger.info(
        f"DEBUG: Agents assemble message_id from add_message: {agents_assemble_message_id} (type: {type(agents_assemble_message_id)})"
    )
    logger.info(
        f"DEBUG: WebSocket parameter is: {websocket} (None: {websocket is None})"
    )
    await send_assistant_message(
        "Agents assemble!",
        router_id,
        websocket,
        agents_assemble_message_id,
    )

    logger.info(
        f"DEBUG: Creating planner using function-based approach with processed_files: {processed_files}"
    )

    # Create planner using function-based task queue system
    planner_id = uuid.uuid4().hex
    logger.info(f"DEBUG: Generated planner_id: {planner_id}")

    # Prepare files for payload - handle None case
    if processed_files is None:
        files = []
    else:
        files = [
            f.model_dump() if hasattr(f, "model_dump") else f for f in processed_files
        ]

    # Queue initial planning task with complete payload
    payload = {
        "user_question": user_question,
        "instruction": "\n\n---\n\n".join(all_instructions),
        "files": files,
        "planner_name": planner_name,
        "message_id": agents_assemble_message_id,
        "router_id": router_id,
    }

    logger.info(f"DEBUG: Queuing initial planning task for planner {planner_id}")
    task_id = uuid.uuid4().hex
    success = await agent_db.enqueue_task(
        task_id=task_id,
        entity_type="planner",
        entity_id=planner_id,
        function_name="execute_initial_planning",
        payload=payload,
    )

    if not success:
        logger.error(f"Failed to queue initial planning task for planner {planner_id}")
        return

    logger.info(
        f"DEBUG: Successfully queued initial planning task for planner {planner_id}"
    )

    # Note: Planner execution now handled asynchronously by background processor


async def generate_and_update_title(router_state: Dict[str, Any]):
    """
    Generate LLM title using existing message chain and update database.

    Args:
        router_state: Router state dictionary
    """
    try:
        message_manager = router_state["message_manager"]
        agent_db = router_state["agent_db"]
        router_id = router_state["id"]

        # Get the first user message to check length
        messages = await message_manager.get_messages()
        user_messages = [msg for msg in messages if msg.get("role") == "user"]
        if not user_messages or len(user_messages[0]["content"]) <= 30:
            return

        # Use the entire message history to generate a title
        title_messages = messages + [
            {
                "role": "user",
                "content": "Create a succinct title for this conversation. "
                "In the response, only provide the title and nothing else. "
                "Keep the title under 30 characters.",
            }
        ]

        # Fetch router's system instruction
        system_instruction = await agent_db.get_router_system_instruction(
            router_id=router_id,
            instruction_type="default"
        )
        
        response = await router_state["llm"].a_get_response(
            messages=title_messages,
            model=router_state["model"],
            temperature=router_state["temperature"],
            system_instruction=system_instruction,
        )
        llm_title = response.content.strip()

        # Update title in database
        await agent_db.update_router(router_id=router_id, title=llm_title)
        logger.info(f"Updated title for router {router_id}: {llm_title}")

    except Exception as e:
        # Log error but don't fail
        logger.error(f"Failed to generate LLM title for {router_state['id']}: {e}")


async def handle_planner_completion(
    router_state: Dict[str, Any], planner_id: str, websocket: WebSocket
):
    """
    Handle completed planner - add response to message chain and send to frontend.

    Args:
        router_state: Router state dictionary
        planner_id: ID of the completed planner
        websocket: WebSocket connection
    """
    router_id = router_state["id"]
    message_manager = router_state["message_manager"]
    agent_db = router_state["agent_db"]

    logger.info(f"Handling planner completion for planner {planner_id}")

    try:
        # Get planner data
        planner = await agent_db.get_planner(planner_id=planner_id)
        if not planner:
            logger.error(f"Planner {planner_id} not found")
            return

        user_response = planner.get("user_response")
        if not user_response:
            logger.error(f"No user response found for completed planner {planner_id}")
            return

        # Add to router's message chain
        await message_manager.add_message(role="assistant", content=user_response)

        # Send to frontend via WebSocket (if connected)
        if websocket:
            await send_assistant_message(
                content=user_response, router_id=router_id, websocket=websocket
            )
            logger.info("Sent planner completion response to frontend")
        else:
            logger.warning(
                f"No WebSocket connection for router {router_id} - response not sent"
            )

        # Update router status back to active
        await agent_db.update_router(router_id=router_id, status="active")

        logger.info(f"Successfully handled planner completion for planner {planner_id}")

    except Exception as e:
        logger.error(f"Error handling planner completion for planner {planner_id}: {e}")
        raise


# ========== END OF ROUTER OPERATIONS MODULE ==========

# Note: RouterAgent class has been completely removed in favour of standalone functions
# All functionality is now available through the functions above
