"""
File management system for planner variables and images.

This module handles storing and retrieving planner state (variables, images)
from the filesystem using file paths stored in the database with lazy loading.
"""

import pickle
import secrets
import json
from pathlib import Path
from typing import Dict, Any, Optional
import logging
from ..config.settings import settings
from ..models.agent_database import AgentDatabase
from ..models import ExecutionPlanModel, Task, TaskResponseModel

logger = logging.getLogger(__name__)


def get_planner_path(planner_id: str) -> Path:
    """Get the base directory path for a planner's files"""
    return Path(settings.collaterals_base_path) / planner_id


def generate_variable_path(planner_id: str, variable_key: str, check_existing: bool = False) -> tuple[str, str]:
    """Generate a file path for a new variable, optionally avoiding collisions
    
    Args:
        planner_id: The planner ID
        variable_key: The original variable key name
        check_existing: If True, check for existing files and append hex suffix if needed
        
    Returns:
        tuple: (file_path, final_variable_key)
    """
    final_variable_key = variable_key
    
    if check_existing:
        base_path = get_planner_path(planner_id) / "variables"
        
        # Check if original path exists
        original_path = base_path / f"{variable_key}.pkl"
        if original_path.exists():
            # Generate unique suffix until we find an available name
            while True:
                hex_suffix = secrets.token_hex(3)[:3]  # 3-char hex
                final_variable_key = f"{variable_key}_{hex_suffix}"
                new_path = base_path / f"{final_variable_key}.pkl"
                if not new_path.exists():
                    break
    
    file_path = get_planner_path(planner_id) / "variables" / f"{final_variable_key}.pkl"
    return str(file_path), final_variable_key


def generate_image_path(planner_id: str, image_key: str, check_existing: bool = False) -> tuple[str, str]:
    """Generate a file path for a new image, optionally avoiding collisions
    
    Args:
        planner_id: The planner ID
        image_key: The original image key name
        check_existing: If True, check for existing files and append hex suffix if needed
        
    Returns:
        tuple: (file_path, final_image_key)
    """
    final_image_key = image_key
    
    if check_existing:
        base_path = get_planner_path(planner_id) / "images"
        
        # Check if original path exists
        original_path = base_path / f"{image_key}.b64"
        if original_path.exists():
            # Generate unique suffix until we find an available name
            while True:
                hex_suffix = secrets.token_hex(3)[:3]  # 3-char hex
                final_image_key = f"{image_key}_{hex_suffix}"
                new_path = base_path / f"{final_image_key}.b64"
                if not new_path.exists():
                    break
    
    file_path = get_planner_path(planner_id) / "images" / f"{final_image_key}.b64"
    return str(file_path), final_image_key


def save_variable_to_file(file_path: str, value: Any) -> bool:
    """Save a variable to the specified file path using pickle"""
    try:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, 'wb') as f:
            pickle.dump(value, f)
        
        logger.info(f"Saved variable to {file_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to save variable to {file_path}: {e}")
        return False


def load_variable_from_file(file_path: str) -> Any:
    """Load a variable from the specified file path using pickle"""
    try:
        path = Path(file_path)
        
        if not path.exists():
            logger.warning(f"Variable file not found: {file_path}")
            return None
        
        with open(path, 'rb') as f:
            value = pickle.load(f)
        
        logger.debug(f"Loaded variable from {file_path}")
        return value
    except Exception as e:
        logger.error(f"Failed to load variable from {file_path}: {e}")
        return None


def save_image_to_file(file_path: str, encoded_image: str) -> bool:
    """Save an encoded image to the specified file path"""
    try:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, 'w', encoding='utf-8') as f:
            f.write(encoded_image)
        
        logger.info(f"Saved image to {file_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to save image to {file_path}: {e}")
        return False


def load_image_from_file(file_path: str) -> Optional[str]:
    """Load an encoded image from the specified file path"""
    try:
        path = Path(file_path)
        
        if not path.exists():
            logger.warning(f"Image file not found: {file_path}")
            return None
        
        with open(path, 'r', encoding='utf-8') as f:
            encoded_image = f.read()
        
        logger.debug(f"Loaded image from {file_path}")
        return encoded_image
    except Exception as e:
        logger.error(f"Failed to load image from {file_path}: {e}")
        return None


def save_planner_variable(planner_id: str, key: str, value: Any, check_existing: bool = False) -> tuple[str, str]:
    """Save a variable and update database with file path
    
    Args:
        planner_id: The planner ID
        key: The variable key name
        value: The variable value to save
        check_existing: If True, avoid overwriting existing files
        
    Returns:
        tuple: (file_path, final_key_used)
    """
    file_path, final_key = generate_variable_path(planner_id, key, check_existing)
    
    if save_variable_to_file(file_path, value):
        # Update database with file path using the final key
        db = AgentDatabase()
        planner = db.get_planner(planner_id)
        if planner:
            variable_paths = planner.get("variable_file_paths", {})
            variable_paths[final_key] = file_path
            db.update_planner_file_paths(planner_id, variable_paths=variable_paths)
        
        return file_path, final_key
    else:
        raise Exception(f"Failed to save variable '{final_key}' for planner {planner_id}")


