"""
Async planner task functions for the function-based architecture.

This module contains all planner execution functions that are called by the
background task processor. Each function operates on a planner_id and manages
its state through the file system and database.
"""

import uuid
import logging
import duckdb
from pathlib import Path
from typing import Optional, List, Union
from PIL import Image
from datetime import datetime
from ..models.agent_database import AgentDatabase
from ..models import (
    InitialExecutionPlan,
    TableMeta,
    ColumnMeta,
    TOOLS,
    Task,
    ExecutionPlanModel,
)
from ..services.llm_service import LLM
from ..config.settings import settings
from ..config.agent_names import get_random_planner_name
from ..utils.execution_plan_converter import (
    initial_plan_to_execution_plan_model,
    execution_plan_model_to_markdown,
    get_next_action_task,
    has_pending_tasks,
)
from ..utils.tools import encode_image
from .file_manager import (
    save_planner_variable,
    save_planner_image,
    save_execution_plan_model,
    load_execution_plan_model,
    save_current_task,
    load_variable_from_file,
    load_image_from_file,
    cleanup_planner_files,
)
from .task_utils import update_planner_next_task_and_queue, queue_worker_task

logger = logging.getLogger(__name__)

llm = LLM(caller="planner")


def clean_table_name(input_string: str):
    """
    Clean input string to create a valid SQL table name.
    (Copied from planner.py to maintain consistency)
    """
    import re

    if not input_string:
        return "table"

    # Remove all non-alphanumeric and non-underscore characters
    cleaned = re.sub(r"[^a-zA-Z0-9]", " ", input_string)
    cleaned = (
        re.sub(r"\s+", " ", cleaned).strip().replace(" ", "_")
    )  # Collapse multiple spaces and trim

    # If string is empty after cleaning, return fallback
    if not cleaned:
        return "table"

    # Ensure first character is alphabetic
    if not cleaned[0].isalpha():
        cleaned = "table_" + cleaned
    try:
        duckdb.sql(f"create or replace temp view {cleaned} as select 1")
        return cleaned
    except:
        return f"table_{cleaned}"


def get_table_metadata(duck_conn, table_name: str):
    """Get table metadata for a DuckDB table"""
    # Get column information
    columns_info = duck_conn.sql(f"PRAGMA table_info('{table_name}')").fetchall()

    columns = []
    for col_info in columns_info:
        # col_info format: (cid, name, type, notnull, default_value, pk)
        column = ColumnMeta(
            name=col_info[1],
            data_type=col_info[2],
            nullable=not bool(col_info[3]),
            is_primary_key=bool(col_info[5]),
        )
        columns.append(column)

    # Get row count
    row_count = duck_conn.sql(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]

    return TableMeta(name=table_name, columns=columns, row_count=row_count)


