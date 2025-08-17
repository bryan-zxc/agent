"""
Agent Library - A comprehensive agent framework for document processing, 
image analysis, and task automation.
"""

import logging

# Configure logging for the entire package
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('agent.log'),
        logging.StreamHandler()
    ]
)

from .core.router import RouterAgent
from .models import (
    # Core models
    File,
    Task,
    # Request/Response models
    RequestResponse,
    TaskResponse,
    # Document models
    PDFContent,
    PDFMetaSummary,
    DocSearchCriteria,
    # Image models
    ImageElement,
    ImageBreakdown,
    ImageContent,
    # Data models
    TableMeta,
    ColumnMeta,
    FileGrouping,
)
from .config.settings import settings, AgentSettings
from .utils.tools import (
    encode_image,
    decode_image,
    get_text_and_table_json_from_image,
    get_chart_readings_from_image,
)
from .services.document_service import (
    extract_document_content,
    create_document_meta_summary,
)
from .services.image_service import is_image, process_image_file

__version__ = "0.1.0"
__author__ = "Agent Library Team"

# Public API
__all__ = [
    # Core classes
    "RouterAgent",
    
    # Models
    "File",
    "Task",
    "RequestResponse",
    "TaskResponse",
    "PDFContent",
    "PDFMetaSummary",
    "DocSearchCriteria",
    "ImageElement",
    "ImageBreakdown",
    "ImageContent",
    "TableMeta",
    "ColumnMeta",
    "FileGrouping",
    
    # Configuration
    "settings",
    "AgentSettings",
    
    # Utilities
    "encode_image",
    "decode_image",
    "get_text_and_table_json_from_image",
    "get_chart_readings_from_image",
    
    # Services
    "extract_document_content",
    "create_document_meta_summary", 
    "is_image",
    "process_image_file",
    
    # Metadata
    "__version__",
    "__author__",
]