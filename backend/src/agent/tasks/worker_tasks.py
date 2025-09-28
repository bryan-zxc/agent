"""
Async worker task functions for the function-based architecture.

This module contains all worker execution functions that are called by the
background task processor. Each function operates on a worker_id and manages
worker execution state through the file system and database.
"""

import logging
import json
import duckdb
from typing import Any
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
    load_wip_answer_template,
)
# Task queueing functions removed - using frontend orchestration with return actions
from .message_manager import MessageManager

logger = logging.getLogger(__name__)

# Initialize LLM service for worker tasks
llm = LLM(caller="worker")


def convert_result_to_str(result: TaskResult) -> str:
    """Convert TaskResult to formatted string"""
    return f"# Task result\n{result.result}\n\n# Task output\n{result.output}"


async def validate_worker_result(
    worker_id: str,
    acceptance_criteria: str,
    db: AgentDatabase,
    message_manager: MessageManager,
) -> bool:
    """Validate if worker task is completed based on acceptance criteria"""
    # Fetch system instruction from satellite table
    system_instruction = await db.get_worker_system_instruction(
        worker_id=worker_id,
        instruction_type="default"
    )
    if not system_instruction:
        raise ValueError(f"System instruction not found for worker {worker_id}. This should not happen.")
    
    # Add validation message and get updated messages in one operation
    validation_messages = await message_manager.add_message(
        role="user",
        content=f"Determine if the task is successfully completed based on the acceptance criteria:\n{acceptance_criteria}\n\n"
        "Note: if python code is generated, the acceptance criteria will also include needing a print statement at the end of the code (unless it is an image, in which case it should be stored as a PIL.Image object).",
    )

    validation = await llm.a_get_response(
        messages=validation_messages,
        model=settings.worker_model,
        temperature=0,
        response_format=TaskValidation,
        system_instruction=system_instruction,
    )

    logger.info(f"Validation result: {validation.model_dump_json(indent=2)}")

    if validation.task_completed:
        task_result = convert_result_to_str(validation.validated_result)
        logger.info(
            f"Task {worker_id} completed successfully. Final result:\n{task_result}"
        )

        # Update worker status to completed and sync to database (like self.sync_task_to_db())
        await db.update_worker(
            worker_id=worker_id,
            task_status="completed",
            task_result=task_result,
        )

        return True
    else:
        task_result = f"{validation.validated_result.result}\n\nFailed criteria: {validation.failed_criteria}"
        # Update task result in database (like self.task.task_result = ...)
        await db.update_worker(worker_id=worker_id, task_result=task_result)
        # Add message to database (like self.add_message)
        await message_manager.add_message(role="assistant", content=task_result)
        return False


async def process_image_variable(
    image: Image,
    variable_name: str,
    router_id: str,
    db: AgentDatabase,
) -> str:
    """Process an output image variable, save to router table, and return formatted string

    Returns:
        str: Formatted string describing the image for display
    """
    # Encode the image
    encoded_image = encode_image(image)

    # Generate file path with collision avoidance
    file_path, final_image_key = generate_image_path(
        router_id, variable_name, check_existing=True
    )

    # Save image to file
    if save_image_to_file(file_path, encoded_image):
        # Update ROUTER database with file path - merge with existing paths
        router_data = await db.get_router(router_id)
        current_img_paths = (
            router_data.get("image_file_paths", {}) if router_data else {}
        )
        current_img_paths.update({final_image_key: file_path})
        await db.update_router(router_id, image_file_paths=current_img_paths)

        # Return formatted string describing the image
        return f"{final_image_key}: Image(size={image.size}, mode={image.mode}) - saved"
    else:
        raise Exception(
            f"Failed to save image '{final_image_key}' for router {router_id}"
        )


