# Services Module

External service integrations and specialized processing services.

## Modules

### `llm_service.py`
Unified interface for multiple large language model providers.

#### Classes

**`LLM`**
- Central service for all language model interactions
- Supports multiple providers: OpenAI, Anthropic Claude, Google Gemini
- **Async Architecture**: All database operations use async patterns with aiosqlite
- **Key Features:**
  - Automatic provider selection based on model name
  - Usage tracking and cost calculation with async database operations
  - Retry logic with exponential backoff
  - Structured output support with Pydantic models

**Key Methods:**
- `__init__(db_path)`: Initialize with usage tracking database
- `get_response(messages, model, temperature, response_format, tools)`: Main inference method
- `a_get_response()`: Async version of get_response
- `_calculate_cost(model, input_tokens, output_tokens)`: Cost calculation
- `_track_usage()`: Async usage logging to SQLite database

#### Database Models

**`LLMUsage(Base)`**
- SQLAlchemy model for usage tracking
- **Fields:**
  - `timestamp`: When the request was made
  - `model`: Model identifier used
  - `input_tokens/output_tokens`: Token usage
  - `cost`: Calculated cost in USD
  - `request_type`: Type of request (text, tools, structured)
  - `purpose`: Purpose category (general, agent)

#### Configuration

**`MODEL_MAPPING`**
- Maps friendly names to actual model identifiers
- Supported models:
  - `sonnet-4`: Claude Sonnet 4
  - `gpt-4.1-nano`: GPT-4.1 Nano
  - `gemini-2.5-pro`: Gemini 2.5 Pro

**`PRICING`**
- Per-1000-token pricing for input and output
- Used for cost calculation and budget tracking

#### Features

**Multi-Provider Support:**
- OpenAI client for GPT models
- Anthropic client for Claude models  
- Google client for Gemini models
- Automatic client selection based on model name

**Structured Output:**
- Pydantic model validation for structured responses
- Special handling for Anthropic models with prefill technique
- JSON object mode support

**Usage Tracking:**
- Comprehensive logging of all API calls
- Cost tracking with detailed breakdowns
- SQLite database for persistence

### `document_service.py`
PDF document processing and content extraction.

#### Functions

**`extract_images_from_page(page, page_number, min_tokens)`**
- Extracts images from PDF pages
- **Parameters:**
  - `page`: pypdf PageObject
  - `page_number`: Page identifier
  - `min_tokens`: Minimum size threshold
- **Returns:** List of ImageContent objects with metadata

**`extract_document_content(pdf_path)`**
- Complete PDF content extraction
- **Returns:** PDFContent object with pages and embedded images
- **Features:**
  - Text extraction from all pages
  - Image extraction with base64 encoding
  - Page label handling

**`create_document_meta_summary(document_content)`**
- Generate statistical metadata about PDF documents
- **Returns:** PDFMetaSummary with counts and statistics
- **Metrics:**
  - Page and image counts
  - Text length statistics (total, max, median)
  - Content distribution analysis

#### Image Processing

**Image Extraction Pipeline:**
1. **Detection**: Identify image objects in PDF pages
2. **Filtering**: Apply size thresholds to exclude small images
3. **Format Handling**: Support for various image formats (FlateDecode, JPEG, etc.)
4. **Encoding**: Convert to base64 for storage and transmission
5. **Metadata**: Capture dimensions and naming information

### `image_service.py`
Image file validation and processing.

#### Functions

**`is_image(file_path)`**
- Validate if a file is a readable image
- **Returns:** Tuple of (is_valid, error_message)
- **Uses:** PIL Image verification

**`process_image_file(filepath)`**
- Complete image file processing pipeline
- **Returns:** Tuple of (image_breakdown, error_message)
- **Features:**
  - Image validation and error handling
  - Content analysis using LLM services
  - Element categorization (charts, tables, diagrams, text)

## Usage Patterns

### LLM Service
```python
from agent.services.llm_service import LLM

llm = LLM()
response = llm.get_response(
    messages=[{"role": "user", "content": "Hello"}],
    model="gemini-2.5-pro",
    temperature=0.1
)
```

### Document Processing
```python
from agent.services.document_service import extract_document_content

content = extract_document_content("document.pdf")
for page in content.pages:
    print(f"Page {page.page_number}: {len(page.text)} characters")
```

### Image Processing
```python
from agent.services.image_service import process_image_file

breakdown, error = process_image_file("chart.png")
if breakdown:
    for element in breakdown.elements:
        print(f"Found {element.element_type}: {element.element_desc}")
```

## Integration Points

- **Agents**: All agents use LLM service for inference
- **Core**: Router uses document and image services for file processing
- **Models**: Services work with Pydantic models for type safety
- **Utils**: Image services integrate with utility functions

## Error Handling

### LLM Service
- Automatic retry with exponential backoff
- Graceful degradation for API failures
- Comprehensive error logging
- Model-specific error handling

### Document Service
- Robust image extraction with format detection
- Graceful handling of corrupted PDFs
- Error reporting with context

### Image Service
- Validation before processing
- Detailed error messages for debugging
- Fallback handling for unreadable images

## Performance Considerations

- **Caching**: LLM responses can be cached for repeated queries
- **Batch Processing**: Multiple images can be processed efficiently
- **Memory Management**: Large documents are processed in chunks
- **Cost Optimization**: Usage tracking helps optimize model selection