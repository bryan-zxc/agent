# Modes and Phases Architecture

## Overview

The agent system operates with three primary modes that determine how user requests are processed. The agent mode further subdivides into two phases, providing granular control over complex request handling.

## Primary Modes

### 1. Auto Mode (Default)
- **Purpose**: Intelligent routing based on request complexity
- **Behaviour**: 
  - Analyses each request to determine if agent assistance is needed
  - Simple requests → Direct response via simple chat
  - Complex requests → Automatically triggers agent mode with plamarination phase
  - Files attached → Typically triggers agent mode
- **Use Case**: General-purpose interaction where the system decides the best approach

### 2. Rapid Mode
- **Purpose**: Fast, lightweight responses without agent processing
- **Behaviour**:
  - Always uses simple chat, bypassing all agent assessment
  - No file processing capabilities
  - No web searches or complex tool usage
  - Warns users when questions may need deeper analysis
- **Use Case**: Quick questions, definitions, explanations where speed is prioritised over depth

### 3. Agent Mode
- **Purpose**: Advanced processing with explicit planning and execution phases
- **Behaviour**:
  - Provides two distinct phases (see below)
  - Always involves deeper analysis and tool usage
  - Supports complex multi-step operations
- **Use Case**: Complex tasks, file analysis, research, multi-step operations

## Agent Mode Phases

When in agent mode, users can toggle between two phases:

### Plamarination Phase (Default)
- **Purpose**: Research, analysis, and planning before execution
- **Process**:
  1. Thoroughly analyse the request and any attached files
  2. Research using available tools (file reading, web search, etc.)
  3. Build comprehensive context
  4. Generate a structured execution plan
  5. Present plan for user approval
- **Automatic Continuation**:
  - After each research step, GPT-5-nano determines if more research is needed
  - If continuing: Frontend automatically sends continuation request
  - If user input needed: System waits for response
  - This creates seamless research cycles without manual intervention
- **Status Flow**:
  ```
  plamarinating (actively researching)
      ↕ (automatic iterations via continuation signals)
  plamarinating_awaiting_user (needs clarification)
      ↓
  awaiting_approval (plan ready)
      ↓
  [User Decision]
      ├─ Approve → executing → active
      └─ Reject/Revise → plamarinating
  ```

### Execution Phase
- **Purpose**: Direct execution without planning overhead
- **Process**:
  1. Skip plamarination entirely
  2. Immediately proceed to handle_complex_request
  3. Execute task with available tools
  4. Return results directly
- **Status Flow**:
  ```
  active → executing → active
  ```

## State Transitions

### Mode Transitions
```
[User Selection via UI Toggle]
Auto ←→ Rapid ←→ Agent
```

### Phase Transitions (Within Agent Mode)
```
[User Selection via Phase Toggle - Only visible in Agent Mode]
Plamarination ←→ Execution
```

### Status Transitions

#### In Auto Mode
```
active → [complexity check] → plamarinating (if complex) → ... → active
                           ↘ active (if simple)
```

#### In Agent Mode + Plamarination Phase
```
active → plamarinating → plamarinating_awaiting_user → plamarinating → awaiting_approval
             ↑_______________|                              ↑                    ↓
                                                            |          [approve] ↓
                                                            |              executing
                                                            |                    ↓
                                                            |________________active
                                                          [reject/revise]
```

#### In Agent Mode + Execution Phase
```
active → executing → active
```

## Implementation Details

### Router State Structure
```python
router_state = {
    "id": "router_uuid",
    "mode": "auto|rapid|agent",      # Primary mode
    "agent_phase": "plamarination|execution",  # Only relevant when mode="agent"
    "status": "active|plamarinating|...",      # Current processing status
    ...
}
```

### Message Routing Logic

The `handle_message` function routes based on **status first**, then mode and phase:

1. **Check router status** (prevents double-triggering):
   - `plamarinating` → Return immediately (no trigger - auto-continuation already running)
   - `plamarinating_awaiting_user` → Process user input, continue planning
   - `awaiting_approval` → Handle approval/rejection
   - `executing` → Execution in progress, no new messages
   - `active` → Check mode for new request routing

