import asyncio
import uuid
import logging
import duckdb
import re
import random
from pathlib import Path
from typing import Union, Optional
from PIL import Image
from datetime import datetime
from ..core.base import BaseAgent
from ..config.settings import settings
from ..config.agent_names import get_random_planner_name
from .worker import WorkerAgent, WorkerAgentSQL
from ..utils.tools import encode_image
from ..utils.execution_plan_converter import (
    initial_plan_to_execution_plan_model,
    execution_plan_model_to_markdown,
    validate_execution_plan_model,
    get_next_action_task,
    has_pending_tasks,
)
from ..models import (
    FullTask,
    Task,
    RequestResponse,
    File,
    TOOLS,
    TableMeta,
    ColumnMeta,
    ExecutionPlanModel,
    InitialExecutionPlan,
)


# Set up logging
logger = logging.getLogger(__name__)


def clean_table_name(input_string: str):
    """
    Clean input string to create a valid SQL table name.

    Steps:
    1. Replace non-alphanumeric characters with spaces
    2. Remove leading/trailing spaces and collapse consecutive spaces
    3. Replace spaces with underscores
    4. Ensure first character is alphabetic
    """
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


def clean_column_name(input_string: str, i: int, all_cols: list[str]):
    """
    Clean input string to create a valid SQL column name.

    Steps:
    1. Replace non-alphanumeric characters with underscores
    2. Remove leading/trailing underscores
    3. Ensure first character is alphabetic
    """
    if not input_string:
        return f"col_{str(i).zfill(3)}"

    # Remove all non-alphanumeric characters except underscores
    cleaned = input_string.replace(r"%", "percent")
    cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", cleaned)
    cleaned = cleaned.strip("_")  # Remove leading/trailing underscores

    # If string is empty after cleaning, return fallback
    if not cleaned:
        return f"col_{str(i).zfill(3)}"

    # Ensure first character is alphabetic
    if not cleaned[0].isalpha():
        cleaned = "col_" + cleaned

    if cleaned in all_cols or f"{cleaned}_" in all_cols:
        return f"{cleaned}_{str(i).zfill(3)}"
    try:
        duckdb.sql(f"select 1 {cleaned}")
        return cleaned
    except:
        return f"{cleaned}_"


