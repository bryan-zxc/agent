import io
import base64
from pathlib import Path
from typing import Union, Tuple
from PIL import Image


def is_image(file_path: str) -> Tuple[bool, str]:
    """
    Validate if a file is a valid image.
    
    Parameters:
    ----------
    file_path : str
        Path to the file to validate
        
    Returns:
    -------
    Tuple[bool, str]
        (is_valid, error_message) - True and None if valid, False and error string if invalid
    """
    try:
        with open(file_path, "rb") as file:
            img = Image.open(file)
            img.verify()  # Verify that it is an image
        return True, None
    except Exception as e:
        return False, str(e)


def encode_image(image: Union[str, Path, Image.Image]):
    """
    Encodes an image to base64 format.

    Parameters:
    ----------
    image : Union[str, Path, Image.Image]
        The image to encode, either as a file path or PIL Image object.

    Returns:
    -------
    str
        Base64 encoded image string.
    """
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


def get_img_breakdown(base64_image: str):
    """
    Analyses an image and returns its breakdown using LLM.

    Parameters:
    ----------
    base64_image : str
        Base64 encoded image string.

    Returns:
    -------
    ImageBreakdown
        Structured breakdown of the image content.
    """
    # Import LLM here to avoid circular imports
    from ..services.llm_service import LLM
    from ..models.schemas import ImageBreakdown

    llm = LLM(caller="image_utils")
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

    image_breakdown = llm.get_response(
        messages=messages,
        model="gemini-2.5-pro",
        response_format=ImageBreakdown,
    )
    return image_breakdown