async def execute_initial_planning(task_data: dict):
    """
    Execute initial planning phase - create planner and execution plan from user question.
    This creates a new planner and generates the initial execution plan.

    Args:
        task_data: Dict containing task information and payload with parameters:
            - entity_id: planner_id
            - payload: dict with user_question, instruction, files, planner_name, message_id, router_id

    """
    logger.info("Starting initial planning with new planner creation")

    # Extract parameters from task_data
    planner_id = task_data["entity_id"]
    payload = task_data.get("payload", {})

    # Check if this is a resume scenario (planner already exists)
    db = AgentDatabase()
    existing_planner = db.get_planner(planner_id) if planner_id else None

    if existing_planner:
        logger.info(
            f"Planner {planner_id} already exists - resuming execution, skipping initialisation"
        )
        # Queue next task: task creation (planner already initialised)
        update_planner_next_task_and_queue(planner_id, "execute_task_creation")
        return

    # New planner scenario - create new planner
    user_question = payload["user_question"]
    instruction = payload.get("instruction")
    files = payload.get("files", [])
    planner_name = payload.get("planner_name")
    message_id = payload.get("message_id")
    router_id = payload.get("router_id")

    # Create new planner ID if not provided
    if not planner_id:
        planner_id = uuid.uuid4().hex

    # Load settings
    model = settings.planner_model
    temperature = 0.0
    failed_task_limit = settings.failed_task_limit

    # Use random name if none provided
    if planner_name is None:
        planner_name = get_random_planner_name()

    try:
        # Create message-planner link BEFORE creating new planner
        if message_id and router_id:
            db.link_message_planner(
                router_id=router_id,
                message_id=message_id,
                planner_id=planner_id,
                relationship_type="initiated",
            )
            logger.info(
                f"Created message-planner link: message {message_id} -> planner {planner_id}"
            )

        # Create planner database record
        db.create_planner(
            planner_id=planner_id,
            planner_name=planner_name,
            user_question=user_question,
            instruction=instruction or "",
            model=model,
            temperature=temperature,
            failed_task_limit=failed_task_limit,
            status="planning",
            next_task="execute_task_creation",  # Set next task for continuation
        )

        # Initialize planner collections (following PlannerAgent.__init__ pattern)
        tables = []
        duck_conn = None

        # Create DuckDB database file path for persistence
        planner_dir = Path(settings.collaterals_base_path) / planner_id
        planner_dir.mkdir(parents=True, exist_ok=True)
        db_path = planner_dir / "database.db"

        # Add system message for new planners only (exact copy from PlannerAgent)
        db.add_message(
            agent_id=planner_id,
            agent_type="planner",
            role="system",
            content="You are an expert planner. Your objective is to break down the user's instruction into a list of tasks that can be individually executed.",
        )

        # Process files following the exact pattern from PlannerAgent.__init__
        if files:
            for f in files:
                if f.file_type == "image":
                    # Load image using encode_image function
                    encoded_image = encode_image(f.filepath)

                    # Save image with cleaned name (using collision avoidance)
                    raw_image_name = Path(f.filepath).stem
                    file_path, image_name = save_planner_image(
                        planner_id, raw_image_name, encoded_image, check_existing=True
                    )

                    # Update file object with cleaned name for message
                    f.filename = image_name

                    # Add message about image processing (exact copy from PlannerAgent)
                    db.add_message(
                        agent_id=planner_id,
                        agent_type="planner",
                        role="user",
                        content=f.model_dump_json(indent=2, include={"image_context"}),
                    )
                    logger.info(f"Processed image: {f.filepath} -> {image_name}")

                elif f.file_type == "data" and f.data_context == "csv":
                    # Create DuckDB file connection if needed
                    if duck_conn is None:
                        duck_conn = duckdb.connect(database=str(db_path))

                    # Create table from CSV (exact copy from PlannerAgent)
                    table_name = clean_table_name(Path(f.filepath).stem)
                    duck_conn.sql(
                        f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM read_csv('{f.filepath}',strict_mode=false)"
                    )

                    # Get table metadata
                    table_meta = get_table_metadata(duck_conn, table_name)
                    tables.append(table_meta)

                    # Add message about table creation (exact copy from PlannerAgent)
                    db.add_message(
                        agent_id=planner_id,
                        agent_type="planner",
                        role="user",
                        content=f"Data file `{f.filepath}` converted to table `{table_name}` in database. Below is table metadata:\n\n{table_meta.model_dump_json(indent=2)}",
                    )
                    logger.info(f"Created table {table_name} from CSV: {f.filepath}")

        # Close DuckDB connection after table creation
        if duck_conn:
            duck_conn.close()
            logger.info(f"Created DuckDB database at: {db_path}")

        # Save tables and files metadata to agent_metadata (not variables)
        metadata = {}
        if tables:
            metadata["tables"] = [table.model_dump() for table in tables]
        if files:
            metadata["files"] = [f.model_dump() for f in files]

        # Update planner with metadata
        if metadata:
            db.update_planner(planner_id, agent_metadata=metadata)

        # Create tools text (exact copy from PlannerAgent)
        tools_text = "\n\n---\n\n".join(
            [f"# {name}\n{tool.__doc__}" for name, tool in TOOLS.items()]
        )

        # Generate execution plan using structured format (exact copy from PlannerAgent)
        plan_prompt = (
            f"**Available tools for execution:**\n{tools_text}\n\n"
            f"**Instructions:**\n{instruction}\n\n"
            "Please create a detailed execution plan with an overall objective and a list of specific tasks. "
            "The objective should describe what the tasks are aiming to achieve. "
            "Each task should be specific enough to be executed independently. "
            "The instructions will no longer be visible when creating tasks later on, so make sure that the tasks are detailed enough. "
            "If required, create placeholder tasks that align to requirements in the instructions so it doesn't get lost even if you can't determine the precise downstream tasks yet."
        )

        # Get messages for LLM call
        messages = db.get_messages_by_agent_id(planner_id, "planner")

        # Get initial execution plan from LLM
        initial_plan = await llm.a_get_response(
            messages=messages + [{"role": "user", "content": plan_prompt}],
            model=model,
            temperature=temperature,
            response_format=InitialExecutionPlan,
        )

        # Convert to full ExecutionPlanModel
        execution_plan_model = initial_plan_to_execution_plan_model(initial_plan)

        # Generate markdown version
        execution_plan_markdown = execution_plan_model_to_markdown(execution_plan_model)

        # Update planner with execution plan
        db.update_planner(
            planner_id, execution_plan=execution_plan_markdown, status="executing"
        )

        # Save execution plan model to dedicated file
        save_execution_plan_model(planner_id, execution_plan_model)

        logger.info(f"Initial planning completed for planner {planner_id}")
        logger.info(f"Planner {planner_id}\nuser question: {user_question}")
        logger.info(f"Planner {planner_id}\ninstruction: {instruction}")
        logger.info(f"Planner {planner_id}\nexecution plan: {execution_plan_markdown}")

        # Queue next task: task creation
        update_planner_next_task_and_queue(planner_id, "execute_task_creation")

    except Exception as e:
        logger.error(f"Initial planning failed for planner {planner_id}: {e}")
        if "planner_id" in locals():
            db.update_planner(planner_id, status="failed")
        raise


