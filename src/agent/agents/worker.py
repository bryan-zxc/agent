import logging
import duckdb
from PIL import Image
from pydantic import BaseModel, Field
from ..core.base import BaseAgent
from ..utils.sandbox import CodeSandbox
from ..utils.tools import encode_image, decode_image, is_serialisable
from ..models import (
    FullTask,
    TaskArtefact,
    TaskValidation,
    ImageDescriptions,
    TaskResult,
    TOOLS,
    TaskArtefactSQL,
)

# Set up logging
logger = logging.getLogger(__name__)


def convert_result_to_str(result: TaskResult) -> str:
    return f"# Task result\n{result.result}\n\n# Task output\n{result.output}"


class BaseWorkerAgent(BaseAgent):
    async def _validate_result(self):
        self.add_message(
            role="developer",
            content=f"Determine if the task is successfully completed based on the acceptance criteria:\n{self.task.acceptance_criteria}\n\n",
        )
        validation = await self.llm.a_get_response(
            messages=self.messages,
            model=self.model,
            temperature=self.temperature,
            response_format=TaskValidation,
        )
        # print(f"Validation result: {validation.model_dump_json(indent=2)}", flush=True)
        logger.debug(f"Validation result: {validation.model_dump_json(indent=2)}")
        if validation.task_completed:
            self.task.task_result = convert_result_to_str(validation.validated_result)
            # print(
            #     f"Task {self.task.task_id} completed successfully. Final result:\n{self.task.task_result}",
            #     flush=True,
            # )
            logger.info(
                f"Task {self.task.task_id} completed successfully. Final result:\n{self.task.task_result}"
            )
            self.task.task_status = "completed"
            return True
        else:
            self.task.task_result = f"{validation.validated_result.result}\n\nFailed criteria: {validation.failed_criteria}"
            self.add_message(role="assistant", content=self.task.task_result)
            self.task.task_status = "failed validation"
            return False


