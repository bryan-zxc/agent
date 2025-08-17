"""
Async worker task functions for the function-based architecture.

This module contains all worker execution functions that are called by the
background task processor. Each function operates on a worker_id and manages
worker execution state through the file system and database.
"""

import logging
import json
import duckdb
from pydantic import BaseModel, Field
from PIL import Image

from ..models.agent_database import AgentDatabase
from ..models import TOOLS, TaskArtefact, TaskValidation, TaskResult, TaskArtefactSQL
from ..config.settings import settings
from ..config.agent_names import get_random_worker_name
from ..services.llm_service import LLM
from ..utils.sandbox import CodeSandbox
from ..utils.tools import decode_image, encode_image, is_serialisable
from .file_manager import (
    load_current_task,
    get_planner_variables,
    get_planner_images,
    save_variable_to_file,
    save_image_to_file,
    generate_variable_path,
    generate_image_path,
)
from .task_utils import (
    update_planner_next_task_and_queue,
    update_worker_next_task_and_queue,
)

logger = logging.getLogger(__name__)

# Initialize LLM service for worker tasks
llm = LLM(caller="worker")


def convert_result_to_str(result: TaskResult) -> str:
    """Convert TaskResult to formatted string"""
    return f"# Task result\n{result.result}\n\n# Task output\n{result.output}"


async def validate_worker_result(
    worker_id: str, acceptance_criteria: str, db: AgentDatabase
) -> bool:
    """Validate if worker task is completed based on acceptance criteria"""
    # Add validation message to database
    db.add_worker_message(
        worker_id=worker_id,
        role="developer",
        content=f"Determine if the task is successfully completed based on the acceptance criteria:\n{acceptance_criteria}\n\n",
    )

    # Get updated messages for validation
    validation_messages = db.get_worker_messages(worker_id)

    validation = await llm.a_get_response(
        messages=validation_messages,
        model=settings.worker_model,
        temperature=0,
        response_format=TaskValidation,
    )

    logger.info(f"Validation result: {validation.model_dump_json(indent=2)}")

    if validation.task_completed:
        task_result = convert_result_to_str(validation.validated_result)
        logger.info(
            f"Task {worker_id} completed successfully. Final result:\n{task_result}"
        )

        # Update worker status to completed and sync to database (like self.sync_task_to_db())
        db.update_worker(
            worker_id=worker_id,
            task_status="completed",
            task_result=task_result,
        )

        return True
    else:
        task_result = f"{validation.validated_result.result}\n\nFailed criteria: {validation.failed_criteria}"
        # Update task result in database (like self.task.task_result = ...)
        db.update_worker(worker_id=worker_id, task_result=task_result)
        # Add message to database (like self.add_message)
        db.add_worker_message(
            worker_id=worker_id, role="assistant", content=task_result
        )
        return False


async def process_image_variable(
    image: Image, variable_name: str, worker_id: str, planner_id: str, db: AgentDatabase
) -> str:
    """Process an output image variable and save to file system

    Returns:
        str: The final image key name used (may be different if collision avoided)
    """
    # Encode the image
    encoded_image = encode_image(image)

    # Generate file path with collision avoidance
    file_path, final_image_key = generate_image_path(
        planner_id, variable_name, check_existing=True
    )

    # Save image to file
    if save_image_to_file(file_path, encoded_image):
        # Update worker database with file path
        db.update_worker_file_paths(worker_id, image_paths={final_image_key: file_path})

        # Add message to database using final key name
        content = [{"type": "text", "text": f"Image: {final_image_key}"}]
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{encoded_image}"},
            }
        )
        db.add_worker_message(worker_id=worker_id, role="user", content=content)

        return final_image_key
    else:
        raise Exception(
            f"Failed to save image '{final_image_key}' for worker {worker_id}"
        )


