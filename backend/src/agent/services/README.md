# Services Module

External service integrations and specialized processing services.

## Modules

### `llm_service.py`
Unified interface for multiple large language model providers.

#### Architecture

**Modular Provider Design**
- **Provider Abstraction**: All providers implement `BaseLLMProvider` interface (backend/src/agent/services/llm/base.py:37)
- **Native SDK Integration**: Each provider uses its official SDK for optimal performance
  - OpenAI: Official OpenAI Python SDK
  - Anthropic: Official Anthropic Python SDK  
  - Google: Google Generative AI SDK
- **Unified Interface**: `LLM` class provides consistent API across all providers
- **Provider Selection**: Automatic routing based on model name

#### Classes

**`LLM`**
- Central service orchestrating multiple LLM providers
- **System Instructions**: Native system instruction support for all providers
  - Instructions are stored in satellite tables (RouterSystemInstructions, PlannerSystemInstructions, WorkerSystemInstructions)
  - Retrieved from database and passed via `system_instruction` parameter
  - No longer embedded in message chains for better separation of concerns
- **MCP Integration**: Full Model Context Protocol support for external tools
- **Key Features:**
  - Provider-based architecture with clean separation
  - Normalised tool calling format across all providers
  - Usage tracking consolidated in main agent database
  - Fire-and-forget async cost tracking
  - WebSocket support for real-time tool execution updates

**Key Methods:**
- `__init__(db_path, caller, mcp_manager)`: Initialise with usage tracking and optional MCP
- `get_response(messages, model, temperature, response_format, system_instruction)`: Sync inference (text/structured only, no tools)
- `a_get_response(messages, model, temperature, response_format, system_instruction, use_tools, enable_web_search, tool_filter, websocket)`: Async with full tool support
  - **Parameters:**
    - `system_instruction`: Optional system instruction for the model
    - `use_tools`: Master switch for MCP tools (default: False)
    - `enable_web_search`: Enable provider-native web search
    - `tool_filter`: Optional function to filter MCP tools by server/name
    - `websocket`: Optional WebSocket for real-time status updates
- `_get_response_with_tools()`: Execute tools and return formatted response

**Deprecated Methods (Backwards Compatibility):**
- `search_web(query, temperature)`: Web search using Google's grounding
  - **Deprecated**: Implementation moved to `GoogleProvider.search_web()`
  - Maintained as thin wrapper for backwards compatibility with existing tools
- `get_response_pdf(pdf_source, prompt, temperature, response_format)`: PDF processing with Gemini
  - **Deprecated**: Implementation moved to `GoogleProvider.process_pdf()`
  - Maintained as thin wrapper for backwards compatibility with existing tools

#### Database Models

**`LLMUsage(Base)`**
- SQLAlchemy model for usage tracking (migrated to backend/src/agent/models/agent_database.py:373)
- **Fields:**
  - `timestamp`: When the request was made
  - `model`: Model identifier used
  - `input_tokens/output_tokens`: Token usage
  - `cost`: Calculated cost in USD
  - `request_type`: Type of request (text, tools, structured)
  - `purpose`: Purpose category (general, agent)

#### Provider Implementations

**`OpenAIProvider`** (backend/src/agent/services/llm/providers.py:152)
- Native OpenAI SDK integration
- Supports GPT models with function calling
- Structured output via response_format parameter
- Tool calls normalised to standard format

**`AnthropicProvider`** (backend/src/agent/services/llm/providers.py:406)
- Native Anthropic SDK integration  
- Supports Claude models with tool use
- System instructions via native system parameter
- Web search through native integration
- Tool calls normalised to standard format

**`GoogleProvider`** (backend/src/agent/services/llm/providers.py:847)
- Native Google Generative AI SDK integration
- Supports Gemini models with function calling
- System instructions via systemInstruction parameter
- Native grounding for web search (cannot mix with tools)
- PDF processing support
- Tool calls normalised to standard format

#### Configuration

**`MODEL_MAPPING`** (backend/src/agent/config/llm_config.py)
- Maps friendly names to actual model identifiers
- Supported models:
  - `sonnet-4`: Claude Sonnet 4
  - `gpt-5-nano`: GPT-5 Nano
  - `gemini-2.5-pro`: Gemini 2.5 Pro

**`PRICING`** (backend/src/agent/config/llm_config.py)
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


## MCP (Model Context Protocol) Integration

### Overview
The LLM service integrates with Model Context Protocol (MCP) to enable agents to use external tools from any MCP-compatible server. This allows seamless integration with third-party services and custom tool servers.

### Architecture
- **MCP Client Manager**: Singleton manager (backend/src/agent/core/mcp_client.py:20) handles all MCP connections
- **Tool Discovery**: Automatic discovery of available tools from connected MCP servers
- **Tool Execution**: Unified execution interface regardless of server type (stdio, HTTP, WebSocket)
- **Provider Integration**: All LLM providers support MCP tools through normalised interface

### Key Features
- **External Tool Servers**: Connect to any MCP-compatible server (GitHub, filesystem, custom)
- **Transport Support**: Multiple transport types - stdio (Node.js), HTTP, WebSocket
- **Tool Filtering**: Filter MCP tools by server or custom criteria
- **WebSocket Updates**: Real-time tool execution status via WebSocket
- **Unified Format**: MCP tools presented in standard OpenAI function calling format

### MCP Tool Usage
```python
from agent.services.llm_service import LLM
from agent.core.mcp_client import get_mcp_manager

# Initialise with MCP support
mcp_manager = await get_mcp_manager()
llm = LLM(caller="my_agent", mcp_manager=mcp_manager)

# Enable MCP tools and optionally web search
response = await llm.a_get_response(
    messages=[{"role": "user", "content": "Get issue #40 from bryan-zxc/agent"}],
    model="gpt-5-nano",
    temperature=0,
    system_instruction="You are a helpful assistant",
    use_tools=True,  # Enable MCP tools
    enable_web_search=False,  # Provider-native web search
    websocket=websocket  # Optional: real-time updates
)
```

### Tool Filtering
```python
# Only use GitHub tools
def github_only(server_name, tool):
    return server_name == "github"

response = await llm.a_get_response(
    messages=messages,
    model="gpt-4.1-nano",
    tool_filter=github_only
)
```

### Combining Regular and MCP Tools
```python
# Define regular tools
regular_tools = [{
    "type": "function",
    "function": {
        "name": "calculate",
        "description": "Perform calculations",
        "parameters": {...}
    }
}]

# Both regular and MCP tools will be available
response = await llm.a_get_response(
    messages=messages,
    model="gpt-4.1-nano",
    tools=regular_tools  # MCP tools are added automatically
)
```

## Usage Patterns

### LLM Service (Basic)
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
from agent.utils.image_utils import is_image, get_img_breakdown, encode_image

# Validate and process image
if is_image("chart.png")[0]:
    breakdown = get_img_breakdown(encode_image("chart.png"))
    if not breakdown.unreadable:
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