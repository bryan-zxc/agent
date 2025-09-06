import json
import string
import logging
import requests
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Union, Literal
from pydantic import BaseModel, Field
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from fastmcp import FastMCP
from ..services.llm_service import LLM
from .image_utils import encode_image, decode_image

logger = logging.getLogger(__name__)

# Initialise MCP server for native tools
mcp = FastMCP("agent-tools")


# Define docstring once for google_search
GOOGLE_SEARCH_DOC = """Perform web search using Google to find current information.

This function searches the web using Google's search engine and returns
comprehensive results with proper citations and source URLs. It provides
access to current information beyond the model's knowledge cutoff date,
including recent events, news, documentation, and real-time data.

Parameters:
----------
query : str
    The search query string to send to Google. Can be a natural language
    question, keywords, or specific phrases. For best results, use clear
    and specific queries. Examples:
    - "latest developments in quantum computing 2024"
    - "Python asyncio best practices"
    - "what is the current status of the Mars mission"

Returns:
-------
str
    Formatted search results containing relevant excerpts from web pages,
    with proper citations including source titles and URLs. Results are
    organised by relevance and include metadata about each source.
    Returns an error message if the search fails."""


@mcp.tool(description=GOOGLE_SEARCH_DOC)
async def google_search(query: str) -> str:
    try:
        # Use the existing LLM service which has search_web method
        llm = LLM(caller="tools")
        result = llm.search_web(query)
        return result
    except Exception as e:
        logger.error(f"Google search error: {e}")
        return f"Error performing search: {str(e)}"

# Set the docstring for the function (for documentation/IDE support)
google_search.__doc__ = GOOGLE_SEARCH_DOC


def is_serialisable(obj) -> tuple[bool, bool]:
    try:
        json.dumps(obj)
        serialisable = True
    except:
        serialisable = False
    try:
        str(obj)
        stringable = True
    except:
        stringable = False
    return serialisable, stringable


def get_text_and_table_json_from_image(image: Union[Image.Image, str]) -> str:
    """
    Extract text and table content from an image as JSON using LLM.

    This function takes an image containing text and/or tables and asks the LLM
    to directly extract the content and structure it as JSON.

    Parameters:
    ----------
    image : Union[Image.Image, str]
        The input image containing text/tables, either as a PIL Image object
        or a base64 encoded string representation of the image.

    Returns:
    -------
    str
        A JSON string representing the structured data extracted from the image.
    """
    # Convert input to base64 string for LLM processing
    if isinstance(image, str):
        base64_image = image
    elif isinstance(image, Image.Image):
        base64_image = encode_image(image)
    else:
        raise TypeError(
            "The image must be a base64 encoded string or a PIL Image object."
        )

    # Initialize LLM service
    llm = LLM(caller="tools")

    # Request JSON extraction directly from the LLM
    response = llm.get_response(
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Extract all text and table content from this image and return it as structured JSON. ",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{base64_image}"},
                    },
                ],
            }
        ],
        response_format="json",
        model="gemini-2.5-pro",
    )

    return response


def get_chart_readings_from_image(image: Union[Image.Image, str]) -> str:
    """
    Extracts all readings from charts in an image as text in the form of structured question-answer pairs.

    This function processes an image containing one or more charts and extracts all possible
    direct readings from the charts (e.g., specific data points, values at certain points,
    maximum/minimum values). It uses Azure OpenAI's image understanding capabilities to
    identify and extract quantitative information in a structured format.

    Parameters:
    ----------
    image : Union[Image.Image, str]
        The input image containing charts, either as a PIL Image object
        or a base64 encoded string representation of the image.

    Returns:
    -------
    str
        All values in the chart, presented as a pair of question and its corresponding answer.

    Example:
    -------
    For a bar chart showing sales by quarter, the output might include pairs like:
    {
        "question": "What were the sales in Q1 2023?",
        "answer": "$4.2 million"
    }
    """
    # Convert input to base64 string regardless of input type
    if isinstance(image, str):
        base64_image = image  # Save the base64 string if that's what was provided
    elif isinstance(image, Image.Image):
        base64_image = encode_image(image)  # Convert PIL Image to base64
    else:
        raise TypeError(
            "The image must be a base64 encoded string or a PIL Image object."
        )

    # Define Pydantic models for structured output
    class ChartQnA(BaseModel):
        question: str = Field(
            description="The question must be about one individual chart reading, do not create analytical question such as the trend of the chart. "
            "Do not create questions about information that does not come from the charts."
        )
        answer: str = Field(
            description="The answer must be a single number, such as 32 million."
        )

    class ChartQnAList(BaseModel):
        chart_qna: list[ChartQnA] = Field(
            ...,
            description="Full list of every fact that can be extracted from direct chart readings in the form of question and answer pairs.",
        )

    # Initialize the Azure LLM service for image analysis
    llm = LLM(caller="tools")

    # Send the image to the LLM with instructions to extract chart readings as Q&A pairs
    response = llm.get_response(
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Extract every fact from the charts as a question and answer pair. "
                        "Ignore all content that is not part of a chart.",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{base64_image}"},
                    },
                ],
            }
        ],
        model="gemini-2.5-pro",  # Using the vision-capable model for image processing
        response_format=ChartQnAList,  # Ensure structured output using Pydantic model
    )

    # Return the result as a formatted JSON string
    return response.model_dump_json(indent=2)


