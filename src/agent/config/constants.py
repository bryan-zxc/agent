"""Constants used throughout the agent library."""

# API Configuration
DEFAULT_TIMEOUT = 120000  # 2 minutes in milliseconds
MAX_TIMEOUT = 600000      # 10 minutes in milliseconds

# File Processing
SUPPORTED_IMAGE_FORMATS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff"}
SUPPORTED_DOCUMENT_FORMATS = {".pdf"}
SUPPORTED_DATA_FORMATS = {".csv", ".xlsx", ".json"}

# Image Processing
DEFAULT_IMAGE_QUALITY = 95
MAX_IMAGE_SIZE = (4096, 4096)  # pixels

# Logging
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
DEFAULT_LOG_LEVEL = "INFO"

# Security
MAX_CODE_EXECUTION_TIME = 30  # seconds
ALLOWED_IMPORTS = {
    "io", "base64", "json", "pandas", "numpy", "matplotlib", "PIL", 
    "Image", "statistics", "math", "datetime", "re", "string"
}

# Database
DEFAULT_DB_TIMEOUT = 30  # seconds