async def execute_task_creation(task_data: dict):
    """
    Create and save new worker task based on execution plan.
    This phase generates a Task and saves it for worker initialisation.
    """
    planner_id = task_data["entity_id"]
    logger.info(f"Starting task creation for planner {planner_id}")

    db = AgentDatabase()
    planner_data = db.get_planner(planner_id)

    if not planner_data:
        logger.error(f"Planner {planner_id} not found")
        db.update_planner(planner_id, status="failed")
        return

    try:
        # Load execution plan model from dedicated file
        execution_plan_model = load_execution_plan_model(planner_id)
        # load_execution_plan_model already handles errors and raises exceptions

        # Check if there are pending tasks to create
        if not has_pending_tasks(execution_plan_model):
            logger.info(f"No pending tasks to create for planner {planner_id}")
            update_planner_next_task_and_queue(planner_id, "execute_completion_check")
            return

        # Get next task from execution plan
        next_task = get_next_action_task(execution_plan_model)
        if not next_task:
            # This should not be possible if has_pending_tasks returned True
            raise ValueError(
                f"No next task available despite having pending tasks for planner {planner_id}"
            )

        # Get planner messages for context
        messages = db.get_messages_by_agent_id(planner_id, "planner")

        # Create tools text for context
        tools_text = "\n\n---\n\n".join(
            [f"# {name}\n{tool.__doc__}" for name, tool in TOOLS.items()]
        )

        # Create task generation prompt (following PlannerAgent pattern)
        appending_msgs = [
            {
                "role": "developer",
                "content": f"You can use the following tools:\n\n{tools_text}",
            }
        ]

        # Add image keys if available
        image_file_paths = planner_data.get("image_file_paths", {})
        if image_file_paths:
            appending_msgs.append(
                {
                    "role": "developer",
                    "content": f"The following image keys are available for use: {list(image_file_paths.keys())}",
                }
            )

        # Add variable keys if available
        variable_file_paths = planner_data.get("variable_file_paths", {})
        if variable_file_paths:
            appending_msgs.append(
                {
                    "role": "developer",
                    "content": f"The following variable keys are available for use: {list(variable_file_paths.keys())}",
                }
            )

        # Add today's date
        today_date = datetime.now().strftime("%d %b %Y")
        appending_msgs.append(
            {
                "role": "developer",
                "content": f"Today's date is {today_date}.\n\n",
            }
        )

        appending_msgs.append(
            {
                "role": "developer",
                "content": f"For context, your complete execution plan is: {planner_data['execution_plan']}\n"
                f"The next todo item to be converted to a task is: {next_task.description}",
            }
        )

        # Generate task from LLM
        task = await llm.a_get_response(
            messages=messages + appending_msgs,
            model=planner_data["model"],
            temperature=planner_data["temperature"],
            response_format=Task,
        )

        logger.info(f"Task: {task.model_dump_json(indent=2)}")

        # Save task to dedicated file for worker initialisation
        save_current_task(planner_id, task)

        # Set next_task to waiting_for_worker (no queue - planner waits for worker completion)
        db.update_planner(planner_id, next_task="waiting_for_worker")

        # Queue worker initialisation (worker will load task and create FullTask)
        queue_worker_task(task.task_id, planner_id, "worker_initialisation")

        logger.info(
            f"Created and queued worker initialisation for task {task.task_id}, planner {planner_id}"
        )

    except Exception as e:
        logger.error(f"Task creation failed for planner {planner_id}: {e}")
        # Set planner as failed
        db.update_planner(planner_id, status="failed")
        raise


