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
    SingleValueColumn,
    TOOLS,
    Task,
    ExecutionPlanModel,
    TaskResponseModel,
    AnswerTemplate,
    File,
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
    save_answer_template,
    save_wip_answer_template,
    load_answer_template,
    load_wip_answer_template,
    load_execution_plan_model,
    save_current_task,
    load_variable_from_file,
    load_image_from_file,
    cleanup_planner_files,
    append_to_worker_message_history,
    load_worker_message_history,
)
from .task_utils import update_planner_next_task_and_queue, queue_worker_task
from .message_manager import MessageManager

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


def clean_column_name(input_string: str, column_index: int, existing_columns: list):
    """
    Clean input string to create a valid SQL column name.
    Handles collisions by appending column index if needed.
    """
    import re

    if not input_string:
        return f"column_{column_index}"

    # Remove all non-alphanumeric and non-underscore characters
    cleaned = re.sub(r"[^a-zA-Z0-9]", " ", input_string)
    cleaned = (
        re.sub(r"\s+", " ", cleaned).strip().replace(" ", "_")
    )  # Collapse multiple spaces and trim

    # If string is empty after cleaning, return fallback
    if not cleaned:
        cleaned = f"column_{column_index}"

    # Ensure first character is alphabetic
    if not cleaned[0].isalpha():
        cleaned = "col_" + cleaned

    # Handle collisions with existing column names
    original_cleaned = cleaned
    counter = 1
    while cleaned in existing_columns:
        cleaned = f"{original_cleaned}_{counter}"
        counter += 1

    return cleaned