async def process_variable(
    variable, variable_name: str, worker_id: str, planner_id: str, db: AgentDatabase
) -> str:
    """Process an output variable and save to file system

    Returns:
        str: The final variable key name used (may be different if collision avoided)
    """
    # Always save variable to file regardless of serialisability
    file_path, final_variable_key = generate_variable_path(
        planner_id, variable_name, check_existing=True
    )

    # Save variable to file
    if save_variable_to_file(file_path, variable):
        # Update worker database with file path
        db.update_worker_file_paths(
            worker_id, variable_paths={final_variable_key: file_path}
        )

        # Add message to database - content depends on serialisability
        serialisable, stringable = is_serialisable(variable)

        if serialisable:
            # Show full variable content since it's serialisable
            db.add_worker_message(
                worker_id=worker_id,
                role="assistant",
                content=f"```python\n{final_variable_key}\n```\n\nOutput:\n```\n{variable}\n```",
            )
        elif stringable:
            # Show string representation but note it's not serialisable
            db.add_worker_message(
                worker_id=worker_id,
                role="assistant",
                content=f"```python\n{final_variable_key}\n```\n\nOutput:\n```\n{str(variable)}\n```\n\n"
                "Note: the output is not serialisable and will not be included as an output variable.",
            )
        # No message for else case - variable saved to file but not displayed

        return final_variable_key
    else:
        raise Exception(
            f"Failed to save variable '{final_variable_key}' for worker {worker_id}"
        )


