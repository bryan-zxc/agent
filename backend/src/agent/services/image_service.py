from pathlib import Path
from PIL import Image
from ..utils.tools import encode_image, get_img_breakdown


def is_image(file_path: str) -> tuple[bool, str]:
    try:
        with open(file_path, "rb") as file:
            img = Image.open(file)
            img.verify()  # Verify that it is an image
        return True, None
    except Exception as e:
        return False, str(e)


def process_image_file(filepath: str):
    """Process an image file and return image breakdown."""
    image_breakdown = get_img_breakdown(base64_image=encode_image(filepath))
    if image_breakdown.unreadable:
        return None, f"The image {filepath} cannot be read.\n\n{image_breakdown.image_quality}"
    
    return image_breakdown, None