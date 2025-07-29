# Models Module

Pydantic data models and schemas that define the structure of data throughout the agent system, including database models for conversation persistence.

## Modules

### `message_db.py`
Database models and service for agent message persistence.

#### Database Models

**`Conversation`**
- Represents a chat conversation with a user
- **Fields:**
  - `id`: Unique conversation identifier (UUID hex string)
  - `created_at`: Conversation creation timestamp
  - `updated_at`: Last message timestamp

**`PlannerMessage`**
- Messages from PlannerAgent instances
- **Fields:**
  - `id`: Auto-incrementing primary key
  - `agent_id`: UUID hex string (planner instance ID)
  - `role`: Message role (user, assistant, system, developer)
  - `content`: JSON content (supports multimodal messages)
  - `created_at`: Message timestamp

**`WorkerMessage`**
- Messages from WorkerAgent instances
- **Fields:**
  - `id`: Auto-incrementing primary key
  - `agent_id`: UUID hex string (task ID)
  - `role`: Message role (user, assistant, system, developer)
  - `content`: JSON content (supports multimodal messages)
  - `created_at`: Message timestamp

**`RouterMessage`**
- Messages from RouterAgent conversations
- **Fields:**
  - `id`: Auto-incrementing primary key
  - `conversation_id`: Foreign key to Conversation table
  - `role`: Message role (user, assistant)
  - `content`: Text content of the message
  - `created_at`: Message timestamp

#### Service Class

**`MessageDatabase`**
- Unified database service for all agent types
- **Methods:**
  - `add_message(agent_type, agent_id, role, content)`: Store message
  - `get_messages(agent_type, agent_id)`: Retrieve conversation history
  - `clear_messages(agent_type, agent_id)`: Clear conversation history
- **Database**: SQLite with automatic table creation
- **Thread Safety**: Session-per-operation pattern

## Modules

### `responses.py`
Models for API responses and request validation.

#### Classes

**`RequestValidation`**
- Validates whether user requests have been completely fulfilled
- **Fields:**
  - `user_request_fulfilled`: Boolean indicating completion status
  - `progress_summary`: Summary of completed tasks and next steps

**`TaskResponse`**
- Represents the outcome of a completed task
- **Fields:**
  - `task_id`: Unique identifier for the task
  - `task_title`: Human-readable task title
  - `task_description`: Non-technical description of task
  - `task_outcome`: Description of results/output

**`RequestResponse`**
- Final response structure combining task workings and answer
- **Fields:**
  - `workings`: List of TaskResponse objects showing task execution
  - `markdown_response`: Final formatted response to user

### `schemas.py`
Core data schemas for files, images, documents, and system entities.

#### Image and Document Models

**`ImageElement`**
- Describes individual elements within images
- **Fields:**
  - `element_desc`: Description of the image element
  - `element_location`: Position within the image
  - `element_type`: Type (chart, table, diagram, text, other)
  - `required`: Whether element is needed to address user question

**`ImageBreakdown`**
- Complete analysis of image content
- **Fields:**
  - `unreadable`: Boolean indicating if image can be processed
  - `image_quality`: Quality assessment or error description
  - `elements`: List of ImageElement objects

**`ImageContent`**
- Raw image data and metadata
- **Fields:**
  - `image_name`: Identifier for the image
  - `image_width/height`: Dimensions in pixels
  - `image_data`: Base64 encoded image data

**`PageContent`**
- Represents a single page in a document
- **Fields:**
  - `page_number`: Page identifier
  - `text`: Extracted text content
  - `images`: List of embedded images

**`PDFContent`**
- Complete PDF document structure
- **Fields:**
  - `pages`: List of PageContent objects

**`PDFMetaSummary`**
- Statistical metadata about PDF documents
- **Fields:**
  - `num_pages`: Total page count
  - `num_images`: Total embedded images
  - `total_text_length`: Combined character count
  - `max_page_text_length`: Longest page character count
  - `median_page_text_length`: Median page length

#### File and Data Models

**`File`**
- Unified file representation for all supported types
- **Fields:**
  - `filepath`: Path to the file
  - `file_type`: Type (image, data, document)
  - `image_context`: ImageElement list for images
  - `data_context`: Data type (csv, excel, other)
  - `document_context`: PDFFull object for documents

**`ColumnMeta`**
- Database column metadata and statistics
- **Fields:**
  - `column_name`: Name of the column
  - `pct_distinct`: Percentage of unique values
  - `min_value/max_value`: Range boundaries
  - `top_3_values`: Most frequent values with counts