async def worker_initialisation(task_data: dict):
    """
    Initialise worker and create FullTask from the saved Task.

    This function is called when a planner creates a task and queues worker initialisation.
    It loads the Task saved by execute_task_creation, creates a FullTask, and prepares
    the worker for execution.

    Args:
        task_data: Dict containing task information and payload:
            - entity_id: worker_id (which IS the task_id from the Task)
            - payload: dict with planner_id
    """
    worker_id = task_data["entity_id"]
    payload = task_data.get("payload", {})
    planner_id = payload["planner_id"]

    logger.info(
        f"Starting worker initialisation for worker {worker_id}, planner {planner_id}"
    )

    db = AgentDatabase()

    # Check if this is a resume scenario (worker already exists)
    existing_worker = db.get_worker(worker_id)

    if existing_worker:
        logger.info(
            f"Worker {worker_id} already exists - resuming execution, skipping initialisation"
        )
        # Queue worker execution task (worker already initialised)
        update_worker_next_task_and_queue(worker_id, "execute_worker_task")
        return

    try:
        # Load the Task that was saved by execute_task_creation
        task = load_current_task(planner_id)
        if not task:
            logger.error(f"No current task found for planner {planner_id}")
            return

        # Verify this worker_id matches the task_id (they should be the same)
        if worker_id != task.task_id:
            logger.error(f"Worker ID {worker_id} does not match task ID {task.task_id}")
            return

        logger.info(f"Loaded task for worker {worker_id}: {task.task_name}")

        # Get planner data to access variables, images, and other context
        planner_data = db.get_planner(planner_id)
        if not planner_data:
            logger.error(f"Planner {planner_id} not found")
            return

        # Load planner context data for worker
        planner_variables = get_planner_variables(planner_id)
        planner_images = get_planner_images(planner_id)

        # Get tables and files from planner metadata (not variables)
        planner_metadata = planner_data.get("agent_metadata", {})
        tables = planner_metadata.get("tables", [])
        files = planner_metadata.get("files", [])

        # Extract filepaths from document files
        filepaths = (
            [f.get("filepath", "") for f in files if f.get("file_type") == "document"]
            if files
            else []
        )

        # Get file paths from planner for worker storage
        input_variable_filepaths = {
            variable_key: planner_data.get("variable_file_paths", {}).get(
                variable_key, ""
            )
            for variable_key in task.variable_keys
            if planner_data.get("variable_file_paths", {}).get(variable_key)
        }
        input_image_filepaths = {
            image_key: planner_data.get("image_file_paths", {}).get(image_key, "")
            for image_key in task.image_keys
            if planner_data.get("image_file_paths", {}).get(image_key)
        }

        # Set querying_structured_data to False if no tables
        querying_structured_data = task.querying_structured_data
        if not tables:
            querying_structured_data = False

        # Generate worker name
        worker_name = get_random_worker_name()

        # Create worker database record with individual parameters
        db.create_worker(
            worker_id=worker_id,
            planner_id=planner_id,
            worker_name=worker_name,
            task_status="pending",
            task_description=task.task_description,
            acceptance_criteria=task.acceptance_criteria,
            task_context=task.task_context.model_dump(),
            task_result="",
            querying_structured_data=querying_structured_data,
            image_keys=task.image_keys,
            variable_keys=task.variable_keys,
            tools=task.tools,
            input_variable_filepaths=input_variable_filepaths,
            input_image_filepaths=input_image_filepaths,
            tables=tables,
            filepaths=filepaths,
        )

        logger.info(f"Created worker database record for worker {worker_id}")

        # Set up initial messages for worker (following WorkerAgent._setup_worker_messages pattern)
        # Add initial task message
        db.add_worker_message(
            worker_id=worker_id,
            role="user",
            content=f"Perform the following task:\n{task.task_description}",
        )

        # Add context message
        db.add_worker_message(
            worker_id=worker_id,
            role="developer",
            content=f"# Context\n{task.task_context.context}\n\n"
            f"# Previous outputs\n{task.task_context.previous_outputs}\n\n"
            f"# Original user request\n{task.task_context.user_request}\n\n"
            "Unless the original user request is necessary to perform the task at hand, "
            "DO NOT change the actions to be performed based on the knowledge of the original request.",
        )

        # Add input images if any
        if task.image_keys and planner_images:
            for image_key in task.image_keys:
                if image_key in planner_images:
                    image = planner_images[image_key]
                    # Create multimodal content for image
                    content = [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{image}"},
                        }
                    ]
                    decoded_image = decode_image(image)
                    content.append(
                        {
                            "type": "text",
                            "text": f"The above image can be accessed via python using the following code to convert the image into PIL.Image object:\n"
                            f"```python\nimport io\nimport base64\nImage.open(io.BytesIO(base64.b64decode({image_key})))\n```\n"
                            f"Note 1: Do not assign {image_key} variable, assume it already exists in the environment.\n"
                            f"Note 2: You must import io and base64 as part of the code.\n"
                            f"The dimensions of the image is width = {decoded_image.width}, height = {decoded_image.height}. "
                            "If image manipulation is required, use these dimensions to produce precise coordinates for cropping or combining charts.",
                        }
                    )
                    db.add_worker_message(
                        worker_id=worker_id, role="user", content=content
                    )

        # Add input variables if any
        if task.variable_keys and planner_variables:
            db.add_worker_message(
                worker_id=worker_id,
                role="developer",
                content="The following variables are available for use, they already exist in the environment, "
                f"you do not need to declare or create it: {', '.join(task.variable_keys)}",
            )
            for variable_name in task.variable_keys:
                if variable_name in planner_variables:
                    variable = planner_variables[variable_name]
                    db.add_worker_message(
                        worker_id=worker_id,
                        role="developer",
                        content=f"# {variable_name}\nType: {type(variable)}\n\n"
                        f"Length of variable: {len(str(variable))}\n\n"
                        f"Variable content (first 10000 characters)```\n{str(variable)[:10000]}\n```",
                    )

        # Add file paths if any
        if filepaths:
            db.add_worker_message(
                worker_id=worker_id,
                role="developer",
                content=f"The following PDF files are available for use: {', '.join(filepaths)}",
            )

        # Add tools if any
        if task.tools:
            tools_text = "\n\n---\n\n".join(
                [f"# {t}\n{TOOLS.get(t).__doc__}" for t in task.tools]
            )
            db.add_worker_message(
                worker_id=worker_id,
                role="developer",
                content=f"You may use the following function(s):\n\n{tools_text}\n\n"
                "When using the function(s) you can assume that they already exists in the environment, "
                "to use it, simply call the function with the required parameters. "
                "You must use the function(s) where possible, do not ever try to perform the same action with other code.",
            )

        logger.info(f"Set up initial messages for worker {worker_id}")

        # Queue worker execution task based on worker type
        if querying_structured_data:
            update_worker_next_task_and_queue(worker_id, "execute_sql_worker")
        else:
            update_worker_next_task_and_queue(worker_id, "execute_standard_worker")

        logger.info(
            f"Worker initialisation completed for worker {worker_id}, queued worker execution"
        )

    except Exception as e:
        logger.error(f"Worker initialisation failed for worker {worker_id}: {e}")
        # Mark worker as failed if it exists
        try:
            db.update_worker(worker_id, status="failed")
        except:
            pass
        # Update planner to continue despite worker failure
        update_planner_next_task_and_queue(planner_id, "execute_synthesis")
        raise