class WorkerAgent(BaseWorkerAgent):
    def __init__(
        self,
        task: FullTask,
        max_retry: int = 5,
        model: str = "sonnet-4",
        temperature: float = 0,
    ):
        super().__init__(id=task.task_id, agent_type="worker")
        self.task = task
        self.max_retry = max_retry
        self.model = model
        self.temperature = temperature
        self.output_variables = []
        self.image_descriptions = ImageDescriptions(descriptions=[])

        self.add_message(
            role="developer",
            content=f"Your goal is to perform the following task:\n{task.task_description}",
            verbose=False,
        )
        self.add_message(
            role="developer",
            content=f"# Context\n{task.task_context.context}\n\n"
            f"# Previous outputs\n{task.task_context.previous_outputs}\n\n"
            f"# Original user request\n{task.task_context.user_request}\n\n"
            "Unless the original user request is necessary to perform the task at hand, "
            "DO NOT change the actions to be performed based on the knowledge of the original request.",
            verbose=False,
        )
        if task.input_images:
            for image_key, image in task.input_images.items():
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
                self.add_message(role="user", content=content, verbose=False)
        if self.task.input_variables:
            for variable_name, variable in task.input_variables.items():
                self.add_message(
                    role="developer",
                    content=f"# {variable_name}\nType: {type(variable)}\n\n```\n{variable}\n```",
                    verbose=False,
                )
        if self.task.tools:
            tools_text = "\n\n-------------------------\n\n".join(
                [f"# {t}\n{TOOLS.get(t).__doc__}" for t in self.task.tools]
            )
            self.add_message(
                role="developer",
                content=f"You may use the following function(s):\n\n{tools_text}\n\n"
                "When using the function(s) you can assume that they already exists in the environment, "
                "to use it, simply call the function with the required parameters. "
                "You must use the function(s) where possible, do not ever try to perform the same action with other code.",
                verbose=False,
            )

    async def invoke(self):
        appending_msgs = []

        if self.task.input_variables:
            appending_msgs.append(
                {
                    "role": "developer",
                    "content": "The following variables are available for use, they already exist in the environment, "
                    f"you do not need to declare or create it: {', '.join(self.task.input_variables.keys())}",
                }
            )
        appending_msgs.append(
            {
                "role": "developer",
                "content": "If writing code, you can assume a variable called 'messages' exists in the environment, "
                "and contains conversation history in the format expected by the LLM, "
                "containing the task at hand and context required such as user request. "
                "Do not assign 'messages' variable, just call it when needed.",
            }
        )
        for n in range(self.max_retry):
            # print(f"Worker {self.task.task_id} - Attempt {n + 1}", flush=True)
            logger.info(f"Worker {self.task.task_id} - Attempt {n + 1}")
            task_result = await self.llm.a_get_response(
                messages=self.messages + appending_msgs,
                model=self.model,
                temperature=self.temperature,
                response_format=TaskArtefact,
            )
            # print(f"Task result: {task_result.model_dump_json(indent=2)}", flush=True)
            logger.debug(f"Task result: {task_result.model_dump_json(indent=2)}")
            if task_result.python_code:
                if task_result.is_malicious:
                    self.task.task_result = "The code is either making changes to the database or creating executable files - this is considered malicious and not permitted."
                    self.add_message(
                        role="assistant",
                        content=f"{self.task.task_result}\nRewrite the python code to fix the error.",
                    )
                    self.task.task_status = "failed validation"
                    continue
                self.add_message(
                    role="assistant",
                    content=f"The python code to execute:\n```python\n{task_result.python_code}\n```",
                )
                # Execute the code in a sandbox
                locals_dict = {"messages": self.messages}
                if self.task.input_images:
                    locals_dict.update(self.task.input_images)
                if self.task.input_variables:
                    locals_dict.update(self.task.input_variables)
                if self.task.tools:
                    for t in self.task.tools:
                        func = TOOLS.get(t)
                        if callable(func):
                            locals_dict[t] = func
                # print(locals_dict.keys(), flush=True)
                logger.debug(f"Locals dict keys: {list(locals_dict.keys())}")
                sandbox = CodeSandbox(locals_dict=locals_dict)
                sandbox_result = sandbox.execute(task_result.python_code)
                if sandbox_result["success"]:
                    self.add_message(
                        role="assistant",
                        content="Below outputs are generated on executing python code.",
                    )
                    if sandbox_result["output"]:
                        self.add_message(
                            role="assistant",
                            content=sandbox_result["output"],
                        )
                    for v in task_result.output_variables:
                        if v.is_image:
                            if isinstance(sandbox_result["variables"][v.name], list):
                                for i, img in enumerate(
                                    sandbox_result["variables"][v.name]
                                ):
                                    await self._process_image_variable(
                                        img, f"{v.name}_{i}"
                                    )
                            elif isinstance(sandbox_result["variables"][v.name], dict):
                                for img_key, img in sandbox_result["variables"][
                                    v.name
                                ].items():
                                    await self._process_image_variable(
                                        img, f"{v.name}_{img_key}"
                                    )
                            elif isinstance(
                                sandbox_result["variables"][v.name], Image.Image
                            ):
                                await self._process_image_variable(
                                    sandbox_result["variables"][v.name], v.name
                                )
                            else:
                                self.task.task_result = f"Incorrect output: if {v.name} is an image, it must be a PIL.Image object or a list[Image] or dict[str:Image] object, no other choices are allowed."
                                self.add_message(
                                    role="assistant",
                                    content=f"{self.task.task_result}\nRewrite the python code to fix the error.",
                                )
                                self.task.task_status = "failed validation"
                                continue
                        else:
                            await self._process_variable(
                                sandbox_result["variables"][v.name], v.name
                            )

                    validated = await self._validate_result()
                    if validated:
                        return
                else:
                    self.task.task_result = (
                        f"Error executing code: {sandbox_result['error']}"
                    )
                    self.add_message(
                        role="assistant",
                        content=f"{self.task.task_result}\n\n{sandbox_result["stack_trace"]}\n\nRewrite the python code to fix the error.",
                    )
                    self.task.task_status = "failed validation"

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

                    repeated_fail = await self.llm.a_get_response(
                        messages=self.messages,
                        model=self.model,
                        temperature=self.temperature,
                        response_format=RepeatFail,
                    )
                    if repeated_fail.repeated_failure:
                        self.task.task_result += (
                            f"\n\nRepeated failure: {repeated_fail.failure_summary}"
                        )
                        return
            else:
                self.add_message(role="assistant", content=task_result.result)
                validated = await self._validate_result()
                if validated:
                    return
        self.task.task_status = "failed validation"
        self.task.task_result = "Task failed after multiple tries."

    async def _process_image_variable(self, image: Image, variable_name: str):
        content = [{"type": "text", "text": f"Image: {variable_name}"}]
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{encode_image(image)}"},
            }
        )
        # content.append(
        #     {
        #         "type": "text",
        #         "text": "Describe the above image in detail. "
        #         "If the image is partially cropped, state that and attempt to describe what is visible on the image. "
        #         "You must stay true to what is visible on this image, do not guess about information that is not visible.",
        #     }
        # )
        self.task.output_images[variable_name] = encode_image(image)
        # image_read = await self.llm.a_get_response(
        #     messages=[{"role": "user", "content": content}],
        #     model=self.model,
        #     temperature=self.temperature,
        # )
        # self.add_message(role="user", content=content[:2])
        self.add_message(role="user", content=content)
        # self.add_message(role="user", content=image_read.content)

        # self.image_descriptions.descriptions.append(
        #     ImageDescription(variable_name=variable_name, image_desc=image_read.content)
        # )
        self.output_variables.append(variable_name)

    async def _process_variable(self, variable, variable_name: str):
        serialisable, stringable = is_serialisable(variable)
        if serialisable:
            self.task.output_variables[variable_name] = variable
            self.add_message(
                role="assistant",
                content=f"```python\n{variable_name}\n```\n\nOutput:\n```\n{variable}\n```",
            )
            self.output_variables.append(variable_name)
        elif stringable:
            self.add_message(
                role="assistant",
                content=f"```python\n{variable_name}\n```\n\nOutput:\n```\n{str(variable)}\n```\n\n"
                "Note: the output is not serialisable and will not be included as an output variable.",
            )