async def execute_synthesis(task_data: dict):
    """
    Process completed workers and merge their outputs back into planner state.
    This phase loads worker outputs, updates execution plan, and merges variables/images.
    Based on task_result_synthesis from original PlannerAgent.
    """
    planner_id = task_data["entity_id"]
    logger.info(f"Starting synthesis for planner {planner_id}")

    db = AgentDatabase()
    planner_data = db.get_planner(planner_id)

    if not planner_data:
        logger.error(f"Planner {planner_id} not found")
        return

    try:
        # Get all workers for this planner
        workers = db.get_workers_by_planner(planner_id)

        # Find completed workers that haven't been processed yet (status = 'completed' or 'failed_validation')
        completed_workers = [
            worker
            for worker in workers
            if worker["task_status"] in ["completed", "failed_validation"]
        ]

        if not completed_workers:
            logger.info(f"No completed workers to process for planner {planner_id}")
            # Queue next task: completion check
            update_planner_next_task_and_queue(planner_id, "execute_completion_check")
            return

        # Process each completed worker (following task_result_synthesis pattern)
        for worker in completed_workers:
            worker_id = worker["worker_id"]
            task_status = worker["task_status"]
            task_description = worker.get("task_description", "Unknown task")

            logger.info(f"Processing completed worker {worker_id}: {task_description}")

            # 1. Add worker response to planner messages (like original task_result_synthesis)
            worker_messages = db.get_messages_by_agent_id(worker_id, "worker")
            task_message_combined = "\n\n---\n\n".join(
                [
                    msg["content"]
                    for msg in worker_messages
                    if msg.get("role") == "assistant"
                ]
            )

            db.add_message(
                agent_id=planner_id,
                agent_type="planner",
                role="assistant",
                content=f"# Responses from worker\n\n"
                f"**Task ID**: {worker_id}\n\n"
                f"**Task Description**: {task_description}\n\n"
                f"**Task Status**: {task_status}\n\n"
                f"**Worker Responses**:\n\n{task_message_combined}",
            )

            # 2. Update execution plan with retry logic (simplified from original)
            try:
                execution_plan_model = load_execution_plan_model(planner_id)

                # Apply task completion logic (mark current next_action task as completed)
                if task_status == "completed":
                    for todo in execution_plan_model.todos:
                        if todo.next_action:
                            todo.completed = True
                            todo.next_action = False
                            break
                elif task_status == "failed_validation":
                    # For failed validation, don't mark as completed - leave for retry
                    logger.info(
                        f"Worker {worker_id} failed validation - task remains open for retry"
                    )

                # Get planner messages for LLM context
                messages = db.get_messages_by_agent_id(planner_id, "planner")

                # Create filtered model with only open todos for LLM
                open_todos = [
                    todo
                    for todo in execution_plan_model.todos
                    if not todo.completed and not todo.obsolete
                ]
                open_todos_model = ExecutionPlanModel(
                    objective=execution_plan_model.objective, todos=open_todos
                )

                # Update execution plan using LLM (simplified version)
                update_messages = messages + [
                    {
                        "role": "developer",
                        "content": f"**Current open tasks from execution plan:**\n\n{open_todos_model.model_dump_json(indent=2)}",
                    },
                    {
                        "role": "developer",
                        "content": f"Based on the completed task execution details above for task `{task_description}`, "
                        f"please update the execution plan. Instructions for reference:\n\n{planner_data.get('instruction', '')}\n\n"
                        "Follow these rules:\n"
                        "1. Update existing task descriptions using updated_description field if needed\n"
                        "2. Add new tasks if required, marking them with '(new)' in the description field\n"
                        "3. Leave next_action as False - separate logic will determine next action\n"
                        "4. Mark unnecessary tasks as obsolete=True\n"
                        "Return the updated ExecutionPlanModel with open tasks only.",
                    },
                ]

                # Get LLM response
                llm_updated_model = await llm.a_get_response(
                    messages=update_messages,
                    model=planner_data["model"],
                    temperature=planner_data["temperature"],
                    response_format=ExecutionPlanModel,
                )

                # Merge LLM output with completed/obsolete todos
                final_todos = []
                # Add completed/obsolete todos from original model
                for todo in execution_plan_model.todos:
                    if todo.completed or todo.obsolete:
                        final_todos.append(todo)

                # Add updated open todos from LLM
                for todo in llm_updated_model.todos:
                    if todo.updated_description.strip():
                        # Update description if provided
                        todo.description = todo.updated_description.strip()
                        todo.updated_description = ""
                    final_todos.append(todo)

                final_model = ExecutionPlanModel(
                    objective=execution_plan_model.objective, todos=final_todos
                )

                # Apply next action logic (like original _apply_next_action_logic)
                # Clear all next_action flags
                for todo in final_model.todos:
                    todo.next_action = False

                # Set first open todo as next_action
                has_next_action = False
                for todo in final_model.todos:
                    if not todo.completed and not todo.obsolete:
                        todo.next_action = True
                        has_next_action = True
                        break

                # Check if planner is complete (no open todos)
                if not has_next_action:
                    logger.info(
                        f"No more todos available for planner {planner_id} - generating final user response"
                    )

                    # Generate final user response (like original PlannerAgent completion)
                    planner_messages = db.get_messages_by_agent_id(
                        planner_id, "planner"
                    )

                    # Filter to get messages after initial system message (context_message_len equivalent)
                    user_response_messages = planner_messages[1:] + [
                        {
                            "role": "developer",
                            "content": "Using the above information only without creating any information, "
                            "either copy or create the response/answer to the user's original question/request and format the result in markdown.\n\n"
                            "Return only the markdown answer and nothing else, do not use the user's question as a title. Do not wrap the response in ```markdown ... ``` block. "
                            "Aggressively use inline citations such that the citing references (if provided) are used individually whenever possible as opposed to making multiple citations at the end. "
                            "Remember the user will only see the next response with zero visibility over the message history, so make sure the finalised response is repeated in full here.",
                        }
                    ]

                    # Generate final response using LLM
                    response = await llm.a_get_response(
                        messages=user_response_messages,
                        model=planner_data["model"],
                        temperature=planner_data["temperature"],
                    )
                    user_response = response.content.strip()
                    logger.info(f"User response generated in planner: {user_response}")

                    # Save final execution plan and mark planner as completed with user response
                    save_execution_plan_model(planner_id, final_model)
                    execution_plan_markdown = execution_plan_model_to_markdown(
                        final_model
                    )
                    db.update_planner(
                        planner_id,
                        execution_plan=execution_plan_markdown,
                        status="completed",
                        next_task="completed",
                        user_response=user_response,  # Store final response
                    )

                    # Mark worker as recorded and skip variable processing - no future tasks need them
                    db.update_worker_status(worker_id, "recorded")
                    logger.info(
                        f"Planner {planner_id} completed with user response generated"
                    )

                    # Clean up planner files since planning is complete
                    cleanup_success = cleanup_planner_files(planner_id)
                    if cleanup_success:
                        logger.info(
                            f"Successfully cleaned up files for completed planner {planner_id}"
                        )
                    else:
                        logger.warning(
                            f"Failed to clean up files for completed planner {planner_id}"
                        )

                    return  # Exit synthesis completely

                # Save updated execution plan (only if not completed)
                save_execution_plan_model(planner_id, final_model)
                execution_plan_markdown = execution_plan_model_to_markdown(final_model)
                db.update_planner(planner_id, execution_plan=execution_plan_markdown)

                logger.info(f"Execution plan updated for planner {planner_id}")

            except Exception as e:
                logger.error(
                    f"Error updating execution plan for planner {planner_id}: {e}"
                )
                # Continue with variable/image processing even if plan update fails

            # 3. Process output images and variables (like original task_result_synthesis)
            if task_status == "completed":
                # Merge worker output variables
                worker_output_vars = worker.get("output_variables", {})
                if worker_output_vars:
                    for key, file_path in worker_output_vars.items():
                        try:
                            # Load variable from worker's file
                            variable = load_variable_from_file(file_path)
                            if variable is not None:
                                # Save to planner's variable collection (with collision checking)
                                save_planner_variable(
                                    planner_id, key, variable, check_existing=True
                                )
                                logger.info(
                                    f"Merged worker variable '{key}' into planner {planner_id}"
                                )
                            else:
                                logger.warning(
                                    f"Failed to load worker variable '{key}' from {file_path}"
                                )
                        except Exception as e:
                            logger.error(
                                f"Error processing worker variable '{key}': {e}"
                            )

                # Merge worker output images
                worker_output_imgs = worker.get("output_images", {})
                if worker_output_imgs:
                    for key, file_path in worker_output_imgs.items():
                        try:
                            # Load image from worker's file
                            image = load_image_from_file(file_path)
                            if image is not None:
                                # Save to planner's image collection (with collision checking)
                                save_planner_image(
                                    planner_id, key, image, check_existing=True
                                )
                                logger.info(
                                    f"Merged worker image '{key}' into planner {planner_id}"
                                )
                            else:
                                logger.warning(
                                    f"Failed to load worker image '{key}' from {file_path}"
                                )
                        except Exception as e:
                            logger.error(f"Error processing worker image '{key}': {e}")
            elif task_status == "failed_validation":
                # Failed validation - don't process outputs, task will be retried
                logger.warning(
                    f"Worker {worker_id} failed validation - outputs not processed"
                )

            # 4. Mark worker as processed by updating its status to 'recorded'
            db.update_worker_status(worker_id, "recorded")
            logger.info(f"Marked worker {worker_id} as recorded")

        logger.info(f"Synthesis completed for planner {planner_id}")

        # Queue next task: task creation (to continue planning cycle)
        update_planner_next_task_and_queue(planner_id, "execute_task_creation")

    except Exception as e:
        logger.error(f"Synthesis failed for planner {planner_id}: {e}")
        db.update_planner(planner_id, status="failed")
        raise
