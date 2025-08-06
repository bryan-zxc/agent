# Entity Relationship Diagram

## Complete Schema Overview

```mermaid
erDiagram
    conversations ||--o{ router_messages : contains
    conversations ||--|| routers : "activates (1:1)"
    routers ||--o{ router_planner_links : "initiates"
    planners ||--o{ router_planner_links : "activated by"
    planners ||--o{ planner_messages : "generates (1:1)"
    planners ||--o{ workers : "creates tasks"
    workers ||--o{ worker_messages : "generates (1:1)"
    
    conversations {
        string id PK
        string title
        string preview  
        datetime created_at
        datetime updated_at
    }
    
    routers {
        string router_id PK
        string status
        string model
        float temperature
        json metadata
        integer schema_version
        datetime created_at
        datetime updated_at
    }
    
    planners {
        string planner_id PK
        text user_question
        text instruction
        text execution_plan
        string model
        float temperature
        integer failed_task_limit
        string status
        json metadata
        integer schema_version
        datetime created_at
        datetime updated_at
    }
    
    workers {
        string worker_id PK
        string planner_id FK
        string task_status
        text task_description
        json acceptance_criteria
        json task_context
        text task_result
        boolean querying_data_file
        json image_keys
        json variable_keys
        json tools
        json input_images
        json input_variables
        json output_images
        json output_variables
        json tables
        json metadata
        integer schema_version
        datetime created_at
        datetime updated_at
    }
    
    router_planner_links {
        integer link_id PK
        string router_id FK
        string planner_id FK
        string relationship_type
        datetime created_at
    }
    
    router_messages {
        integer message_id PK
        string agent_id FK
        string role
        text content
        text image
        datetime timestamp
    }
    
    planner_messages {
        integer message_id PK
        string agent_id FK
        string role
        text content
        text image
        datetime timestamp
    }
    
    worker_messages {
        integer message_id PK
        string agent_id FK
        string role
        text content
        text image
        datetime timestamp
    }
```

## Relationship Details

### Core Agent Flow
1. **Conversation → Router**: Each conversation activates exactly one router (1:1)
2. **Router → Planner**: Router can initiate multiple planners over time (1:n via link table)
3. **Planner → Worker**: Each planner creates multiple tasks/workers (1:n)

### Message Relationships
Each agent type maintains its own message history:
- **Router Messages**: Conversation-level messaging
- **Planner Messages**: Planning and task management messaging  
- **Worker Messages**: Task execution and result messaging

### Key Constraints

#### Primary Keys
- All agent IDs use 32-character UUID hex strings
- Message IDs use auto-incrementing integers
- Link table uses auto-incrementing link_id

#### Foreign Key Relationships
```sql
-- Core agent relationships
workers.planner_id → planners.planner_id
router_planner_links.router_id → routers.router_id  
router_planner_links.planner_id → planners.planner_id

-- Message relationships
router_messages.agent_id → routers.router_id
planner_messages.agent_id → planners.planner_id
worker_messages.agent_id → workers.worker_id

-- Conversation relationship  
routers.router_id → conversations.id (implicit via same UUID)
```

## Data Flow Patterns

### Agent Lifecycle
```mermaid
sequenceDiagram
    participant C as Conversation
    participant R as Router
    participant P as Planner  
    participant W as Worker
    participant DB as Database
    
    C->>R: Activate router
    R->>DB: Create router record
    R->>P: Create planner
    P->>DB: Create planner record
    DB->>DB: Link router-planner
    P->>W: Create worker/task
    W->>DB: Create worker record
    W->>DB: Update task status
    P->>DB: Process completed task
```

### State Persistence
- **Real-time Updates**: Agent properties auto-sync to database via setters
- **Restart Recovery**: Agents can initialise from existing database records
- **Message Continuity**: All conversations preserved across restarts

### Task Management Flow
```mermaid
stateDiagram-v2
    [*] --> pending : TaskManager.queue_single_task()
    pending --> in_progress : execute_current_task()
    in_progress --> completed : Worker success
    in_progress --> failed_validation : Worker failure
    completed --> recorded : assess_completion()
    failed_validation --> recorded : assess_completion()
    recorded --> [*]
```

## Schema Evolution Support

### Version Tracking
- Each table includes `schema_version` field
- Current version tracked in `settings.AGENT_DATABASE_SCHEMA_VERSION`
- Migration system supports gradual transitions

### JSON Flexibility
- Metadata fields allow new attributes without schema changes
- Frequently accessed attributes can be promoted to columns
- Maintains backward compatibility during transitions

---

**Schema Version**: 1.0  
**Last Updated**: 2025-08-06