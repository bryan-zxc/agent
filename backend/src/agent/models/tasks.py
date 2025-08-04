from pydantic import BaseModel, Field
from typing import Literal
from ..utils.tools import (
    get_text_and_table_json_from_image,
    get_chart_readings_from_image,
    get_facts_from_pdf,
    search_web_general,
    search_web_pdf,
)
from ..security.guardrails import guardrail_prompt
from .schemas import TableMeta, Variable

TOOLS = {
    "get_chart_readings_from_image": get_chart_readings_from_image,
    "get_text_and_table_json_from_image": get_text_and_table_json_from_image,
    "get_facts_from_pdf": get_facts_from_pdf,
    "search_web_general": search_web_general,
    "search_web_pdf": search_web_pdf,
}
tools_type = Literal[tuple(TOOLS)]


class TaskContext(BaseModel):
    user_request: str = Field(description="The original user request or question.")
    context: str = Field(
        description="Provide any relevant context that will help in performing the task. "
        "The more information provided, the better. "
        "If past tasks have been performed, extract all relevant information to be included into the context. "
        "Note: context provided must be independently sufficient to verify all acceptance criteria without any further information."
    )
    previous_outputs: str = Field(
        description="State all outputs from previous tasks that are required to perform this task, including a description of what they are. "
        "For example, JSON or Mermaid outputs from previous tasks (if determined to be relevant) must be restated in full with no alteration."
    )


class Task(BaseModel):
    task_context: TaskContext
    task_description: str = Field(
        description="A detailed description of the action that needs to be performed."
    )
    acceptance_criteria: list[str] = Field(
        description="Provide a list of criteria that needs to be satisfied for the task to be considered successful. "
        "Note: never save anything to file, for example if images need to be produced, they should be outputed as variables."
    )
    querying_data_file: bool = Field(
        description="Does the task require querying a data file (for example csv file)?"
    )
    image_keys: list[str] = Field(
        [],
        description="List of images keys that can be used to identify images relevant to the task.",
    )
    variable_keys: list[str] = Field(
        [],
        description="List of variable keys that can be used to identify variables relevant to the task.",
    )
    tools: list[tools_type] = Field(
        [],
        description="List of tools that will be helpful to performance the task. If there are no tools required, leave this empty.",
    )


class FullTask(Task):
    task_id: str
    task_status: Literal["new", "completed", "failed validation", "recorded"] = "new"
    task_result: str = ""
    input_images: dict = {}
    input_variables: dict = {}
    tables: list[TableMeta] = None
    output_images: dict = {}
    output_variables: dict = {}


class Tasks(BaseModel):
    tasks: list[Task] = Field(
        description="Break down the user request into a list of tasks that will be executed one at a time. Do not repeat any tasks that has already been performed."
    )


class PlanValidation(BaseModel):
    is_context_sufficient: bool = Field(
        description="Is the provided context sufficient to allow all acceptance criteria to be verified? If not, set this to False."
    )
    additional_context: str = Field(
        description="If the context is not sufficient, what additional context is required? "
        "Leave this field blank if context is sufficient."
    )
    is_acceptance_criteria_complete: bool = Field(
        description="Are all acceptance criteria complete and clearly defined? If not, set this to False. "
    )
    additional_criteria: str = Field(
        description="If the acceptance criteria are not complete, what additional criteria are required? "
        "If there are inaccuracies or insufficiencies in any criteria, what will be the correct criteria?"
        "Leave this field blank if acceptance criteria is complete."
    )
    updated_task: Task = Field(
        description="Update the task to address any deficiencies in context or acceptance criteria identified."
        "Leave this field blank if context is sufficient and acceptance criteria is complete."
    )


class TaskResult(BaseModel):
    result: str = Field(
        "",
        description="A detailed summary of all the actions taken, and critical outcomes of the task."
        "If the task was repeated failed with no change in the process, and then accepted as complete directly as a result of inconclusive repetitive failure, then explicitly state this.",
    )
    output: str = Field(
        "",
        description="State every output and the actual content of the output. For example if the output is requested to be a JSON string, the full JSON string must be stated here. "
        "Note: images as output are the only exception, only the name of the output image variable need to be stated with a description of what the image is, the actual content of the image (e.g. base 64 encoding) does not need to be mentioned.",
    )