async def process_variable(
    variable,
    variable_name: str,
    router_id: str,
    db: AgentDatabase,
) -> str:
    """Process an output variable, save to router table, and return formatted string

    Returns:
        str: Formatted string describing the variable for display
    """
    # Always save variable to file regardless of serialisability
    file_path, final_variable_key = generate_variable_path(
        router_id, variable_name, check_existing=True
    )

    # Save variable to file
    if save_variable_to_file(file_path, variable):
        # Update ROUTER database with file path - merge with existing paths
        router_data = await db.get_router(router_id)
        current_var_paths = (
            router_data.get("variable_file_paths", {}) if router_data else {}
        )
        current_var_paths.update({final_variable_key: file_path})
        await db.update_router(router_id, variable_file_paths=current_var_paths)

        # Format variable for display - handle different types
        serialisable, stringable = is_serialisable(variable)

        # Special handling for common types
        try:
            import pandas as pd
            if isinstance(variable, pd.DataFrame):
                # Convert DataFrame to markdown table with character limit
                markdown_str = variable.to_markdown()
                if len(markdown_str) > 100000:
                    # Truncate at character limit
                    markdown_str = markdown_str[:100000] + "\n... (truncated at 100,000 characters)"
                return f"{final_variable_key}: DataFrame(shape={variable.shape})\n{markdown_str}"
        except ImportError:
            pass

        try:
            from pydantic import BaseModel
            if isinstance(variable, BaseModel):
                fields = list(type(variable).model_fields.keys())[:30]
                if len(type(variable).model_fields) > 30:
                    fields.append(f"... {len(type(variable).model_fields)-30} more")
                return f"{final_variable_key}: {type(variable).__name__}(fields={fields})"
        except ImportError:
            pass

        if serialisable:
            # Truncate long outputs
            value_str = str(variable)
            if len(value_str) > 200:
                if isinstance(variable, (list, tuple)):
                    value_str = f"{type(variable).__name__}(len={len(variable)})"
                elif isinstance(variable, dict):
                    keys_preview = list(variable.keys())[:3]
                    value_str = f"dict(keys={keys_preview}{'...' if len(variable) > 3 else ''}, total={len(variable)})"
                else:
                    value_str = value_str[:200] + "... (truncated)"
            return f"{final_variable_key} = {value_str}"
        elif stringable:
            # Show string representation with truncation
            value_str = str(variable)[:200]
            if len(str(variable)) > 200:
                value_str += "..."
            return f"{final_variable_key}: {type(variable).__name__} = {value_str}"
        else:
            return f"{final_variable_key}: {type(variable).__name__} (saved)"
    else:
        raise Exception(
            f"Failed to save variable '{final_variable_key}' for router {router_id}"
        )


async def process_output(
    value: Any,
    variable_name: str,
    router_id: str,
    db: AgentDatabase,
) -> str:
    """Process an output variable and route to appropriate handler

    Detects whether the value is an image or regular variable and
    calls the appropriate process function.

    Returns:
        str: Formatted string describing the variable for display
    """
    # Check if it's a PIL Image
    try:
        from PIL import Image
        if isinstance(value, Image.Image):
            return await process_image_variable(value, variable_name, router_id, db)
    except ImportError:
        pass

    # Otherwise treat as regular variable
    return await process_variable(value, variable_name, router_id, db)