def get_doc_json(document_content, include_image: bool = False) -> str:
    if include_image:
        return document_content.model_dump_json(indent=2)
    # Using nested exclude pattern
    exclude_pattern = {"pages": {"__all__": {"images"}}}
    return document_content.model_dump_json(exclude=exclude_pattern, indent=2)


def get_images_from_doc(doc):
    images = []
    for page in doc.pages:
        for img in page.images:
            images.append((page.page_number, img.image_data))
    return images


class FactQuestion(BaseModel):
    question: str = Field(
        description="The question should enquire about one fact that will help answer the user's question. "
        "It must not ask for calculations or analysis, but simple to provide a single fact."
    )
    answer: str = Field(
        "",
        description="The answer should be a single fact that comes directly from the context. "
        "The answer must not extend on facts from the context by performing calculations or analysis. "
        "The answer must not create facts that does not exist in the context. ",
    )
    citation: str = Field(
        description="The citation must include filename andpage number where the fact was found. "
        "If the source is from a labelled table/chart/diagram/etc, then also extend the citation with the label. "
        "The citation must be succinct and clear for example 'santos_annual_report.pdf Table 4.1, page 12' or 'sustainability.pdf Page 36'. "
        "Avoid unclear citation such as '7'. "
    )


class AnalyticalQuestion(BaseModel):
    question: str = Field(
        description="An analytical question that can't be easily answered by one or a collection of facts, but the question is required to address the user's request/question. For example 'What is the document clear and concise?'"
    )
    answer: str


class UnansweredQuestion(BaseModel):
    question: str = Field(
        description="The question that cannot be answered by the context, but is required to answer the user's question. "
    )
    reason: str = Field(
        "Not available in the searched context.",
        description="This field can be generically left as not available in the searched context. Where appropriate, additional context around why the question can't be answered can also be provided.",
    )


class QnAList(BaseModel):
    thought: str = Field(
        description="Think through the steps that needs to be taken to answer the user's question. "
        "Think about all information required to answer the question comprehensively even if it is not in the provided context "
        "(note we may be able to search other parts of the document to find it). "
        "Create a comprehensieve list of questions to represent the information required. "
        "Those whose answer is already present in the context will appear as a question and answer pair. "
        "The questions pending answers will also be listed."
    )
    answer_template: str = Field(
        description="Pretend you cannot see the context, create a comprehensive template to answer the user's question. "
        "It must include everything mentioned in the thought field. "
        "The template must be comprehensive, but does not need any facts filled in. "
        "Just leave placeholders for facts to be filled in."
    )
    fact_question_answer: list[FactQuestion] = Field(
        description="Facts that can be extracted from the context in the form of question answer pairs (i.e. answer is available). "
        "This must completely cover every answerable component of the answer template."
    )
    analytical_question_answer: list[AnalyticalQuestion] = Field(
        [],
        description="This field can be defaulted to blank, but left as a placeholder for questions that are required, but difficult to answer via facts provided by fact_question_answer. "
        "IMPORTANT: the actual document content will not be accessible after this point, so downstream tasks can only rely what is provided in fact_question_answer and this field. "
        "Therefore, for questions asking about information such as tone or styling in the document (as an example), they have to be provided here otherwise downstream activities will no longer have access to original document text. "
        "Do not include the question here if answer cannot be provided, leave the question in unanswered_questions. "
        "Do not include analytical questions that can be answered using the facts provided in fact_question_answer (there will be subsequent tasks to perform analysis separately). ",
    )
    unanswered_questions: list[UnansweredQuestion] = Field(
        [],
        description="The list of questions that cannot be answered by the context but is required to fill in the answer template. "
        "This must fill in all remaining gaps from the answer template."
        "If the answer template can be completed with the provided context, leave this field blank.",
    )


