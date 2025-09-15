from pathlib import Path
from typing import Optional, Union, List, Dict, Any
from fastapi import WebSocket
from PIL import Image
from datetime import datetime, timezone
import asyncio
import logging
import uuid
import duckdb
from pydantic import BaseModel, Field
from ..config.settings import settings
from ..models import File, DocumentContext
from ..models.responses import RequireAgent
from ..models.schemas import FileGrouping, RouterMode
from ..models.agent_database import AgentDatabase, AgentType, Router
from sqlalchemy import select, update
from ..utils.image_utils import is_image, get_img_breakdown, encode_image
from ..services.llm_service import LLM
from ..tasks.task_utils import update_planner_next_task_and_queue
from ..tasks.message_manager import MessageManager
from .mcp_client import get_mcp_manager

logger = logging.getLogger(__name__)

# ========== PLAMARINATION CONFIGURATION ==========


def plamarination_tool_filter(server_name, tool):
    """Filter tools for plamarination phase."""
    if server_name == "filesystem":
        # Block only media reading - use our read_image instead
        return tool.name != "read_media_file"

    if server_name == "agent_tools":
        # Only research/analysis tools
        allowed = [
            "google_search",
            "get_facts_from_pdf",
            "read_image",
            "set_plan_and_answer",
        ]
        return tool.name in allowed

    # Block other servers during plamarination
    return False


PLAMARINATION_INSTRUCTION = f"""You are in Plamarination Phase. The definition of 'Plamarination' is the process of thoroughly researching and gathering all necessary information related to the user's request to be completely ready for the next phase which is Execution.

Today's date: {datetime.now().strftime('%Y-%m-%d')}

Your role consists of two distinct phases:

1. RESEARCH PHASE (Execute immediately during plamarination):
   - Read and analyse every uploaded file NOW
   - Extract all data and insights from documents NOW  
   - Search the web for any required context NOW
   - Ask the user for clarifications NOW
   All information gathering happens immediately in this phase.

2. PLANNING PHASE (Only after research complete):
   Create a plan containing exclusively:
   - Calculations using the data you've already extracted
   - Analysis based on facts you've already gathered
   - File writes/updates based on facts you've already gathered
   - Response formulation using information you've already collected
   Every plan step must reference concrete data you already possess.

File handling approach:
- Text files (.txt, .md, .json, .csv, etc): Use filesystem tools (read_file, read_text_file) immediately
- CSV files: Read 10 rows first to understand structure, then read all required data immediately
- Images: Use read_image tool from agent_tools immediately for complete analysis
- PDFs: Use get_facts_from_pdf tool from agent_tools to extract all relevant facts immediately

Research Completion Checklist - Verify all are TRUE before proceeding:
- [ ] Every mentioned file has been read and its contents are in your context
- [ ] Every external fact needed has been searched and retrieved
- [ ] Every clarification from the user has been obtained
- [ ] You can complete the user's request using only information currently in your possession
- [ ] Your plan will operate exclusively on concrete data you've already gathered

Continue researching until ALL items are verified TRUE.

Steps to execute:
1. Identify all information sources mentioned or needed
2. Execute immediate retrieval of ALL information from these sources one step at a time. In any one step only perform one action, such as reading a single file, searching the web about one question, or asking the user about a single question. Note, don't ever ask the user too many questions at once, guide them question by question to share their answer.
3. Continue gathering until you have concrete data for every aspect
4. Verify completeness using the Research Completion Checklist
5. Create a plan that operates solely on your gathered information
6. Use set_plan_and_answer tool with your data-backed plan

Important operational notes:
- Acknowledge user messages immediately if they appear during your work
- The execution phase has no user interaction, so gather all clarifications NOW
- Execute research tasks one at a time for thoroughness
- If the user asks you to write a summary of research to file during plamarination, this is acceptable as it documents your immediate findings

---

Examples of what should be done during research and what should be done during planning:

Research actions to execute immediately:
- When you see "analyse this data": Read the file NOW and extract all metrics
- When you need context about a topic: Search for it NOW and gather all facts
- When information seems missing: Ask the user NOW for clarification
- When you encounter a reference: Look it up NOW and understand it fully

Your final plan will then contain only:
- "Calculate the average using the 50 data points extracted from sales.csv"
- "Generate a summary combining the 3 key insights found about market trends"
- "Create a report using the competitor analysis data already collected"

"""


