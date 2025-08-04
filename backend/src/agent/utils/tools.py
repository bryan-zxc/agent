import io
import base64
import json
import string
import logging
from pathlib import Path
from typing import Union, Literal
from pydantic import BaseModel, Field
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from ..services.llm_service import LLM

logger = logging.getLogger(__name__)


def encode_image(image: Union[str, Path, Image.Image]):
    if isinstance(image, str):
        image = Path(image)  # better handling of windows for unix file systems
    if isinstance(image, Path):
        with open(image, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")


def decode_image(image_base64: str) -> Image.Image:
    """
    Decodes a base64 encoded image string into a PIL Image object.

    :param image_base64: Base64 encoded image string.
    :return: PIL Image object.
    """
    image_data = base64.b64decode(image_base64)
    return Image.open(io.BytesIO(image_data))


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


def draw_gridlines(
    img: Image.Image, line_orientation: Literal["horizontal", "vertical"]
):
    # Create a copy of the image to avoid modifying the original
    img_with_grid = img.copy()

    # Get image dimensions
    img_width, img_height = img_with_grid.size

    # Calculate cell dimensions
    cell_width = img_width // 10
    cell_height = img_height // 10

    # Create drawing object
    draw = ImageDraw.Draw(img_with_grid)

    # Try to load a font
    font = ImageFont.load_default()

    # Function to get text size (compatible with different Pillow versions)
    def get_text_size(text):
        if hasattr(font, "getbbox"):
            bbox = font.getbbox(text)
            return bbox[2] - bbox[0], bbox[3] - bbox[1]
        elif hasattr(font, "getsize"):
            return font.getsize(text)
        else:
            return draw.textsize(text, font=font)

    # Draw grid lines
    for i in range(11):
        if line_orientation == "vertical":
            # Vertical lines
            x = i * cell_width
            draw.line([(x, 0), (x, img_height)], fill=(255, 0, 0), width=2)
        else:
            # Horizontal lines
            y = i * cell_height
            draw.line([(0, y), (img_width, y)], fill=(255, 0, 0), width=2)
    # Dictionary to store grid coordinates
    grid_coordinates = {}
    # Add row annotations (letters A-J)
    for i in range(10):
        text = string.ascii_uppercase[i]
        text_width, text_height = get_text_size(text)
        if line_orientation == "vertical":
            x = i * cell_width + (cell_width - text_width) // 2
            draw.text((x, 5), text, fill=(255, 0, 0), font=font)
            grid_coordinates[text] = (
                i * cell_width,
                0,
                (i + 1) * cell_width,
                img_height,
            )
        else:
            y = i * cell_height + (cell_height - text_height) // 2
            draw.text((5, y), text, fill=(255, 0, 0), font=font)
            grid_coordinates[text] = (
                0,
                i * cell_height,
                img_width,
                (i + 1) * cell_height,
            )

    return img_with_grid, grid_coordinates


def apply_selective_blur(img, grid_coordinates):
    blurred_image = img.copy().filter(ImageFilter.GaussianBlur(radius=1))
    cropped = img.crop(grid_coordinates)
    blurred_image.paste(cropped, grid_coordinates)
    return blurred_image, cropped


def combine_image_slices(
    slices: list[Image.Image], combine_orientation: Literal["horizontal", "vertical"]
) -> Image.Image:
    mode = slices[0].mode
    if combine_orientation == "horizontal":
        # To merge horizontally, sum widths and use max height
        total_width = sum(img.width for img in slices)
        max_height = max(img.height for img in slices)

        # Create a new blank image with the calculated dimensions
        merged_image = Image.new(mode, (total_width, max_height))

        # Paste each slice at the appropriate x position
        x_offset = 0
        for img in slices:
            merged_image.paste(img, (x_offset, 0))
            x_offset += img.width

    else:
        # To merge vertically, sum heights and use max width
        max_width = max(img.width for img in slices)
        total_height = sum(img.height for img in slices)

        # Create a new blank image with the calculated dimensions
        merged_image = Image.new(mode, (max_width, total_height))

        # Paste each slice at the appropriate y position
        y_offset = 0
        for img in slices:
            merged_image.paste(img, (0, y_offset))
            y_offset += img.height
    return merged_image


def identify_relevant_slices(
    original_image: Image.Image,
    slices: list[Image.Image],
    vertical_or_horizontal: Literal["vertical", "horizontal"],
    messages: list[dict],
) -> tuple[Image.Image, str]:
    """
    Analyzes image slices to identify those relevant to the user's request and merges them.
    This tool is reserved specifically to read charts.
    For images of tables or flow diagrams or text or illustrations, do not use this tool.

    This function evaluates slices of a larger image to determine which contain information
    relevant to a user's query. It uses Azure OpenAI to analyze each slice, filters out
    irrelevant ones, merges the relevant slices back together, and generates a response
    addressing the user's request based on the merged image.

    Parameters:
    ----------
    original_image : Image.Image
        The original image from which the slices were created, used for context analysis.
    slices : list[Image.Image]
        A list of PIL Image objects representing segments of the original image.
    vertical_or_horizontal : Literal["vertical", "horizontal"]
        Specifies the orientation of the slices - "vertical" means slices are arranged left-to-right,
        "horizontal" means slices are arranged top-to-bottom.
    messages : list[dict]
        Conversation history containing the user's request and context.

    Returns:
    -------
    tuple[Image.Image, str]
        A tuple containing:
        - The merged image containing all identified relevant slices, or None if no relevant slices found
        - A response string addressing the user's request or explaining why no answer is possible

    Process:
    -------
    1. Determines what information is relevant based on the original image and user request
    2. Analyzes each slice to determine if it contains relevant axis or chart information
    3. Collects and tracks relevant slices
    4. Merges relevant slices into a single image (horizontally or vertically based on slice orientation)
    5. Generates a comprehensive response to the user's request based on the merged image
    """

    class ImageRelevance(BaseModel):
        """
        Pydantic model defining the structure for LLM responses about image relevance.
        This structured output helps categorize and filter image slices.
        """

        contains_relevant_axis: bool = Field(
            description="Based strictly on the stated relevant axis, does this image slice contain any part of the defined relevant axis? "
            "If the description of the image specifically mentions that the axis is not visible, this must be False whether or not there are other related information."
        )
        relevant_axis_explanation: str = Field(
            description="Explain why the image slice contains or does not contain the stated relevant axis information."
        )
        contains_relevant_chart_section: bool = Field(
            description="Based strictly on the stated relevant chart section, does this image contain any part of the defined relevant chart section?"
        )
        relevant_section_explanation: str = Field(
            description="Explain why the image slice contains or does not contain the stated relevant chart section."
        )

    # Dictionary to store relevant image slices with their generated variable names
    # slices_dict = {}

    # Initialize the Azure LLM service for image analysis
    llm = LLM(caller="tools")
    new_messages = messages[:2].copy()
    base64_orig = encode_image(original_image)
    reverse_vertical_or_horizontal = (
        "horizontal" if vertical_or_horizontal == "vertical" else "vertical"
    )
    required_slices_description = llm.get_response(
        messages=new_messages
        + [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"Based on the full image, describe which {vertical_or_horizontal} slices will contain information relevant to the user request."
                        f"The answer should describe the relevant {vertical_or_horizontal} axis (as there may be more than one {vertical_or_horizontal} axis), "
                        "and the relevant chart section (for example in a bar chart, a description to identify the bar that needs to be read)."
                        "The format of the response should be:\n"
                        "# User request\n<user request>\n\n"
                        "# Relevant axis\n<description of the relevant axis>\n<description of which axis is not relevant "
                        f"(for example the {reverse_vertical_or_horizontal} axis MUST be stated as not relevant. Other examples include unneeded {vertical_or_horizontal} axis when there is multiple)>\n\n"
                        f"# Relevant chart section\n<description of the relevant chart section>\n"
                        f"<description of which chart section is not relevant - this MUST include the values of the {reverse_vertical_or_horizontal} axis that is not relevant.>\n\n",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{base64_orig}"},
                    },
                ],
            }
        ],
        model="gemini-2.5-pro",
    ).content
    logger.debug(f"Required slices description: {required_slices_description}")

    relevant_slices = []
    relevant_slice_ids = []
    # Process each image slice to determine its relevance
    for i, slice in enumerate(slices):
        # Convert the image to base64 for inclusion in the API request
        # slice.show()  # Ensure the image is loaded and ready for processing
        base64_slice = encode_image(slice)
        image_desc = llm.get_response(
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "The image is a cropped slice of a bigger image. Describe it in detail. "
                            f"The description should be focused on describing whether on not the {vertical_or_horizontal} axis is present / partially cut off / not present in the chart; "
                            f"as well as describing what is visible on the {reverse_vertical_or_horizontal} including partially cut off information. ",
                            # "You must stay true to what is visible on this image, do not guess about information that is not visible.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_slice}"
                            },
                        },
                    ],
                }
            ],
            model="gemini-2.5-pro",
        ).content
        # print(image_desc, flush=True)

        # Query the LLM to analyze the image and determine its relevance
        # The response is structured according to the ImageRelevance model
        if relevant_slice_ids:
            additional_context = f"Slices {','.join(relevant_slice_ids)} have already been marked as relevant."
        else:
            additional_context = "No slices have been marked as relevant yet."
        slice_messages = [
            {
                "role": "developer",
                "content": f"The goal is as follows:\n\n{required_slices_description}\n\n"
                f"You are been progressively provided a slice at a time from {"from left to right" if vertical_or_horizontal == 'vertical' else 'from top to bottom'} of the original image. "
                f"There are {len(slices)} slices in total, this is slice number {i}. {additional_context}",
            },
            {
                "role": "developer",
                "content": f"The verbal description of the image slice is as follows:\n\n{image_desc}\n\n",
            },
        ]
        image_relevance = llm.get_response(
            messages=slice_messages,
            response_format=ImageRelevance,
            model="gemini-2.5-pro",
        )
        # print(slice_messages, flush=True)
        # Log the analysis results for debugging/monitoring
        # print(
        #     f"Image relevance:\n{image_relevance.model_dump_json(indent=2)}", flush=True
        # )

        # If the image contains relevant information (axis or chart section),
        # add it to the result dictionary with the generated variable name
        if (
            image_relevance.contains_relevant_axis
            or image_relevance.contains_relevant_chart_section
        ):
            # slices_dict[f"slice_{i}"] = slice
            relevant_slices.append(slice)
            relevant_slice_ids.append(str(i))
    # print(
    #     f"The following slices are all identified to be required to address the user request: {list(slices_dict.keys())}",
    #     flush=True,
    # )
    if not relevant_slices:
        return (
            None,
            "The image provided does not contain relevant information to answer the question/request.",
        )

    merged_image = combine_image_slices(
        slices=relevant_slices, combine_orientation=reverse_vertical_or_horizontal
    )
    merged_image.show()

    # gridded_image, grid_coordinates = draw_gridlines(
    #     merged_image, reverse_vertical_or_horizontal
    # )
    # # gridded_image.show()
    # base64_gridded = encode_image(gridded_image)

    # class GridPicker(BaseModel):
    #     slice_code: Literal["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]

    # messages = [
    #     {
    #         "role": "user",
    #         "content": [
    #             {
    #                 "type": "text",
    #                 "text": f"We have just selected the {vertical_or_horizontal} slices based on the following goal:\n{required_slices_description}\n\n"
    #                 f"Now from this new image, select the {reverse_vertical_or_horizontal} slice that contains the {reverse_vertical_or_horizontal} axis.",
    #             },
    #             {
    #                 "type": "image_url",
    #                 "image_url": {"url": f"data:image/pgn;base64,{base64_gridded}"},
    #             },
    #         ],
    #     }
    # ]
    # axis_response = llm.get_response(messages=messages, response_format=GridPicker)
    # axis_cropped = merged_image.crop(grid_coordinates[axis_response.slice_code])
    # for _ in range(3):
    #     review_messages = messages.copy() + [
    #         {
    #             "role": "assistant",
    #             "content": f"The slice with the axis is: {axis_response.slice_code}",
    #         }
    #     ]
    #     review_messages.append(
    #         {
    #             "role": "user",
    #             "content": [
    #                 {
    #                     "type": "text",
    #                     "text": f"Below is the grid slice {axis_response.slice_code} cropped out. Using only the below image, confirm if it contains the {reverse_vertical_or_horizontal} axis. If not, which slice should it be?",
    #                 },
    #                 {
    #                     "type": "image_url",
    #                     "image_url": {
    #                         "url": f"data:image/pgn;base64,{encode_image(axis_cropped)}"
    #                     },
    #                 },
    #             ],
    #         }
    #     )

    #     class AxisReview(BaseModel):
    #         contains_axis: bool
    #         correct_slice: Literal["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"] = (
    #             Field(
    #                 None,
    #                 description="If the selected slice does not contain the axis, which slice would contain it? "
    #                 "Leave the field empty if the correct slice has already been chosen.",
    #             )
    #         )

    #     axis_review = llm.get_response(
    #         messages=review_messages, response_format=AxisReview
    #     )
    #     # print(axis_review.model_dump_json(indent=2), flush=True)
    #     if axis_review.contains_axis:
    #         break
    #     axis_cropped = merged_image.crop(grid_coordinates[axis_review.correct_slice])
    # # axis_cropped.show()
    # messages = [
    #     {
    #         "role": "user",
    #         "content": [
    #             {
    #                 "type": "text",
    #                 "text": f"We have just selected the {vertical_or_horizontal} slices based on the following goal:\n{required_slices_description}\n\n"
    #                 f"Now select the {reverse_vertical_or_horizontal} slice that contains the relevant chart section. "
    #                 "For example, if the chart is a bar chart, select the slice that contains the top of the relevant bar. "
    #                 "If it is a line chart, select the slice where the relevant line segment is present.",
    #             },
    #             {
    #                 "type": "image_url",
    #                 "image_url": {"url": f"data:image/pgn;base64,{base64_gridded}"},
    #             },
    #         ],
    #     }
    # ]
    # grid_response = llm.get_response(messages=messages, response_format=GridPicker)
    # blurred_image, cropped = apply_selective_blur(
    #     gridded_image, grid_coordinates[grid_response.slice_code]
    # )
    # slice_code = grid_response.slice_code
    # # blurred_image.show()
    # for _ in range(3):
    #     review_messages = messages.copy() + [
    #         {
    #             "role": "assistant",
    #             "content": f"The slice with relevant chart section is: {slice_code}",
    #         }
    #     ]
    #     review_messages.append(
    #         {
    #             "role": "user",
    #             "content": [
    #                 {
    #                     "type": "text",
    #                     "text": "I have blurred out all other sections other than the selected. Use this as context.",
    #                 },
    #                 {
    #                     "type": "image_url",
    #                     "image_url": {
    #                         "url": f"data:image/pgn;base64,{encode_image(blurred_image)}"
    #                     },
    #                 },
    #             ],
    #         }
    #     )
    #     review_messages.append(
    #         {
    #             "role": "user",
    #             "content": [
    #                 {
    #                     "type": "text",
    #                     "text": "Below is a crop of the selected slice of the image. "
    #                     "Use the full image with blurring from above as context, and determine from this image if it contains the relevant chart section to address the user's question. "
    #                     "If not, which section should it be?\n",
    #                 },
    #                 {
    #                     "type": "image_url",
    #                     "image_url": {
    #                         "url": f"data:image/pgn;base64,{encode_image(cropped)}"
    #                     },
    #                 },
    #             ],
    #         }
    #     )

    #     class SlicesReview(BaseModel):
    #         thought: str = Field(
    #             description="Articulate your thoughts step by step to assess if this is the correct image slice. The field should contain numbered steps."
    #         )
    #         contains_correct_content: bool = Field(
    #             description="If the relevant chart section (for example the top of relevant bar in a bar chart, or the line segment of a line chart) is not blurred in the image with blur. "
    #             "You must also confirm that the relevant chart section like top of bar or line is visible in the cropped image. "
    #             "Only if you believe both are true, set this to True. "
    #         )
    #         correct_slice: Literal["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"] = (
    #             Field(
    #                 None,
    #                 description="If the selected slice (the unblurred section) does not contain the relevant chart section, which slice would contain it? "
    #                 "Leave the field empty if the correct slice has already been chosen.",
    #             )
    #         )

    #     slices_review = llm.get_response(
    #         messages=review_messages, response_format=SlicesReview
    #     )
    #     # print(slices_review.model_dump_json(indent=2), flush=True)
    #     if slices_review.contains_correct_content:
    #         break
    #     slice_code = slices_review.correct_slice
    #     blurred_image, cropped = apply_selective_blur(
    #         gridded_image, grid_coordinates.get(slice_code)
    #     )
    # # blurred_image.show()
    # # cropped.show()
    # final_merge = combine_image_slices(
    #     slices=[cropped, axis_cropped], combine_orientation=vertical_or_horizontal
    # )
    # # final_merge.show()
    # base64_final = encode_image(final_merge)
    # response_to_user = llm.get_response(
    #     messages=[
    #         {
    #             "role": "user",
    #             "content": [
    #                 {
    #                     "type": "text",
    #                     "text": f"The first goal is as follows:\n\n{required_slices_description}\n\n"
    #                     f"Due to limitations in the LLM, the original image was cut up into {vertical_or_horizontal} slices, removed the irrelevant ones and created a new image, achieving the above goal. "
    #                     f"Subsequently the new image is separated into {reverse_vertical_or_horizontal} slices, and the correct slice is placed with the {reverse_vertical_or_horizontal} axis (the are combined in no particular order and can look reversed). "
    #                     "Using this new image, answer the user's question/request. "
    #                     "The response should have two sections - the axis markers the relevant bar or line (or whichever chart type) is between, and the final answer to the user's question. ",
    #                 },
    #                 {
    #                     "type": "image_url",
    #                     "image_url": {"url": f"data:image/png;base64,{base64_final}"},
    #                 },
    #             ],
    #         },
    #     ]
    # ).content
    base64_merged = encode_image(merged_image)
    response_to_user = llm.get_response(
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"The goal is as follows:\n\n{required_slices_description}\n\n"
                        "Due to limitations in the LLM, the original image was cut up into slices, removed the irrelevant ones and created the new image below. "
                        "Use this image to answer the user's question/request",
                        # "When reading a chart always first articulate which two axis markers the bar or line (or whichever chart type) is between, before taking a guess at the more accurate value.",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{base64_merged}"},
                    },
                ],
            }
        ],
        model="gemini-2.5-pro",
    ).content
    return merged_image, response_to_user


