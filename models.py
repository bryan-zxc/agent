from pydantic import BaseModel, Field
from typing import Literal
from agent.tools import (
    get_text_and_table_json_from_image,
    get_chart_readings_from_image,
)
from agent.code_guardrail import guardrail_prompt

TOOLS = {
    "get_chart_readings_from_image": get_chart_readings_from_image,
    "get_text_and_table_json_from_image": get_text_and_table_json_from_image,
}
tools_type = Literal[tuple(TOOLS)]


class ImageElement(BaseModel):
    element_desc: str = Field(
        description="A short description of the image element, e.g. 'a chart showing the sales data for 2023'. If there are available chart/table/illustation/etc titles or descriptions existing in the image, use those."
    )
    element_location: str = Field(
        description="The location of the image element within the image, e.g. 'top right corner'"
    )
    element_type: Literal["chart", "table", "diagram", "text", "other"] = Field(
        description="If the image element is any form of chart or graph, use 'chart'. "
        "If it is tabular information, use 'table'. "
        "If it is a flow chart, network relationship, or similar diagram containing linked shapes (e.g. boxes) with text annotations, use 'diagram'. "
        "If it contains a body of text, use 'text'. Note, light text as part of charts/tables/diagrams/illustrations, including annotations, is not considered a body of text."
        "Other types of images, such as photographs, illustrations, etc should be classified as 'other'."
    )
    required: bool = Field(
        description="Is the element required to address the user question? "
    )


class ImageBreakdown(BaseModel):
    unreadable: bool = Field(
        False,
        description="If the image is unreadable, e.g. low resolution, blurry, or otherwise cannot extract content, set this to True.",
    )
    image_quality: str = Field(
        "",
        description="Leave as blank if the image is readable. If the image is unreadable, explain why it is unreadable.",
    )
    elements: list[ImageElement]


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


class PDFMetaSummary(BaseModel):
    num_pages: int
    num_images: int
    total_text_length: int
    max_page_text_length: int
    median_page_text_length: int


class PDFType(BaseModel):
    is_image_based: bool = Field(
        description="Is the PDF likely an image based document where the content in every page is stored as an image, and hardly any information is available in text form?"
    )


class PDFSection(BaseModel):
    title: str = Field(..., description="Title of the section")
    summary: str = Field(..., description="Summary of the section")
    page_start: str = Field(
        ..., description="Page number of the first page section content appears"
    )
    page_end: str = Field(
        ..., description="Page number of the last page section content appears"
    )


class PDFIndex(BaseModel):
    title: str = Field(..., description="Title of the document")
    summary: str = Field(..., description="One paragraph overview of the document")
    sections: list[PDFSection] = Field(
        ..., description="List of sections in the document"
    )


class PDFFull(BaseModel):
    filename: str
    is_image_based: bool
    content: PDFContent
    meta: PDFMetaSummary
    index: PDFIndex = None


class DocSearchCriteria(BaseModel):
    filename: str
    page_start: str = Field(
        None,
        description="The first page to use for the search. "
        "If not provided, then search the entire document. "
        "Only fill in the starting page number if there is evidence to suggest this is the correct page, do not make up a page number or give a random page number just to populate it. "
        "In absence of evidence this field should be left empty to indicate full document search.",
    )
    page_end: str = Field(
        None,
        description="The last page to use for the search. "
        "If equal to page start then only one page is selected. "
        "If page start is empty, this field must be empty.",
    )


class File(BaseModel):
    filepath: str
    file_type: Literal["image", "data", "document"]
    image_context: list[ImageElement] = None
    data_context: Literal["csv", "excel", "other"] = None
    document_context: PDFFull = None


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


class ColumnMeta(BaseModel):
    column_name: str
    pct_distinct: float
    min_value: str
    max_value: str
    top_3_values: dict


class TableMeta(BaseModel):
    table_name: str
    row_count: int
    top_10_md: str
    colums: list[ColumnMeta]


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


class Variable(BaseModel):
    name: str
    is_image: bool


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


class RequestValidation(BaseModel):
    user_request_fulfilled: bool = Field(
        description="Based on the executed tasks, has the user request been fulfilled, and all user questions completely answered? "
        "Only use True if we are ready to provide a finalised response to the user. "
        "If a task was completed due to repeated failure with no change in process, then immediately set this field to True which will end the process to avoid being stuck in an infinite loop of failure."
    )
    progress_summary: str = Field(
        description="Provide a summary of the tasks that has been completed, and describe the next task in line with the instructions. "
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
        "No new information is allowed to be introduced at this point."
    )


class ImageDescription(BaseModel):
    variable_name: str
    image_desc: str


class ImageDescriptions(BaseModel):
    descriptions: list[ImageDescription]


class SinglevsMultiRequest(BaseModel):
    request_type: Literal["single", "multiple"] = Field(
        description="If the user is looking for a single response to be compiled after reviewing all files, use 'single'. "
        "If the user wants one answer per file when there are multiple files, use 'multiple'."
    )