class PlamarinationContinuation(BaseModel):
    """Determine if plamarination should continue researching."""

    continue_research: bool = Field(
        description="True if mid-research/analysis/exploring files. False if assistant asked a question at the end or needs user clarification"
    )


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
            "agent_phase": loaded_state.get("agent_phase"),
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

    # Load agent_phase if present
    agent_phase = state.get("agent_phase")
    mode = state.get("mode", "auto")

    logger.info(
        f"Router {router_id} state loaded - model: {model}, temp: {temperature}, status: {status}, mode: {mode}, agent_phase: {agent_phase}"
    )

    return {
        "model": model,
        "temperature": temperature,
        "status": status,
        "mode": mode,
        "agent_phase": agent_phase,
    }


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

    # Set agent_phase if in agent mode
    if mode == "agent":
        # Default to plamarination phase when entering agent mode
        await agent_db.update_router(router_id=router_id, agent_phase="plamarination")
        router_state["agent_phase"] = "plamarination"
    else:
        router_state["agent_phase"] = None

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
        instruction_type="default",
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
        "form": "You must use the provided tool get_text_and_table_json_from_image to extract form fields and their values as a JSON string first before performing further actions. "
        "This must be a standalone task.",
        "diagram": "You must convert the diagram into mermaid code first before performing further actions.",
        "text": "You must use the provided tool get_text_and_table_json_from_image, read the text content as a JSON string first before performing further actions. "
        "This must be a standalone task.",
    },
    "document": {
        "pdf": "You must first use the provided tool get_facts_from_pdf to extract relevant facts in the form of question answer pairs from each document until there are no longer any unanswered questions (ie missing facts to answer the user's original question). "
        "Extracting from each file must be a standalone task.\n"
        "When compiling the final response, you must aggressively use in-line citations, and your answer should be in markdown format."
        "If the document(s) do not contain all necessary information, in other words there are still unanswered questions, you can search the web for information that can answer the user's question.",
        "text": "(No specific instructions)",
    },
    "non_file": {
        # Note: Web search is now handled through MCP tools (google_search) when enabled
        "web_search": "You should search the web for information that can answer the user's question. ",
    },
}


async def should_activate_agent_mode(router_state: Dict[str, Any]) -> bool:
    """
    Determine if auto mode should activate agent mode.

    Uses existing assess_agent_requirements to determine complexity.
    """
    # Use existing assess_agent_requirements
    agent_requirements = await assess_agent_requirements(router_state)

    # Check if any requirements are true
    boolean_requirements = [
        getattr(agent_requirements, field_name)
        for field_name, field_info in agent_requirements.__class__.model_fields.items()
        if field_info.annotation == bool and hasattr(agent_requirements, field_name)
    ]

    return any(boolean_requirements)