def legacy_get_text_and_table_json_from_image(image: Union[Image.Image, str]) -> str:
    """
    Extracting text and table content as JSON from an image by breaking it into overlapping slices and
    extracting structured data piece meal.

    This function takes an image containing a table and/or text and processes it in smaller slices to overcome
    context limitations of the LLM when dealing with large images. It slices the image vertically,
    processes each slice to extract the table content, and then combines the results to generate
    a consolidated JSON representation of the entire table and/or text.

    Parameters:
    ----------
    image : Union[Image.Image, str]
        The input image containing the table/text, either as a PIL Image object
        or a base64 encoded string representation of the image.

    Returns:
    -------
    str
        A JSON string representing the structured data extracted from the table and any relevant text.

    Process:
    -------
    1. Handles the input image whether it's a base64 string or PIL Image object
    2. Slices the image into overlapping vertical segments to ensure context continuity
    3. Processes each slice with Azure OpenAI to extract table content as markdown
    4. Combines all extracted markdown content with the original image
    5. Generates a final consolidated JSON output that represents the complete table
    """
    # Convert input to both PIL Image and base64 string for processing
    if isinstance(image, str):
        base64_image = image  # Save the base64 string if that's what was provided
        image = Image.open(
            io.BytesIO(base64.b64decode(base64_image))
        )  # Convert to PIL Image
    elif isinstance(image, Image.Image):
        base64_image = encode_image(image)  # Convert PIL Image to base64
    else:
        raise TypeError(
            "The image must be a base64 encoded string or a PIL Image object."
        )

    # Define slicing parameters
    slice_height = 300  # Height of each slice in pixels
    overlap = 30  # Overlap between slices in pixels to maintain context
    width, height = image.size
    llm = LLM(caller="tools")  # Initialize Azure OpenAI LLM service

    if height < slice_height * 1.5:
        return llm.get_response(
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Extract the table and/or text content from the image in JSON format.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_image}"
                            },
                        },
                    ],
                }
            ],
            response_format={"type": "json_object"},
        )
    # Calculate the number of slices needed to cover the entire image height
    num_slices = height // slice_height
    if height % slice_height > 0:  # Add an extra slice if there's a remainder
        num_slices += 1

    # Initialize message list with a context message for the LLM
    messages = [
        {
            "role": "developer",
            "content": "Below are markdown content extracted from slices of the full table image starting from top to bottom with some overlap.",
        }
    ]

    # Process each slice to extract table content as markdown
    for i in range(num_slices):
        # Calculate the base slice boundaries (without overlap)
        base_top = i * slice_height
        base_bottom = min((i + 1) * slice_height, height)

        # Add overlap to ensure context continuity, respecting image boundaries
        top = max(0, base_top - overlap)
        bottom = min(height, base_bottom + overlap)

        # Crop the slice and convert to base64 for API request
        slice = image.crop((0, top, width, bottom))
        # slice.show()
        base64_slice = encode_image(slice)

        # Extract table content from this slice as markdown using Azure OpenAI
        slice_md = llm.get_response(
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "I am progressively extracting information as markdown from the full image, one slice at a time. "
                            f"This is the slice {i+1} out of {num_slices}. "
                            "There might be partially cropped information on this slice, do not skip it, do your best to extract all visible content into markdown. "
                            "IMPORTANT: You must stay true to what is visible on this image, do not make up any values especially column headers if they are not present in the image.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_slice}"
                            },
                        },
                    ],
                }
            ],
            model="gemini-2.5-pro",
        ).content
        # print(slice_md)

        # Add the markdown result to the conversation history
        messages.append({"role": "assistant", "content": slice_md})
        # print(slice_md, flush=True)

    # Add the full original image as final context
    image_message = {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": "Extract the table and/or text content from the image in markdown format.",
            },
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{base64_image}"},
            },
        ],
    }

    full_md = llm.get_response(messages=[image_message], model="gemini-2.5-pro").content
    # Request a consolidated JSON representation of all tables in the image
    messages.append(image_message)
    messages.append({"role": "assistant", "content": full_md})
    messages.append(
        {
            "role": "developer",
            "content": "Cross compare the markdown extracted directly from the full image to the piece meal markdown extracted from the slices. "
            "The markdown from the full version will contain the correct structure, but the piece meal markdown will contain the correct values. "
            "Where there are discrepancies in the values read, always change the values in the full markdown into the values from the piecemeal markdowns. "
            "Note that in the piecemeal markdowns, due to overlap, the same information at the edge may be repeated and possibly different due to partially cut off information. "
            "As long as the full markdown agrees with one of the piecemeal markdowns, it is correct. "
            "Return a new updated markdown.",
        }
    )
    final_md = llm.get_response(messages=messages, model="gemini-2.5-pro").content

    # Generate the final JSON response that consolidates all table data
    final_json = llm.get_response(
        messages=[
            {
                "role": "user",
                "content": f"Convert the following markdown into a JSON object:\n\n{final_md}",
            }
        ],
        response_format={"type": "json_object"},
    )
    return final_json


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
        response_format={"type": "json_object"},
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


