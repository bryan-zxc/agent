import pypdf
import statistics
import io
import base64
from PIL import Image
from pathlib import Path
from agent.planner import (
    BaseAgent,
    PlannerAgent,
    encode_image,
    File,
)
from agent.models import (
    SinglevsMultiRequest,
    ImageContent,
    PDFContent,
    PageContent,
    PDFMetaSummary,
    PDFType,
    PDFFull,
)
from rag.document_search import legacy_get_answer
from models import RagRequest
from security.aws_role import get_aws_resource_factory
from s3.s3_utils import download_file_from_s3
from postgres.postgresql import get_s3_key

INSTRUCTION_LIBRARY = {
    "data": {
        "csv": "When querying a data file such as csv, you must do so via SQL query. "
        "If required, create intermediate queries such as those that give you precise values in a field to apply an accurate filter on. "
        "You must not ever make up table names, column names, or values in tables. "
        "If you don't know, use intermediate queries to get the information you need. "
    },
    "image": {
        "chart": "Breakdown the task as follows:\n"
        "  1. If the image has 3 or more elements such as charts, tables, diagrams, text blocks (any combination of 3 such as 3 charts or two charts and a table), then crop the image to isolate the chart(s) of relevance. "
        "Otherwise, skip this step.\n"
        "  2. Use the provided tool get_chart_readings_from_image to extract the chart readings as text. This must be a standalone task.\n"
        "  3. If the user's question is a composite question requiring multiple pieces of information to be read from the chart, split the questions into atomic questions that can be answered by a single fact. "
        "Answer each question that is aiming to extract facts from the chart individually, and ignore analytical questions.\n"
        "  4. Compose a comprehensive answer to address the user's question.\n",
        "table": "Breakdown the task as follows:\n"
        "  1. Using the provided tool get_text_and_table_json_from_image, read the table contents as a JSON string. This must be the first standalone task.\n"
        "  2. If the user's question is a composite question requiring multiple pieces of information to be read from the table, split the questions into atomic questions that can be answered by a single fact. "
        "Answer each question that is aiming to extract facts from the table individually, and ignore analytical questions.\n"
        "  3. Compose a comprehensive answer to address the user's question.",
        "diagram": "Breakdown the task as follows:\n"
        "  1. Read the diagram and its contents as mermaid code."
        "  2. If the user's question is a composite question requiring multiple pieces of information to be read from the diagram, split the questions into atomic questions that can be answered by a single fact. "
        "Answer each question that is aiming to extract facts from the diagram individually, and ignore analytical questions."
        "  3. Compose a comprehensive answer to address the user's question.",
        "text": "Breakdown the task as follows:\n"
        "  1. Using the provided tool get_text_and_table_json_from_image, read the table contents as a JSON string. This must be the first standalone task.\n"
        "  2. If the user's question is a composite question requiring multiple pieces of information to be read from the text, split the questions into atomic questions that can be answered by a single fact. "
        "Answer each question that is aiming to extract facts from the text individually, and ignore analytical questions.\n"
        "  3. Compose a comprehensive answer to address the user's question.",
    },
}


def is_image(file_path: str) -> tuple[bool, str]:
    try:
        with open(file_path, "rb") as file:
            img = Image.open(file)
            img.verify()  # Verify that it is an image
        return True, None
    except Exception as e:
        return False, str(e)


