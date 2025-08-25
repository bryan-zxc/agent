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
from ..services.llm_service import LLM
from .image_utils import encode_image, decode_image

logger = logging.getLogger(__name__)




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
    logger.info(f"Required slices description: {required_slices_description}")

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
        and missing facts for the template in the form of unanswered questions.
    """
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
    return response.model_dump_json(
        exclude=["thought","answer_template"], indent=2
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
    Search for PDF documents online using Google Search and extract Q&A pairs from each PDF.

    This function searches for PDFs, then extracts facts from each PDF one at a time
    until there are no longer any unanswered questions or the list of PDFs is exhausted.

    Parameters:
    ----------
    query : str
        The search query or topic to find relevant PDF documents for and extract facts from.

    Returns:
    -------
    str
        A JSON string containing comprehensive Q&A pairs extracted from all analysed PDFs,
        along with any remaining unanswered questions.
    """

    class PDFResult(BaseModel):
        description: str = Field(description="Description of the PDF document")
        hyperlink: str = Field(
            description="URL/hyperlink to the PDF document. The link must end in .pdf."
        )

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

    # First, search for PDFs
    response = llm.search_web(
        query=f"Provide hyperlinks to the PDF documents for: {query}\n\n"
        "Can include additional complementary PDFs if noticed."
    )

    def get_pdf_url_from_redirect(redirect_url: str) -> str:
        """Extract actual PDF URL from Google redirect."""
        try:
            response_redirect = requests.get(redirect_url, allow_redirects=False, timeout=10)
            if response_redirect.status_code in [301, 302]:
                redirect_location = response_redirect.headers.get('Location', '')
                if redirect_location.lower().endswith('.pdf'):
                    return redirect_location
            
            # If no direct redirect, try to extract from HTML
            response_redirect = requests.get(redirect_url, timeout=10)
            pdf_url_match = re.search(r'HREF="([^"]*\.pdf[^"]*)"', response_redirect.text)
            if pdf_url_match:
                return pdf_url_match.group(1)
                
            return redirect_url  # Return original if no PDF found
        except Exception as e:
            logger.warning(f"Failed to resolve redirect {redirect_url}: {e}")
            return redirect_url

    def is_valid_pdf(file_path: str) -> bool:
        """Check if downloaded file is actually a PDF."""
        try:
            with open(file_path, 'rb') as f:
                header = f.read(4)
                return header == b'%PDF'
        except:
            return False

    def download_pdf_with_curl(pdf_url: str, output_path: str) -> bool:
        """Download PDF using curl to handle Cloudflare protection."""
        try:
            logger.info(f"🔄 CURL: Attempting to download {pdf_url}")
            result = subprocess.run([
                'curl', '-L', '-o', output_path, pdf_url
            ], capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0 and is_valid_pdf(output_path):
                logger.info(f"✅ CURL: Successfully downloaded valid PDF to {output_path}")
                return True
            else:
                logger.warning(f"❌ CURL: Download failed or invalid PDF. Return code: {result.returncode}")
                if result.stderr:
                    logger.warning(f"CURL stderr: {result.stderr}")
                # Clean up invalid file
                Path(output_path).unlink(missing_ok=True)
                return False
        except Exception as e:
            logger.warning(f"❌ CURL: Exception during download: {e}")
            return False

    def download_pdf_with_selenium(pdf_url: str, output_path: str) -> bool:
        """Download PDF using Selenium for JavaScript-heavy protection."""
        logger.info(f"🔄 SELENIUM: Attempting to download {pdf_url}")
        driver = None
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            import time
            import os
            import platform
            
            # Configure Chrome/Chromium options for headless mode
            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--disable-web-security')
            chrome_options.add_argument('--disable-features=VizDisplayCompositor')
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            
            # Set binary location based on architecture
            arch = platform.machine().lower()
            logger.info(f"🏗️ SELENIUM: Detected architecture: {arch}")
            if arch in ['aarch64', 'arm64']:
                chrome_options.binary_location = '/usr/bin/chromium'
                driver_executable = 'chromium-driver'
                use_chromedriver_autoinstaller = False  # Skip for ARM64
                logger.info("🏗️ SELENIUM: ARM64 detected, using system chromium-driver")
            else:
                chrome_options.binary_location = '/usr/bin/google-chrome'
                driver_executable = 'chromedriver'
                use_chromedriver_autoinstaller = True
                logger.info("🏗️ SELENIUM: x86_64 detected, using chromedriver-autoinstaller")
            
            # Setup ChromeDriver service with proper path handling
            service = None
            driver_path = None
            
            # Only use chromedriver-autoinstaller for x86_64
            if use_chromedriver_autoinstaller:
                try:
                    import chromedriver_autoinstaller
                    # Install and get the path to the driver
                    driver_path = chromedriver_autoinstaller.install()
                    logger.info(f"📦 SELENIUM: Auto-installed ChromeDriver at {driver_path}")
                    
                    # Create service with the installed driver path
                    if driver_path and os.path.exists(driver_path):
                        # Ensure the driver has execute permissions
                        os.chmod(driver_path, 0o755)
                        service = Service(executable_path=driver_path)
                        logger.info(f"🔧 SELENIUM: Using driver service at {driver_path}")
                    else:
                        logger.warning(f"⚠️ SELENIUM: Driver path {driver_path} doesn't exist, trying default")
                        service = Service()
                        
                except ImportError:
                    logger.info("🔧 SELENIUM: chromedriver_autoinstaller not available, using system driver")
                    service = Service()
                except Exception as e:
                    logger.warning(f"⚠️ SELENIUM: ChromeDriver auto-install failed: {e}, trying system driver")
                    service = Service()
            else:
                logger.info("🔧 SELENIUM: Skipping chromedriver-autoinstaller for ARM64")
            
            # Alternative: try to find system drivers
            if not driver_path:
                system_paths = [
                    '/usr/local/bin/chromedriver',
                    '/usr/bin/chromedriver', 
                    '/usr/local/bin/chromium-driver',
                    '/usr/bin/chromium-driver'
                ]
                for path in system_paths:
                    if os.path.exists(path):
                        driver_path = path
                        # Ensure the system driver has execute permissions
                        os.chmod(path, 0o755)
                        service = Service(executable_path=path)
                        logger.info(f"🔍 SELENIUM: Found system driver at {path}")
                        break
            
            logger.info("🚀 SELENIUM: Starting browser")
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.set_page_load_timeout(30)
            
            logger.info(f"🌐 SELENIUM: Navigating to {pdf_url}")
            driver.get(pdf_url)
            
            # Wait for potential redirects and JavaScript execution
            logger.info("⏳ SELENIUM: Waiting for page to load and JS to execute...")
            time.sleep(10)
            
            # Check if we ended up at a PDF
            current_url = driver.current_url
            logger.info(f"🔍 SELENIUM: Final URL: {current_url}")
            
            if current_url.lower().endswith('.pdf') or 'pdf' in current_url.lower():
                logger.info("📄 SELENIUM: Detected PDF URL, downloading with session cookies")
                # Use requests with the session cookies from Selenium
                cookies = driver.get_cookies()
                driver.quit()
                driver = None
                
                session = requests.Session()
                for cookie in cookies:
                    session.cookies.set(cookie['name'], cookie['value'])
                
                headers = {
                    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                }
                
                response = session.get(current_url, headers=headers)
                with open(output_path, 'wb') as f:
                    f.write(response.content)
                
                # Validate that we actually got a PDF
                if is_valid_pdf(output_path):
                    logger.info(f"✅ SELENIUM: Successfully downloaded valid PDF to {output_path}")
                    return True
                else:
                    logger.warning(f"❌ SELENIUM: Downloaded file is not a valid PDF")
                    Path(output_path).unlink(missing_ok=True)
                    return False
            else:
                logger.warning(f"❌ SELENIUM: Did not reach PDF URL, got: {current_url}")
                driver.quit()
                driver = None
                return False
                
        except Exception as e:
            logger.warning(f"❌ SELENIUM: Exception during download: {e}")
            if driver:
                try:
                    driver.quit()
                except:
                    pass
            return False

    # Extract grounding chunks from the response
    try:
        chunks = response.candidates[0].grounding_metadata.grounding_chunks
        pdf_urls = []
        
        for chunk in chunks:
            if hasattr(chunk, 'web') and chunk.web.uri:
                uri = chunk.web.uri
                
                # Check if it's a Google redirect that might lead to a PDF
                if 'vertexaisearch.cloud.google.com/grounding-api-redirect' in uri:
                    actual_pdf_url = get_pdf_url_from_redirect(uri)
                    if actual_pdf_url.lower().endswith('.pdf'):
                        pdf_urls.append(actual_pdf_url)
                elif uri.lower().endswith('.pdf'):
                    pdf_urls.append(uri)
        
        if not pdf_urls:
            return '{"answer_template": "", "question_answer": [], "unanswered_questions": ["No relevant PDFs found for the query"]}'
            
    except Exception as e:
        logger.error(f"Failed to extract grounding chunks: {e}")
        return '{"answer_template": "", "question_answer": [], "unanswered_questions": ["Failed to extract PDFs from search results"]}'

    # Start with empty results
    combined_results = (
        '{"answer_template": "", "question_answer": [], "unanswered_questions": ["'
        + query
        + '"]}'
    )

    # Use TemporaryDirectory for automatic cleanup
    with tempfile.TemporaryDirectory(prefix='agent_pdfs_') as temp_dir:
        # Process each PDF one at a time
        for i, pdf_url in enumerate(pdf_urls):
            current_data = json.loads(combined_results)

            # Stop if no more unanswered questions
            if not current_data.get("unanswered_questions"):
                break

            try:
                # Download PDF to temporary directory
                temp_pdf_path = Path(temp_dir) / f"pdf_{i}.pdf"
                
                # Try to download the PDF - first with curl, then with Selenium as fallback
                logger.info(f"📥 DOWNLOAD: Processing PDF {i+1}/{len(pdf_urls)}: {pdf_url}")
                download_success = download_pdf_with_curl(pdf_url, str(temp_pdf_path))
                if not download_success:
                    logger.info(f"🔄 DOWNLOAD: Curl failed for {pdf_url}, trying Selenium...")
                    download_success = download_pdf_with_selenium(pdf_url, str(temp_pdf_path))
                
                if download_success:
                    logger.info(f"✅ DOWNLOAD: Successfully obtained PDF, processing content...")
                    # Build contextual question for this PDF
                    contextual_question = f"The full question is: {query}. "

                    if current_data.get("question_answer"):
                        answered_summary = ", ".join(
                            [
                                f"{qa['question']}: {qa['answer']}"
                                for qa in current_data["question_answer"]
                            ]
                        )
                        contextual_question += (
                            f"We already know answers to the following: {answered_summary}. "
                        )

                    if len(current_data.get("unanswered_questions", [])) > 1:
                        missing_summary = ", ".join(current_data["unanswered_questions"][1:])
                        contextual_question += (
                            f"We are still missing the following: {missing_summary}. "
                        )

                    if current_data.get("answer_template"):
                        contextual_question += (
                            f"Response template is: {current_data['answer_template']}. "
                        )

                    contextual_question += (
                        f"Focus on: {current_data['unanswered_questions'][0]}"
                    )

                    # Get facts from the current PDF using local file
                    new_pdf_results = get_facts_from_pdf(contextual_question, str(temp_pdf_path))

                    # Use LLM to combine previous results with new PDF results
                    combine_prompt = f"""
                    Previous results from earlier PDFs:
                    {combined_results}
                    
                    New results from current PDF ({pdf_url}):
                    {new_pdf_results}
                    
                    Combine these results into a single comprehensive response. 
                    - Update the answer_template if the new one is more comprehensive
                    - Merge all question_answer pairs, avoiding duplicates
                    - Update unanswered_questions by removing any that were answered in the new PDF
                    - Ensure citations properly reference the source PDF
                    """

                    combined_results = llm.get_response(
                        messages=[{"role": "user", "content": combine_prompt}],
                        model="gemini-2.5-pro",
                        response_format=QnAList,
                    ).model_dump_json(
                        include={"answer_template", "question_answer", "unanswered_questions"},
                        indent=2,
                    )
                else:
                    logger.warning(f"Failed to download PDF from {pdf_url}")
                    continue

            except Exception as e:
                logger.warning(f"Failed to process PDF {pdf_url}: {str(e)}")
                continue

    return combined_results