def get_img_breakdown(base64_image: str):
    llm = LLM(caller="tools")
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "What type of image is this?"},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/pgn;base64,{base64_image}"},
                },
            ],
        }
    ]
    from ..models.schemas import ImageBreakdown

    image_breakdown = llm.get_response(
        messages=messages,
        model="gemini-2.5-pro",
        response_format=ImageBreakdown,
    )
    return image_breakdown


class QnA(BaseModel):
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
    question_answer: list[QnA] = Field(
        description="The list of questions where the answers can already be extracted from the context. "
        "This must completely cover every answerable component of the answer template."
    )
    unanswered_questions: list[str] = Field(
        "",
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

    # # Define structured response format for consistent output parsing
    # class SearchResponse(BaseModel):
    #     markdown_answer: str = Field(
    #         description="Comprehensive answer to the user's question in markdown format."
    #     )
    #     unanswered_questions: list[str] = Field(
    #         description="What additional information is required to answer the user's question or make it more complete and cohesive? "
    #         "Return this as a list of questions to be asked."
    #     )
    #     # required_images: list[str] = Field(
    #     #     [],
    #     #     description="List of image_name that are deemed to be potentially useful to address unanswered_questions. "
    #     #     "If there are none, then leave the field blank.",
    #     # )

    # # Execute initial search using text content only
    # search_response = llm.get_response(
    #     messages=messages + extension_messages,
    #     model="gemini-2.5-pro",
    #     response_format=SearchResponse,
    # )
    # print(search_response.model_dump_json(indent=2), flush=True)
    # # If no additional questions, return the initial answer

    # # Phase 3: Analyze relevant images to gather additional information
    # added_info_count = 0
    # if search_response.unanswered_questions:
    #     for page_number, img_data in get_images_from_doc(doc):
    #         # Determine image content type for appropriate processing
    #         image_breakdown = get_img_breakdown(base64_image=img_data)
    #         element_types = [e.element_type for e in image_breakdown.elements]

    #         # Process tables and text content
    #         if "table" in element_types or "text" in element_types:
    #             tt_json = get_text_and_table_json_from_image(image=img_data)
    #             print(tt_json, flush=True)
    #             messages.append(
    #                 {
    #                     "role": "developer",
    #                     "content": f"Image on page {page_number} contains the following text and table content:\n\n{tt_json}",
    #                 }
    #             )
    #             added_info_count += 1

    #         # Process chart content
    #         if "chart" in element_types:
    #             chart_json = get_chart_readings_from_image(image=img_data)
    #             messages.append(
    #                 {
    #                     "role": "developer",
    #                     "content": f"The image on page {page_number} contains the following chart readings in the form of question answer pairs:\n\n{chart_json}",
    #                 }
    #             )
    #             added_info_count += 1
    # else:
    #     return search_response.markdown_answer

    # # Phase 4: Generate final response based on available information
    # if added_info_count == 0:
    #     # No additional information found in images
    #     return (
    #         f"The following answer can be provided using the context:\n\n{search_response.markdown_answer}\n\n"
    #         f"However, the following questions remain unanswered:\n\n{"\n".join([f' - {q}' for q in search_response.unanswered_questions])}\n\n"
    #     )

    # # Generate comprehensive response incorporating image analysis results
    # response = llm.get_response(
    #     messages=messages + extension_messages, model="gemini-2.5-pro"
    # ).content
    # return response


def get_facts_from_pdf(question: str, pdf_source: Union[str, Path]) -> str:
    """
    Extract facts from a PDF document to answer a specific question.

    This function takes a user's question and a PDF source (local path or URL),
    then uses LLM to extract relevant facts from the PDF in the form of
    question-answer pairs and identifies any unanswered questions.

    Parameters:
    ----------
    question : str
        The user's question to be answered using the PDF content.
    pdf_source : Union[str, Path]
        Path to local PDF file or URL to web PDF.

    Returns:
    -------
    str
        A JSON string containing question-answer pairs and unanswered questions.
    """
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
    return response.model_dump_json(
        include={"question_answer", "unanswered_questions"}, indent=2
    )


def search_web_general(query: str) -> str:
    """
    Searches the web using Google Search.
    Do not use this function for document search, use `search_web_pdf` instead.

    Parameters:
    ----------
    query : str
        The search query or question to be answered using web search results.

    Returns:
    -------
    str
        Web search results.
    """
    llm = LLM(caller="tools")
    return llm.search_web(query=query)


def search_web_pdf(query: str) -> str:
    """
    Search for PDF documents online using Google Search.

    Parameters:
    ----------
    query : str
        The search query or topic to find relevant PDF documents for.

    Returns:
    -------
    str
        A JSON string containing structured data with PDF document information, including
        descriptions and hyperlinks for each found document.
    """

    class PDFResult(BaseModel):
        description: str = Field(description="Description of the PDF document")
        hyperlink: str = Field(description="URL/hyperlink to the PDF document")

    class PDFSearchResults(BaseModel):
        requested_pdfs: list[PDFResult] = Field(
            [],
            description="List of PDF documents requested. If none found, leave empty.",
        )
        complementary_pdfs: list[PDFResult] = Field(
            [],
            description="If there are non-requested PDF documents that may help address the query, list them here, otherwise leave empty.",
        )

    llm = LLM(caller="tools")
    response = llm.search_web(query=query, response_format=PDFSearchResults)
    return response.model_dump_json(indent=2)