class TaskManager:
    def __init__(self, planner_id: str, agent_db):
        self.planner_id = planner_id
        self.agent_db = agent_db
        # In-memory queue for new tasks - prevents premature database creation
        self._pending_queue = []

    async def queue_single_task(self, task) -> str:
        """Queue a single FullTask in memory and return worker_id"""
        # Store task in memory queue - do NOT create database record yet
        worker_id = task.task_id
        self._pending_queue.append(task)

        logger.info(f"Queued task {worker_id} for planner {self.planner_id} in memory")
        return worker_id

    async def get_current_task(self) -> Optional[Union[str, FullTask]]:
        """Get current pending task - prioritise database (resumption) over memory queue (new tasks)"""
        # Check database first for resumed tasks (highest priority)
        workers = self.agent_db.get_workers_by_planner(self.planner_id)
        for worker in workers:
            if worker["task_status"] == "pending":
                return worker["worker_id"]  # Return worker_id for resumption

        # If no database tasks, check in-memory queue for new tasks
        if self._pending_queue:
            return self._pending_queue[0]  # Return FullTask object for new tasks

        # No tasks available
        return None

    async def execute_current_task(self, duck_conn=None) -> bool:
        """Execute the current pending task and return success status"""
        current_task = await self.get_current_task()
        if not current_task:
            return False

        try:
            # Handle two cases: FullTask from memory queue or worker_id from database
            if isinstance(current_task, FullTask):
                # New task from in-memory queue
                task = current_task
                task_id = task.task_id

                # Remove this specific task from memory queue by ID (future-proof for multiple tasks)
                self._pending_queue = [
                    t for t in self._pending_queue if t.task_id != task_id
                ]
                logger.info(f"Removed task {task_id} from memory queue for execution")

                # Create appropriate worker with FullTask (this will create database record)
                if task.querying_structured_data:
                    worker = WorkerAgentSQL(
                        task=task, planner_id=self.planner_id, duck_conn=duck_conn
                    )
                else:
                    worker = WorkerAgent(task=task, planner_id=self.planner_id)

            else:
                # Existing task from database (resumption case)
                task_id = current_task

                # Update task status to in_progress
                self.agent_db.update_worker_status(task_id, "in_progress")

                # Get task data from database
                worker_data = self.agent_db.get_worker(task_id)
                if not worker_data:
                    logger.error(f"Could not find worker data for {task_id}")
                    return False

                # Create appropriate worker by ID (loads from database)
                if worker_data["querying_structured_data"]:
                    worker = WorkerAgentSQL(
                        id=task_id, planner_id=self.planner_id, duck_conn=duck_conn
                    )
                else:
                    worker = WorkerAgent(id=task_id, planner_id=self.planner_id)

            # Execute the worker
            await worker.invoke()

            # Worker will update its own status during execution
            logger.info(f"Task {task_id} execution completed")
            return True

        except Exception as e:
            task_id = (
                current_task.task_id
                if isinstance(current_task, FullTask)
                else current_task
            )
            logger.error(f"Task {task_id} execution failed: {e}")
            self.agent_db.update_worker_status(task_id, "failed_validation")
            return False

    async def get_completed_task(self) -> Optional[FullTask]:
        """Get a completed task that needs recording"""
        workers = self.agent_db.get_workers_by_planner(self.planner_id)

        for worker in workers:
            if worker["task_status"] in ["completed", "failed_validation"]:
                # Convert from database format back to FullTask
                return FullTask(
                    task_id=worker["worker_id"],
                    task_status=worker["task_status"],
                    task_description=worker["task_description"],
                    acceptance_criteria=worker["acceptance_criteria"],
                    task_context=worker["task_context"],
                    task_result=worker["task_result"],
                    querying_structured_data=worker["querying_structured_data"],
                    image_keys=worker["image_keys"],
                    variable_keys=worker["variable_keys"],
                    tools=worker["tools"],
                    input_images=worker["input_images"],
                    input_variables=worker["input_variables"],
                    output_images=worker["output_images"],
                    output_variables=worker["output_variables"],
                    tables=worker["tables"],
                    filepaths=worker["filepaths"],
                )
        return None

    async def mark_task_recorded(self, task_id: str):
        """Mark task as recorded after planner processes it"""
        self.agent_db.update_worker_status(task_id, "recorded")

    async def recover_from_restart(self) -> Optional[str]:
        """Recover any in-progress task from previous session"""
        workers = self.agent_db.get_workers_by_planner(self.planner_id)
        for worker in workers:
            if worker["task_status"] == "in_progress":
                logger.info(
                    f"Found interrupted task {worker['worker_id']}, marking as pending for retry"
                )
                # Reset to pending for retry
                self.agent_db.update_worker_status(worker["worker_id"], "pending")
                return worker["worker_id"]
        return None