2. **When status is active, check router mode**:
   - `rapid` → Always simple chat
   - `agent` → **INVALID STATE** - Raises error (agent mode should never have active status)
   - `auto` → Assess complexity
     - Simple → Simple chat
     - Complex → Start plamarination_response

**Important**: Agent mode is activated through mode/phase toggles which immediately set status and trigger actions. The router never naturally reaches `active` status in agent mode.

### Plamarination Message Flow

The plamarination phase uses a sophisticated message flow to handle research iterations:

#### WebSocket Message Types
- `response`: Assistant's message to display in chat
- `status`: Processing status updates ("Thinking", etc.)
- `continue_plamarination_signal`: Signal to frontend to auto-continue research
- `continue_plamarination`: Frontend's request to continue research

#### Message Sequences

**When Tools Are Called (Always Continues)**:
1. Backend sends multiple `response` messages (one per tool result)
2. Backend sends `continue_plamarination_signal`
3. Frontend automatically sends `continue_plamarination`
4. Loop continues with next research iteration

**When Text Response + Continue Research**:
1. GPT-5-nano determines continuation is needed
2. Backend sends `response` with assistant's thoughts
3. Backend sends `continue_plamarination_signal`
4. Frontend automatically sends `continue_plamarination`

**When Text Response + User Input Needed**:
1. GPT-5-nano determines user input is required
2. Backend sends `response` with assistant's question
3. No continuation signal sent
4. Frontend stays idle, waiting for user input

#### Key Design Decisions
- **Separation of Concerns**: Messages are for display, signals are for control flow
- **Automatic Continuation**: Frontend handles continuation without user intervention
- **Clean State Management**: Each message type has a single, clear purpose
- **No Redundant Messages**: Only send signals when action is needed

### User Interface

#### Mode Toggle (Always Visible)
```
[Auto] [Rapid] [Agent]
```

#### Phase Toggle (Only in Agent Mode)
```
Mode: Agent
Phase: [Plamarination] [Execution]
```

### Database Schema

The Router table includes:
- `mode`: String(10) - "auto", "rapid", or "agent"
- `agent_phase`: String(20) - "plamarination" or "execution" (NULL by default, only set when agent mode is active)
- `status`: String(50) - Current processing status

## Decision Guidelines

### When to Use Each Mode

**Auto Mode**:
- Default choice for most users
- Mixed workload of simple and complex tasks
- Want system to intelligently route requests

**Rapid Mode**:
- Need quick responses
- Simple questions that don't require research
- Willing to sacrifice accuracy for speed

**Agent Mode**:
- Know you have complex tasks
- Want explicit control over planning vs execution
- Working with multiple files or complex research

### When to Use Each Phase (in Agent Mode)

**Plamarination Phase**:
- Need thorough research and planning
- Working with unfamiliar files or domains
- Want to review plan before execution
- Complex multi-step tasks

**Execution Phase**:
- Already know what needs to be done
- Repeating similar tasks
- Trust the system to execute correctly
- Want fastest path to results

## Status Reference

| Status | Description | Valid In Modes | Next States |
|--------|-------------|----------------|-------------|
| active | Ready for input | All | plamarinating, executing |
| plamarinating | Actively researching/planning | Auto, Agent | plamarinating_awaiting_user, awaiting_approval |
| plamarinating_awaiting_user | Needs user clarification | Auto, Agent | plamarinating |
| awaiting_approval | Plan ready for approval | Auto, Agent | executing, plamarinating |
| executing | Running complex request | All | active |
| completed | Conversation ended | All | - |

## Frontend-Backend Communication

### Mode Changes
```json
{
  "type": "update_mode",
  "router_id": "uuid",
  "mode": "auto|rapid|agent",
  "agent_phase": "plamarination|execution"  // Only if mode="agent"
}
```

**Mode Toggle Behaviour**:
- Switching to `agent` mode immediately:
  - Sets `agent_phase` to "plamarination" (default)
  - Sets `status` to "plamarinating"
  - Triggers `plamarination_response()` to start planning