async def worker_initialisation(task_data: dict):
    """
    Initialise worker and create FullTask from the saved Task.

    This function is called when router creates a task and frontend requests worker initialisation.
    It loads the Task from router's current_task field, creates worker record, and prepares
    the worker for execution.
    Now uses router_id and returns next action for frontend.

    Args:
        task_data: Dict containing task information and payload:
            - entity_id: worker_id (which IS the task_id from the Task)
            - payload: dict with router_id
    """
    worker_id = task_data["entity_id"]
    payload = task_data.get("payload", {})
    router_id = payload["router_id"]

    logger.info(
        f"Starting worker initialisation for worker {worker_id}, router {router_id}"
    )

    db = await AgentDatabase.create()

    # Check if this is a resume scenario (worker already exists)
    existing_worker = await db.get_worker(worker_id)

    if existing_worker:
        logger.info(
            f"Worker {worker_id} already exists - resuming execution, skipping initialisation"
        )
        # Return next action for frontend to execute
        querying_structured_data = existing_worker.get("querying_structured_data", False)
        return {
            "next_action": "execute_sql_worker" if querying_structured_data else "execute_standard_worker",
            "worker_id": worker_id,
            "router_id": router_id
        }

    try:
        # Get router data to access current task and context
        router_data = await db.get_router(router_id)
        if not router_data:
            logger.error(f"Router {router_id} not found")
            return {"error": f"Router {router_id} not found"}

        # Load the Task from router's current_task field
        from ..models import Task
        current_task_data = router_data.get("current_task")
        if not current_task_data:
            logger.error(f"No current task found for router {router_id}")
            return {"error": "No current task found"}

        task = Task(**current_task_data)
        logger.info(f"Loaded task for worker {worker_id}: {task.task_description}")

        # Load router context data for worker
        planner_variables = get_planner_variables(router_id)  # These functions are ID-agnostic
        planner_images = get_planner_images(router_id)  # These functions are ID-agnostic

        # Get tables and files from router metadata
        router_metadata = router_data.get("agent_metadata", {})
        tables = router_metadata.get("tables", [])
        files = router_metadata.get("files", [])

        # Extract filepaths from document files
        filepaths = (
            [f.get("filepath", "") for f in files if f.get("file_type") == "document"]
            if files
            else []
        )

        # Get file paths from router for worker storage
        input_variable_filepaths = {
            variable_key: router_data.get("variable_file_paths", {}).get(
                variable_key, ""
            )
            for variable_key in task.variable_keys
            if router_data.get("variable_file_paths", {}).get(variable_key)
        }
        input_image_filepaths = {
            image_key: router_data.get("image_file_paths", {}).get(image_key, "")
            for image_key in task.image_keys
            if router_data.get("image_file_paths", {}).get(image_key)
        }

        # Set querying_structured_data to False if no tables
        querying_structured_data = task.querying_structured_data
        if not tables:
            querying_structured_data = False

        # Generate worker name
        worker_name = get_random_worker_name()

        # Create worker database record with individual parameters
        await db.create_worker(
            worker_id=worker_id,
            router_id=router_id,
            worker_name=worker_name,
            task_status="pending",
            task_description=task.task_description,
            acceptance_criteria=task.acceptance_criteria,
            user_request=task.user_request,
            wip_answer_template=router_data.get("wip_answer", ""),
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

        # Create message manager for this worker (now that worker exists)
        message_manager = MessageManager(db, "worker", worker_id)

        # Store system instruction in satellite table instead of message chain
        system_instruction = f"Your goal is to perform the following task:\n{task.task_description}"
        await db.set_worker_system_instruction(
            worker_id=worker_id,
            system_instruction=system_instruction,
            instruction_type="default"
        )

        # Build complete content list for the user message
        content = []
        
        # Add broader context from router
        wip_template = router_data.get("wip_answer", "")
        content.append({
            "type": "text",
            "text": "Below is broader level context for your task:\n\n"
            f"**Original user request:**\n\n{task.user_request}\n\n"
            f"**Work in progress answer template:**\n\n{wip_template}\n\n"
            "This is not your goal for this task, make sure you stay focused on the task at hand."
        })

        # Add input images if any
        if task.image_keys and planner_images:
            for image_key in task.image_keys:
                if image_key in planner_images:
                    image = planner_images[image_key]
                    # Add image content
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image}"}
                    })
                    # Add image instructions
                    decoded_image = decode_image(image)
                    content.append({
                        "type": "text",
                        "text": f"The above image can be accessed via python using the following code to convert the image into PIL.Image object:\n"
                        f"```python\nimport io\nimport base64\nImage.open(io.BytesIO(base64.b64decode({image_key})))\n```\n"
                        f"Note 1: Do not assign {image_key} variable, assume it already exists in the environment.\n"
                        f"Note 2: You must import io and base64 as part of the code.\n"
                        f"The dimensions of the image is width = {decoded_image.width}, height = {decoded_image.height}. "
                        "If image manipulation is required, use these dimensions to produce precise coordinates for cropping or combining charts."
                    })

        # Add input variables if any
        if task.variable_keys and planner_variables:
            content.append({
                "type": "text",
                "text": "The following variables are available for use, they already exist in the environment, "
                f"you do not need to declare or create it: {', '.join(task.variable_keys)}"
            })
            for variable_name in task.variable_keys:
                if variable_name in planner_variables:
                    variable = planner_variables[variable_name]
                    content.append({
                        "type": "text",
                        "text": f"# {variable_name}\nType: {type(variable)}\n\n"
                        f"Length of variable: {len(str(variable))}\n\n"
                        f"Variable content (first 10000 characters)```\n{str(variable)[:10000]}\n```"
                    })

        # Add file paths if any
        if filepaths:
            content.append({
                "type": "text",
                "text": f"The following PDF files are available for use: {', '.join(filepaths)}"
            })

        # Add tools if any
        if task.tools:
            tools_text = "\n\n---\n\n".join(
                [f"# {t}\n{TOOLS.get(t).__doc__}" for t in task.tools]
            )
            content.append({
                "type": "text",
                "text": f"You may use the following function(s):\n\n{tools_text}\n\n"
                "When using the function(s) you can assume that they already exists in the environment, "
                "to use it, simply call the function with the required parameters. "
                "You must use the function(s) where possible, do not ever try to perform the same action with other code."
            })
        
        # Single add_message call with all content
        await message_manager.add_message(role="user", content=content)

        logger.info(f"Set up initial messages for worker {worker_id}")

        # Return next action for frontend to execute based on worker type
        next_action = "execute_sql_worker" if querying_structured_data else "execute_standard_worker"

        logger.info(
            f"Worker initialisation completed for worker {worker_id}, ready for {next_action}"
        )

        return {
            "next_action": next_action,
            "worker_id": worker_id,
            "router_id": router_id
        }

    except Exception as e:
        logger.error(f"Worker initialisation failed for worker {worker_id}: {e}")
        # Mark worker as failed if it exists
        try:
            await db.update_worker(worker_id, task_status="failed")
        except:
            pass
        # Return error for frontend to handle
        return {
            "error": f"Worker initialisation failed: {str(e)}",
            "worker_id": worker_id,
            "router_id": router_id
        }