async def execute_standard_worker(task_data: dict):
    """
    Execute one attempt of standard worker task with code generation and sandboxed execution.

    This function handles ONE execution attempt and decides whether to retry (queue self)
    or complete (queue planner synthesis). Always ensures planner synthesis is queued.

    Args:
        task_data: Dict containing task information:
            - entity_id: worker_id
            - payload: dict with planner_id and other context
    """
    worker_id = task_data["entity_id"]
    payload = task_data.get("payload", {})
    planner_id = payload["planner_id"]

    logger.info(f"Starting standard worker execution attempt for worker {worker_id}")

    db = AgentDatabase()

    # Load worker state from database
    worker_data = db.get_worker(worker_id)
    if not worker_data:
        logger.error(f"Worker {worker_id} not found in database")
        return

    # Load planner variables and images for worker execution
    planner_variables = get_planner_variables(planner_id)
    planner_images = get_planner_images(planner_id)

    # Get worker messages from database
    messages = db.get_worker_messages(worker_id)

    # Get worker configuration from settings
    max_retry = settings.max_retry_tasks

    # Track current attempt number
    current_attempt = worker_data.get("current_attempt", 0) + 1

    # No need to track output dictionaries - process functions handle file persistence

    try:
        logger.info(f"Worker {worker_id} - Attempt {current_attempt} of {max_retry}")
        logger.info(f"Messages: {json.dumps(messages, indent=2)}")

        # Get task result from LLM
        task_result = await llm.a_get_response(
            messages=messages,
            model=settings.worker_model,
            temperature=0,
            response_format=TaskArtefact,
        )

        logger.info(f"Task result: {task_result.model_dump_json(indent=2)}")

        # Update attempt counter
        db.update_worker(worker_id=worker_id, current_attempt=current_attempt)

        if task_result.python_code:
            # Check for malicious code
            if task_result.is_malicious:
                error_message = "The code is either making changes to the database or creating executable files - this is considered malicious and not permitted."
                db.add_worker_message(
                    worker_id=worker_id,
                    role="assistant",
                    content=f"{error_message}\\nRewrite the python code to fix the error.",
                )

                # Queue retry if attempts remain
                if current_attempt < max_retry:
                    update_worker_next_task_and_queue(
                        worker_id, "execute_standard_worker"
                    )
                else:
                    # Max retries reached - mark as failed and queue synthesis
                    db.update_worker(
                        worker_id=worker_id,
                        task_status="failed_validation",
                        task_result="Task failed: Malicious code detected after multiple attempts.",
                    )
                    update_planner_next_task_and_queue(planner_id, "execute_synthesis")
                return

            db.add_worker_message(
                worker_id=worker_id,
                role="assistant",
                content=f"The python code to execute:\\n```python\\n{task_result.python_code}\\n```",
            )

            # Prepare sandbox environment
            locals_dict = {}

            # Add input variables from planner
            variable_keys = worker_data.get("variable_keys", [])
            for var_key in variable_keys:
                if var_key in planner_variables:
                    locals_dict[var_key] = planner_variables[var_key]

            # Add input images from planner
            image_keys = worker_data.get("image_keys", [])
            for img_key in image_keys:
                if img_key in planner_images:
                    locals_dict[img_key] = planner_images[img_key]

            # Add available tools
            tools = worker_data.get("tools", [])
            if tools:
                for tool_name in tools:
                    func = TOOLS.get(tool_name)
                    if callable(func):
                        locals_dict[tool_name] = func

            logger.info(f"Locals dict keys: {list(locals_dict.keys())}")

            # Execute code in sandbox
            sandbox = CodeSandbox(locals_dict=locals_dict)
            sandbox_result = sandbox.execute(task_result.python_code)

            if sandbox_result["success"]:
                db.add_worker_message(
                    worker_id=worker_id,
                    role="assistant",
                    content="Below outputs are generated on executing python code.",
                )

                if sandbox_result["output"]:
                    db.add_worker_message(
                        worker_id=worker_id,
                        role="assistant",
                        content=sandbox_result["output"],
                    )

                # Process output variables
                for output_var in task_result.output_variables:
                    if output_var.is_image:
                        var_value = sandbox_result["variables"][output_var.name]
                        if isinstance(var_value, list):
                            for i, img in enumerate(var_value):
                                await process_image_variable(
                                    img,
                                    f"{output_var.name}_{i}",
                                    worker_id,
                                    planner_id,
                                    db,
                                )
                        elif isinstance(var_value, dict):
                            for img_key, img in var_value.items():
                                await process_image_variable(
                                    img,
                                    f"{output_var.name}_{img_key}",
                                    worker_id,
                                    planner_id,
                                    db,
                                )
                        elif isinstance(var_value, Image.Image):
                            await process_image_variable(
                                var_value, output_var.name, worker_id, planner_id, db
                            )
                        else:
                            error_message = f"Incorrect output: if {output_var.name} is an image, it must be a PIL.Image object or a list[Image] or dict[str:Image] object, no other choices are allowed."
                            db.add_worker_message(
                                worker_id=worker_id,
                                role="assistant",
                                content=f"{error_message}\\nRewrite the python code to fix the error.",
                            )

                            # Queue retry
                            if current_attempt < max_retry:
                                update_worker_next_task_and_queue(
                                    worker_id, "execute_standard_worker"
                                )
                            else:
                                db.update_worker(
                                    worker_id=worker_id,
                                    task_status="failed_validation",
                                    task_result=error_message,
                                )
                                update_planner_next_task_and_queue(
                                    planner_id, "execute_synthesis"
                                )
                            return
                    else:
                        var_value = sandbox_result["variables"][output_var.name]
                        await process_variable(
                            var_value, output_var.name, worker_id, planner_id, db
                        )

                # Process functions have already saved outputs to files and updated database paths
                # No need to update worker output dictionaries

                # Validate result
                validated = await validate_worker_result(
                    worker_id, worker_data["acceptance_criteria"], db
                )
                if validated:
                    # Queue planner synthesis on successful completion
                    update_planner_next_task_and_queue(planner_id, "execute_synthesis")
                    return

            else:
                # Handle execution error
                error_message = f"Error executing code: {sandbox_result['error']}"

                # Check if error is due to missing tool
                class ToolMissing(BaseModel):
                    tool_not_available: bool = Field(
                        False,
                        description="True if the error indicates a tool or function is not available or doesn't exist",
                    )

                tool_check = await llm.a_get_response(
                    messages=[
                        {"role": "user", "content": f"Error: {sandbox_result['error']}"}
                    ],
                    model=settings.worker_model,
                    response_format=ToolMissing,
                )

                if tool_check.tool_not_available:
                    failure_message = "Task failed: Required tool was not provided"
                    db.update_worker(
                        worker_id=worker_id,
                        task_status="failed_validation",
                        task_result=failure_message,
                    )
                    db.add_worker_message(
                        worker_id=worker_id,
                        role="assistant",
                        content=f"{failure_message}\\n\\n{sandbox_result['stack_trace']}\\n\\nRequired tool is not available, please supply the task with the required tool and try again.",
                    )
                    # Queue synthesis regardless of tool failure
                    update_planner_next_task_and_queue(planner_id, "execute_synthesis")
                    return

                db.add_worker_message(
                    worker_id=worker_id,
                    role="assistant",
                    content=f"{error_message}\\n\\n{sandbox_result['stack_trace']}\\n\\nRewrite the python code to fix the error.",
                )

                # Check for repeated failures
                class RepeatFail(BaseModel):
                    repeated_failure: bool = Field(
                        False,
                        description="Set this to True if the task has been repeated failed with no change in the process. "
                        "To consider it a repeated failure, you need to have see the exact same error at least three times in a row. "
                        "Failing with different code and different errors does not count as repeated failure.",
                    )
                    failure_summary: str = Field(
                        "",
                        description="If repeated_failure is True, explain what the agent is repeatedly failing to achieve in non-technical terms.",
                    )

                repeated_fail = await llm.a_get_response(
                    messages=db.get_worker_messages(worker_id),
                    model=settings.worker_model,
                    temperature=0,
                    response_format=RepeatFail,
                )

                if repeated_fail.repeated_failure:
                    failure_message = f"{error_message}\\n\\nRepeated failure: {repeated_fail.failure_summary}"
                    db.update_worker(
                        worker_id=worker_id,
                        task_status="failed_validation",
                        task_result=failure_message,
                    )
                    # Queue synthesis for repeated failure
                    update_planner_next_task_and_queue(planner_id, "execute_synthesis")
                    return

        else:
            # No Python code generated, just text response
            db.add_worker_message(
                worker_id=worker_id, role="assistant", content=task_result.result
            )

            validated = await validate_worker_result(
                worker_id, worker_data["acceptance_criteria"], db
            )
            if validated:
                # Queue planner synthesis on successful completion
                update_planner_next_task_and_queue(planner_id, "execute_synthesis")
                return

        # If we reach here, validation failed - check if more retries available
        if current_attempt < max_retry:
            logger.info(
                f"Worker {worker_id} validation failed, queueing retry {current_attempt + 1}/{max_retry}"
            )
            update_worker_next_task_and_queue(worker_id, "execute_standard_worker")
        else:
            # All retries exhausted - mark as failed and queue synthesis
            logger.info(
                f"Worker {worker_id} exhausted all {max_retry} retries, marking as failed"
            )
            db.update_worker(
                worker_id=worker_id,
                task_status="failed_validation",
                task_result="Task failed after multiple tries.",
            )
            update_planner_next_task_and_queue(planner_id, "execute_synthesis")

    except Exception as e:
        logger.error(f"Standard worker execution failed for worker {worker_id}: {e}")
        db.update_worker(
            worker_id=worker_id,
            task_status="failed",
            task_result=f"Worker execution failed: {str(e)}",
        )
        # Always queue synthesis even on unexpected errors
        update_planner_next_task_and_queue(planner_id, "execute_synthesis")
        raise