- Switching from `agent` to other modes:
  - Clears `agent_phase` (sets to NULL)
  - Sets `status` to "active"
  - Ready for normal message processing

### Phase Changes (Agent Mode Only)
```json
{
  "type": "update_phase",
  "router_id": "uuid",
  "agent_phase": "plamarination|execution"
}
```

**Phase Toggle Behaviour**:
- Switching to `plamarination` phase:
  - Sets `status` to "plamarinating"
  - Triggers `plamarination_response()` immediately
- Switching to `execution` phase:
  - Sets `status` to "executing"
  - Triggers `handle_complex_request()` immediately

### Status Updates
```json
{
  "type": "status_update",
  "router_id": "uuid",
  "status": "plamarinating|executing|...",
  "continue_plamarination": true|false  // For auto-continuation
}
```

### Approval Flow Details

#### 1. Backend Completes Planning
When the `set_plan_and_answer` tool completes:
- Tool generates execution plan with todos
- Post-tool hook (`tool_hooks.py`) detects "# Execution Plan" format
- Updates router status to `"plamarinating_awaiting_user"`
- Sends WebSocket status update to trigger frontend approval UI

#### 2. Frontend Shows Approval UI
Upon receiving `plamarinating_awaiting_user` status:
- Displays the plan to the user
- Shows two options: Approve or Reject/Revise
- User can provide additional feedback text

#### 3. Frontend Sends Approval Response
```json
{
  "type": "message",
  "router_id": "uuid",
  "message": "User's feedback or instructions",
  "approval_response": {
    "approved": true|false,
    "feedback": "Additional context if rejecting"
  }
}
```

#### 4. Backend Processes Approval
The WebSocket handler (`main.py`):
- Detects `approval_response` in message data
- Transforms into structured format:
  ```python
  message_data = {
    "type": "approval_response",
    "approved": true/false,
    "feedback": "user feedback",
    "message": "original message"
  }
  ```
- Passes to `handle_message` which routes based on approval:
  - If approved → Immediately triggers `handle_complex_request`
  - If rejected → Returns to plamarination with feedback

#### 5. Execution Begins
When approved:
- Status changes to `"executing"`
- Planner/Worker pipeline starts immediately
- No further user interaction needed until completion

**Note**: The planner/worker entry point will be redesigned in future iterations.

## Double-Triggering Prevention

The system prevents double-triggering of plamarination through status-based routing:

### Three Types of Plamarination Triggers

1. **Auto-continuation** (Frontend-triggered):
   - Frontend sends `continue_plamarination: true` in status update
   - Backend continues existing plamarination chain
   - No user message involved

2. **Proactive User Input** (No trigger):
   - User sends message while `status="plamarinating"`
   - `handle_message` returns immediately without triggering
   - Message is added to chain, picked up by ongoing plamarination
   - No duplicate processing occurs

3. **Required User Response** (User-triggered):
   - Status is `"plamarinating_awaiting_user"`
   - User input triggers continuation of plamarination
   - Processes user's response and continues planning

### Key Implementation Details

- `handle_message` **always checks status first** before mode/phase
- When `status="plamarinating"`, function returns immediately
- Mode/phase toggles are **active state changes** that set status and trigger immediately
- Agent mode **never has `active` status** - it's always in a processing state
- Invalid states (e.g., agent mode with active status) **raise errors** instead of silent recovery

## Testing Scenarios

1. **Mode Transitions**:
   - Switch between all modes during conversation
   - Verify phase toggle appears/disappears appropriately
   - Ensure status resets correctly

2. **Plamarination Flow**:
   - Test approval → execution
   - Test rejection → continued plamarination
   - Test clarification requests

3. **Execution Phase**:
   - Verify skips plamarination
   - Test direct execution
   - Ensure returns to active status

4. **Auto Mode Routing**:
   - Simple request → Simple response
   - Complex request → Plamarination
   - File upload → Plamarination

5. **Edge Cases**:
   - Mode change during plamarination
   - Phase change during execution
   - Network disconnection/reconnection