async def execute_standard_worker(task_data: dict):
    """
    Execute one attempt of standard worker task with code generation and sandboxed execution.

    This function handles ONE execution attempt and decides whether to retry (queue self)
    or complete (queue planner synthesis). Always ensures planner synthesis is queued.

    Args:
        task_data: Dict containing task information:
            - entity_id: worker_id
            - payload: optional dict (router_id passed for context)
    """
    worker_id = task_data["entity_id"]

    logger.info(f"Starting standard worker execution attempt for worker {worker_id}")

    db = await AgentDatabase.create()

    # Load worker state from database
    worker_data = await db.get_worker(worker_id)
    if not worker_data:
        logger.error(f"Worker {worker_id} not found in database")
        return

    # Always get router_id from worker database record for consistency
    router_id = worker_data["router_id"]

    # Fetch system instruction from satellite table
    system_instruction = await db.get_worker_system_instruction(
        worker_id=worker_id,
        instruction_type="default"
    )
    if not system_instruction:
        raise ValueError(f"System instruction not found for worker {worker_id}. This should not happen.")

    # Create message manager for this worker
    message_manager = MessageManager(db, "worker", worker_id)

    # Load router variables and images for worker execution
    planner_variables = get_planner_variables(router_id)
    planner_images = get_planner_images(router_id)

    # Get worker messages from database
    messages = await message_manager.get_messages()

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
            system_instruction=system_instruction,
        )

        # Defensive check: Handle case where LLM service returns None
        if task_result is None:
            logger.error(
                f"LLM service returned None for worker {worker_id}. This typically indicates API errors or authentication issues."
            )
            return

        logger.info(f"Task result: {task_result.model_dump_json(indent=2)}")

        # Update attempt counter
        await db.update_worker(worker_id=worker_id, current_attempt=current_attempt)

        if task_result.python_code:
            # Check for malicious code
            if task_result.is_malicious:
                error_message = "The code is either making changes to the database or creating executable files - this is considered malicious and not permitted."
                messages = await message_manager.add_message(
                    role="assistant",
                    content=f"{error_message}\\nRewrite the python code to fix the error.",
                )

                # Queue retry if attempts remain
                if current_attempt < max_retry:
                    return {
                        "next_action": "execute_standard_worker",
                        "worker_id": worker_id,
                        "router_id": router_id
                    }
                else:
                    # Max retries reached - mark as failed and queue synthesis
                    await db.update_worker(
                        worker_id=worker_id,
                        task_status="failed_validation",
                        task_result="Task failed: Malicious code detected after multiple attempts.",
                    )
                    return {
                        "next_action": "synthesis",
                        "worker_id": worker_id,
                        "router_id": router_id
                    }
                return

            messages = await message_manager.add_message(
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
                messages = await message_manager.add_message(
                    role="assistant",
                    content="Below outputs are generated on executing python code.",
                )

                if sandbox_result["output"]:
                    messages = await message_manager.add_message(
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
                                    router_id,
                                    db,
                                )
                        elif isinstance(var_value, dict):
                            for img_key, img in var_value.items():
                                await process_image_variable(
                                    img,
                                    f"{output_var.name}_{img_key}",
                                    worker_id,
                                    router_id,
                                    db,
                                )
                        elif isinstance(var_value, Image.Image):
                            await process_image_variable(
                                var_value,
                                output_var.name,
                                worker_id,
                                router_id,
                                db,
                                message_manager,
                            )
                        else:
                            error_message = f"Incorrect output: if {output_var.name} is an image, it must be a PIL.Image object or a list[Image] or dict[str:Image] object, no other choices are allowed."
                            messages = await message_manager.add_message(
                                role="assistant",
                                content=f"{error_message}\\nRewrite the python code to fix the error.",
                            )

                            # Queue retry
                            if current_attempt < max_retry:
                                return {
                                    "next_action": "execute_standard_worker",
                                    "worker_id": worker_id,
                                    "router_id": router_id
                                }
                            else:
                                await db.update_worker(
                                    worker_id=worker_id,
                                    task_status="failed_validation",
                                    task_result=error_message,
                                )
                                update_planner_next_task_and_queue(
                                    router_id, "execute_synthesis"
                                )
                            return
                    else:
                        var_value = sandbox_result["variables"][output_var.name]
                        await process_variable(
                            var_value,
                            output_var.name,
                            worker_id,
                            router_id,
                            db,
                            message_manager,
                        )

                # Process functions have already saved outputs to files and updated database paths
                # No need to update worker output dictionaries

                # Validate result
                validated = await validate_worker_result(
                    worker_id, worker_data["acceptance_criteria"], db, message_manager
                )
                if validated:
                    # Queue planner synthesis on successful completion
                    await update_planner_next_task_and_queue(
                        router_id, "execute_synthesis"
                    )
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
                    system_instruction=system_instruction,
                )

                if tool_check.tool_not_available:
                    failure_message = "Task failed: Required tool was not provided"
                    await db.update_worker(
                        worker_id=worker_id,
                        task_status="failed_validation",
                        task_result=failure_message,
                    )
                    messages = await message_manager.add_message(
                        role="assistant",
                        content=f"{failure_message}\\n\\n{sandbox_result['stack_trace']}\\n\\nRequired tool is not available, please supply the task with the required tool and try again.",
                    )
                    # Queue synthesis regardless of tool failure
                    return {
                        "next_action": "synthesis",
                        "worker_id": worker_id,
                        "router_id": router_id
                    }
                    return

                messages = await message_manager.add_message(
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
                    messages=messages,
                    model=settings.worker_model,
                    temperature=0,
                    response_format=RepeatFail,
                    system_instruction=system_instruction,
                )

                if repeated_fail.repeated_failure:
                    failure_message = f"{error_message}\\n\\nRepeated failure: {repeated_fail.failure_summary}"
                    await db.update_worker(
                        worker_id=worker_id,
                        task_status="failed_validation",
                        task_result=failure_message,
                    )
                    # Queue synthesis for repeated failure
                    return {
                        "next_action": "synthesis",
                        "worker_id": worker_id,
                        "router_id": router_id
                    }
                    return

        else:
            # No Python code generated, just text response
            messages = await message_manager.add_message(
                role="assistant", content=task_result.result
            )

            validated = await validate_worker_result(
                worker_id, worker_data["acceptance_criteria"], db, message_manager
            )
            if validated:
                # Queue planner synthesis on successful completion
                return {
                    "next_action": "synthesis",
                    "worker_id": worker_id,
                    "router_id": router_id
                }
                return

        # If we reach here, validation failed - check if more retries available
        if current_attempt < max_retry:
            logger.info(
                f"Worker {worker_id} validation failed, queueing retry {current_attempt + 1}/{max_retry}"
            )
            return {
                "next_action": "execute_standard_worker",
                "worker_id": worker_id,
                "router_id": router_id
            }
        else:
            # All retries exhausted - mark as failed and queue synthesis
            logger.info(
                f"Worker {worker_id} exhausted all {max_retry} retries, marking as failed"
            )
            await db.update_worker(
                worker_id=worker_id,
                task_status="failed_validation",
                task_result="Task failed after multiple tries.",
            )
            return {
                "next_action": "synthesis",
                "worker_id": worker_id,
                "router_id": router_id
            }

    except Exception as e:
        logger.error(f"Standard worker execution failed for worker {worker_id}: {e}")
        await db.update_worker(
            worker_id=worker_id,
            task_status="failed",
            task_result=f"Worker execution failed: {str(e)}",
        )
        # Always return synthesis even on unexpected errors
        return {
            "next_action": "synthesis",
            "worker_id": worker_id,
            "router_id": router_id,
            "error": str(e)
        }


