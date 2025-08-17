from pydantic import BaseModel, Field
from typing import Literal


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


class DocumentContext(BaseModel):
    file_type: Literal["pdf", "text"]
    encoding: str = None  # For text files
    pdf_content: PDFFull = None  # For PDF files


class File(BaseModel):
    filepath: str
    file_type: Literal["image", "data", "document"]
    image_context: list[ImageElement] = None
    data_context: Literal["csv", "excel", "other"] = None
    document_context: DocumentContext = None


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


class Variable(BaseModel):
    name: str
    is_image: bool