def get_table_metadata(duck_conn, table_name: str) -> TableMeta:
    """Get comprehensive table metadata for a DuckDB table"""
    # Get basic table info
    row_count = duck_conn.sql(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]

    # Get column names and types
    columns_info = duck_conn.sql(f"DESCRIBE {table_name}").fetchall()
    total_columns = len(columns_info)
    columns_new = []
    column_metas = []
    single_value_columns = []
    selected_columns = []  # Track columns that will be included in final output
    current_metadata_length = (
        len(table_name) + 100
    )  # Base overhead (will add top_10_md length later)

    for i, col in enumerate(columns_info):
        col_name = clean_column_name(col[0], i, columns_new)
        columns_new.append(col_name)
        if col_name != col[0]:
            duck_conn.sql(
                f'ALTER TABLE {table_name} RENAME COLUMN "{col[0]}" TO {col_name}'
            )
        if col[1].startswith("VARCHAR"):
            duck_conn.sql(
                f"UPDATE {table_name} SET {col_name} = LTRIM(RTRIM({col_name}))"
            )

        # Check if column is completely blank/null/whitespace
        non_empty_count = duck_conn.sql(
            f"""
            SELECT COUNT(*) FROM {table_name} 
            WHERE {col_name} IS NOT NULL 
            AND LTRIM(RTRIM(CAST({col_name} AS VARCHAR))) != ''
            """
        ).fetchone()[0]

        if non_empty_count == 0:
            # Skip completely empty columns
            continue

        # Check if column has only one distinct non-null value
        distinct_values = duck_conn.sql(
            f"""
            SELECT DISTINCT ifnull(LTRIM(RTRIM(CAST({col_name} AS VARCHAR))),'') FROM {table_name}
            """
        ).fetchall()

        if len(distinct_values) == 1:
            # Single value column - add to single_value_columns list
            single_value_column = SingleValueColumn(
                column_name=col_name,
                only_value_in_column=str(distinct_values[0][0]),
            )
            single_value_columns.append(single_value_column)
            continue

        # Calculate percentage of distinct values
        distinct_count = duck_conn.sql(
            f"SELECT COUNT(DISTINCT {col_name}) FROM {table_name}"
        ).fetchone()[0]
        pct_distinct = (distinct_count / row_count) if row_count > 0 else 0

        # Get min and max values
        min_max = duck_conn.sql(
            f"SELECT MIN({col_name}), MAX({col_name}) FROM {table_name}"
        ).fetchone()
        min_value = str(min_max[0]) if min_max[0] is not None else ""
        max_value = str(min_max[1]) if min_max[1] is not None else ""

        # Get top 3 most frequent values
        top_3_result = duck_conn.sql(
            f"""
            SELECT {col_name}, COUNT(*) as freq 
            FROM {table_name} 
            WHERE {col_name} IS NOT NULL
            GROUP BY {col_name} 
            ORDER BY freq DESC 
            LIMIT 3
        """
        ).fetchall()

        top_3_values = {str(value): freq for value, freq in top_3_result}

        column_meta = ColumnMeta(
            column_name=col_name,
            pct_distinct=round(pct_distinct, 2),
            min_value=min_value,
            max_value=max_value,
            top_3_values=top_3_values,
        )
        column_metas.append(column_meta)
        selected_columns.append(col_name)  # Track this column for top 10 query

        # Estimate metadata length for this column (rough approximation)
        column_meta_str = column_meta.model_dump_json()
        current_metadata_length += len(column_meta_str)

        # Check if adding this column would exceed the character limit
        if current_metadata_length > 100000:
            # Skip remaining columns to stay under limit
            break

    # Generate top 10 rows markdown using only the selected columns
    if selected_columns:
        selected_columns_str = ", ".join(selected_columns)
        top_10_md = (
            duck_conn.sql(
                f"SELECT {selected_columns_str} FROM {table_name} LIMIT 10"
            )
            .df()
            .to_markdown(index=False)
        )
    else:
        # Fallback if no columns were selected (shouldn't happen in normal cases)
        top_10_md = "No columns available for display"

    return TableMeta(
        table_name=table_name,
        row_count=row_count,
        top_10_md=top_10_md,
        columns=column_metas,
        single_value_columns=single_value_columns,
        total_columns=total_columns,
    )


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
    existing_planner = await db.get_planner(planner_id) if planner_id else None

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
    # Convert dictionary files back to File objects, filtering None values to allow Pydantic defaults
    cleaned_files = []
    for f in files:
        if isinstance(f, dict):
            # Remove None values so Pydantic can use default values (e.g., image_context = [])
            cleaned_f = {k: v for k, v in f.items() if v is not None}
            cleaned_files.append(File.model_validate(cleaned_f))
        else:
            cleaned_files.append(f)
    files = cleaned_files
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
            await db.link_message_planner(
                router_id=router_id,
                message_id=message_id,
                planner_id=planner_id,
                relationship_type="initiated",
            )
            logger.info(
                f"Created message-planner link: message {message_id} -> planner {planner_id}"
            )

        # Create planner database record
        await db.create_planner(
            planner_id=planner_id,
            planner_name=planner_name,
            user_question=user_question,
            instruction=instruction or "",
            model=model,
            temperature=temperature,
            failed_task_limit=failed_task_limit,
            status="planning",
            next_task="execute_initial_planning",  # Current task for restart/resumability
        )

        # Create message manager for this planner (now that planner exists)
        message_manager = MessageManager(db, "planner", planner_id)

        # Initialize messages variable for consistent state tracking
        messages = await message_manager.get_messages()

        # Initialize planner collections (following PlannerAgent.__init__ pattern)
        tables = []
        duck_conn = None

        # Create DuckDB database file path for persistence
        planner_dir = Path(settings.collaterals_base_path) / planner_id
        planner_dir.mkdir(parents=True, exist_ok=True)
        db_path = planner_dir / "database.db"

        # Add system message for new planners only (exact copy from PlannerAgent)
        messages = await message_manager.add_message(
            role="system",
            content="You are an expert planner. "
            "Your objective is to break down the user's instruction into a list of tasks that can be individually executed."
            "Keep in mind that quite often the first step(s) are to extra facts which commonly comes in the form of question and answer pairs. "
            "Even if there are no further unanswered questions, it only means you have all the facts required to answer the user's question, it doesn't always mean the process is complete. "
            "If there still are analysis especially calculations that is required to be applied to the facts, then you need to create further tasks to complete. "
            "Typically facts are pre-extracted and likely to be in the form of question and answer pairs, "
            "if the questions don't seem to be fully aligned to what is required for analysis, you can activate relevant tools to re-extract facts. ",
        )

        # Add user question to planner message history so it has user context for answer template creation
        messages = await message_manager.add_message(
            role="user",
            content=user_question,
        )

        # Process files following the exact pattern from PlannerAgent.__init__
        if files:
            for f in files:
                if f.file_type == "image":
                    # Load image using encode_image function
                    encoded_image = encode_image(f.filepath)

                    # Save image with cleaned name (using collision avoidance)
                    raw_image_name = Path(f.filepath).stem
                    _, image_name = save_planner_image(
                        planner_id, raw_image_name, encoded_image, check_existing=True
                    )

                    # Update file object with cleaned name for message
                    f.filename = image_name

                    # Add message about image processing (exact copy from PlannerAgent)
                    messages = await message_manager.add_message(
                        role="user",
                        content=f.model_dump_json(indent=2, include={"image_context"}),
                    )
                    logger.info(f"Processed image: {f.filepath} -> {image_name}")

                elif f.file_type == "data" and f.data_context == "csv":
                    # Create DuckDB file connection if needed
                    if duck_conn is None:
                        duck_conn = duckdb.connect(database=str(db_path))

                    # Create table from CSV with fallback to all_varchar on failure
                    table_name = clean_table_name(Path(f.filepath).stem)
                    try:
                        # First attempt: normal CSV reading
                        duck_conn.sql(
                            f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM read_csv('{f.filepath}',strict_mode=false)"
                        )
                        logger.info(
                            f"Created table {table_name} from CSV: {f.filepath}"
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to create table {table_name} with normal CSV read, trying all_varchar: {e}"
                        )
                        try:
                            # Fallback: try with all_varchar=true
                            duck_conn.sql(
                                f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM read_csv('{f.filepath}',strict_mode=false,all_varchar=true)"
                            )
                            logger.info(
                                f"Created table {table_name} from CSV using all_varchar fallback: {f.filepath}"
                            )
                        except Exception as e2:
                            logger.error(
                                f"Failed to create table {table_name} even with all_varchar: {e2}"
                            )
                            # Add error message instead of table creation message
                            await message_manager.add_message(
                                role="user",
                                content=f"CSV file `{f.filepath}` could not be processed into a database table. Error: {str(e2)}",
                            )
                            continue  # Skip metadata processing for failed CSV

                    # Get table metadata
                    table_meta = get_table_metadata(duck_conn, table_name)
                    tables.append(table_meta)

                    # Add message about table creation (exact copy from PlannerAgent)
                    await message_manager.add_message(
                        role="user",
                        content=f"Data file `{f.filepath}` converted to table `{table_name}` in database. Below is table metadata:\n\n{table_meta.model_dump_json(indent=2)}",
                    )

                elif (
                    f.file_type == "document" and f.document_context.file_type == "text"
                ):
                    # Read the text file content using the stored encoding
                    try:
                        text_content = Path(f.filepath).read_text(
                            encoding=f.document_context.encoding
                        )
                        # Limit to first 1 million characters
                        limited_content = text_content[:1000000]
                        if len(text_content) > 1000000:
                            limited_content += "...\n\n[Content truncated to first 1 million characters]"

                        await message_manager.add_message(
                            role="user",
                            content=f"Text file `{Path(f.filepath).name}` contains the following content:\n\n{limited_content}",
                        )
                        logger.info(
                            f"Processed text file: {f.filepath} with encoding {f.document_context.encoding}"
                        )
                    except Exception as e:
                        await message_manager.add_message(
                            role="user",
                            content=f"Text file `{Path(f.filepath).name}` could not be read with encoding `{f.document_context.encoding}`. Error: {str(e)}",
                        )
                        logger.error(f"Failed to read text file {f.filepath}: {e}")

                elif (
                    f.file_type == "document" and f.document_context.file_type == "pdf"
                ):
                    # Add message about PDF file being available for processing
                    await message_manager.add_message(
                        role="user",
                        content=f"PDF document `{Path(f.filepath).name}` is available for processing at: {f.filepath}",
                    )
                    logger.info(f"Registered PDF file for processing: {f.filepath}")

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
            await db.update_planner(planner_id, agent_metadata=metadata)

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
        messages = await message_manager.get_messages()

        # Get initial execution plan from LLM
        initial_plan = await llm.a_get_response(
            messages=messages + [{"role": "developer", "content": plan_prompt}],
            model=model,
            temperature=temperature,
            response_format=InitialExecutionPlan,
        )

        # Convert to full ExecutionPlanModel
        execution_plan_model = initial_plan_to_execution_plan_model(initial_plan)

        # Generate markdown version
        execution_plan_markdown = execution_plan_model_to_markdown(execution_plan_model)

        # Update planner with execution plan
        await db.update_planner(
            planner_id, execution_plan=execution_plan_markdown, status="executing"
        )

        # Save execution plan model to dedicated file
        save_execution_plan_model(planner_id, execution_plan_model)

        # Create initial answer template
        messages = await message_manager.get_messages()
        logger.info(
            f"DEBUG: Retrieved {len(messages)} messages for planner {planner_id}"
        )

        answer_template_prompt = (
            "Based on the information so far, produce a first cut template in Markdown format to provide the final answer to the user's question. "
            "This should include placeholders for facts, analysis outcomes, and any other relevant information. "
            "Don't fill any answers into this template even if you have the information, just leave placeholders. "
            "Do not return anything other than the template itself, don't use ```markdown ... ``` block either."
        )

        answer_template_messages = messages + [
            {"role": "developer", "content": answer_template_prompt}
        ]

        answer_template_response = await llm.a_get_response(
            messages=answer_template_messages,
            model=model,
            temperature=temperature,
        )

        initial_answer_template = answer_template_response.content.strip()

        # Save both answer template and WIP template (initially the same)
        save_answer_template(planner_id, initial_answer_template)
        save_wip_answer_template(planner_id, initial_answer_template)

        logger.info(
            f"Created and saved initial answer template for planner {planner_id}"
        )

        logger.info(f"Initial planning completed for planner {planner_id}")
        logger.info(f"Planner {planner_id}\nuser question: {user_question}")
        logger.info(f"Planner {planner_id}\ninstruction: {instruction}")
        logger.info(f"Planner {planner_id}\nexecution plan: {execution_plan_markdown}")

        # Queue next task: task creation
        update_planner_next_task_and_queue(planner_id, "execute_task_creation")

    except Exception as e:
        logger.error(f"Initial planning failed for planner {planner_id}: {e}")
        if "planner_id" in locals():
            await db.update_planner(planner_id, status="failed")
        raise