async def execute_sql_worker(task_data: dict):
    """
    Execute one attempt of SQL worker task with DuckDB execution.

    This function handles ONE execution attempt and decides whether to retry (queue self)
    or complete (queue planner synthesis). Always ensures planner synthesis is queued.

    Args:
        task_data: Dict containing task information:
            - entity_id: worker_id
            - payload: optional dict (router_id passed for context)
    """

    worker_id = task_data["entity_id"]

    logger.info(f"Starting SQL worker execution attempt for worker {worker_id}")

    db = await AgentDatabase.create()

    # Load worker state from database
    worker_data = await db.get_worker(worker_id)
    if not worker_data:
        logger.error(f"Worker {worker_id} not found in database")
        return

    # Always get router_id from worker database record for consistency
    router_id = worker_data["router_id"]

    # Fetch system instruction from satellite table
    system_instruction = await db.get_worker_system_instruction(
        worker_id=worker_id,
        instruction_type="default"
    )
    if not system_instruction:
        raise ValueError(f"System instruction not found for worker {worker_id}. This should not happen.")

    # Create message manager for this worker
    message_manager = MessageManager(db, "worker", worker_id)

    # Get worker messages from database
    messages = await message_manager.get_messages()

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
        await db.update_worker(worker_id=worker_id, current_attempt=current_attempt)

        # Get SQL artefact from LLM
        sql_artefact = await llm.a_get_response(
            messages=messages,
            model=settings.worker_model,
            temperature=0,
            response_format=TaskArtefactSQL,
            system_instruction=system_instruction,
        )

        logger.info(f"SQL artefact: {sql_artefact.model_dump_json(indent=2)}")

        if sql_artefact.sql_code:
            try:
                # Execute SQL in DuckDB
                sql_output = duck_conn.execute(sql_artefact.sql_code).df().to_markdown()
                messages = await message_manager.add_message(
                    role="assistant",
                    content=f"The following code was executed:\\n\\n```sql\\n\\n{sql_artefact.sql_code}\\n\\n```\\n\\n"
                    f"The output is:\\n\\n{sql_output}",
                )

                # Validate result
                validated = await validate_worker_result(
                    worker_id, worker_data["acceptance_criteria"], db, message_manager
                )
                if validated:
                    # Queue planner synthesis on successful completion
                    await update_planner_next_task_and_queue(
                        router_id, "execute_synthesis"
                    )
                    return

            except Exception as e:
                error_message = f"Error executing SQL code: {e}"
                messages = await message_manager.add_message(
                    role="assistant",
                    content=f"{error_message}\\n\\nRewrite the SQL code to fix the error.",
                )

        else:
            # No SQL code generated
            error_message = (
                f"SQL code cannot be generated. {sql_artefact.reason_code_not_created}"
            )
            await db.update_worker(
                worker_id=worker_id,
                task_status="failed_validation",
                task_result=error_message,
            )
            messages = await message_manager.add_message(
                role="assistant", content=error_message
            )
            # Queue synthesis for SQL generation failure
            return {
                "next_action": "synthesis",
                "worker_id": worker_id,
                "router_id": router_id
            }
            return

        # If we reach here, validation failed - check if more retries available
        if current_attempt < max_retry:
            logger.info(
                f"SQL Worker {worker_id} validation failed, queueing retry {current_attempt + 1}/{max_retry}"
            )
            return {
                "next_action": "execute_sql_worker",
                "worker_id": worker_id,
                "router_id": router_id
            }
        else:
            # All retries exhausted - mark as failed and queue synthesis
            logger.info(
                f"SQL Worker {worker_id} exhausted all {max_retry} retries, marking as failed"
            )
            await db.update_worker(
                worker_id=worker_id,
                task_status="failed_validation",
                task_result="SQL task failed after multiple tries.",
            )
            return {
                "next_action": "synthesis",
                "worker_id": worker_id,
                "router_id": router_id
            }

    except Exception as e:
        logger.error(f"SQL worker execution failed for worker {worker_id}: {e}")
        await db.update_worker(
            worker_id=worker_id,
            task_status="failed",
            task_result=f"SQL worker execution failed: {str(e)}",
        )
        # Always return synthesis even on unexpected errors
        return {
            "next_action": "synthesis",
            "worker_id": worker_id,
            "router_id": router_id,
            "error": str(e)
        }
    finally:
        # Clean up DuckDB connection
        if "duck_conn" in locals():
            duck_conn.close()
