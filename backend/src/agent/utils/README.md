# Utils Module

Utility functions and tools for image processing, code execution, and data manipulation.

## Modules

### `tools.py`
Comprehensive toolkit for image processing, chart reading, and document analysis.

#### Core Utility Functions

**`encode_image(image)`**
- Convert images to base64 encoded strings
- **Parameters:** Image path, Path object, or PIL Image
- **Returns:** Base64 encoded string
- **Usage:** Preparing images for LLM API calls

**`decode_image(image_base64)`**
- Convert base64 strings back to PIL Image objects
- **Parameters:** Base64 encoded image string
- **Returns:** PIL Image object
- **Usage:** Processing images received from APIs

**`is_serialisable(obj)`**
- Check if an object can be JSON serialized
- **Returns:** Tuple of (serializable, stringable) booleans
- **Usage:** Validating data before storage or transmission

#### Image Processing Functions

**`draw_gridlines(img, line_orientation)`**
- Add gridlines to images for coordinate reference
- **Parameters:**
  - `img`: PIL Image object
  - `line_orientation`: "horizontal" or "vertical"
- **Returns:** Tuple of (gridded_image, grid_coordinates)
- **Features:**
  - 10x10 grid with letter annotations (A-J)
  - Text placement with font handling
  - Coordinate mapping for selective processing

**`apply_selective_blur(img, grid_coordinates)`**
- Apply Gaussian blur to specific image regions
- **Parameters:**
  - `img`: PIL Image object
  - `grid_coordinates`: Region boundaries
- **Returns:** Tuple of (blurred_image, cropped_region)
- **Usage:** Highlighting specific areas in images

**`combine_image_slices(slices, combine_orientation)`**
- Merge multiple image slices into a single image
- **Parameters:**
  - `slices`: List of PIL Image objects
  - `combine_orientation`: "horizontal" or "vertical"
- **Returns:** Merged PIL Image
- **Features:**
  - Automatic dimension calculation
  - Proper alignment and positioning

#### Advanced Image Analysis

**`identify_relevant_slices(original_image, slices, vertical_or_horizontal, messages)`**
- Intelligent slice selection for chart analysis
- **Complex Pipeline:**
  1. Analyze original image to determine relevance criteria
  2. Process each slice to identify chart elements
  3. Filter slices based on relevance scoring
  4. Merge relevant slices for final analysis
  5. Generate comprehensive response

**`get_text_and_table_json_from_image(image)`**
- Extract structured text and table data from images
- **Process:**
  1. Slice large images to overcome context limits
  2. Extract markdown content from each slice
  3. Cross-validate with full image analysis
  4. Generate consolidated JSON output
- **Returns:** JSON string with structured table data

**`get_chart_readings_from_image(image)`**
- Extract numerical data and facts from charts
- **Returns:** JSON string with question-answer pairs
- **Features:**
  - Automatic chart type detection
  - Data point extraction
  - Structured fact representation

#### Document Processing Functions

**`get_doc_json(document_content, include_image)`**
- Convert document content to JSON format
- **Options:** Include or exclude embedded images
- **Returns:** JSON string representation

**`get_images_from_doc(doc)`**
- Extract all images from document pages
- **Returns:** List of (page_number, image_data) tuples

**`get_img_breakdown(base64_image)`**
- Analyze image content and categorize elements
- **Returns:** ImageBreakdown object with element analysis

**`search_doc(question, criteria, doc)`**
- Intelligent document search with image analysis
- **Advanced Features:**
  - Page range filtering
  - Multi-modal content search
  - Automatic image analysis integration
  - Structured Q&A extraction

### `file_utils.py`
File management utilities for content hashing and unique filename generation.

#### File Hash Functions

**`calculate_file_hash(file_path)`**
- Calculate SHA-256 hash of file content for duplicate detection
- **Parameters:** File path (str or Path object)
- **Returns:** Hexadecimal SHA-256 hash string
- **Features:**
  - Efficient chunk-based processing for large files (4KB chunks)
  - Path object compatibility
  - Comprehensive error handling and logging