async def handle_message(
    router_state: Dict[str, Any], message_data: dict, websocket: WebSocket
):
    """
    Main message handler - routes based on status, mode, and phase.

    Critical: When status is "plamarinating", this function returns immediately
    to avoid double-triggering with auto-continuation.

    Args:
        router_state: Router state dictionary from create_router
        message_data: Message data containing 'message' and optional 'files'
        websocket: WebSocket connection for real-time communication
    """
    router_id = router_state["id"]
    message_manager = router_state["message_manager"]
    agent_db = router_state["agent_db"]

    # Input locking temporarily disabled - tracked in separate ticket
    # await send_input_lock(router_id=router_id, agent_db=agent_db, websocket=websocket)

    # Get current router state from database
    router_record = await agent_db.get_router(router_id)
    router_status = router_record.get("status") if router_record else "active"
    router_mode = router_state.get("mode", "auto")
    agent_phase = router_state.get("agent_phase")

    user_message = message_data.get("message", "")
    files = message_data.get("files", [])

    logger.info(
        f"Router {router_id} - mode: {router_mode}, phase: {agent_phase}, status: {router_status}"
    )
    logger.info(f"Message data type: {message_data.get('type', 'message')}")

    # Store user message
    await message_manager.add_message(role="user", content=user_message)

    try:
        # CRITICAL: Check status first to handle ongoing operations

        if router_status == "plamarinating":
            # DO NOT TRIGGER - auto-continuation is already running
            # Just acknowledge and return immediately
            logger.info(
                f"Proactive input during plamarination for router {router_id} - not triggering"
            )
            # Message is already added to chain, will be picked up by ongoing plamarination
            # No status message, just return

        elif router_status == "plamarinating_awaiting_user":
            # User provided required input - DO TRIGGER
            logger.info(
                f"Required user response received for router {router_id} - triggering plamarination"
            )
            await send_status(
                status="Processing your input", router_id=router_id, websocket=websocket
            )
            await agent_db.update_router(router_id=router_id, status="plamarinating")
            # Continue plamarination with user input
            await plamarination_response(router_state, websocket)

        elif router_status == "awaiting_approval":
            # Handle approval/revision of plan
            if message_data.get("type") == "approval_response":
                approved = message_data.get("approved", False)

                if approved:
                    # Move to execution
                    logger.info(
                        f"Plan approved for router {router_id}, starting execution"
                    )
                    await agent_db.update_router(
                        router_id=router_id, status="executing"
                    )
                    await send_status(
                        status="Executing approved plan",
                        router_id=router_id,
                        websocket=websocket,
                    )
                    # Execute the approved plan
                    await handle_complex_request(
                        router_state=router_state, websocket=websocket, files=files
                    )
                else:
                    # User wants revision
                    feedback = message_data.get("feedback", "")
                    logger.info(
                        f"Plan rejected for router {router_id}, continuing plamarination"
                    )

                    await agent_db.update_router(
                        router_id=router_id, status="plamarinating"
                    )
                    # Continue plamarination with feedback
                    await plamarination_response(router_state, websocket)
            else:
                # Regular message during awaiting_approval - treat as revision request
                logger.info(f"Message during awaiting_approval, treating as revision")
                await agent_db.update_router(
                    router_id=router_id, status="plamarinating"
                )
                await plamarination_response(router_state, websocket)

        elif router_status == "executing":
            # Currently executing - shouldn't receive messages
            logger.warning(f"Message received while executing for router {router_id}")
            await send_status(
                status="Currently executing. Please wait for completion.",
                router_id=router_id,
                websocket=websocket,
            )

        else:
            # Status is "active" - only valid for rapid/auto modes
            # Agent mode should NEVER have status="active"

            if router_mode == "agent":
                # This should never happen - agent mode toggles set status immediately
                raise ValueError(
                    f"Invalid state: Agent mode with status='active'. "
                    f"Router {router_id} is in agent mode but has active status. "
                    f"This indicates a bug in the mode/phase toggle handlers."
                )

            await send_status(
                status="Thinking", router_id=router_id, websocket=websocket
            )

            if router_mode == "rapid":
                # RAPID MODE: Always simple chat
                logger.info(f"RAPID mode: Using simple chat only")
                response = await handle_simple_chat(router_state=router_state)
                await message_manager.add_message(role="assistant", content=response)
                await send_assistant_message(
                    content=response, router_id=router_id, websocket=websocket
                )

            else:
                # AUTO MODE: Assess and decide
                logger.info(f"AUTO mode: Assessing complexity")

                # Check if we should activate agent mode
                if files or await should_activate_agent_mode(router_state):
                    # Complex request - start plamarination
                    logger.info(
                        f"AUTO mode: Complexity detected, switching to agent mode and starting plamarination"
                    )

                    # Update router to agent mode with plamarination phase
                    await agent_db.update_router(
                        router_id=router_id,
                        mode="agent",
                        agent_phase="plamarination",
                        status="plamarinating",
                    )

                    # Notify frontend of mode change
                    await websocket.send_json(
                        {
                            "type": "mode_updated",
                            "mode": "agent",
                            "router_id": router_id,
                        }
                    )

                    # Notify frontend of phase change
                    await websocket.send_json(
                        {
                            "type": "phase_updated",
                            "agent_phase": "plamarination",
                            "router_id": router_id,
                        }
                    )

                    await plamarination_response(router_state, websocket)
                else:
                    # Simple request - use simple chat
                    logger.info(f"AUTO mode: Simple request, using chat")
                    response = await handle_simple_chat(router_state=router_state)
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
        # Input unlocking temporarily disabled - tracked in separate ticket
        # await send_input_unlock(
        #     router_id=router_id, agent_db=agent_db, websocket=websocket
        # )
        pass


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
        router_id=router_id, instruction_type="default"
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
        router_id=router_id, instruction_type="default"
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