**`TableMeta`**
- Database table metadata and sample data
- **Fields:**
  - `table_name`: Name of the table
  - `row_count`: Total number of rows
  - `top_10_md`: First 10 rows as markdown
  - `colums`: List of ColumnMeta objects

#### Utility Models

**`Variable`**
- Represents variables in task execution
- **Fields:**
  - `name`: Variable identifier
  - `is_image`: Boolean indicating if variable contains image data

**`SinglevsMultiRequest`**
- Determines processing strategy for multiple files
- **Fields:**
  - `request_type`: "single" for combined processing, "multiple" for per-file

### `tasks.py`
Task definition and execution models.

#### Core Task Models

**`TaskContext`**
- Contextual information for task execution
- **Fields:**
  - `user_request`: Original user question/request
  - `context`: Relevant background information
  - `previous_outputs`: Results from prior tasks

**`Task`**
- Basic task definition and requirements
- **Fields:**
  - `task_context`: TaskContext object
  - `task_description`: Detailed action description
  - `acceptance_criteria`: Success criteria list
  - `querying_data_file`: Boolean for data file operations
  - `image_keys`: List of relevant image identifiers
  - `variable_keys`: List of relevant variable identifiers
  - `tools`: List of required tools

**`FullTask(Task)`**
- Extended task with execution state and results
- **Additional Fields:**
  - `task_id`: Unique identifier
  - `task_status`: Execution status (new, completed, failed, recorded)
  - `task_result`: Execution outcome
  - `input_images/variables`: Input data
  - `output_images/variables`: Output data
  - `tables`: Database table metadata

#### Execution Models

**`TaskArtefact`**
- Output from task execution attempts
- **Fields:**
  - `summary_of_previous_failures`: Previous error analysis
  - `thought`: Step-by-step execution planning
  - `result`: Non-code task completion description
  - `python_code`: Executable code for task completion
  - `output_variables`: List of expected outputs
  - `is_malicious`: Security validation flag

**`TaskArtefactSQL`**
- SQL-specific task execution output
- **Fields:**
  - `summary_of_previous_failures`: Previous error analysis
  - `thought`: SQL query planning
  - `sql_code`: Executable DuckDB query
  - `reason_code_not_created`: Explanation if query cannot be generated

**`TaskValidation`**
- Validation of task completion against criteria
- **Fields:**
  - `most_recent_failure`: Latest error description
  - `second_most_recent_failure`: Previous error
  - `third_most_recent_failure`: Earlier error
  - `three_identical_failures`: Boolean for repeated failure detection
  - `task_completed`: Boolean completion status
  - `validated_result`: TaskResult if successful
  - `failed_criteria`: Description of unmet criteria

#### Constants

**`TOOLS`**
- Dictionary mapping tool names to function implementations
- Available tools: chart reading, table extraction

**`tools_type`**
- Type hint for valid tool names

## Usage Patterns

### Database Operations
```python
from agent.models.message_db import MessageDatabase

db = MessageDatabase()

# Store conversation message
db.add_message("router", "conversation-123", "user", "Hello!")
db.add_message("router", "conversation-123", "assistant", "Hi there!")

# Retrieve conversation
messages = db.get_messages("router", "conversation-123")
```

### File Processing
```python
from agent.models.schemas import File, ImageElement

file = File(
    filepath="chart.png",
    file_type="image",
    image_context=[
        ImageElement(
            element_desc="Sales chart",
            element_type="chart",
            required=True
        )
    ]
)
```

### Task Creation
```python
from agent.models.tasks import Task, TaskContext

task = Task(
    task_context=TaskContext(
        user_request="Analyze sales data",
        context="CSV file with monthly sales",
        previous_outputs=""
    ),
    task_description="Generate summary statistics",
    acceptance_criteria=["Mean and median calculated", "Results formatted"],
    querying_data_file=True
)
```

### Response Formatting
```python
from agent.models.responses import RequestResponse, TaskResponse

response = RequestResponse(
    workings=[
        TaskResponse(
            task_id="123",
            task_title="Data Analysis",
            task_description="Analyzed sales data",
            task_outcome="Generated summary statistics"
        )
    ],
    markdown_response="## Analysis Results\n\nMean sales: $50,000"
)
```

## Validation Features

- **Pydantic Validation**: Automatic type checking and data validation
- **Database Constraints**: Foreign keys and proper relationships
- **Field Descriptions**: Comprehensive documentation for LLM interaction
- **Type Safety**: Strong typing with Literal types for enums
- **Nested Models**: Complex hierarchical data structures
- **Optional Fields**: Flexible schemas with sensible defaults
- **SQLAlchemy Integration**: ORM-based database operations with automatic table creation