- **Usage:** Content-based duplicate detection in file uploads

**`generate_unique_filename(original_filename, existing_files)`**
- Generate unique filename by appending counter for conflict resolution
- **Parameters:**
  - `original_filename`: The original filename to make unique
  - `existing_files`: List of existing filenames to check against
- **Returns:** Unique filename (original if no conflict exists)
- **Features:**
  - Preserves file extension correctly
  - Incremental naming pattern: `filename_copy_1.ext`, `filename_copy_2.ext`
  - Path-safe filename handling
- **Usage:** Automatic filename conflict resolution in file storage

### `sandbox.py`
Safe code execution environment for Python code.

#### Classes

**`CodeSandbox`**
- Isolated Python code execution environment
- **Features:**
  - Controlled global and local namespaces
  - stdout capture for output collection
  - Exception handling with stack traces
  - Variable state preservation

**Key Methods:**
- `__init__(globals_dict, locals_dict)`: Initialize sandbox environment
- `execute(code_string)`: Execute Python code safely
  - **Returns:** Dictionary with success status, output, and variables
  - **Error Handling:** Comprehensive exception capture
  - **Output Capture:** Redirects stdout for clean output collection

#### Security Features

**Namespace Control:**
- Restricted global namespace
- Controlled builtin access
- Variable isolation between executions

**Output Management:**
- Clean stdout capture
- Proper stream restoration
- Detailed error reporting

## Usage Patterns

### File Management
```python
from agent.utils.file_utils import calculate_file_hash, generate_unique_filename

# Calculate content hash for duplicate detection
file_hash = calculate_file_hash("uploaded_file.pdf")

# Generate unique filename if conflicts exist
existing_files = ["report.pdf", "report_copy_1.pdf"]
unique_name = generate_unique_filename("report.pdf", existing_files)  # "report_copy_2.pdf"
```

### Image Processing
```python
from agent.utils.tools import encode_image, get_chart_readings_from_image

# Encode image for API
encoded = encode_image("chart.png")

# Extract chart data
chart_data = get_chart_readings_from_image(encoded)
```

### Code Execution
```python
from agent.utils.sandbox import CodeSandbox

sandbox = CodeSandbox(locals_dict={"data": [1, 2, 3]})
result = sandbox.execute("result = sum(data)")

if result["success"]:
    print(result["variables"]["result"])  # 6
```

### Document Search
```python
from agent.utils.tools import search_doc
from agent.models.schemas import DocSearchCriteria

criteria = DocSearchCriteria(filename="report.pdf", page_start="5", page_end="10")
results = search_doc("What are the sales figures?", criteria, document)
```

## Advanced Features

### Intelligent Image Slicing
- Automatic slice size optimization
- Overlap management for context preservation
- Relevance-based filtering
- Multi-stage analysis pipeline

### Chart Analysis Pipeline
1. **Element Detection**: Identify charts, axes, and data points
2. **Slice Selection**: Choose relevant image regions
3. **Data Extraction**: Read numerical values and labels
4. **Validation**: Cross-check extracted data
5. **Response Generation**: Create structured output

### Document Intelligence
- Multi-modal content analysis
- Automatic image type detection
- Context-aware search
- Structured information extraction

## Integration Points

- **LLM Services**: All image analysis functions use the unified LLM interface
- **Models**: Functions work with Pydantic models for type safety
- **Agents**: Worker agents use sandbox for safe code execution
- **Security**: Sandbox provides isolation for untrusted code

## Performance Optimizations

- **Lazy Loading**: Images processed only when needed
- **Caching**: Results cached for repeated operations
- **Batch Processing**: Multiple operations combined for efficiency
- **Memory Management**: Large images processed in chunks

## Error Handling

- **Graceful Degradation**: Fallback strategies for failed operations
- **Detailed Logging**: Comprehensive error reporting
- **Recovery Mechanisms**: Automatic retry for transient failures
- **User Feedback**: Clear error messages for debugging