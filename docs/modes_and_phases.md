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
- **Status Flow**:
  ```
  plamarinating (actively researching)
      ↕ (iterations)
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

The `handle_message` function routes based on mode and phase:

1. **Check router mode**:
   - `rapid` → Always simple chat
   - `agent` → Check agent_phase
     - `plamarination` → Start planning_mode_response
     - `execution` → Start handle_complex_request
   - `auto` → Assess complexity
     - Simple → Simple chat
     - Complex → Start planning_mode_response

2. **Check router status** (for continuation):
   - `plamarinating` → Continue planning_mode_response
   - `plamarinating_awaiting_user` → Process user input, continue planning
   - `awaiting_approval` → Handle approval/rejection
   - `executing` → Execution in progress, no new messages

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
- `agent_phase`: String(20) - "plamarination" or "execution" (nullable, only set in agent mode)
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

### Status Updates
```json
{
  "type": "status_update",
  "router_id": "uuid",
  "status": "plamarinating|executing|...",
  "continue_plamarination": true|false  // For auto-continuation
}
```

### Approval Flow
```json
// Frontend sends
{
  "type": "approval_response",
  "router_id": "uuid",
  "approved": true|false,
  "feedback": "Optional revision feedback"
}
```

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