def clean_image_name(raw_name: str, existing_names: set) -> str:
    """
    Clean and validate image name with comprehensive rules:
    - Only alphanumeric and underscores
    - No repeated underscores
    - No leading/trailing underscores
    - Fallback if empty after cleaning
    - Handle duplicates with counter
    """
    import re
    
    if not raw_name:
        raw_name = "image"
    
    # Remove all non-alphanumeric characters except underscores
    cleaned = re.sub(r'[^a-zA-Z0-9_]', '_', raw_name)
    
    # Remove repeated underscores
    cleaned = re.sub(r'_+', '_', cleaned)
    
    # Remove leading and trailing underscores
    cleaned = cleaned.strip('_')
    
    # Fallback if empty after cleaning
    if not cleaned:
        cleaned = "image"
    
    # Handle duplicates with counter
    original_cleaned = cleaned
    counter = 1
    while cleaned in existing_names:
        cleaned = f"{original_cleaned}_{counter}"
        counter += 1
    
    return cleaned


def save_planner_image(planner_id: str, raw_image_name: str, encoded_image: str, check_existing: bool = False) -> tuple[str, str]:
    """
    Save an image with cleaned name and update database with file path.
    
    Args:
        planner_id: The planner ID
        raw_image_name: Raw image name (usually filename without extension)
        encoded_image: Base64 encoded image data
        check_existing: If True, avoid overwriting existing files using hex suffix
        
    Returns:
        tuple: (file_path, final_image_name_used)
    """
    # Get current image names from database to avoid duplicates
    db = AgentDatabase()
    planner = db.get_planner(planner_id)
    existing_image_paths = planner.get("image_file_paths", {}) if planner else {}
    existing_names = set(existing_image_paths.keys())
    
    # Clean the image name first
    cleaned_image_name = clean_image_name(raw_image_name, existing_names)
    
    # Generate file path with collision avoidance if requested
    file_path, final_image_name = generate_image_path(planner_id, cleaned_image_name, check_existing)
    
    if save_image_to_file(file_path, encoded_image):
        # Update database with file path using final name
        if planner:
            image_paths = existing_image_paths.copy()
            image_paths[final_image_name] = file_path
            db.update_planner_file_paths(planner_id, image_paths=image_paths)
        
        return file_path, final_image_name
    else:
        raise Exception(f"Failed to save image '{final_image_name}' for planner {planner_id}")


def get_planner_variable(planner_id: str, key: str) -> Any:
    """Lazy load a specific variable for a planner"""
    db = AgentDatabase()
    planner = db.get_planner(planner_id)
    
    if not planner:
        logger.warning(f"Planner {planner_id} not found")
        return None
    
    variable_paths = planner.get("variable_file_paths", {})
    
    if key not in variable_paths:
        logger.warning(f"Variable '{key}' not found for planner {planner_id}")
        return None
    
    return load_variable_from_file(variable_paths[key])


def get_planner_image(planner_id: str, key: str) -> Optional[str]:
    """Lazy load a specific image for a planner"""
    db = AgentDatabase()
    planner = db.get_planner(planner_id)
    
    if not planner:
        logger.warning(f"Planner {planner_id} not found")
        return None
    
    image_paths = planner.get("image_file_paths", {})
    
    if key not in image_paths:
        logger.warning(f"Image '{key}' not found for planner {planner_id}")
        return None
    
    return load_image_from_file(image_paths[key])


def get_planner_variable_keys(planner_id: str) -> list[str]:
    """Get list of available variable keys for a planner"""
    db = AgentDatabase()
    planner = db.get_planner(planner_id)
    
    if not planner:
        return []
    
    variable_paths = planner.get("variable_file_paths", {})
    return list(variable_paths.keys())


def get_planner_image_keys(planner_id: str) -> list[str]:
    """Get list of available image keys for a planner"""
    db = AgentDatabase()
    planner = db.get_planner(planner_id)
    
    if not planner:
        return []
    
    image_paths = planner.get("image_file_paths", {})
    return list(image_paths.keys())


def get_planner_variables(planner_id: str) -> Dict[str, Any]:
    """Load all variables for a planner"""
    db = AgentDatabase()
    planner = db.get_planner(planner_id)
    
    if not planner:
        logger.warning(f"Planner {planner_id} not found")
        return {}
    
    variable_paths = planner.get("variable_file_paths", {})
    variables = {}
    
    for key, file_path in variable_paths.items():
        variable = load_variable_from_file(file_path)
        if variable is not None:
            variables[key] = variable
        else:
            logger.warning(f"Failed to load variable '{key}' from {file_path}")
    
    return variables


