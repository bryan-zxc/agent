from pydantic import BaseModel, Field
from typing import Literal


class RequireAgent(BaseModel):
    calculation_required: bool
    web_search_required: bool
    complex_question: bool = Field(
        description="Is it a complex question that requires multiple steps to answer? "
    )
    chilli_request: bool = Field(description="If help from Chilli is required")
    context_rich_agent_request: str = Field(
        "",
        description="If any of the above is true, summarise the conversation into a context-rich request for the agent. "
        "Otherwise, leave this field empty. ",
    )
    # Temporarily not supporting this yet
    # action_needed: bool = Field(
    #     description="Does the question require an action to be taken, such as setting reminder, sending email, etc.? "
    # )


class RequestValidation(BaseModel):
    acceptance_criteria_satisfied: str = Field(
        description="List the acceptance criteria that has been satisfied and why."
    )
    acceptance_criteria_not_satisfied: str = Field(
        description="List the acceptance criteria that has not been satisfied and why."
    )
    user_request_fulfilled: bool = Field(
        description="Based on the executed tasks, has the acceptance criteria all completely been satisfied such that the user request is fulfilled, and user question is completely answered? "
        "Only use True if all acceptance criteria are a pass and we are ready to provide a finalised response to the user. "
        "If a task was completed due to repeated failure with no change in process, then immediately set this field to True which will end the process to avoid being stuck in an infinite loop of failure."
    )
    progress_summary: str = Field(
        description="Provide a summary of the tasks that has been completed, and describe which acceptance criteria have not been met, and should therefore be the focus of the next steps. "
        "This field should only be populated if user_request_fulfilled is False."
    )


class TaskResponse(BaseModel):
    task_id: str = Field(
        description="The stated ID of the task that was completed. Do not create IDs."
    )
    task_title: str = Field(
        description="Succinct title for display of the task performed specific to the ID."
    )
    task_description: str = Field(
        description="A non-technical description of the task performed specific to the ID. "
        "Do not create description that doesn't align or exist in the corresponding task ID."
    )
    task_outcome: str = Field(
        description="A non-technical description of the result/output after executing the task. "
        "Only rephrase the outcome, do not create any information that doesn't align or exist in the corresponding task ID. "
        "If this is the third failed task that resulted in the agent terminating due to repeated failure, then explicitly state that in the task outcome and explain to the user that this is done to avoid them waiting endlessly on repeated failing tasks."
    )


class RequestResponse(BaseModel):
    workings: list[TaskResponse] = Field(
        description="This is a list of tasks completed to represent the workings of the agent to reach the final response. "
        "The list must align completely to the tasks that has already been completed. "
        "Do not create tasks that has not already been performed."
    )
    markdown_response: str = Field(
        description="The final response to the user question/request in markdown format. "
        "This must be simply a rephrase of the outcome of the final task completed. "
        "Do not include the workings as that is already stated in the workings section "
        "(unless the answer format specifically needs information from the workings, then compile what ever is required). "
        "No new information is allowed to be introduced at this point. "
        "Where citations are available, you must aggressively use inline citations where possible."
    )
