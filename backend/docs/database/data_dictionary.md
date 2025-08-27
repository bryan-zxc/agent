# Data Dictionary

## Table Definitions and Field Specifications

### routers

Main router message persistence table, handles chat routing and agent state.

| Field | Type | Constraints | Description | Business Rules |
|-------|------|-------------|-------------|----------------|
| id | VARCHAR(32) | PRIMARY KEY | UUID hex string | Router uses same ID for 1:1 relationship |
| title | TEXT | | Router display title | Auto-generated from first user message |
| preview | TEXT | | Short router summary | Truncated first message content |
| created_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Record creation time | Immutable after creation |
| updated_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Last modification time | Auto-updated on changes |

---

### routers

Router agent state and configuration persistence.

| Field | Type | Constraints | Description | Business Rules |
|-------|------|-------------|-------------|----------------|
| router_id | VARCHAR(32) | PRIMARY KEY | UUID hex string | Primary router identifier |
| status | VARCHAR(50) | NOT NULL | Router execution state | Values: active, completed, failed, archived |
| model | VARCHAR(100) | | LLM model identifier | e.g., "gpt-4", "claude-3-sonnet" |
| temperature | FLOAT | | LLM temperature setting | Range: 0.0-2.0, default varies by model |
| agent_metadata | JSON | | Extensible router attributes | Future-proofing for new router features |
| schema_version | INTEGER | DEFAULT 1 | Table schema version | Enables migration tracking |
| created_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Record creation time | Immutable after creation |
| updated_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Last modification time | Auto-updated via property setters |

**Status Values:**
- `active`: Router currently processing messages
- `completed`: Router completed successfully  
- `failed`: Router encountered unrecoverable error
- `archived`: Historical record, no longer active

---

### planners

Planner agent execution plans and state management.

| Field | Type | Constraints | Description | Business Rules |
|-------|------|-------------|-------------|----------------|
| planner_id | VARCHAR(32) | PRIMARY KEY | UUID hex string | Unique planner identifier |
| planner_name | VARCHAR(255) | | Human readable planner name | Character name from TV shows/Disney |
| user_question | TEXT | NOT NULL | Original user request | Immutable source of truth |
| instruction | TEXT | | Processing instructions | Additional context for task planning |
| execution_plan | TEXT | | Generated execution strategy | LLM-generated markdown plan |
| model | VARCHAR(100) | | LLM model identifier | Can differ from router model |
| temperature | FLOAT | | LLM temperature setting | Task-specific temperature |
| failed_task_limit | INTEGER | | Max allowed task failures | Prevents infinite retry loops |
| status | VARCHAR(50) | NOT NULL | Planner execution state | Values: planning, executing, completed, failed |
| agent_metadata | JSON | | Extensible planner attributes | Future enhancements |
| schema_version | INTEGER | DEFAULT 1 | Table schema version | Migration support |
| created_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Record creation time | Immutable |
| updated_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Last modification time | Auto-sync via properties |

**Status Values:**
- `planning`: Generating task breakdown
- `executing`: Running tasks sequentially
- `completed`: All tasks completed successfully
- `failed`: Exceeded failure limit or unrecoverable error

---

### workers

Task/worker execution details and lifecycle management.

| Field | Type | Constraints | Description | Business Rules |
|-------|------|-------------|-------------|----------------|
| worker_id | VARCHAR(32) | PRIMARY KEY | UUID hex string | Links to worker_messages.agent_id |
| worker_name | VARCHAR(255) | | Human readable worker name | Character name from children's shows |
| planner_id | VARCHAR(32) | NOT NULL, FK | Parent planner ID | FOREIGN KEY to planners.planner_id |
| task_status | VARCHAR(50) | NOT NULL | Task execution state | Values: pending, in_progress, completed, failed_validation, recorded |
| task_description | TEXT | | Detailed task description | Human-readable task definition |
| acceptance_criteria | JSON | | Success criteria list | Array of validation requirements |
| user_request | TEXT | | Original user request | Simplified context from user's question |
| wip_answer_template | TEXT | | Work-in-progress answer template | Progressively filled markdown template |
| task_result | TEXT | | Execution outcome | Detailed result description |
| querying_structured_data | BOOLEAN | DEFAULT FALSE | Data file query flag | Determines WorkerAgent vs WorkerAgentSQL |
| image_keys | JSON | | Relevant image identifiers | Array of image keys from planner |
| variable_keys | JSON | | Relevant variable identifiers | Array of variable keys from planner |
| tools | JSON | | Required tools list | Array of tool names for execution |
| input_variable_filepaths | JSON | DEFAULT {} | Input variable file paths | Key-value pairs mapping variable keys to file paths |
| input_image_filepaths | JSON | DEFAULT {} | Input image file paths | Key-value pairs mapping image keys to file paths |
| output_variable_filepaths | JSON | DEFAULT {} | Output variable file paths | Key-value pairs mapping variable keys to file paths |
| output_image_filepaths | JSON | DEFAULT {} | Output image file paths | Key-value pairs mapping image keys to file paths |
| tables | JSON | | TableMeta objects | Array of table metadata for data tasks |
| agent_metadata | JSON | | Extensible task attributes | Future enhancements |
| schema_version | INTEGER | DEFAULT 1 | Table schema version | Migration support |
| created_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Record creation time | Immutable |
| updated_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Last modification time | Auto-updated during execution |