def extract_images_from_page(
    page: pypdf._page.PageObject, page_number: int, min_tokens: int = 64
):
    images = []
    pixel_limit = min_tokens * 32 * 32
    # Check if page has images
    if "/XObject" in page["/Resources"]:
        xObject = page["/Resources"]["/XObject"].get_object()

        for i, obj in enumerate(xObject):
            if xObject[obj]["/Subtype"] == "/Image":
                # Get image object
                img_obj = xObject[obj]

                # Extract image data
                img_data = img_obj.get_data()

                # Get image properties
                width = img_obj["/Width"]
                height = img_obj["/Height"]

                if width * height < pixel_limit:
                    continue

                # Handle different image formats
                pil_image = None
                if "/Filter" in img_obj:
                    img_filter = img_obj["/Filter"]

                    if img_filter == "/FlateDecode":  # PNG-like
                        # Determine color mode
                        if "/ColorSpace" in img_obj:
                            color_space = img_obj["/ColorSpace"]
                            if color_space == "/DeviceRGB":
                                mode = "RGB"
                            elif color_space == "/DeviceGray":
                                mode = "L"
                            else:
                                mode = "RGB"
                        else:
                            mode = "RGB"

                        pil_image = Image.frombytes(mode, (width, height), img_data)

                    else:
                        try:
                            pil_image = Image.open(io.BytesIO(img_data))
                        except:
                            continue
                else:
                    try:
                        pil_image = Image.frombytes("RGB", (width, height), img_data)
                    except:
                        continue

                if pil_image:
                    image_content = ImageContent(
                        image_name=f"pg{str(page_number).zfill(4)}_im_{str(i).zfill(3)}",
                        image_width=width,
                        image_height=height,
                        image_data=base64.b64encode(img_data).decode("utf-8"),
                    )
                    images.append(image_content)

    return images


def extract_document_content(pdf_path: str) -> PDFContent:
    reader = pypdf.PdfReader(pdf_path)
    pages = []

    # Get page labels if available, otherwise use page indices
    page_labels = (
        reader.page_labels
        if hasattr(reader, "page_labels") and reader.page_labels
        else None
    )

    for i, page in enumerate(reader.pages):
        # Use page label if available, otherwise use page number (1-indexed)
        if page_labels and i < len(page_labels):
            page_number = str(page_labels[i])
        else:
            page_number = str(i + 1)

        # Extract text from the page
        text = page.extract_text()
        images = extract_images_from_page(page, page_number)

        # Create PageContent object
        page_content = PageContent(page_number=page_number, text=text, images=images)
        pages.append(page_content)

    return PDFContent(pages=pages)


def create_document_meta_summary(
    document_content: PDFContent,
) -> PDFMetaSummary:
    pages = document_content.pages

    # Calculate basic metrics
    num_pages = len(pages)
    num_images = sum(len(page.images) for page in pages)

    # Calculate text length metrics
    page_text_lengths = [len(page.text) for page in pages]
    total_text_length = sum(page_text_lengths)
    max_page_text_length = max(page_text_lengths) if page_text_lengths else 0

    # Calculate median (handle empty case)
    median_page_text_length = (
        statistics.median(page_text_lengths) if page_text_lengths else 0
    )

    return PDFMetaSummary(
        num_pages=num_pages,
        num_images=num_images,
        total_text_length=total_text_length,
        max_page_text_length=max_page_text_length,
        median_page_text_length=int(median_page_text_length),
    )


