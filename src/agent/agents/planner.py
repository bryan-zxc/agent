import uuid
import logging
import duckdb
import re
from pathlib import Path
from typing import Union
from PIL import Image
from ..core.base import BaseAgent
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


class TaskQueue:
    def __init__(self):
        self.planned_tasks = []
        self.loaded_tasks = []
        self.completed_tasks = []
        self.workers = {}

    async def load_plan(
        self, tasks: list[FullTask], duck_conn: duckdb.DuckDBPyConnection
    ):
        self.duck_conn = duck_conn
        self.planned_tasks = tasks
        await self.load_task(tasks[0])
        # TODO: add ability to catch already completed tasks and not load

    async def load_task(self, task: FullTask):
        self.loaded_tasks.append(task)
        await self.execute_task(task)

    async def execute_task(self, task: FullTask):
        # initiate worker
        worker = (
            WorkerAgentSQL(task=task, duck_conn=self.duck_conn)
            if task.querying_data_file
            else WorkerAgent(task=task)
        )
        self.workers[task.task_id] = worker
        await worker.invoke()
        # Move completed task to completed_tasks list
        self.completed_tasks.append(task)
        # Remove from loaded_tasks
        self.loaded_tasks = [t for t in self.loaded_tasks if t.task_id != task.task_id]


class PlannerAgent(BaseAgent):
    def __init__(
        self,
        user_question: str,
        instruction: str = None,
        files: list[File] = None,
        model: str = "gemini-2.5-pro",
        temperature: float = 0,
        failed_task_limit: int = 3,
    ):
        super().__init__(agent_type="planner")
        self.add_message(
            role="system",
            content="You are an expert planner. Your objective is to break down the user's instruction into a list of tasks that can be individually executed.",
        )
        self.task_queue = TaskQueue()
        self.model = model
        self.temperature = temperature
        self.instruction = instruction
        self.files = files
        self.images = {}
        self.variables = {}
        self.failed_task = []
        self.failed_task_limit = failed_task_limit
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
        self.add_message(role="user", content=user_question)

    async def invoke(self):
        while True:
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

            tasks = await self.llm.a_get_response(
                messages=self.messages + appending_msgs,
                model=self.model,
                temperature=self.temperature,
                response_format=Tasks,
            )
            # plan_validation = await self.llm.a_get_response(
            #     messages=self.messages
            #     + [
            #         {
            #             "role": "system",
            #             "content": f"The following image keys are available for use: {self.images.keys()}",
            #         },
            #         {
            #             "role": "assistant",
            #             "content": f"Assess the following task:\n{tasks.tasks[0].model_dump_json()}",
            #         },
            #     ],
            #     model=self.model,
            #     temperature=self.temperature,
            #     response_format=PlanValidation,
            # )
            # if (
            #     not plan_validation.is_context_sufficient
            #     or not plan_validation.is_acceptance_criteria_complete
            # ):
            #     # Update the task with the additional context and criteria
            #     tasks.tasks[0] = plan_validation.updated_task
            # print(tasks.model_dump_json(indent=2), flush=True)
            logger.info(f"Tasks: {tasks.model_dump_json(indent=2)}")
            fulltasks = [
                FullTask(
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
                )
                for task in tasks.tasks
            ]
            await self.task_queue.load_plan(tasks=fulltasks, duck_conn=self.duck_conn)
            request_validation = await self.assess_completion()
            # print(request_validation.model_dump_json(indent=2))
            logger.debug(
                f"Request validation: {request_validation.model_dump_json(indent=2)}"
            )
            if request_validation.user_request_fulfilled:
                self.user_response = await self.llm.a_get_response(
                    messages=self.messages[self.context_message_len :],
                    model="gpt-4o-mini-if-global",  # intentionally hardcoded
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
        for t in self.task_queue.completed_tasks:
            if t.task_status != "recorded":
                if t.task_status == "completed":
                    # Add a message to the conversation history about the completed task
                    self.add_message(
                        role="system",
                        content=f"Task {t.task_id} has been completed:\n"
                        f"Task context:\n{t.task_context.context}\n\n"
                        f"Task description:\n{t.task_description}\n\n"
                        f"Acceptance criteria:\n{t.acceptance_criteria}\n\n"
                        f"Task result:\n{t.task_result}",
                    )
                    t.task_status = "recorded"
                    for image_key, image in t.output_images.items():
                        self.load_image(encoded_image=image, image_name=image_key)
                    for variable_key, variable in t.output_variables.items():
                        self.variables[variable_key] = variable
                if t.task_status == "failed validation":
                    self._process_failed_task(t)

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
                    "content": f"For context, the full set of instructions are:\n\n{self.instruction}",
                }
            ],
            model=self.model,
            temperature=self.temperature,
            response_format=RequestValidation,
        )
        return request_validation

    async def _process_failed_task(self, t: FullTask):
        # Add a message to the conversation history about the failed task
        self.add_message(
            role="system",
            content=f"Task {t.task_id} was actioned but did not pass validation:\n"
            f"Task context:\n{t.task_context.context}\n\n"
            f"Task description:\n{t.task_description}\n\n"
            f"Acceptance criteria:\n{t.acceptance_criteria}\n\n"
            f"Task result:\n{t.task_result}",
        )
        t.task_status = "recorded"
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
        columns_orig = [col[0] for col in columns_info]
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
