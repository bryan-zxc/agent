from pathlib import Path
from ..core.base import BaseAgent
from ..agents.planner import PlannerAgent
from ..utils.tools import encode_image
from ..models import (
    SinglevsMultiRequest,
    PDFType,
    PDFFull,
    File,
)
from ..services.document_service import (
    extract_document_content,
    create_document_meta_summary,
)
from ..services.image_service import process_image_file

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


class RouterAgent(BaseAgent):
    def __init__(
        self,
        user_request,  # RagRequest type - keeping flexible for now
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
        self.files = files
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
                            filename=Path(f).stem,
                            is_image_based=is_image_pdf.is_image_based,
                            content=document_content,
                            meta=doc_meta,
                        ),
                    )
                )
                continue

            # Process image files
            image_breakdown, error_message = process_image_file(f)
            if error_message:
                self.user_response.append(f"\n\n{error_message}")
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

    async def get_response_to_user(self):
        return "\n\n---\n\n".join(self.user_response)