def get_planner_images(planner_id: str) -> Dict[str, str]:
    """Load all images for a planner"""
    db = AgentDatabase()
    planner = db.get_planner(planner_id)
    
    if not planner:
        logger.warning(f"Planner {planner_id} not found")
        return {}
    
    image_paths = planner.get("image_file_paths", {})
    images = {}
    
    for key, file_path in image_paths.items():
        image = load_image_from_file(file_path)
        if image is not None:
            images[key] = image
        else:
            logger.warning(f"Failed to load image '{key}' from {file_path}")
    
    return images


def cleanup_planner_files(planner_id: str) -> bool:
    """Clean up all files for a completed planner"""
    planner_dir = get_planner_path(planner_id)
    
    if not planner_dir.exists():
        return True
    
    try:
        import shutil
        shutil.rmtree(planner_dir)
        logger.info(f"Cleaned up files for planner {planner_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to cleanup files for planner {planner_id}: {e}")
        return False


def save_execution_plan_model(planner_id: str, execution_plan_model: ExecutionPlanModel) -> bool:
    """Save execution plan model to dedicated JSON file using Pydantic native methods"""
    try:
        planner_dir = get_planner_path(planner_id)
        planner_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = planner_dir / settings.execution_plan_model_filename
        
        # Use Pydantic's model_dump_json for serialisation
        json_str = execution_plan_model.model_dump_json(indent=2)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(json_str)
        
        logger.info(f"Saved execution plan model to {file_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to save execution plan model for planner {planner_id}: {e}")
        return False


def load_execution_plan_model(planner_id: str) -> Optional[ExecutionPlanModel]:
    """Load execution plan model from dedicated JSON file using Pydantic native methods"""
    try:
        planner_dir = get_planner_path(planner_id)
        file_path = planner_dir / settings.execution_plan_model_filename
        
        if not file_path.exists():
            logger.warning(f"Execution plan model file not found: {file_path}")
            return None
        
        with open(file_path, 'r', encoding='utf-8') as f:
            json_str = f.read()
        
        # Use Pydantic's model_validate_json for deserialisation
        execution_plan_model = ExecutionPlanModel.model_validate_json(json_str)
        
        logger.debug(f"Loaded execution plan model from {file_path}")
        return execution_plan_model
    except Exception as e:
        logger.error(f"Failed to load execution plan model for planner {planner_id}: {e}")
        return None


def save_current_task(planner_id: str, task: Task) -> bool:
    """Save current task to dedicated JSON file using Pydantic native methods"""
    try:
        planner_dir = get_planner_path(planner_id)
        planner_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = planner_dir / settings.current_task_filename
        
        # Use Pydantic's model_dump_json for serialisation
        json_str = task.model_dump_json(indent=2)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(json_str)
        
        logger.info(f"Saved current task to {file_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to save current task for planner {planner_id}: {e}")
        return False


def load_current_task(planner_id: str) -> Optional[Task]:
    """Load current task from dedicated JSON file using Pydantic native methods"""
    try:
        planner_dir = get_planner_path(planner_id)
        file_path = planner_dir / settings.current_task_filename
        
        if not file_path.exists():
            logger.warning(f"Current task file not found: {file_path}")
            return None
        
        with open(file_path, 'r', encoding='utf-8') as f:
            json_str = f.read()
        
        # Use Pydantic's model_validate_json for deserialisation
        task = Task.model_validate_json(json_str)
        
        logger.debug(f"Loaded current task from {file_path}")
        return task
    except Exception as e:
        logger.error(f"Failed to load current task for planner {planner_id}: {e}")
        return None


def save_worker_message_history(planner_id: str, task_responses: list[TaskResponseModel]) -> bool:
    """Save worker message history to dedicated JSON file"""
    try:
        planner_dir = get_planner_path(planner_id)
        planner_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = planner_dir / settings.worker_message_history_filename
        
        # Convert list of TaskResponseModel to JSON-serialisable format
        json_data = [task_response.model_dump() for task_response in task_responses]
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved worker message history to {file_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to save worker message history for planner {planner_id}: {e}")
        return False


def load_worker_message_history(planner_id: str) -> list[TaskResponseModel]:
    """Load worker message history from dedicated JSON file"""
    try:
        planner_dir = get_planner_path(planner_id)
        file_path = planner_dir / settings.worker_message_history_filename
        
        if not file_path.exists():
            logger.debug(f"Worker message history file not found: {file_path}, returning empty list")
            return []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        
        # Convert JSON data to list of TaskResponseModel
        task_responses = [TaskResponseModel.model_validate(item) for item in json_data]
        
        logger.debug(f"Loaded {len(task_responses)} task responses from {file_path}")
        return task_responses
    except Exception as e:
        logger.error(f"Failed to load worker message history for planner {planner_id}: {e}")
        return []


def append_to_worker_message_history(planner_id: str, task_response: TaskResponseModel) -> bool:
    """Append a single task response to the worker message history"""
    try:
        # Load existing history
        existing_history = load_worker_message_history(planner_id)
        
        # Append new response
        existing_history.append(task_response)
        
        # Save updated history
        return save_worker_message_history(planner_id, existing_history)
    except Exception as e:
        logger.error(f"Failed to append to worker message history for planner {planner_id}: {e}")
        return False