class WorkerAgentSQL(BaseWorkerAgent):
    def __init__(
        self,
        task: FullTask,
        duck_conn: duckdb.DuckDBPyConnection,
        max_retry: int = 5,
        model: str = "sonnet-4",
        temperature: float = 0,
    ):
        super().__init__(id=task.task_id, agent_type="worker")
        self.task = task
        self.max_retry = max_retry
        self.model = model
        self.temperature = temperature
        self.duck_conn = duck_conn

        self.add_message(
            role="system",
            content="You are an expert in DuckDB SQL which closely follows PostgreSQL dialect.",
        )

        self.add_message(
            role="developer",
            content=f"Your goal is to perform the following task:\n{task.task_description}",
            verbose=False,
        )
        self.add_message(
            role="developer",
            content=f"# Context\n{task.task_context.context}\n\n"
            f"# Previous outputs\n{task.task_context.previous_outputs}\n\n"
            f"# Original user request\n{task.task_context.user_request}\n\n"
            "Unless the original user request is necessary to perform the task at hand, "
            "DO NOT change the actions to be performed based on the knowledge of the original request.",
            verbose=False,
        )
        self.add_message(
            role="developer",
            content=f"The files have been all transferred into the DuckDB database, below are their details:\n\n{task.model_dump_json(indent=2,include="tables")}\n\n",
            verbose=False,
        )

    async def invoke(self):
        for n in range(self.max_retry):
            # print(f"Worker {self.task.task_id} - Attempt {n + 1}", flush=True)
            logger.info(f"Worker {self.task.task_id} - Attempt {n + 1}")
            sql_artefact = await self.llm.a_get_response(
                messages=self.messages,
                model=self.model,
                temperature=self.temperature,
                response_format=TaskArtefactSQL,
            )
            # print(f"SQL artefact: {sql_artefact.model_dump_json(indent=2)}", flush=True)
            logger.debug(f"SQL artefact: {sql_artefact.model_dump_json(indent=2)}")
            if sql_artefact.sql_code:
                try:
                    sql_output = (
                        self.duck_conn.execute(sql_artefact.sql_code).df().to_markdown()
                    )
                    self.add_message(
                        role="assistant",
                        content=f"The following code was executed:\n\n```sql\n\n{sql_artefact.sql_code}\n\n```\n\n"
                        f"THe output is:\n\n{sql_output}",
                    )
                    validated = await self._validate_result()
                    if validated:
                        return
                except Exception as e:
                    self.task.task_result = f"Error executing SQL code: {e}"
                    self.add_message(
                        role="assistant",
                        content=f"{self.task.task_result}\n\nRewrite the SQL code to fix the error.",
                    )
                    self.task.task_status = "failed validation"
            else:
                self.task.task_result = f"SQL code cannot be generated. {sql_artefact.reason_code_not_created}"
                self.task.task_status = "failed validation"
                return
