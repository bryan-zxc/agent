# Security Module

Security guardrails and safety mechanisms for the agent system.

## Modules

### `guardrails.py`
Security validation prompts and safety checks for code execution.

#### Constants

**`guardrail_prompt`**
- Security validation prompt used to assess code safety
- Checks for potentially malicious operations:
  - **Database Modifications**: Detects attempts to change or delete existing database objects
  - **Executable File Creation**: Identifies creation of .exe, .bat, or other executable files
  - **File System Changes**: Monitors for unauthorized file modifications or deletions
  - **Safe Operations**: Allows adding new files or tables without blocking legitimate operations

## Security Features

### Code Execution Safety
The guardrail system evaluates all generated Python code before execution to prevent:

- **Data Corruption**: Prevents modification or deletion of existing database tables
- **Malware Creation**: Blocks generation of executable files that could be harmful
- **File System Tampering**: Prevents unauthorized changes to the file system
- **System Compromise**: Guards against code that could affect system security

### Safety Classifications

**Allowed Operations:**
- Creating new files or directories
- Adding new database tables
- Reading existing data
- Generating reports and analyses
- Image processing and manipulation
- Data visualization

**Blocked Operations:**
- Deleting existing files or databases
- Modifying system files
- Creating executable files (.exe, .bat, .sh)
- Changing database schemas
- Network operations (if configured)

## Usage

### Automatic Validation
```python
from agent.models.tasks import TaskArtefact

# The guardrail_prompt is automatically used in TaskArtefact validation
task_result = TaskArtefact(
    python_code="import pandas as pd\ndf = pd.read_csv('data.csv')",
    is_malicious=False  # Automatically validated against guardrails
)
```

### Manual Security Check
```python
from agent.security.guardrails import guardrail_prompt

# Use the prompt to evaluate code safety
code_to_check = "os.remove('important_file.txt')"
# This would be flagged as potentially malicious
```

## Integration Points

- **TaskArtefact Model**: Automatic security validation using the `is_malicious` field
- **Worker Agents**: Code execution is blocked if marked as malicious
- **LLM Evaluation**: The guardrail prompt is used by language models to assess code safety

## Security Best Practices

### For Developers
- Always use the guardrail system for code validation
- Regularly review and update security criteria
- Test edge cases for false positives/negatives
- Monitor code execution patterns

### For System Integration
- Implement defense in depth with multiple security layers
- Log all security violations for audit purposes
- Provide clear error messages for blocked operations
- Ensure legitimate operations are not inadvertently blocked

## Limitations and Considerations

### Current Scope
- Focuses primarily on file system and database safety
- Designed for Python code execution in sandboxed environments
- May require updates for new attack vectors

### Future Enhancements
- Network operation monitoring
- Resource usage limits
- Advanced static code analysis
- Machine learning-based threat detection

## Error Handling

When malicious code is detected:
1. Execution is immediately blocked
2. Clear error message is provided to the user
3. The task is marked as failed with security violation
4. Alternative approaches are suggested when possible

## Compliance

The security module helps ensure:
- **Data Protection**: Prevents unauthorized data access or modification
- **System Integrity**: Maintains system stability and security
- **User Safety**: Protects users from potentially harmful operations
- **Audit Trail**: Provides logging for security analysis