async def execute_task_creation(task_data: dict):
    """
    Create and save new worker task based on execution plan.
    This phase generates a Task and saves it for worker initialisation.
    """
    planner_id = task_data["entity_id"]
    logger.info(f"Starting task creation for planner {planner_id}")

    db = AgentDatabase()
    planner_data = await db.get_planner(planner_id)

    if not planner_data:
        logger.error(f"Planner {planner_id} not found")
        await db.update_planner(planner_id, status="failed")
        return

    # Create message manager for this planner
    message_manager = MessageManager(db, "planner", planner_id)

    try:
        # Load execution plan model from dedicated file
        execution_plan_model = load_execution_plan_model(planner_id)
        # load_execution_plan_model already handles errors and raises exceptions

        # Check if there are pending tasks to create
        if not has_pending_tasks(execution_plan_model):
            logger.error(
                f"Planner {planner_id} has no pending tasks - this should not happen, marking as failed"
            )
            await db.update_planner(planner_id, status="failed")
            return

        # Get next task from execution plan
        next_task = get_next_action_task(execution_plan_model)
        if not next_task:
            # This should not be possible if has_pending_tasks returned True
            raise ValueError(
                f"No next task available despite having pending tasks for planner {planner_id}"
            )

        # Get planner messages for context
        messages = await message_manager.get_messages()

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

        # Add latest 10 task responses if available (worker context)
        task_responses = load_worker_message_history(planner_id)
        if task_responses:
            latest_responses = task_responses[-10:]  # Get latest 10 items
            responses_content = "\n\n---\n\n".join(
                [response.model_dump_json(indent=2) for response in latest_responses]
            )
            appending_msgs.append(
                {
                    "role": "developer",
                    "content": f"For additional context, the detailed outcomes of the previous {len(latest_responses)} tasks are as follows:\n\n{responses_content}",
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

        # Generate worker_id for this task
        worker_id = uuid.uuid4().hex

        # Set next_task to waiting_for_worker (no queue - planner waits for worker completion)
        await db.update_planner(planner_id, next_task="waiting_for_worker")

        # Queue worker initialisation (worker will load task and create worker record)
        queue_worker_task(worker_id, planner_id, "worker_initialisation")

        logger.info(
            f"Created and queued worker initialisation for worker {worker_id}, planner {planner_id}"
        )

    except Exception as e:
        logger.error(f"Task creation failed for planner {planner_id}: {e}")
        # Set planner as failed
        await db.update_planner(planner_id, status="failed")
        raise


async def _complete_planner_execution(
    planner_id: str,
    execution_plan_model: ExecutionPlanModel,
    worker_id: str,
    planner_data: dict,
    db: AgentDatabase,
) -> None:
    """
    Helper function to handle planner completion logic.

    Args:
        planner_id: The planner ID
        execution_plan_model: The current execution plan model to save
        worker_id: The current worker ID to mark as recorded
        planner_data: Planner data from database
        db: Database connection
    """
    # Generate final user response (exactly copying planner.py lines 619-637)
    final_wip_template = load_wip_answer_template(planner_id) or ""
    planner_messages = await db.get_messages(agent_type="planner", agent_id=planner_id)

    # Filter to exclude system messages for final response generation
    user_response_messages = [
        msg for msg in planner_messages if msg.get("role") != "system"
    ] + [
        {
            "role": "developer",
            "content": "The current answer template to the user's original question is:"
            f"```markdown\n{final_wip_template}\n```\n\n"
            "Using only provided information without creating any new, complete the answer template to a state that will be seen by the user. "
            "If there is missing information, simply explain that the information is not found in the provided context, do not try to fill it yourself. "
            "Return only the markdown answer and nothing else, do not use the user's question as a title. Do not wrap the response in ```markdown ... ``` block. "
            "Agressively use inline citation such that the citing references provided are used individually whenever possible as opposed to making multiple citings at the end. "
            "Citations must not ever use information that is meaningless to the user such as task IDs. "
            "It should be using web links, or file references including page numbers, table/illustration references, or data references. ",
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
    save_execution_plan_model(planner_id, execution_plan_model)
    execution_plan_markdown = execution_plan_model_to_markdown(execution_plan_model)
    await db.update_planner(
        planner_id,
        execution_plan=execution_plan_markdown,
        status="completed",
        next_task="completed",
        user_response=user_response,  # Store final response
    )

    # PHASE 1: Direct database completion - add response to router messages
    try:
        # Get router_id from planner links
        router_id = await db.get_router_id_for_planner(planner_id)
        if router_id:
            # Add assistant response directly to router messages
            message_id = await db.add_message("router", router_id, "assistant", user_response)
            logger.info(f"Added planner completion response to router {router_id} as message {message_id}")
        else:
            logger.warning(f"No router_id found for planner {planner_id} - response not added to router messages")
    except Exception as e:
        logger.error(f"Failed to add completion response to router messages for planner {planner_id}: {e}")
        # Don't fail the entire planner - just log the error

    # Mark worker as recorded and skip variable processing - no future tasks need them
    await db.update_worker(worker_id, task_status="recorded")
    logger.info(f"Planner {planner_id} completed with user response generated")

    # Clean up planner files since planning is complete
    cleanup_success = cleanup_planner_files(planner_id)
    if cleanup_success:
        logger.info(f"Successfully cleaned up files for completed planner {planner_id}")
    else:
        logger.warning(f"Failed to clean up files for completed planner {planner_id}")


async def execute_synthesis(task_data: dict):
    """
    Process completed workers and merge their outputs back into planner state.
    This phase loads worker outputs, updates execution plan, and merges variables/images.
    Based on task_result_synthesis from original PlannerAgent.
    """
    planner_id = task_data["entity_id"]
    logger.info(f"Starting synthesis for planner {planner_id}")

    db = AgentDatabase()
    planner_data = await db.get_planner(planner_id)

    if not planner_data:
        logger.error(f"Planner {planner_id} not found")
        return

    # Create message manager for this planner
    message_manager = MessageManager(db, "planner", planner_id)

    try:
        # Get all workers for this planner
        workers = await db.get_workers_by_planner(planner_id)

        # Find completed workers that haven't been processed yet (status = 'completed' or 'failed_validation')
        completed_workers = [
            worker
            for worker in workers
            if worker["task_status"] in ["completed", "failed_validation"]
        ]

        if not completed_workers:
            logger.error(
                f"Planner {planner_id} has no completed workers to process - this should not happen, marking as failed"
            )
            await db.update_planner(planner_id, status="failed")
            return

        # Process each completed worker (following task_result_synthesis pattern)
        for worker in completed_workers:
            worker_id = worker["worker_id"]
            task_status = worker["task_status"]
            task_description = worker.get("task_description", "Unknown task")

            logger.info(f"Processing completed worker {worker_id}: {task_description}")

            # 1. Add worker response to planner messages (like original task_result_synthesis)
            # Create temporary MessageManager for reading worker messages
            worker_message_manager = MessageManager(db, "worker", worker_id)
            worker_messages = await worker_message_manager.get_messages()
            task_message_combined = "\n\n---\n\n".join(
                [
                    msg["content"]
                    for msg in worker_messages
                    if msg.get("role") == "assistant"
                ]
            )

            await message_manager.add_message(
                role="assistant",
                content=f"# Responses from worker\n\n"
                f"**Task ID**: {worker_id}\n\n"
                f"**Task Description**: {task_description}\n\n"
                f"**Task Status**: {task_status}\n\n"
                f"**Worker Responses**:\n\n{task_message_combined}",
            )

            # Append to worker message history for future worker context
            task_response = TaskResponseModel(
                task_id=worker_id,
                task_description=task_description,
                task_status=task_status,
                assistance_responses=task_message_combined,
            )
            append_to_worker_message_history(planner_id, task_response)

            # Update answer template after completed worker (following planner.py pattern lines 414-438)
            if task_status == "completed":
                try:
                    # Load current answer templates
                    current_answer_template = load_answer_template(planner_id) or ""
                    current_wip_template = load_wip_answer_template(planner_id) or ""

                    # Get planner messages for template update context
                    planner_messages = await message_manager.get_messages()

                    # Create answer template update prompt (following planner.py pattern)
                    template_update_messages = planner_messages + [
                        {
                            "role": "developer",
                            "content": "The current answer template that will be filled to provide the final answer to the user's question is:\n\n"
                            f"```markdown\n{current_answer_template}\n```\n\n"
                            "The latest work in progress fill of the answer template is:\n\n"
                            f"```markdown\n{current_wip_template}\n```\n\n"
                            "Update the template if required and further fill the WIP answer with latest information available.\n"
                            "IMPORTANT: the original template is typically created in absence of information, if the structure should change on discovery of information, do not be restrained by the starting template. "
                            "If different concepts identified in the data that can answer the user's question as it wasn't specific enough, be eager to include all concepts consistently across the template "
                            "(e.g. if differing concepts are found in one document, add the concepts to the answer template and make sure you look for the same differences in other documents too). ",
                        }
                    ]

                    # Get updated answer template from LLM
                    answer_template_response = await llm.a_get_response(
                        messages=template_update_messages,
                        model=planner_data["model"],
                        temperature=planner_data["temperature"],
                        response_format=AnswerTemplate,
                    )

                    # Save updated templates
                    updated_template = answer_template_response.template
                    updated_wip_template = answer_template_response.wip_filled_template

                    save_answer_template(planner_id, updated_template)
                    save_wip_answer_template(planner_id, updated_wip_template)

                    logger.info(f"Updated answer template for planner {planner_id}")
                    logger.info(f"Updated answer template:\n{updated_template}")
                    logger.info(f"Updated WIP answer template:\n{updated_wip_template}")

                except Exception as e:
                    logger.error(
                        f"Error updating answer template for planner {planner_id}: {e}"
                    )
                    # Continue with execution plan processing even if template update fails

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
                messages = await message_manager.get_messages()

                # Create filtered model with only open todos for LLM
                open_todos = [
                    todo
                    for todo in execution_plan_model.todos
                    if not todo.completed and not todo.obsolete
                ]

                # Early completion check - if no open todos, activate completion immediately
                if not open_todos:
                    logger.info(
                        f"No open todos found for planner {planner_id} - activating early completion"
                    )
                    await _complete_planner_execution(
                        planner_id, execution_plan_model, worker_id, planner_data, db
                    )
                    return  # Exit synthesis completely

                open_todos_model = ExecutionPlanModel(
                    objective=execution_plan_model.objective, todos=open_todos
                )

                # Update execution plan using LLM (simplified version)
                update_messages = messages + [
                    {
                        "role": "developer",
                        "content": f"**Current open tasks from execution plan:**\n\n{open_todos_model.model_dump_json(indent=2)}\n\n"
                        f"The latest answer template is:\n\n{updated_wip_template}\n\n"
                        f"Instructions for reference:\n\n{planner_data.get('instruction', '')}",
                    },
                    {
                        "role": "developer",
                        "content": f"Based on the completed task execution details above for task `{task_description}`, "
                        f"please update the execution plan as follows:\n"
                        "1. Update existing task descriptions using updated_description field if needed\n"
                        "2. Add new tasks if required, marking them with '(new)' in the description field\n"
                        "3. Leave next_action as False - separate logic will determine next action\n"
                        "4. Mark unnecessary tasks as obsolete=True\n"
                        "Do not create tasks to formulate answer, as the answer is already being formulated progressively with the answer template.",
                    },
                ]
                # Prepare update messages using only open tasks
                # update_messages = self.messages + [
                #     {
                #         "role": "developer",
                #         "content": f"**Current open tasks from execution plan:**\n\n{open_tasks_model.model_dump_json(indent=2)}",
                #     },
                #     {
                #         "role": "developer",
                #         "content": f"Based on the completed task execution details above for task `{t.task_description}`, please update the execution plan. "
                #         f"For context, this is the instructions:\n\n{self.instruction}\n\n"
                #         f"This is the template to answer the user's question:\n\n"
                #         f"```markdown\n{self.answer_template}\n```\n\n"
                #         f"This is the partly filled answer template so far:\n\n"
                #         f"```markdown\n{self.wip_filled_answer_template}\n```\n\n"
                #         "Think through what is still required to finish populating the answer template and use that to guide yourself in performing the following steps:\n"
                #         "1. Update existing task descriptions using updated_description field if needed\n"
                #         "2. Add new tasks if required, marking them with '(new)' in the description field\n"
                #         "3. Leave next_action as False - separate logic will determine next action\n"
                #         "4. Mark unnecessary tasks as obsolete=True\n"
                #         "Note: aggressively prune down unneeded tasks if they appear to overlap with outputs already produced. "
                #         "DO NOT prune out calculation tasks, even if the answer template has already pre-filled the calculation. "
                #         "Tasks will be executed strictly in order on the list, if a new task is created please place it in the position of when it is supposed to be executed, don't leave it to the end.\n"
                #         "Note 2: Do not create tasks to formulate answer, as the answer is already being formulated progressively with the answer template. "
                #         "You can return an empty todo list if the answer template is completely populated or if you determine that the missing information does not exist in provided context.",
                #     },
                # ]
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
                    await _complete_planner_execution(
                        planner_id, final_model, worker_id, planner_data, db
                    )
                    return  # Exit synthesis completely

                # Save updated execution plan (only if not completed)
                save_execution_plan_model(planner_id, final_model)
                execution_plan_markdown = execution_plan_model_to_markdown(final_model)
                await db.update_planner(planner_id, execution_plan=execution_plan_markdown)

                logger.info(f"Execution plan updated for planner {planner_id}")

            except Exception as e:
                logger.error(
                    f"Error updating execution plan for planner {planner_id}: {e}"
                )
                # Continue with variable/image processing even if plan update fails

            # 3. Process output images and variables (like original task_result_synthesis)
            if task_status == "completed":
                # Merge worker output variables
                worker_output_vars = worker.get("output_variable_filepaths", {})
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
                worker_output_imgs = worker.get("output_image_filepaths", {})
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
            await db.update_worker(worker_id, task_status="recorded")
            logger.info(f"Marked worker {worker_id} as recorded")

        logger.info(f"Synthesis completed for planner {planner_id}")

        # Queue next task: task creation (to continue planning cycle)
        update_planner_next_task_and_queue(planner_id, "execute_task_creation")

    except Exception as e:
        logger.error(f"Synthesis failed for planner {planner_id}: {e}")
        await db.update_planner(planner_id, status="failed")
        raise