class TaskArtefact(BaseModel):
    summary_of_previous_failures: str = Field(
        description="If there are no failures, leave this section blank, otherwise provide a summary of why the previous run(s) failed."
    )
    thought: str = Field(
        description="Think through step by step what needs to be done to perform the task. "
        "Is code required? If so, what is the thought process that will help generate the correct code in as little tries as possible? "
        "If code is not required, simply fill in the result field and leave the python_code field empty. "
        "If a function is provided and can be used, you must generate python code to use the function, even if the result can be achieved without code. "
        "Has there been past failures in validation? If so, provide a detailed description of not just what the adjust should be, but also exactly how to adjust it and why this adjustment will work. "
        "DO not ever use OCR technique to read images. The LLM that is running this agent is capable of reading images directly.\n"
    )
    result: str = Field(
        description="This field is reserved for the description of a successful outcome when the task can be completed without executing any code. "
        "If code needs to be created and executed to get the result of the task, this field should be left empty. "
        "If a task fails validation and need to be rewritten, this should contain what the updated correct task result should be, given the reason of the previous failure. "
        "If code needs to be readjusted to correct the outcomes based on previous failed reason, this field can be left empty.\n"
        # "IMPORTANT: if the goal of the task is to create code (or code like) outputs that is not to be executed, then instead of writing the code in the python_code field, write it here in the output section. "
        # "The most likely example is a request to output in JSON or Mermaid format - these are just ways of representing information, and not intended to be executed."
    )
    # need_code: bool = Field(
    #     description="Is code still required to perform the task? Is the answer to the task already available? Return False greedily if code is not required."
    # )
    python_code: str = Field(
        description="Executable and error free python code that needs to be executed to perform the task. "
        "You must use functions provided where possible, do not ever create code to perform a similar purpose to an existing function. "
        "If provided with a useable function for the task, this python_code field must be populated to use the supplied function accordingly even if the outcome can be achieved without code. "
        "The output of the code that addresses the task must be stored in a variable. If the output is an image, then save the output as PIL.Image object. "
        "The name of the outputs must provide a context of the task being executed, to avoid naming conflicts from similar outputs in other tasks. "
        "Leave the field empty if no code is required.\n"
        "If the previous outcome failed validation, do not simply repeat the previous code, but make adjustments based on the reason of the previous failure."
    )
    output_variables: list[Variable] = Field(
        description="The output variable name(s) (if there is more than one output), from the code."
    )
    is_malicious: bool = Field(description=guardrail_prompt)


class TaskArtefactSQL(BaseModel):
    summary_of_previous_failures: str = Field(
        description="If there are no failures, leave this section blank, otherwise provide a summary of why the previous run(s) failed."
    )
    thought: str = Field(
        description="Think through step by step what needs to be done to perform the task. "
        "Has there been past failures in validation? "
        "If so, provide a detailed description of not just what the adjust should be, but also exactly how to adjust it and why this adjustment will work.\n"
        "If there isn't enough information in the context to generate the query, then don't generate any code and leave an explanation for why code cannot be generated."
    )
    sql_code: str = Field(
        description="Executable and error free DuckDB compliant SQL query to access information that can address the task. "
        "Do not ever make up table names, column names, or values in columns. "
        "If the context did not provide sufficient information to create the correct query, leave this field blank."
    )
    reason_code_not_created: str = Field(
        description="If SQL code cannot be generated, explain why that is the case."
    )


class TaskValidation(BaseModel):
    most_recent_failure: str = Field(
        "",
        description="If there are no failures, leave this section blank, otherwise provide a description of why the previous run failed.",
    )
    second_most_recent_failure: str = Field(
        "",
        description="If there are no failures or only 1 failure on this task, leave this section blank, otherwise provide a description of the failure before the last.",
    )
    third_most_recent_failure: str = Field(
        "",
        description="If there are no failures or only 1 or 2 failures on this task, leave this section blank, otherwise provide a description of the failure before the second last.",
    )
    three_identical_failures: bool = Field(
        False,
        description="Check if there are at least 3 failures, if so were they identical failures (did not import io, and did not import base64 are not identical failures), only if the answer to both questions is yes, then make this field true, otherwise, set it as false.",
    )
    task_completed: bool = Field(
        description="If three_identical_failures is true, then mark the task as completed (ie true) straightaway. "
        "Otherwise, determine if all acceptance criteria are met. "
        "If all criteria are met, set this to true. "
        "If any criteria are not met, set this to false.\n"
    )
    validated_result: TaskResult = Field(
        description="The result of the task, if it is completed successfully. "
        "Leave this field blank if task_completed is False. "
        "Note: if the task was completed due to repeated failure, explicitly state that in the result."
    )
    failed_criteria: str = Field(
        "",
        description="If any acceptance criteria are not met, explain which ones and why they were not met. If all criteria are met, leave this field empty.",
    )
