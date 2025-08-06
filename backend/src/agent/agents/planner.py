import uuid
import logging
import duckdb
import re
from pathlib import Path
from typing import Union, Optional
from PIL import Image
from datetime import datetime
from ..core.base import BaseAgent
from ..config.settings import settings
from .worker import WorkerAgent, WorkerAgentSQL
from ..utils.tools import encode_image
from ..models import (
    FullTask,
    Tasks,
    RequestResponse,
    RequestValidation,
    File,
    TOOLS,
    TableMeta,
    ColumnMeta,
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
    
    async def queue_single_task(self, task) -> str:
        """Queue a single FullTask to database and return worker_id"""
        # task is already a FullTask, use it directly
        worker_id = task.task_id
        
        # Create worker record in database
        self.agent_db.create_worker(
            worker_id=worker_id,
            planner_id=self.planner_id,
            task_data=task
        )
        
        logger.info(f"Queued task {worker_id} for planner {self.planner_id}")
        return worker_id
    
    async def get_current_task(self) -> Optional[str]:
        """Get worker_id of current pending task"""
        workers = self.agent_db.get_workers_by_planner(self.planner_id)
        for worker in workers:
            if worker['task_status'] == 'pending':
                return worker['worker_id']
        return None
    
    async def execute_current_task(self, duck_conn=None) -> bool:
        """Execute the current pending task and return success status"""
        current_task_id = await self.get_current_task()
        if not current_task_id:
            return False
        
        # Update task status to in_progress
        self.agent_db.update_worker_status(current_task_id, "in_progress")
        
        # Get task data from database
        worker_data = self.agent_db.get_worker(current_task_id)
        if not worker_data:
            logger.error(f"Could not find worker data for {current_task_id}")
            return False
        
        try:
            # Create appropriate worker
            if worker_data['querying_data_file']:
                worker = WorkerAgentSQL(
                    id=current_task_id,
                    planner_id=self.planner_id,
                    duck_conn=duck_conn
                )
            else:
                worker = WorkerAgent(
                    id=current_task_id,
                    planner_id=self.planner_id
                )
            
            # Execute the worker
            await worker.invoke()
            
            # Worker will update its own status during execution
            logger.info(f"Task {current_task_id} execution completed")
            return True
            
        except Exception as e:
            logger.error(f"Task {current_task_id} execution failed: {e}")
            self.agent_db.update_worker_status(current_task_id, "failed_validation")
            return False
    
    async def get_completed_task(self) -> Optional[FullTask]:
        """Get a completed task that needs recording"""
        workers = self.agent_db.get_workers_by_planner(self.planner_id)
        
        for worker in workers:
            if worker['task_status'] in ['completed', 'failed_validation']:
                # Convert from database format back to FullTask
                return FullTask(
                    task_id=worker['worker_id'],
                    task_status=worker['task_status'],
                    task_description=worker['task_description'],
                    acceptance_criteria=worker['acceptance_criteria'],
                    task_context=worker['task_context'],
                    task_result=worker['task_result'],
                    querying_data_file=worker['querying_data_file'],
                    image_keys=worker['image_keys'],
                    variable_keys=worker['variable_keys'],
                    tools=worker['tools'],
                    input_images=worker['input_images'],
                    input_variables=worker['input_variables'],
                    output_images=worker['output_images'],
                    output_variables=worker['output_variables'],
                    tables=worker['tables']
                )
        return None
    
    async def mark_task_recorded(self, task_id: str):
        """Mark task as recorded after planner processes it"""
        self.agent_db.update_worker_status(task_id, "recorded")
    
    async def has_pending_tasks(self) -> bool:
        """Check if there are any pending tasks"""
        return await self.get_current_task() is not None
    
    async def recover_from_restart(self) -> Optional[str]:
        """Recover any in-progress task from previous session"""
        workers = self.agent_db.get_workers_by_planner(self.planner_id)
        for worker in workers:
            if worker['task_status'] == 'in_progress':
                logger.info(f"Found interrupted task {worker['worker_id']}, marking as pending for retry")
                # Reset to pending for retry
                self.agent_db.update_worker_status(worker['worker_id'], "pending")
                return worker['worker_id']
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
    ):
        super().__init__(id=id, agent_type="planner")
        
        state = self._agent_db.get_planner(self.id) if self._init_by_id else None
        if state:
            self._load_existing_state(state)
        else:
            self._create_new_planner(user_question, instruction, model, temperature, failed_task_limit)
        
        # Initialize planner-specific attributes (both new and existing)
        self.task_manager = TaskManager(planner_id=self.id, agent_db=self._agent_db)
        self.files = files
        self.images = {}
        self.variables = {}
        self.failed_task = []
        self.user_response = RequestResponse(workings=[], markdown_response="")
        self.duck_conn = None
        self.tables = []
        self.docs = []
        if files:
            for f in files:
                if f.file_type == "image":
                    self.load_image(image=f.filepath)
                    self.add_message(
                        role="user",
                        content=f.model_dump_json(indent=2, include={"image_context"}),
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
                        self.add_message(
                            role="user",
                            content=f"Data file `{f.filepath}` converted to table `{table_name}` in database. Below is table metadata:\n\n{table_meta.model_dump_json(indent=2)}",
                        )
                elif f.file_type == "document":
                    pass

        self.context_message_len = len(self.messages)
        if not state:
            self.add_message(role="user", content=user_question)
        logger.debug(f"Planner {self.id}\nuser question: {self.user_question}")
        logger.debug(f"Planner {self.id}\ninstruction: {self.instruction}")
    def _load_existing_state(self, state):
        """Load planner-specific state from database"""
        self._user_question = state['user_question']
        self._instruction = state['instruction']
        self._model = state['model']
        self._temperature = state['temperature']
        self._failed_task_limit = state['failed_task_limit']
        self._status = state['status']
        self._execution_plan = state['execution_plan'] or ""
    
    def _create_new_planner(self, user_question, instruction, model, temperature, failed_task_limit):
        """Create new planner with database record and initial setup"""
        # Create database record first
        self._agent_db.create_planner(
            planner_id=self.id,
            user_question=user_question or "",
            instruction=instruction or "",
            model=model,
            temperature=temperature,
            failed_task_limit=failed_task_limit,
            status="planning"
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
        return getattr(self, '_user_question', '')
    
    @user_question.setter
    def user_question(self, value):
        self._user_question = value
        self.update_agent_state(user_question=value)
    
    @property
    def instruction(self):
        return getattr(self, '_instruction', '')
    
    @instruction.setter
    def instruction(self, value):
        self._instruction = value
        self.update_agent_state(instruction=value)
    
    @property
    def status(self):
        return getattr(self, '_status', 'planning')
    
    @status.setter
    def status(self, value):
        self._status = value
        self.update_agent_state(status=value)
    
    @property
    def execution_plan(self):
        return getattr(self, '_execution_plan', '')
    
    @execution_plan.setter
    def execution_plan(self, value):
        self._execution_plan = value
        self.update_agent_state(execution_plan=value)
    
    @property
    def failed_task_limit(self):
        return getattr(self, '_failed_task_limit', settings.failed_task_limit)
    
    @failed_task_limit.setter
    def failed_task_limit(self, value):
        self._failed_task_limit = value
        self.update_agent_state(failed_task_limit=value)
    
    async def invoke(self):
        # Step 1: Check for restart recovery first
        await self.task_manager.recover_from_restart()
        
        while True:
            # Step 2: Check if we have pending/in-progress work from restart
            if await self.task_manager.has_pending_tasks():
                logger.info("Found pending task, resuming execution")
            else:
                # Step 3: Generate new tasks from LLM
                tools_text = "\n\n---\n\n".join(
                    [f"# {name}\n{tool.__doc__}" for name, tool in TOOLS.items()]
                )
                appending_msgs = [
                    {
                        "role": "developer",
                        "content": f"You can use the following tools:\n\n{tools_text}",
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
                if self.instruction:
                    appending_msgs.append(
                        {
                            "role": "developer",
                            "content": f"Here is the instruction:\n\n{self.instruction}\n\n"
                            "Some parts of the instructions may have already been performed, "
                            "just ignore them and produce a list of subsequent tasks to proceed with.",
                        }
                    )

                # Add today's date
                today_date = datetime.now().strftime("%d %b %Y")
                appending_msgs.append(
                    {
                        "role": "developer",
                        "content": f"Today's date is {today_date}.",
                    }
                )

                tasks = await self.llm.a_get_response(
                    messages=self.messages + appending_msgs,
                    model=self.model,
                    temperature=self.temperature,
                    response_format=Tasks,
                )
                
                logger.info(f"Tasks: {tasks.model_dump_json(indent=2)}")
                
                # Step 4: Queue ONLY the first task
                first_task = tasks.tasks[0]
                fulltask = FullTask(
                    **first_task.model_dump(),
                    task_id=uuid.uuid4().hex,
                    input_images={
                        image_key: self.images.get(image_key)
                        for image_key in first_task.image_keys
                        if self.images.get(image_key)
                    },
                    input_variables={
                        variable_key: self.variables.get(variable_key)
                        for variable_key in first_task.variable_keys
                        if self.variables.get(variable_key)
                    },
                    tables=self.tables,
                )
                
                await self.task_manager.queue_single_task(fulltask)
            
            # Step 5: Execute current task (whether from restart or newly created)
            success = await self.task_manager.execute_current_task(duck_conn=self.duck_conn)
            if not success:
                logger.error("Task execution failed, breaking loop")
                break
            
            # Step 6: assess_completion handles task processing and marking as recorded
            request_validation = await self.assess_completion()
            logger.debug(
                f"Request validation: {request_validation.model_dump_json(indent=2)}"
            )
            if request_validation.user_request_fulfilled:
                self.user_response = await self.llm.a_get_response(
                    messages=self.messages[self.context_message_len :],
                    model=self.model,  # intentionally hardcoded
                    temperature=0,  # intentionally hardcoded
                    response_format=RequestResponse,
                )
                break
            else:
                self.add_message(
                    role="assistant",
                    content=request_validation.progress_summary,
                )

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

    async def assess_completion(self):
        # Get completed tasks from database that need recording
        result = await self.task_manager.get_completed_task()
        if result:
            if result.task_status == "completed":
                # Add a message to the conversation history about the completed task
                self.add_message(
                    role="developer",
                    content=f"Task {result.task_id} has been completed:\n"
                    f"Task context:\n{result.task_context.context}\n\n"
                    f"Task description:\n{result.task_description}\n\n"
                    f"Acceptance criteria:\n{result.acceptance_criteria}\n\n"
                    f"Task result:\n{result.task_result}",
                )
                
                # Process output images and variables
                for image_key, image in result.output_images.items():
                    self.load_image(encoded_image=image, image_name=image_key)
                for variable_key, variable in result.output_variables.items():
                    self.variables[variable_key] = variable
                    
            elif result.task_status == "failed_validation":
                await self._process_failed_task(result)
            
            # Mark task as recorded in database
            await self.task_manager.mark_task_recorded(result.task_id)

        if len(self.failed_task) >= self.failed_task_limit:
            self.add_message(
                role="developer",
                content=f"The following tasks have failed validation so far:\n{'\n - '.join(self.failed_task)}. "
                "The agent will be terminated here to avoid endless loops.",
            )
            # response = await self.llm.a_get_response(
            #     messages=self.messages, model=self.model, temperature=self.temperature
            # )
            return RequestValidation(
                user_request_fulfilled=True,
                progress_summary="",
            )
        request_validation = await self.llm.a_get_response(
            messages=self.messages
            + [
                {
                    "role": "developer",
                    "content": f"For context, the full set of instructions are:\n\n{self.instruction}\n\n"
                    "Determine if the user request has been fulfilled based on the original request and instructions.",
                }
            ],
            model=self.model,
            temperature=self.temperature,
            response_format=RequestValidation,
        )
        logger.debug(
            f"Planner {self.id} request validation:\n\n{request_validation.model_dump_json(indent=2)}"
        )
        return request_validation

    async def _process_failed_task(self, t: FullTask):
        # Add a message to the conversation history about the failed task
        self.add_message(
            role="developer",
            content=f"Task {t.task_id} was actioned but did not pass validation:\n"
            f"Task context:\n{t.task_context.context}\n\n"
            f"Task description:\n{t.task_description}\n\n"
            f"Acceptance criteria:\n{t.acceptance_criteria}\n\n"
            f"Task result:\n{t.task_result}",
        )
        self.failed_task.append(t.task_description)

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
