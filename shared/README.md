# Shared - Type Definitions

Shared TypeScript type definitions used across frontend and backend to ensure type safety and consistency.

## Structure

```
shared/
└── types/
    └── index.ts        # All shared type definitions
```

## Purpose

This directory contains TypeScript interfaces and types that are shared between:
- **Frontend** (Next.js React application)
- **Backend** (FastAPI Python server - for documentation)

By centralizing type definitions, we ensure:
- **Consistency** - Same data structures across the stack
- **Type Safety** - Compile-time checking for API contracts
- **Documentation** - Types serve as living documentation
- **Maintainability** - Single source of truth for data models

## Type Definitions

### ChatMessage
Core message structure for chat routers:
```typescript
interface ChatMessage {
  id: string;
  message: string;
  sender: 'user' | 'assistant';
  timestamp: Date;
  files?: string[];
  model?: string;
  temperature?: number;
}
```

### WebSocketMessage
WebSocket communication protocol:
```typescript
interface WebSocketMessage {
  type: 'message' | 'status' | 'response' | 'error';
  data: any;
  timestamp?: Date;
}
```

### FileUpload
File upload response structure:
```typescript
interface FileUpload {
  filename: string;
  path: string;
  size: number;
  type: string;
}
```

### AgentStatus
Agent processing status indicators:
```typescript
interface AgentStatus {
  status: 'idle' | 'processing' | 'analyzing' | 'error';
  message?: string;
  progress?: number;
}
```

### RouterHistory
Router management structure:
```typescript
interface RouterHistory {
  id: string;
  messages: ChatMessage[];
  createdAt: Date;
  updatedAt: Date;
}
```

## Usage

### In Frontend (TypeScript/React)
```typescript
import { ChatMessage, AgentStatus } from '../../../shared/types';

const message: ChatMessage = {
  id: '123',
  message: 'Hello, agent!',
  sender: 'user',
  timestamp: new Date()
};
```

### In Backend (Python/FastAPI)
While the backend is Python-based, these types serve as documentation for API contracts and can be used to generate Pydantic models:

```python
# Equivalent Pydantic model
class ChatMessage(BaseModel):
    id: str
    message: str
    sender: Literal['user', 'assistant']
    timestamp: datetime
    files: Optional[List[str]] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
```

## Development Guidelines

### Adding New Types
1. Add type definition to `types/index.ts`
2. Export the type from the index file
3. Update both frontend and backend to use the new type
4. Document the type with JSDoc comments

### Modifying Existing Types
1. **Breaking changes** - Coordinate with both frontend and backend teams
2. **Non-breaking changes** - Use optional properties when possible
3. **Version compatibility** - Consider backwards compatibility

### Best Practices
- Use **descriptive names** for types and properties
- Add **JSDoc comments** for complex types
- Use **union types** for constrained values (`'idle' | 'processing'`)
- Make properties **optional** when appropriate
- Use **Date** objects for timestamps (converted to ISO strings in JSON)

## Type Safety Benefits

### Compile-time Validation
```typescript
// TypeScript will catch this error at compile time
const invalidMessage: ChatMessage = {
  id: '123',
  message: 'Hello',
  sender: 'invalid-sender', // Error: not assignable to 'user' | 'assistant'
  timestamp: new Date()
};
```

### API Contract Enforcement
```typescript
// WebSocket message handling with type safety
const handleMessage = (message: WebSocketMessage) => {
  switch (message.type) {
    case 'response':
      // TypeScript knows this is a response message
      break;
    case 'error':
      // TypeScript knows this is an error message
      break;
    // TypeScript will warn if we miss a case
  }
};
```

### IDE Support
- **IntelliSense** - Auto-completion for type properties
- **Error highlighting** - Immediate feedback on type mismatches
- **Refactoring support** - Safe renaming across the codebase

## Import Patterns

### Frontend Components
```typescript
import { ChatMessage, AgentStatus } from '../../../shared/types';
```

### Frontend Hooks
```typescript
import { WebSocketMessage, ChatMessage } from '../../../shared/types';
```

### Frontend Stores
```typescript
import { ChatMessage, AgentStatus } from '../../../shared/types';
```

## Maintenance

### Regular Reviews
- Review types quarterly for consistency
- Remove unused types
- Update documentation as types evolve
- Coordinate breaking changes across teams

### Version Management
- Consider semantic versioning for major type changes
- Document breaking changes in commit messages
- Use TypeScript's strict mode for maximum type safety

## Future Enhancements

- **Runtime validation** - Consider using libraries like Zod for runtime type checking
- **Code generation** - Generate Pydantic models from TypeScript types
- **API documentation** - Generate OpenAPI specs from shared types
- **Validation schemas** - Create JSON Schema from TypeScript types