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
}
tools_type = Literal[tuple(TOOLS)]


class AnswerTemplate(BaseModel):
    """Answer template for the final response"""

    template: str = Field(
        description="The answer template in markdown format that will be filled to provide the final answer to the user's question."
        "Based on new information available, update the above template if required. "
        "Remember that if you choose not to update the template just return the same template as is. "
        "If you do update the template, make sure that you continue to use placeholders even if you have the information, this should be just a template, not the actual answer. "
        "Keep the template succinct."
    )
    wip_filled_template: str = Field(
        description="The work in progress filled answer template, which is the latest population of placeholders with information currently available."
        "Where information is not available, leave unknown placeholders untouched. "
        "You must stay completely faithful to the template, do not change the structure, do not remove sections you don't have information for, just keep them with corresponding placeholders. "
        "Agressively use inline citation such that the citing references provided are used individually whenever possible as opposed to making multiple citings at the end. "
        "DO NOT EVER perform any calculations, you must leave that as a placeholder so a task can be created to perform the calculation. "
        "If python code has been ran to generate the outcome of a calculation, you MUST use that answer whether you agree or not as the final answer - DO NOT CHANGE IT."
    )


class Task(BaseModel):
    image_keys: list[str] = Field(
        [],
        description="List of images keys that can be used to identify images relevant to the task.",
    )
    variable_keys: list[str] = Field(
        [],
        description="List of variable keys that can be used to identify variables relevant to the task.",
    )
    user_request: str = Field(
        description="The original user request or question that this task contributes to answering."
    )
    task_description: str = Field(
        description="A detailed description of the action that needs to be performed."
    )
    acceptance_criteria: list[str] = Field(
        description="Provide a list of criteria that needs to be satisfied for the task to be considered successful. "
        "This is task level acceptance criteria, not objective level acceptance criteria. "
        "Please don't be confused by the two."
        "Note: never save anything to file, for example if images need to be produced, they should be outputed as variables."
    )
    querying_structured_data: bool = Field(
        description="Are there data tables available for use? If so, does the task require querying an existing data table (sourced from csv file)? "
        "If the answers to both questions are yes, then this field should be set to true, otherwise false."
    )
    tools: list[tools_type] = Field(
        [],
        description="List of tools or functions that will be required to performance the task. If there are no tools or functions required, leave this empty.",
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
        "The result of the execution must be stored in a variable and the variable must be printed. "
        "For example\n```python\nresult = some_function()\nprint(result)\n```\n"
        "IF the output is an image, you don't need to print it, just make sure the output variable is a PIL.Image object.\n"
        "You must use functions provided where possible, do not ever create code to perform a similar purpose to an existing function. "
        "If provided with a useable function for the task, this python_code field must be populated to use the supplied function accordingly even if the outcome can be achieved without code. "
        "The name of the outputs must provide a context of the task being executed, to avoid naming conflicts from similar outputs in other tasks. "
        "Leave the field empty if no code is required.\n"
        "If the previous outcome failed validation, do not simply repeat the previous code, but make adjustments based on the reason of the previous failure."
    )
    output_variables: list[Variable] = Field(
        description="The output variable name(s) (if there is more than one output), from the code. "
        "Note, once a variable is printed, it doesn't need to be considered an output variable. "
        "The only required output is when you expect future tasks to need to directly access the output as a variable as opposed to the print. "
        "For example, images can't be printed."
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
        "If the context did not provide sufficient information to create the correct query, leave this field blank. "
        "If suspecting that the query will return many rows of data (for reference, more than 50 rows), then try to apply aggregation techniques that can help the question at hand rather than brute force printing all data. "
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


class TodoItem(BaseModel):
    description: str = Field(
        description="Original task description (may contain '(new)' for new tasks)"
    )
    updated_description: str = Field(
        default="", description="Updated description if changed"
    )
    next_action: bool = Field(
        default=False,
        description="This field should just be left False, there is separate logic to determine the next action.",
    )
    completed: bool = Field(
        default=False,
        description="This can be if the todo item is no longer relevant, or if it has been completed as part of previous task execution.",
    )
    obsolete: bool = Field(default=False, description="Mark for deletion")


class ExecutionPlanModel(BaseModel):
    """Structured execution plan with objective and todo items"""

    objective: str = Field(description="Overall objective of the execution plan")
    remaining_information_required: str = Field(
        default="",
        description="Review the answer template and the partly filled answer carefully and think through what additional information is still required before achieving the objective. "
        "This should drive and guide how to change the next todo's (if required) to obtain the information. "
        "Missing information can be because you haven't exhausted your search in available context provided, it could also be the absence of available information in your context, "
        "you need to make a determination of whether information is already exhausted and give the user the best answer based on what is available, or to keep digging for more information by adding to or going through the todo list.\n"
        "Note: Calculations required must be considered as information required and must be assigned a corresponding todo item. "
        "Even if the answer template has already done its own calculation and pre-filled the answer, still have a calculation todo item.",
    )
    todos: list[TodoItem] = Field(
        description="List of todo items. ""Can be empty if there are no more todos, for example when the answer template is completely filled out. ""Make the list succinct - meaning all required actions to get remaining information should be done, but don't break actions that can be done in one step into multiple unnecessarily, nor create filler tasks."
    )


class InitialExecutionPlan(BaseModel):
    objective: str = Field(description="Overall goal description")
    todos: list[str] = Field(description="Simple list of task descriptions")


class TaskResponseModel(BaseModel):
    """Model for storing completed worker task information in message history"""

    task_id: str = Field(description="The ID of the completed task")
    task_description: str = Field(
        description="Description of the task that was executed"
    )
    task_status: str = Field(
        description="Status of the task (completed, failed validation, etc.)"
    )
    assistance_responses: str = Field(
        description="The assistant responses from the worker during task execution"
    )