async def execute_sql_worker(task_data: dict):
    """
    Execute one attempt of SQL worker task with DuckDB execution.

    This function handles ONE execution attempt and decides whether to retry (queue self)
    or complete (queue planner synthesis). Always ensures planner synthesis is queued.

    Args:
        task_data: Dict containing task information:
            - entity_id: worker_id
            - payload: dict with planner_id and other context
    """

    worker_id = task_data["entity_id"]
    payload = task_data.get("payload", {})
    planner_id = payload["planner_id"]

    logger.info(f"Starting SQL worker execution attempt for worker {worker_id}")

    db = AgentDatabase()

    # Load worker state from database
    worker_data = db.get_worker(worker_id)
    if not worker_data:
        logger.error(f"Worker {worker_id} not found in database")
        return

    # Get worker messages from database
    messages = db.get_worker_messages(worker_id)

    # Get worker configuration from settings
    max_retry = settings.max_retry_tasks

    # Track current attempt number
    current_attempt = worker_data.get("current_attempt", 0) + 1

    # Get DuckDB connection (this should come from planner context)
    # For now, create a new connection - this may need to be passed differently
    duck_conn = duckdb.connect(":memory:")

    try:
        logger.info(
            f"Worker {worker_id} - SQL Attempt {current_attempt} of {max_retry}"
        )
        logger.info(f"Messages: {json.dumps(messages, indent=2)}")

        # Update attempt counter
        db.update_worker(worker_id=worker_id, current_attempt=current_attempt)

        # Get SQL artefact from LLM
        sql_artefact = await llm.a_get_response(
            messages=messages,
            model=settings.worker_model,
            temperature=0,
            response_format=TaskArtefactSQL,
        )

        logger.info(f"SQL artefact: {sql_artefact.model_dump_json(indent=2)}")

        if sql_artefact.sql_code:
            try:
                # Execute SQL in DuckDB
                sql_output = duck_conn.execute(sql_artefact.sql_code).df().to_markdown()
                db.add_worker_message(
                    worker_id=worker_id,
                    role="assistant",
                    content=f"The following code was executed:\\n\\n```sql\\n\\n{sql_artefact.sql_code}\\n\\n```\\n\\n"
                    f"The output is:\\n\\n{sql_output}",
                )

                # Validate result
                validated = await validate_worker_result(
                    worker_id, worker_data["acceptance_criteria"], db
                )
                if validated:
                    # Queue planner synthesis on successful completion
                    update_planner_next_task_and_queue(planner_id, "execute_synthesis")
                    return

            except Exception as e:
                error_message = f"Error executing SQL code: {e}"
                db.add_worker_message(
                    worker_id=worker_id,
                    role="assistant",
                    content=f"{error_message}\\n\\nRewrite the SQL code to fix the error.",
                )

        else:
            # No SQL code generated
            error_message = (
                f"SQL code cannot be generated. {sql_artefact.reason_code_not_created}"
            )
            db.update_worker(
                worker_id=worker_id,
                task_status="failed_validation",
                task_result=error_message,
            )
            db.add_worker_message(
                worker_id=worker_id, role="assistant", content=error_message
            )
            # Queue synthesis for SQL generation failure
            update_planner_next_task_and_queue(planner_id, "execute_synthesis")
            return

        # If we reach here, validation failed - check if more retries available
        if current_attempt < max_retry:
            logger.info(
                f"SQL Worker {worker_id} validation failed, queueing retry {current_attempt + 1}/{max_retry}"
            )
            update_worker_next_task_and_queue(worker_id, "execute_sql_worker")
        else:
            # All retries exhausted - mark as failed and queue synthesis
            logger.info(
                f"SQL Worker {worker_id} exhausted all {max_retry} retries, marking as failed"
            )
            db.update_worker(
                worker_id=worker_id,
                task_status="failed_validation",
                task_result="SQL task failed after multiple tries.",
            )
            update_planner_next_task_and_queue(planner_id, "execute_synthesis")

    except Exception as e:
        logger.error(f"SQL worker execution failed for worker {worker_id}: {e}")
        db.update_worker(
            worker_id=worker_id,
            task_status="failed",
            task_result=f"SQL worker execution failed: {str(e)}",
        )
        # Always queue synthesis even on unexpected errors
        update_planner_next_task_and_queue(planner_id, "execute_synthesis")
        raise
    finally:
        # Clean up DuckDB connection
        if "duck_conn" in locals():
            duck_conn.close()