class RouterAgent(BaseAgent):
    def __init__(
        self,
        user_request: RagRequest,
        test_mode: bool = False,
    ):
        super().__init__()
        self.user_request = user_request
        self.user_question = user_request.searchText
        self.test_mode = test_mode
        self.router_model = "gpt-4.1-mini-if-global"
        self.router_temperature = 0.0
        self.model = user_request.model
        self.temperature = user_request.temperature
        self.user_response = []

    async def load_files(self):
        files = self.user_request.pattern.split(",")
        if self.test_mode:
            self.files = files
        else:
            awsResourceFactory = get_aws_resource_factory()
            self.s3_client = awsResourceFactory.get_s3_client()
            self.files = []
            if files:
                for f in files:
                    k = await get_s3_key(document=f, user=self.user_request.user)
                    self.files.append(
                        download_file_from_s3(s3_client=self.s3_client, s3_key=k)
                    )
        if not self.files:
            self.question_type = "no_file"
        elif len(self.files) == 1:
            self.question_type = "single"
        else:
            response = await self.llm.a_get_response(
                messages=[
                    {
                        "role": "user",
                        "content": f"{self.user_question}\n\nFiles: {",".join(self.files)}",
                    },
                    {
                        "role": "developer",
                        "content": "Is the user looking for a single response or multiple responses - one for each file?",
                    },
                ],
                model="gpt-4.1-mini-if-global",
                response_format=SinglevsMultiRequest,
            )
            self.question_type = response.request_type

    async def invoke(self):
        await self.load_files()
        if self.question_type == "multiple":
            for f in self.files:
                await self._invoke_single([f])
        elif self.question_type == "single":
            await self._invoke_single(self.files)

    async def _invoke_single(self, files: list[str]):
        file_list = []
        image_types = []
        data_types = []
        document_types = []
        for f in files:
            if Path(f).suffix == ".csv":
                file_list.append(File(filepath=f, file_type="data", data_context="csv"))
                data_types.append("csv")
                continue
            if Path(f).suffix == ".pdf":

                document_types.append("pdf")
                document_content = extract_document_content(f)
                doc_meta = create_document_meta_summary(document_content)
                is_image_pdf = await self.llm.a_get_response(
                    messages=[
                        {
                            "role": "developer",
                            "content": f"Based on the following document metadata, is the document likely an image based pdf?\n\n```json\n{doc_meta.model_dump_json(indent=2)}\n```",
                        }
                    ],
                    response_format=PDFType,
                )
                file_list.append(
                    File(
                        filepath=f,
                        file_type="document",
                        document_context=PDFFull(
                            filename=Path(f.filepath).stem,
                            is_image_based=is_image_pdf.is_image_based,
                            content=document_content,
                            meta=doc_meta,
                        ),
                    )
                )
                continue

            is_image_bool, error_message = is_image(f)
            if is_image_bool:
                from agent.tools import get_img_breakdown

                image_breakdown = get_img_breakdown(base64_image=encode_image(f))
                if image_breakdown.unreadable:
                    self.user_response += f"\n\nThe image {f} cannot be read.\n\n{image_breakdown.image_quality}"
                else:
                    file_list.append(
                        File(
                            filepath=f,
                            file_type="image",
                            image_context=image_breakdown.elements,
                        )
                    )
                    image_types.extend(
                        [element.element_type for element in image_breakdown.elements]
                    )
                continue
            # Not handling documents just yet
            # file_list.append(File(filepath=f, file_type="document"))
        data_types = list(set(data_types))
        image_types = list(set(image_types))
        instructions = []
        if image_types:
            instructions.extend(
                [
                    f"# Instructions for handling - {element_type} image:\n\n{INSTRUCTION_LIBRARY.get("image").get(element_type, "")}"
                    for element_type in image_types
                ]
            )
        if data_types:
            instructions.extend(
                [
                    f"# Instructions for handling - {data_type} data:\n\n{INSTRUCTION_LIBRARY.get("data").get(data_type, "")}"
                    for data_type in data_types
                ]
            )

        if instructions:
            self.planner = PlannerAgent(
                user_question=self.user_question,
                instruction="\n\n---\n\n".join(instructions),
                files=file_list,
                model=self.model,
                temperature=self.temperature,
            )
            await self.planner.invoke()
            workings = []
            for i, t in enumerate(self.planner.user_response.workings):
                workings.append(
                    f"**Task {i+1}: {t.task_title}**\n\n"
                    f"{t.task_description}\n\n"
                    f"{"\n > ".join(t.task_outcome.split('\n'))}"
                )
            workings.append(
                f"**Answer:**\n\n{self.planner.user_response.markdown_response}"
            )
            self.user_response.append("\n\n".join(workings))
        else:
            self.user_response.append(await legacy_get_answer(self.user_request))

    async def get_response_to_user(self):
        return "\n\n---\n\n".join(self.user_response)
        # response = await self.llm.a_get_response(
        #     messages=[
        #         {
        #             "role": "developer",
        #             "content": f"The user's question is: {self.user_question}.\n\nThe agent's response is:\n\n{self.user_response}\n\n"
        #             "Without changing provide content or creating new content, simply repackage the agent response into a clean markdown output. "
        #             "An example is:\n\n"
        #             "**Task 1: [task title]**\n\n"
        #             "[task description]\n\n"
        #             "> [task outcome]\n\n"
        #             "---\n\n"
        #             "[More tasks can be added here as needed]\n\n"
        #             "---\n\n"
        #             "**Final Response**\n\n"
        #             "[Whatever the response is]",
        #         }
        #     ],
        #     model=self.router_model,
        #     temperature=self.router_temperature,
        # )
        # return response.content