def search_doc(question: str, criteria, doc):
    """
    Performs intelligent document search with optional image analysis to answer user questions.

    This function searches through a PDF document's content to answer user questions, with the ability
    to focus on specific page ranges and automatically analyse relevant images when the initial text-based
    search is insufficient. It uses a two-phase approach: first searching text content, then analyzing
    images if additional information is needed.

    Parameters:
    ----------
    question : str
        The user's question to be answered using the document content.
    criteria : DocSearchCriteria
        The pydantic details for DocSearchCriteria is:
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
    doc : PDFContent
        The PDF document content object containing pages with text and image data.

    Returns:
    -------
    str
        A comprehensive markdown-formatted answer to the user's question. If additional information
        is found in images, it's incorporated into the response. If questions remain unanswered,
        they are explicitly listed.

    Process:
    -------
    1. **Content Filtering**: Filters document pages based on search criteria
       - If page range specified: includes only pages within the range
       - If no range specified: includes entire document
       - Excludes image_data from initial search to reduce token usage

    2. **Initial Text-Based Search**:
       - Sends filtered content to LLM for initial answer generation
       - Identifies unanswered questions and potentially relevant images
       - Uses structured response format for consistent output

    3. **Image Analysis (if needed)**:
       - For each identified relevant image:
         - Determines image type (table, text, chart, etc.)
         - Extracts structured data based on image type:
           * Tables/Text: Converts to JSON format using slice-based extraction
           * Charts: Extracts all readings as question-answer pairs
         - Adds extracted information to context

    4. **Final Response Generation**:
       - If no additional information found: returns initial answer with unanswered questions
       - If images provided additional context: generates comprehensive final answer
    """
    # Initialize message list for LLM conversation
    messages = []

    # Phase 1: Filter and prepare document content based on search criteria
    if criteria.page_start:
        # Search within specified page range
        for p in doc.pages:
            if (
                criteria.page_end
                and p.page_number >= criteria.page_start
                and p.page_number <= criteria.page_end
            ):
                # Exclude image data to reduce token usage in initial search
                messages.append(
                    {
                        "role": "developer",
                        "content": f"{p.model_dump_json(exclude="images", indent=2)}",
                    }
                )
    else:
        # Search entire document if no page range specified
        messages.append(
            {
                "role": "developer",
                "content": f"{get_doc_json(doc, include_image=False)}",
            }
        )

    # Phase 2: Prepare search instructions and execute initial text-based search
    extension_messages = [
        {
            "role": "developer",
            "content": "Based completely on the above context, extract all the facts useful for providing a comprehensive answer to the user's question. "
            "The facts will be presented as question answer pairs.",
        },
        {"role": "user", "content": question},
    ]
    llm = LLM(caller="tools")

    response = llm.get_response(
        messages=messages + extension_messages,
        model="gemini-2.5-pro",
        response_format=QnAList,
    )
    return response


# Define docstring once for get_facts_from_pdf
GET_FACTS_FROM_PDF_DOC = """Extract facts from a PDF document to answer a specific question.

This function takes a user's question and a PDF source (local path or URL),
then uses LLM to extract relevant facts from the PDF in the form of
question-answer pairs and identifies any unanswered questions.

IMPORTANT: when using this function/tool, the results must be accepted - the acceptance criteria of the task must not
be forcing an outcome from running this function, as there may be none. The acceptance criteria should only check if
the function is called correctly and the output is in the correct format.

Parameters:
----------
question : str
    The user's question to be answered using the PDF content.
pdf_source : Union[str, Path]
    Path to local PDF file or URL to web PDF. The link must end with .pdf.

Returns:
-------
str
    A JSON string containing a template for providing a comprehensive answer to the user's question,
    facts to fill in the template in the form of question-answer pairs,
    and missing facts for the template in the form of unanswered questions."""


@mcp.tool(description=GET_FACTS_FROM_PDF_DOC)
async def get_facts_from_pdf(question: str, pdf_source: Union[str, Path]) -> str:
    if not str(pdf_source).lower().endswith(".pdf"):
        return "Not PDF source, please provide a valid PDF file or URL ending with .pdf"

    # Initialize the LLM service
    llm = LLM(caller="tools")

    # Create the prompt with the user's question on a new line with backticks
    prompt = (
        "Based completely on the above context, extract all the facts useful for providing a comprehensive answer to the user's question:\n"
        f"`{question}`\n"
        "The facts will be presented as question answer pairs."
    )

    # Get the response from the PDF using the LLM service
    response = llm.get_response_pdf(
        pdf_source=pdf_source, prompt=prompt, response_format=QnAList
    )

    # Return only question_answer and unanswered_questions fields
    return response.model_dump_json(exclude=["thought", "answer_template"], indent=2)

# Set the docstring for the function (for documentation/IDE support)
get_facts_from_pdf.__doc__ = GET_FACTS_FROM_PDF_DOC


# Run as MCP server when called directly
if __name__ == "__main__":
    import logging
    
    # Set up logging using repository standards
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger.info("Starting MCP tools server...")
    mcp.run()