class PlannerAgent(BaseAgent):
    def __init__(
        self,
        id: str = None,
        user_question: str = None,
        instruction: str = None,
        files: list[File] = None,
        model: str = settings.planner_model,
        temperature: float = 0,
        failed_task_limit: int = settings.failed_task_limit,
        planner_name: str = None,
    ):
        super().__init__(id=id, agent_type="planner")

        state = self._agent_db.get_planner(self.id) if self._init_by_id else None
        if state:
            self._load_existing_state(state)
        else:
            self._create_new_planner(
                user_question,
                instruction,
                model,
                temperature,
                failed_task_limit,
                planner_name,
            )

        # Initialize planner-specific attributes (both new and existing)
        self.task_manager = TaskManager(planner_id=self.id, agent_db=self._agent_db)
        self.files = files
        self.images = {}
        self.variables = {}
        self.failed_task = []
        self.user_response = ""
        self.duck_conn = None
        self.tables = []
        self.docs = []
        self.execution_plan_model = None
        self.execution_plan_callback = None
        self.tools_text = "\n\n---\n\n".join(
            [f"# {name}\n{tool.__doc__}" for name, tool in TOOLS.items()]
        )
        if files:
            for f in files:
                if f.file_type == "image":
                    self.load_image(image=f.filepath)
                    if not state:
                        self.add_message(
                            role="user",
                            content=f.model_dump_json(
                                indent=2, include={"image_context"}
                            ),
                            image=f.filepath,
                        )
                elif f.file_type == "data":
                    if not self.duck_conn:
                        self.duck_conn = duckdb.connect(database=":memory:")
                    table_name = clean_table_name(Path(f.filepath).stem)
                    if f.data_context == "csv":
                        self.duck_conn.sql(
                            f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM read_csv('{f.filepath}',strict_mode=false)"
                        )
                        table_meta = self.get_table_metadata(table_name)
                        self.tables.append(table_meta)
                        if not state:
                            self.add_message(
                                role="user",
                                content=f"Data file `{f.filepath}` converted to table `{table_name}` in database. Below is table metadata:\n\n{table_meta.model_dump_json(indent=2)}",
                            )
                elif f.file_type == "document":
                    if not state:
                        self.add_message(
                            role="user",
                            content=f"PDF file at path `{f.filepath}` is available for use.",
                        )

        self.context_message_len = len(self.messages)
        if not state:
            self.add_message(role="user", content=user_question)

            # Generate execution plan using structured format
            plan_prompt = (
                f"**Available tools for execution:**\n{self.tools_text}\n\n"
                f"**Instructions:**\n{self.instruction}\n\n"
                "Please create a detailed execution plan with an overall objective and a list of specific tasks. "
                "The objective should describe what the tasks are aiming to achieve. "
                "Each task should be specific enough to be executed independently. "
                "The instructions will no longer be visible when creating tasks later on, so make sure that the tasks are detailed enough. "
                "If required, create placeholder tasks that align to requirements in the instructions so it doesn't get lost even if you can't determine the precise downstream tasks yet."
            )

            # Get initial execution plan from LLM
            initial_plan = self.llm.get_response(
                messages=self.messages + [{"role": "user", "content": plan_prompt}],
                model=self.model,
                temperature=self.temperature,
                response_format=InitialExecutionPlan,
            )

            # Convert to full ExecutionPlanModel
            self.execution_plan_model = initial_plan_to_execution_plan_model(
                initial_plan
            )

            # Generate markdown version
            self.execution_plan = execution_plan_model_to_markdown(
                self.execution_plan_model
            )

        logger.info(f"Planner {self.id}\nuser question: {self.user_question}")
        logger.info(f"Planner {self.id}\ninstruction: {self.instruction}")
        logger.info(f"Planner {self.id}\nexecution plan: {self.execution_plan}")

    def _load_existing_state(self, state):
        """Load planner-specific state from database"""
        self._user_question = state["user_question"]
        self._instruction = state["instruction"]
        self._model = state["model"]
        self._temperature = state["temperature"]
        self._failed_task_limit = state["failed_task_limit"]
        self._status = state["status"]
        self._execution_plan = state["execution_plan"] or ""

    def _create_new_planner(
        self,
        user_question,
        instruction,
        model,
        temperature,
        failed_task_limit,
        planner_name,
    ):
        """Create new planner with database record and initial setup"""
        # Create database record first
        # Use provided name or generate random name if None
        if not planner_name:
            planner_name = get_random_planner_name()

        self._agent_db.create_planner(
            planner_id=self.id,
            planner_name=planner_name,
            user_question=user_question or "",
            instruction=instruction or "",
            model=model,
            temperature=temperature,
            failed_task_limit=failed_task_limit,
            status="planning",
        )
        # Set private attributes
        self._user_question = user_question or ""
        self._instruction = instruction or ""
        self._model = model
        self._temperature = temperature
        self._failed_task_limit = failed_task_limit
        self._status = "planning"
        self._execution_plan = ""

        # Add system message for new planners only
        self.add_message(
            role="system",
            content="You are an expert planner. Your objective is to break down the user's instruction into a list of tasks that can be individually executed.",
        )

    # Planner-specific properties with auto-sync

    @property
    def user_question(self):
        return getattr(self, "_user_question", "")

    @user_question.setter
    def user_question(self, value):
        self._user_question = value
        self.update_agent_state(user_question=value)

    @property
    def instruction(self):
        return getattr(self, "_instruction", "")

    @instruction.setter
    def instruction(self, value):
        self._instruction = value
        self.update_agent_state(instruction=value)

    @property
    def status(self):
        return getattr(self, "_status", "planning")

    @status.setter
    def status(self, value):
        self._status = value
        self.update_agent_state(status=value)

    @property
    def execution_plan(self):
        return getattr(self, "_execution_plan", "")

    @execution_plan.setter
    def execution_plan(self, value):
        self._execution_plan = value
        self.update_agent_state(execution_plan=value)
        
        # Notify callback if set (for real-time updates)
        if self.execution_plan_callback and value:
            asyncio.create_task(self.execution_plan_callback(self.id, value))
    
    def set_execution_plan_callback(self, callback):
        """Set callback function for execution plan updates"""
        self.execution_plan_callback = callback

    @property
    def failed_task_limit(self):
        return getattr(self, "_failed_task_limit", settings.failed_task_limit)

    @failed_task_limit.setter
    def failed_task_limit(self, value):
        self._failed_task_limit = value
        self.update_agent_state(failed_task_limit=value)

    async def invoke(self):
        # Step 1: Check for restart recovery first
        await self.task_manager.recover_from_restart()

        while True:
            # Step 2: Check if we have pending/in-progress work from restart
            current_task = await self.task_manager.get_current_task()
            if current_task:
                logger.info("Found pending task, resuming execution")
            else:
                # Step 3: Generate new tasks from LLM

                appending_msgs = [
                    {
                        "role": "developer",
                        "content": f"You can use the following tools:\n\n{self.tools_text}",
                    }
                ]
                if self.images:
                    appending_msgs.append(
                        {
                            "role": "developer",
                            "content": f"The following image keys are available for use: {list(self.images.keys())}",
                        }
                    )
                if self.variables:
                    appending_msgs.append(
                        {
                            "role": "developer",
                            "content": f"The following variable keys are available for use: {list(self.variables.keys())}",
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
                        "content": f"For context, your complete execution plan is: {self.execution_plan}\n"
                        f"The next todo item to be converted to a task is: {get_next_action_task(self.execution_plan_model).description}",
                    }
                )
                task = await self.llm.a_get_response(
                    messages=self.messages + appending_msgs,
                    model=self.model,
                    temperature=self.temperature,
                    response_format=Task,
                )

                logger.info(f"Task: {task.model_dump_json(indent=2)}")

                # Step 4: Queue the single task
                fulltask = FullTask(
                    **task.model_dump(),
                    task_id=uuid.uuid4().hex,
                    input_images={
                        image_key: self.images.get(image_key)
                        for image_key in task.image_keys
                        if self.images.get(image_key)
                    },
                    input_variables={
                        variable_key: self.variables.get(variable_key)
                        for variable_key in task.variable_keys
                        if self.variables.get(variable_key)
                    },
                    tables=self.tables,
                    filepaths=(
                        [f.filepath for f in self.files if f.file_type == "document"]
                        if self.files
                        else []
                    ),
                )
                if not self.tables:
                    fulltask.querying_structured_data = False

                await self.task_manager.queue_single_task(fulltask)

            # Step 5: Execute current task (whether from restart or newly created)
            success = await self.task_manager.execute_current_task(
                duck_conn=self.duck_conn
            )
            if not success:
                logger.error("Task execution failed, breaking loop")
                break

            await self.task_result_synthesis()

            # Step 6: assess_completion handles task processing and marking as recorded
            if await self.assess_completion():
                user_response_messages = self.messages[self.context_message_len :] + [
                    {
                        "role": "developer",
                        "content": "Using the above information only without creating any information, "
                        "either copy or create the response/answer to the user's original question/request and format the result in markdown.\n\n"
                        "Return only the markdown answer and nothing else, do not use the user's question as a title. Do not wrap the response in ```markdown ... ``` block. "
                        "Aggressively use inline citations where possible. "
                        "Remember the user will only see the next response with zero visibility over the message history, so make sure the finalised response is repeated in full here.",
                    }
                ]
                response = await self.llm.a_get_response(
                    messages=user_response_messages,
                    model=self.model,  # intentionally hardcoded
                    temperature=self.temperature,
                )
                self.user_response = response.content.strip()
                logger.info(f"User response generated in planner: {self.user_response}")
                break

    def load_image(
        self,
        image: Union[str, Path, Image.Image] = None,
        encoded_image: str = None,
        image_name="image_original",
    ):
        """
        Loads an image to be used in the planning process.
        """
        if image:
            self.images[image_name] = encode_image(image)
        elif encoded_image:
            self.images[image_name] = encoded_image
        else:
            raise ValueError("Either image or encoded_image must be provided.")

    async def task_result_synthesis(self):
        """
        Updates the execution plan using Pydantic models with validation and retry logic.
        """
        # Get the completed task that needs synthesis
        completed_task = await self.task_manager.get_completed_task()
        if not completed_task:
            logger.warning("No completed task found for synthesis")
            return

        # Get all worker messages for this task and combine non-system messages
        worker_messages = self._agent_db.get_messages("worker", completed_task.task_id)
        task_message_combined = "\n\n---\n\n".join(
            [
                msg["content"]
                for msg in worker_messages
                if msg.get("role") == "assistant"
            ]
        )
        self.add_message(
            role="assistant",
            content=f"# Responses from worker\n\n"
            f"**Task ID**: {completed_task.task_id}\n\n"
            f"**Task Description**: {completed_task.task_description}\n\n"
            f"**Task Status**: {completed_task.task_status}\n\n"
            f"**Worker Responses**:\n\n{task_message_combined}",
        )

        # Apply task completion logic BEFORE LLM call
        previous_model = self.execution_plan_model
        updated_previous_model = self._apply_task_completion_logic(
            previous_model, completed_task.task_status
        )

        # Create filtered model with only open tasks for LLM
        open_tasks_model = self._create_open_tasks_model(updated_previous_model)

        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                # Prepare update messages using only open tasks
                update_messages = self.messages + [
                    {
                        "role": "developer",
                        "content": f"**Current open tasks from execution plan:**\n\n{open_tasks_model.model_dump_json(indent=2)}",
                    },
                    {
                        "role": "developer",
                        "content": f"Based on the completed task execution details above for task `{completed_task.task_description}`, "
                        f"please update the execution plan. Instructions for reference:\n\n{self.instruction}\n\n"
                        "Follow these rules:\n"
                        "1. Update existing task descriptions using updated_description field if needed\n"
                        "2. Add new tasks if required, marking them with '(new)' in the description field\n"
                        "3. Leave next_action as False - separate logic will determine next action\n"
                        "4. Mark unnecessary tasks as obsolete=True\n"
                        "Return the updated ExecutionPlanModel with open tasks only.",
                    },
                ]

                # Add retry-specific message if this is a retry
                if retry_count > 0:
                    update_messages.append(
                        {
                            "role": "developer",
                            "content": f"Previous validation failed with errors: {validation_errors}. Please fix these issues.",
                        }
                    )

                llm_updated_model = await self.llm.a_get_response(
                    messages=update_messages,
                    model=self.model,
                    temperature=self.temperature,
                    response_format=ExecutionPlanModel,
                )

                # Merge LLM output with completed/obsolete tasks
                final_model = self._merge_models(
                    updated_previous_model, llm_updated_model
                )

                # Apply next action logic
                final_model = self._apply_next_action_logic(final_model)

                # Validate the final model
                is_valid, validation_errors = validate_execution_plan_model(
                    final_model, previous_model
                )

                if is_valid:
                    self.execution_plan_model = final_model
                    self.execution_plan = execution_plan_model_to_markdown(final_model)
                    logger.info(
                        f"Execution plan updated successfully after {retry_count + 1} attempts:\n\n{self.execution_plan}"
                    )
                    break
                else:
                    retry_count += 1
                    logger.warning(
                        f"Execution plan validation failed (attempt {retry_count}/{max_retries}): {validation_errors}"
                    )

            except Exception as e:
                retry_count += 1
                logger.error(
                    f"Error updating execution plan (attempt {retry_count}/{max_retries}): {e}"
                )
                if retry_count >= max_retries:
                    logger.error(
                        "Maximum retries reached, keeping previous execution plan"
                    )
                    break

        if completed_task.task_status == "completed":
            # Process output images and variables
            for image_key, image in completed_task.output_images.items():
                self.load_image(encoded_image=image, image_name=image_key)
            for variable_key, variable in completed_task.output_variables.items():
                self.variables[variable_key] = variable
        else:
            self.failed_task.append(completed_task.task_description)

        # Mark task as recorded in database
        await self.task_manager.mark_task_recorded(completed_task.task_id)

    def _apply_task_completion_logic(
        self, model: ExecutionPlanModel, task_status: str
    ) -> ExecutionPlanModel:
        """
        Apply task completion logic before LLM call.

        If task_status is 'completed', mark the current next_action task as completed.
        """
        if task_status == "completed":
            # Find and mark the current next_action task as completed
            for todo in model.todos:
                if todo.next_action:
                    todo.completed = True
                    todo.next_action = False
                    logger.info(f"Marked task '{todo.description}' as completed")
                    break

        return model

    def _create_open_tasks_model(self, model: ExecutionPlanModel) -> ExecutionPlanModel:
        """
        Create a model containing only open (not completed, not obsolete) tasks.
        """
        open_todos = [
            todo for todo in model.todos if not todo.completed and not todo.obsolete
        ]

        return ExecutionPlanModel(objective=model.objective, todos=open_todos)

    def _merge_models(
        self, previous_model: ExecutionPlanModel, llm_model: ExecutionPlanModel
    ) -> ExecutionPlanModel:
        """
        Merge LLM output (open tasks) with previous completed/obsolete tasks.
        """
        # Get completed and obsolete tasks from previous model
        completed_obsolete_todos = [
            todo for todo in previous_model.todos if todo.completed or todo.obsolete
        ]

        # Combine with LLM updated open tasks
        all_todos = completed_obsolete_todos + llm_model.todos

        return ExecutionPlanModel(
            objective=llm_model.objective or previous_model.objective, todos=all_todos
        )

    def _apply_next_action_logic(self, model: ExecutionPlanModel) -> ExecutionPlanModel:
        """
        Set the first open task as next_action=True, all others as False.
        """
        # Clear all next_action flags
        for todo in model.todos:
            todo.next_action = False

        # Set first open task as next_action
        for todo in model.todos:
            if not todo.completed and not todo.obsolete:
                todo.next_action = True
                break

        return model

    async def assess_completion(self):
        if len(self.failed_task) >= self.failed_task_limit:
            self.add_message(
                role="developer",
                content=f"The following tasks have failed validation so far:\n{'\n - '.join(self.failed_task)}. "
                "The agent will be terminated here to avoid endless loops.",
            )
            return True

        # Pydantic model-based completion check
        if not self.execution_plan_model or not self.execution_plan_model.todos:
            logger.info("No tasks found in execution plan - considering as completed")
            return True

        # Check if there are any pending tasks
        all_completed = not has_pending_tasks(self.execution_plan_model)

        logger.info(
            f"Pydantic model completion assessment: {len(self.execution_plan_model.todos)} total tasks, "
            f"all_completed={all_completed}"
        )
        return all_completed

    def get_table_metadata(self, table_name: str) -> TableMeta:
        # Get basic table info
        row_count = self.duck_conn.sql(f"SELECT COUNT(*) FROM {table_name}").fetchone()[
            0
        ]

        # Get top 10 rows as markdown
        top_10_md = (
            self.duck_conn.sql(f"SELECT * FROM {table_name} LIMIT 10")
            .df()
            .to_markdown(index=False)
        )

        # Get column names and types
        columns_info = self.duck_conn.sql(f"DESCRIBE {table_name}").fetchall()
        columns_new = []
        column_metas = []
        for i, col in enumerate(columns_info):
            col_name = clean_column_name(col[0], i, columns_new)
            columns_new.append(col_name)
            if col_name != col[0]:
                self.duck_conn.sql(
                    f'ALTER TABLE {table_name} RENAME COLUMN "{col[0]}" TO {col_name}'
                )
            if col[1].startswith("VARCHAR"):
                self.duck_conn.sql(
                    f"UPDATE {table_name} SET {col_name} = LTRIM(RTRIM({col_name}))"
                )
            # Calculate percentage of distinct values
            distinct_count = self.duck_conn.sql(
                f"SELECT COUNT(DISTINCT {col_name}) FROM {table_name}"
            ).fetchone()[0]
            pct_distinct = (distinct_count / row_count) if row_count > 0 else 0

            # Get min and max values
            min_max = self.duck_conn.sql(
                f"SELECT MIN({col_name}), MAX({col_name}) FROM {table_name}"
            ).fetchone()
            min_value = str(min_max[0]) if min_max[0] is not None else ""
            max_value = str(min_max[1]) if min_max[1] is not None else ""

            # Get top 3 most frequent values
            top_3_result = self.duck_conn.sql(
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

        return TableMeta(
            table_name=table_name,
            row_count=row_count,
            top_10_md=top_10_md,
            colums=column_metas,
        )
