import hashlib
import logging
import re
from pathlib import Path
from typing import Union

logger = logging.getLogger(__name__)


def calculate_file_hash(file_path: Union[str, Path]) -> str:
    """
    Calculate SHA-256 hash of a file's content.
    
    Parameters:
    ----------
    file_path : Union[str, Path]
        Path to the file to hash
        
    Returns:
    -------
    str
        Hexadecimal SHA-256 hash of the file content
    """
    if isinstance(file_path, str):
        file_path = Path(file_path)
        
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            # Read file in chunks to handle large files efficiently
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()
    except Exception as e:
        logger.error(f"Error calculating hash for {file_path}: {str(e)}")
        raise


def generate_unique_filename(original_filename: str, existing_files: list[str]) -> str:
    """
    Generate a unique filename by appending a counter if needed.
    
    Parameters:
    ----------
    original_filename : str
        The original filename
    existing_files : list[str]
        List of existing filenames to check against
        
    Returns:
    -------
    str
        A unique filename (may be the original if no conflict)
    """
    if original_filename not in existing_files:
        return original_filename
    
    # Split filename and extension
    path = Path(original_filename)
    name = path.stem
    suffix = path.suffix
    
    counter = 1
    while True:
        new_filename = f"{name}_copy_{counter}{suffix}"
        if new_filename not in existing_files:
            return new_filename
        counter += 1


def sanitise_filename(filename: str) -> str:
    """
    Sanitise filename to contain only alphanumeric characters and underscores.
    
    Parameters:
    ----------
    filename : str
        The original filename
        
    Returns:
    -------
    str
        Sanitised filename with only alphanumeric characters and underscores
    """
    if not filename:
        return "unnamed_file"
    
    # Split filename and extension
    path = Path(filename)
    name = path.stem
    suffix = path.suffix
    
    # Remove or replace invalid characters in the name
    # Keep only alphanumeric and convert spaces/special chars to underscores
    sanitised_name = re.sub(r'[^a-zA-Z0-9_]', '_', name)
    
    # Remove multiple consecutive underscores
    sanitised_name = re.sub(r'_+', '_', sanitised_name)
    
    # Remove leading/trailing underscores
    sanitised_name = sanitised_name.strip('_')
    
    # Ensure we have at least some content
    if not sanitised_name:
        sanitised_name = "unnamed_file"
    
    # Sanitise extension (remove dots and special chars, keep alphanumeric only)
    if suffix:
        sanitised_extension = re.sub(r'[^a-zA-Z0-9]', '', suffix)
        if sanitised_extension:
            return f"{sanitised_name}.{sanitised_extension}"
    
    return sanitised_name