async def plamarination_response(router_state: Dict[str, Any], websocket: WebSocket):
    """
    Execute one iteration of plamarination (research/context gathering).
    Non-blocking - returns after single iteration, frontend orchestrates continuation.
    """
    router_id = router_state["id"]
    message_manager = router_state["message_manager"]
    agent_db = router_state["agent_db"]

    # Send thinking status for continuation calls (first entry already has it from handle_message)
    await send_status(status="Thinking", router_id=router_id, websocket=websocket)

    # Create LLM with MCP manager specifically for plamarination
    mcp_manager = await get_mcp_manager()
    llm = LLM(caller="router", mcp_manager=mcp_manager)

    messages = await message_manager.get_messages()

    try:
        # Get response (dict if tools called, string if not)
        response = await llm.a_get_response(
            messages=messages,
            model=settings.planner_model,
            temperature=0,  # Deterministic for plamarination
            use_tools=True,
            enable_web_search=True,  # Enable native web search for research phase
            tool_filter=plamarination_tool_filter,
            system_instruction=PLAMARINATION_INSTRUCTION,
            websocket=websocket,
            payload={"router_id": router_id},  # For hook context
        )

        # Extract content
        content = response["content"] if isinstance(response, dict) else response

        # Store message and get display texts
        result = await message_manager.add_message(
            role="assistant", content=content, need_message_id=True
        )
        message_id = result["message_id"]
        messages = result["messages"]
        display_texts = result["display_texts"]

        # Determine continuation based on response type
        if isinstance(response, dict):
            # Tools were called
            tool_calls = response["tool_calls"]

            # Check for set_plan_and_answer
            if "agent_tools__set_plan_and_answer" in tool_calls:
                # Hook handles approval flow and status update
                # The hook will send the appropriate WebSocket messages
                return

            # Other tools - must continue to process results
            continue_plamarination = True
            status = "plamarinating"

            # Send each display text as a separate WebSocket message
            for idx, text in enumerate(display_texts):
                await websocket.send_json(
                    {
                        "type": "response",
                        "message": text,
                        "message_id": message_id,
                        "router_id": router_id,
                    }
                )

        else:
            # No tools - simple text response (display_texts will have single entry)
            continuation = llm.get_response(
                messages=messages,  # Use returned messages with latest context
                model=settings.router_model,  # GPT-5-nano for fast decision
                temperature=0,
                response_format=PlamarinationContinuation,
            )

            # Defensive check - log and raise error if structured response fails
            if continuation is None:
                error_msg = (
                    f"Failed to get PlamarinationContinuation from LLM for router {router_id}. "
                    "This likely indicates a message format issue with the OpenAI API. "
                    "Check that message content is properly formatted for structured responses."
                )
                logger.error(error_msg)
                raise ValueError(error_msg)

            continue_plamarination = continuation.continue_research
            status = (
                "plamarinating"
                if continue_plamarination
                else "plamarinating_awaiting_user"
            )

            # Send single message (display_texts[0] is the text response)
            await websocket.send_json(
                {
                    "type": "response",
                    "message": display_texts[0] if display_texts else content,
                    "message_id": message_id,
                    "router_id": router_id,
                }
            )

        # Update status
        await agent_db.update_router(router_id=router_id, status=status)

        # Send continuation signal if needed
        if continue_plamarination:
            await websocket.send_json(
                {
                    "type": "continue_plamarination_signal",
                    "router_id": router_id,
                }
            )
        # No else needed - frontend already idle after receiving response

    except Exception as e:
        logger.error(f"Error in plamarination: {e}")
        await send_error(
            error=f"Error during plamarination: {str(e)}",
            router_id=router_id,
            websocket=websocket,
        )
        # Reset to active status on error
        await agent_db.update_router(router_id=router_id, status="active")


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
        # Use the new display-specific method for frontend
        agent_db = router_state["agent_db"]
        router_id = router_state["id"]

        # Get messages formatted for display (with display_text, filtered)
        display_messages = await agent_db.get_messages_for_display(
            agent_type="router", agent_id=router_id
        )

        try:
            await websocket.send_json(
                {
                    "type": "message_history",
                    "messages": display_messages,
                    "router_id": router_id,
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


async def send_mode_status(mode: str, router_id: str, websocket: WebSocket):
    """Send mode change status to frontend."""
    if not websocket:
        return

    try:
        await websocket.send_json(
            {
                "type": "mode_status",
                "mode": mode,
                "router_id": router_id,
                "message": f"Switched to {mode} mode",
            }
        )
        logger.info(f"Sent mode status update for router {router_id}: {mode}")
    except RuntimeError as e:
        if "close message has been sent" in str(e):
            logger.warning(f"WebSocket closed while sending mode status: {e}")
        else:
            raise


async def send_phase_status(phase: str, router_id: str, websocket: WebSocket):
    """Send phase change status to frontend."""
    if not websocket:
        return

    try:
        await websocket.send_json(
            {
                "type": "phase_status",
                "phase": phase,
                "router_id": router_id,
                "message": f"Switched to {phase} phase",
            }
        )
        logger.info(f"Sent phase status update for router {router_id}: {phase}")
    except RuntimeError as e:
        if "close message has been sent" in str(e):
            logger.warning(f"WebSocket closed while sending phase status: {e}")
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
            image_breakdown = get_img_breakdown(encode_image(file_path))
            if not image_breakdown.unreadable:
                processed_files.append(
                    File(
                        filepath=file_path,
                        file_type="image",
                        image_context=image_breakdown.elements,
                    )
                )
                image_types.extend(
                    [element.element_type for element in image_breakdown.elements]
                )
            else:
                errors.append(
                    f"Error processing image '{file_obj.name}': The image cannot be read. {image_breakdown.image_quality}"
                )
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
            router_id=router_id, instruction_type="default"
        )

        file_grouping_response = await router_state["llm"].a_get_response(
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": f"User question/request:\n\n{user_question}\n\nFiles: {', '.join(files)}",
                        },
                        {
                            "type": "text",
                            "text": "Restructure the files to a list of groups of files that need to be processed one by one. "
                            "By default, in case of doubt, there should only be one group with all the files in it. "
                            "If the user's question indicates that they want to process files independently from each other, looking for one response per file (as opposed to a single response using all files), "
                            "then by default, each group should contain only one file unless there is evidence to suggest otherwise. "
                            "In the case where the user specifically instructs to repeatedly use a particular file (for example) when processing other files one by one, the groups should reflect that and have the file repeat across groups.",
                        },
                    ],
                }
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
            router_id=router_id, instruction_type="default"
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