**Task Status Values:**
- `pending`: Queued for execution (was 'new' in FullTask model)
- `in_progress`: Currently executing
- `completed`: Successfully completed, awaiting processing
- `failed_validation`: Execution failed validation
- `recorded`: Processed by planner, ready for cleanup

**JSON Field Structures:**

```json
// user_request example
"Analyse the sales data to identify trends and create visualisations"

// wip_answer_template example
"# Sales Analysis Results\n\n## Overview\n[Analysis summary to be filled]\n\n## Key Findings\n- Q3 trends: [To be determined]\n- Top products: [To be filled]"

// acceptance_criteria example
[
  "Generate quarterly sales summary",
  "Identify top 3 declining products", 
  "Create visualisation of trends"
]

// tables example
[
  {
    "table_name": "sales_data",
    "row_count": 1500,
    "columns": [...]
  }
]
```

---

### router_planner_links

Many-to-many relationship tracking between routers and planners.

| Field | Type | Constraints | Description | Business Rules |
|-------|------|-------------|-------------|----------------|
| link_id | INTEGER | PRIMARY KEY AUTOINCREMENT | Unique link identifier | Auto-generated |
| router_id | VARCHAR(32) | NOT NULL, FK | Router identifier | FOREIGN KEY to routers.router_id |
| planner_id | VARCHAR(32) | NOT NULL, FK | Planner identifier | FOREIGN KEY to planners.planner_id |
| relationship_type | VARCHAR(50) | NOT NULL | Link relationship type | Values: initiated, continued, forked |
| created_at | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Link creation time | Immutable |

**Unique Constraint:** `UNIQUE(router_id, planner_id)` prevents duplicate links.

**Relationship Types:**
- `initiated`: Router created new planner
- `continued`: Router resumed existing planner
- `forked`: Router created planner branch

---

### Message Tables

All message tables share identical structure for different agent types.

#### router_messages, planner_messages, worker_messages

| Field | Type | Constraints | Description | Business Rules |
|-------|------|-------------|-------------|----------------|
| message_id | INTEGER | PRIMARY KEY AUTOINCREMENT | Unique message identifier | Auto-generated |
| agent_id | VARCHAR(32) | NOT NULL | Agent identifier | FK to respective agent table |
| role | VARCHAR(20) | NOT NULL | Message role | Values: system, user, assistant, developer |
| content | TEXT | | Message content | Main message text |
| image | TEXT | | Image data/path | Base64 or file path |
| timestamp | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Message timestamp | Chronological ordering |

**Role Values:**
- `system`: System instructions and setup
- `user`: User input messages  
- `assistant`: LLM responses
- `developer`: Internal agent communication

---

## Field Validation Rules

### ID Standards
- All agent IDs: 32-character lowercase hexadecimal UUID
- Generated via `uuid.uuid4().hex`
- No hyphens, consistent format

### JSON Field Validation
- All JSON fields accept `null` values
- Empty arrays/objects represented as `[]`/`{}`
- Complex objects serialised via pydantic models

### Timestamp Standards
- All timestamps in UTC
- ISO format: `YYYY-MM-DD HH:MM:SS`
- Automatic timezone handling in application layer

### Status Enumerations
Defined in application code, enforced via business logic:
- Router status: `['active', 'completed', 'failed', 'archived']`
- Planner status: `['planning', 'executing', 'completed', 'failed']`  
- Worker task_status: `['pending', 'in_progress', 'completed', 'failed_validation', 'recorded']`

---

**Schema Version**: 1.0  
---

### file_metadata

File storage and duplicate detection via content hashing.

| Field | Type | Constraints | Description | Business Rules |
|-------|------|-------------|-------------|----------------|
| file_id | VARCHAR(32) | PRIMARY KEY | UUID hex string | Unique file identifier |
| content_hash | VARCHAR(64) | NOT NULL, INDEX | SHA-256 file hash | Content-based duplicate detection |
| original_filename | VARCHAR(512) | NOT NULL | User-provided filename | Preserved for display purposes |
| file_path | TEXT | NOT NULL | Physical file location | Server filesystem path |
| file_size | INTEGER | NOT NULL | File size in bytes | Used for duplicate resolution UI |
| mime_type | VARCHAR(100) | | File MIME type | Content type identification |
| user_id | VARCHAR(100) | NOT NULL | File owner identifier | Multi-tenancy support |
| reference_count | INTEGER | DEFAULT 1 | Usage reference count | Enables safe file cleanup |
| upload_timestamp | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Initial upload time | Immutable creation timestamp |
| last_accessed | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | Last usage timestamp | Updated on file access |

**Indexes:**
- `content_hash, user_id` (compound) - Fast duplicate detection per user
- `user_id` - User file queries
- `upload_timestamp` - Chronological file listing

**Business Logic:**
- Duplicate detection: Files with identical `content_hash` for same `user_id` are considered duplicates
- Reference counting: Prevents premature deletion of files referenced by multiple routers
- User isolation: File visibility restricted by `user_id`

---

**Schema Version**: 1.0  
**Last Updated**: 2025-08-10