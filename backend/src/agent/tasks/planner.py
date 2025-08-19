import logging
import duckdb
import re
import os
import uuid
from pathlib import Path
from typing import Union
from typing import Union
from PIL import Image
from agent.base import BaseAgent
from agent.worker import WorkerAgent, WorkerAgentSQL
from agent.tools import encode_image
from agent.models import (
    FullTask,
    Task,
    RequestResponse,
    File,
    TOOLS,
    TableMeta,
    ColumnMeta,
    SingleValueColumn,
    ExecutionPlanModel,
    InitialExecutionPlan,
    TaskResponseModel,
    AnswerTemplate,
)
from agent.execution_plan_utils import (
    initial_plan_to_execution_plan_model,
    execution_plan_model_to_markdown,
    get_next_action_task,
    merge_models,
    apply_task_completion_logic,
    create_open_tasks_model,
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
        self.planned_task = None
        self.loaded_task = None
        self.completed_task = None
        self.workers = {}

    async def load_plan(
        self,
        tasks: list[FullTask],
        duck_conn: duckdb.DuckDBPyConnection,
        task_responses: list = None,
    ):
        self.duck_conn = duck_conn
        self.task_responses = task_responses or []
        # Take only the first task since we're handling single tasks now
        await self.load_task(tasks[0])

    async def load_task(self, task: FullTask):
        self.loaded_task = task
        await self.execute_task(task)

    async def execute_task(self, task: FullTask):
        # initiate worker
        worker = (
            WorkerAgentSQL(
                task=task, duck_conn=self.duck_conn, task_responses=self.task_responses
            )
            if task.querying_data_file
            else WorkerAgent(task=task, task_responses=self.task_responses)
        )
        self.workers[task.task_id] = worker
        await worker.invoke()
        # Move completed task to completed_task
        self.completed_task = task
        # Clear loaded_task
        self.loaded_task = None


pdf_content_str = """
class ImageContent(BaseModel):
    image_name: str
    image_width: int
    image_height: int
    image_data: str  # Base64 encoded image data


class PageContent(BaseModel):
    page_number: str
    text: str
    images: list[ImageContent] = []


class PDFContent(BaseModel):
    pages: list[PageContent]
"""


class PlannerAgent(BaseAgent):
    def __init__(
        self,
        user_question: str,
        instruction: str = None,
        files: list[File] = None,
        failed_task_limit: int = 3,
    ):
        super().__init__()
        self.add_message(
            role="system",
            content="You are an expert planner. "
            "Your objective is to break down the user's instruction into a list of tasks that can be individually executed."
            "Keep in mind that quite often the first step(s) are to extra facts which commonly comes in the form of question and answer pairs. "
            "Even if there are no further unanswered questions, it only means you have all the facts required to answer the user's question, it doesn't always mean the process is complete. "
            "If there still are analysis especially calculations that is required to be applied to the facts, then you need to create further tasks to complete. "
            "Typically facts are pre-extracted and likely to be in the form of question and answer pairs, "
            "if the questions don't seem to be fully aligned to what is required for analysis, you can activate relevant tools to re-extract facts. "
            "Note: the ability to interact with user is not available, so you must not create any tasks to ask or interact with the user.",
        )
        self.task_queue = TaskQueue()
        self.model = os.getenv("AGENT_MODEL", "gpt-4.1-if-global")
        self.temperature = float(os.getenv("AGENT_TEMPERATURE", "0.0"))
        self.instruction = instruction
        self.files = files
        self.files = files
        self.images = {}
        self.variables = {}
        self.failed_task = []
        self.failed_task_limit = failed_task_limit
        self.user_response = RequestResponse(workings=[], markdown_response="")
        self.task_responses = []  # List of TaskResponseModel objects
        self.duck_conn = None
        self.tables = []
        # Execution plan attributes
        self.execution_plan_model = None
        self.execution_plan = ""
        self.tools_text = "\n\n---\n\n".join(
            [f"# {name}\n{tool.__doc__}" for name, tool in TOOLS.items()]
        )
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
                        try:
                            self.duck_conn.sql(
                                f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM read_csv('{f.filepath}',strict_mode=false)"
                            )
                            table_meta = self.get_table_metadata(table_name)
                            self.tables.append(table_meta)
                            data_file_msg = (
                                f"Data file `{f.filepath}` converted to table `{table_name}` in database. "
                                f"Below is table metadata:\n\n{table_meta.model_dump_json(indent=2)}"
                            )
                            self.add_message(
                                role="user",
                                content=data_file_msg,
                            )
                        except Exception as e:
                            logging.error(f"Error during normal CSV loading: {e}")
                            try:
                                # Second attempt: Try loading all columns as VARCHAR
                                logging.info(
                                    f"Attempting to load {f.filepath} with all columns as VARCHAR"
                                )
                                self.duck_conn.sql(
                                    f"CREATE OR REPLACE TABLE {table_name} AS SELECT * FROM read_csv('{f.filepath}', strict_mode=false, all_varchar=true)"
                                )
                                table_meta = self.get_table_metadata(table_name)
                                self.tables.append(table_meta)
                                data_file_msg = (
                                    f"Data file `{f.filepath}` converted to table `{table_name}` in database with all columns as text. "
                                    f"The original format had issues, so all data was loaded as text. "
                                    f"Below is table metadata:\n\n{table_meta.model_dump_json(indent=2)}"
                                )
                                self.add_message(
                                    role="user",
                                    content=data_file_msg,
                                )
                            except Exception as e2:
                                logging.error(
                                    f"Error during VARCHAR fallback CSV loading: {e2}"
                                )
                                data_file_msg = (
                                    f"Data file `{f.filepath}` could not be processed due to format issues. "
                                    f"Both standard and VARCHAR fallback loading failed. "
                                    f"Error: {str(e)[:250]}... Fallback error: {str(e2)[:250]}..."
                                )
                                self.add_message(
                                    role="user",
                                    content=data_file_msg,
                                )
                elif f.file_type == "document":
                    if f.document_context.file_type == "pdf":
                        # Initialize document_contents if it doesn't exist, or get existing one
                        if "document_contents" not in self.variables:
                            self.variables["document_contents"] = {}

                        # Add the new filename-content pair to the existing dictionary
                        self.variables["document_contents"][
                            f.document_context.pdf_content.filename
                        ] = f.document_context.pdf_content.content
                        self.add_message(
                            role="user",
                            content=f"Document `{f.document_context.pdf_content.filename}` loaded with the following metadata:\n\n{f.document_context.pdf_content.model_dump_json(indent=2,exclude='content')}\n\n"
                            f"The variable `document_contents` now additionally contain a new dictionary entry for `{f.document_context.pdf_content.filename}` which stores a PDFContent pydantic model. "
                            f"Below is details of DocumentContext and PDFContent:\n\n```python\n\n{pdf_content_str}\n\n```"
                            "Note `document_contents` is required for input to both search_doc tool and get_doc_index tool. ",
                        )
                    elif f.document_context.file_type == "text":
                        # Read the text file content using the stored encoding
                        try:
                            text_content = Path(f.filepath).read_text(
                                encoding=f.document_context.encoding
                            )
                            # Limit to first 100k characters
                            limited_content = text_content[:100000]
                            if len(text_content) > 100000:
                                limited_content += "...\n\n[Content truncated to first 100k characters]"

                            self.add_message(
                                role="user",
                                content=f"Text file `{Path(f.filepath).name}` contains the following content:\n\n{limited_content}",
                            )
                        except Exception as e:
                            self.add_message(
                                role="user",
                                content=f"Text file `{Path(f.filepath).name}` could not be read with encoding `{f.document_context.encoding}`. Error: {str(e)}",
                            )
        self.context_message_len = len(self.messages)
        self.add_message(role="user", content=user_question)

        # Generate execution plan using structured format
        self._generate_execution_plan()

    def _generate_execution_plan(self):
        """Generate execution plan using structured format"""
        plan_prompt = (
            f"**Available tools for execution:**\n{self.tools_text}\n\n"
            f"**Instructions:**\n{self.instruction}\n\n"
            "Please create a detailed execution plan with an overall objective and a list of specific tasks. "
            "The objective should describe what the tasks are aiming to achieve. "
            "Each task should be specific enough to be executed independently. "
        )

        # Get initial execution plan from LLM
        initial_plan = self.llm.get_response(
            messages=self.messages + [{"role": "user", "content": plan_prompt}],
            model=self.model,
            temperature=self.temperature,
            response_format=InitialExecutionPlan,
        )

        # Convert to full ExecutionPlanModel
        self.execution_plan_model = initial_plan_to_execution_plan_model(initial_plan)

        # Generate markdown version
        self.execution_plan = execution_plan_model_to_markdown(
            self.execution_plan_model
        )
        logger.info(f"Generated initial execution plan:\n{self.execution_plan}")

        self.answer_template = self.llm.get_response(
            messages=self.messages
            + [
                {
                    "role": "developer",
                    "content": "Based on the information so far, produce a first cut template in Markdown format to provide the final answer to the user's question. "
                    "This should include placeholders for facts, analysis outcomes, and any other relevant information. "
                    "Don't fill any answers into this template even if you have the information, just leave placeholders. "
                    "Do not return anything other than the template itself, don't use ```markdown ... ``` block either.",
                }
            ],
            model=self.model,
            temperature=self.temperature,
        ).content
        self.wip_filled_answer_template = self.answer_template
        logger.info(f"Initial answer template:\n{self.wip_filled_answer_template}")

    async def _update_execution_plan_after_task(self):
        """
        Updates the execution plan using Pydantic models.
        """
        t = self.task_queue.completed_task
        worker = self.task_queue.workers.get(t.task_id)
        worker_assistant_messages = ""
        if worker and hasattr(worker, "messages"):
            assistant_messages = [
                msg["content"]
                for msg in worker.messages
                if msg.get("role") == "assistant"
            ]
            worker_assistant_messages = "\n\n---\n\n".join(assistant_messages)

        # Add a message to the conversation history about the completed task
        task_completion_msg = (
            f"# Responses from worker\n\n"
            f"**Task ID**: {t.task_id}\n\n"
            f"**Task Description**: {t.task_description}\n\n"
            f"**Task Status**: {t.task_status}\n\n"
            f"**Worker Responses**:\n\n{worker_assistant_messages}"
        )
        self.add_message(
            role="assistant",
            content=task_completion_msg,
        )

        answer_template_response = self.llm.get_response(
            messages=self.messages
            + [
                {
                    "role": "developer",
                    "content": "The current answer template that will be filled to provide the final answer to the user's question is:\n\n"
                    f"```markdown\n{self.answer_template}\n```\n\n"
                    "The latest work in progress fill of the answer template is:\n\n"
                    f"```markdown\n{self.wip_filled_answer_template}\n```\n\n"
                    "Update the template if required and further fill the WIP answer with latest information available.\n"
                    "IMPORTANT: the original template is typically created in absence of information, if the structure should change on discovery of information, do not be restrained by the starting template. "
                    "If different concepts identified in the data that can answer the user's question as it wasn't specific enough, be eager to include all concepts consistently across the template "
                    "(e.g. if differing concepts are found in one document, add the concepts to the answer template and make sure you look for the same differences in other documents too). ",
                }
            ],
            model=self.model,
            temperature=self.temperature,
            response_format=AnswerTemplate,
        )
        self.answer_template = answer_template_response.template
        logger.info(f"Updated answer template:\n{self.answer_template}")
        self.wip_filled_answer_template = answer_template_response.wip_filled_template
        logger.info(
            f"Work in progress answer template:\n{self.wip_filled_answer_template}"
        )

        # Append to task_responses list
        task_response = TaskResponseModel(
            task_id=t.task_id,
            task_description=t.task_description,
            task_status=t.task_status,
            assistance_responses=worker_assistant_messages,
        )
        self.task_responses.append(task_response)

        # Apply task completion logic BEFORE LLM call
        previous_model = self.execution_plan_model
        updated_previous_model = apply_task_completion_logic(
            previous_model, t.task_status
        )

        # Create filtered model with only open tasks for LLM
        open_tasks_model = create_open_tasks_model(updated_previous_model)

        # Prepare update messages using only open tasks
        update_messages = self.messages + [
            {
                "role": "developer",
                "content": f"**Current open tasks from execution plan:**\n\n{open_tasks_model.model_dump_json(indent=2)}",
            },
            {
                "role": "developer",
                "content": f"Based on the completed task execution details above for task `{t.task_description}`, please update the execution plan. "
                f"For context, this is the instructions:\n\n{self.instruction}\n\n"
                f"This is the template to answer the user's question:\n\n"
                f"```markdown\n{self.answer_template}\n```\n\n"
                f"This is the partly filled answer template so far:\n\n"
                f"```markdown\n{self.wip_filled_answer_template}\n```\n\n"
                "Think through what is still required to finish populating the answer template and use that to guide yourself in performing the following steps:\n"
                "1. Update existing task descriptions using updated_description field if needed\n"
                "2. Add new tasks if required, marking them with '(new)' in the description field\n"
                "3. Leave next_action as False - separate logic will determine next action\n"
                "4. Mark unnecessary tasks as obsolete=True\n"
                "Note: aggressively prune down unneeded tasks if they appear to overlap with outputs already produced. "
                "Do so by either marking them as obsolete or adding to the updated_description field to performing only the actions that has not already been covered yet. "
                "DO NOT remove existing tasks. "
                "DO NOT prune out calculation tasks, even if the answer template has already pre-filled the calculation. "
                "Tasks will be executed strictly in order on the list, if a new task is created please place it in the position of when it is supposed to be executed, don't leave it to the end.\n"
                "Note 2: remaining information required should be used to drive the description of subsequent tasks. "
                "If the remaining information required cannot be addressed by items on the list, either add new task in place or use the updated_description field to reflect the need for the missing information.\n",
            },
        ]

        llm_updated_model = await self.llm.a_get_response(
            messages=update_messages,
            model=self.model,
            temperature=self.temperature,
            response_format=ExecutionPlanModel,
        )
        logger.info(
            f"Execution plan's unanswered questions: {llm_updated_model.remaining_information_required}"
        )

        # Merge LLM output with completed/obsolete tasks
        final_model = merge_models(updated_previous_model, llm_updated_model)

        has_next_action = False
        for todo in final_model.todos:
            if not todo.completed and not todo.obsolete:
                todo.next_action = True
                has_next_action = True
                break

        # Update execution plan
        self.execution_plan_model = final_model
        self.execution_plan = execution_plan_model_to_markdown(final_model)

        logger.info(
            f"Updated execution plan after task completion:\n{self.execution_plan}"
        )
        if not has_next_action:
            return True

        if t.task_status == "completed":
            # Process output images and variables
            for image_key, image in t.output_images.items():
                self.load_image(encoded_image=image, image_name=image_key)
            for variable_key, variable in t.output_variables.items():
                self.variables[variable_key] = variable

        else:
            self.failed_task.append(t.task_description)

        if len(self.failed_task) >= self.failed_task_limit:
            failed_tasks_list = "\n - ".join(self.failed_task)
            self.add_message(
                role="developer",
                content=f"The following tasks have failed validation so far:\n{failed_tasks_list}. "
                "The agent will be terminated here to avoid endless loops.",
            )
            return True

        t.task_status = "recorded"
        return False

    async def invoke(self):
        while True:
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

            # Add execution plan context
            if self.execution_plan_model:
                next_task = get_next_action_task(self.execution_plan_model)
                if next_task:
                    appending_msgs.append(
                        {
                            "role": "developer",
                            "content": f"For context, your complete execution plan is: {self.execution_plan}\n"
                            f"The next todo item to be converted to a task is: {next_task.description}",
                        }
                    )
                else:
                    # No more tasks in execution plan
                    break

            # Generate single task instead of multiple tasks
            task = await self.llm.a_get_response(
                messages=self.messages + appending_msgs,
                model=self.model,
                temperature=self.temperature,
                response_format=Task,
            )

            logger.info(f"Task: {task.model_dump_json(indent=2)}")

            # Create single FullTask
            fulltask = FullTask(
                **task.model_dump(),
                task_id=str(uuid.uuid4()),
                wip_answer_template=self.wip_filled_answer_template,
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
            if not self.tables:
                fulltask.querying_data_file = False

            # Execute single task
            await self.task_queue.load_plan(
                tasks=[fulltask],
                duck_conn=self.duck_conn,
                task_responses=self.task_responses,
            )

            # Update execution plan and process completed task
            end_process = await self._update_execution_plan_after_task()

            # Check completion
            if end_process:
                user_response_messages = self.messages[self.context_message_len :] + [
                    {
                        "role": "developer",
                        "content": "The current answer template to the user's original question is:"
                        f"```markdown\n{self.wip_filled_answer_template}\n```\n\n"
                        "Using only provided information without creating any new, complete the answer template to a state that will be seen by the user. "
                        "If there is missing information, simply explain that the information is not found in the provided context, do not try to fill it yourself. "
                        "Return only the markdown answer and nothing else, do not use the user's question as a title. Do not wrap the response in ```markdown ... ``` block. "
                        "Agressively use inline citation such that the citing references provided are used individually whenever possible as opposed to making multiple citings at the end. "
                        "Citations must not ever use information that is meaningless to the user such as task IDs. "
                        "It should be using web links, or file references including page numbers, table/illustration references, or data references. ",
                    }
                ]
                response = await self.llm.a_get_response(
                    messages=user_response_messages,
                    model=self.model,
                    temperature=self.temperature,
                )
                self.user_response = response.content.strip()
                return

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

    def get_table_metadata(self, table_name: str) -> TableMeta:
        # Get basic table info
        row_count = self.duck_conn.sql(f"SELECT COUNT(*) FROM {table_name}").fetchone()[
            0
        ]

        # Get column names and types
        columns_info = self.duck_conn.sql(f"DESCRIBE {table_name}").fetchall()
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
                self.duck_conn.sql(
                    f'ALTER TABLE {table_name} RENAME COLUMN "{col[0]}" TO {col_name}'
                )
            if col[1].startswith("VARCHAR"):
                self.duck_conn.sql(
                    f"UPDATE {table_name} SET {col_name} = LTRIM(RTRIM({col_name}))"
                )

            # Check if column is completely blank/null/whitespace
            non_empty_count = self.duck_conn.sql(
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
            distinct_values = self.duck_conn.sql(
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
                self.duck_conn.sql(
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
