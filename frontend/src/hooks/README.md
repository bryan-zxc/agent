# Hooks - Custom React Hooks

Custom React hooks for managing WebSocket connections, state, and side effects.

## Structure

```
hooks/
├── useWebSocket.ts     # WebSocket connection management hook
└── usePlannerInfo.ts   # Planner execution plan fetching hook
```

## Hooks Overview

### useWebSocket.ts
Custom hook that manages WebSocket connection lifecycle and real-time communication with the backend agent system.

#### Purpose
- **Connection Management** - Handle WebSocket connection/disconnection
- **Message Handling** - Send and receive real-time messages
- **State Integration** - Sync with Zustand store for UI updates
- **Error Recovery** - Automatic reconnection and error handling

#### API
```typescript
const useWebSocket = (url?: string) => {
  // Returns
  sendMessage: (message: string, files?: string[]) => void;
  disconnect: () => void;
  isConnected: boolean;
}
```

#### Parameters
- `url` (optional): WebSocket URL (defaults to `ws://localhost:8000/chat`)

#### Return Values
- `sendMessage`: Function to send messages to the agent
- `disconnect`: Function to manually close the connection
- `isConnected`: Current connection status

#### Features

**Connection Lifecycle:**
```typescript
// Automatic connection on mount
useEffect(() => {
  connect();
  return () => disconnect();
}, []);

// Automatic reconnection on disconnect
ws.current.onclose = () => {
  setConnected(false);
  setTimeout(connect, 3000); // Reconnect after 3 seconds
};
```

**Message Types Handled:**
- `status` - Agent processing status updates
- `response` - Final agent responses to user messages
- `error` - Error messages from the backend

**State Integration:**
```typescript
const { addMessage, updateStatus, setConnected } = useChatStore();

// Automatically updates store based on WebSocket events
ws.current.onmessage = (event) => {
  const data = JSON.parse(event.data);
  switch (data.type) {
    case 'response':
      addMessage(assistantMessage);
      updateStatus({ status: 'idle' });
      break;
    // ... other cases
  }
};
```

#### Usage Example
```typescript
import { useWebSocket } from '../hooks/useWebSocket';

const ChatComponent = () => {
  const { sendMessage, isConnected } = useWebSocket();
  
  const handleSendMessage = () => {
    if (isConnected) {
      sendMessage('Hello, agent!', ['/path/to/file.pdf']);
    }
  };
  
  return (
    <button 
      onClick={handleSendMessage}
      disabled={!isConnected}
    >
      Send Message
    </button>
  );
};
```

### usePlannerInfo.ts
Custom hook that fetches and manages planner execution plan information for routers.

#### Purpose
- **Plan Fetching** - Retrieve execution plans from planner agents
- **Loading States** - Handle loading and error states for API requests
- **Cache Management** - Avoid unnecessary API calls
- **Integration** - Works with router state to show relevant plans

#### API
```typescript
const usePlannerInfo = (
  routerId: string | null,
  isProcessing: boolean
) => {
  // Returns
  plannerInfo: PlannerInfo | null;
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}
```

#### Parameters
- `routerId`: Current router ID to fetch planner info for
- `isProcessing`: Whether the agent is currently processing (triggers fetching)

#### Return Values
- `plannerInfo`: Planner data including execution plan and status
- `loading`: Loading state for the API request
- `error`: Error message if the request fails
- `refetch`: Function to manually refetch planner information

#### Features

**Conditional Fetching:**
```typescript
useEffect(() => {
  // Only fetch when we have a router ID and system is processing
  if (routerId && isProcessing) {
    fetchPlannerInfo();
  } else if (!isProcessing) {
    // Clear planner info when not processing
    setPlannerInfo(null);
  }
}, [routerId, isProcessing]);
```

**Error Handling:**
```typescript
try {
  const response = await fetch(`/api/routers/${routerId}/planner-info`);
  if (!response.ok) throw new Error('Failed to fetch planner information');
  const data: PlannerInfo = await response.json();
  setPlannerInfo(data);
} catch (err) {
  setError(err instanceof Error ? err.message : 'Unknown error occurred');
}
```

#### Usage Example
```typescript
import { usePlannerInfo } from '../hooks/usePlannerInfo';
import { useChatStore } from '../stores/chatStore';

const MessageList = () => {
  const { currentRouterId } = useChatStore();
  const isProcessing = status.status === 'processing';
  
  const { plannerInfo, loading } = usePlannerInfo(
    currentRouterId, 
    isProcessing
  );
  
  return (
    <>
      {plannerInfo?.has_planner && plannerInfo.execution_plan && (
        <ExecutionPlanDisplay plan={plannerInfo.execution_plan} />
      )}
    </>
  );
};
```

## Hook Development Patterns

### Custom Hook Structure
```typescript
export const useCustomHook = (param: string) => {
  // State
  const [state, setState] = useState();
  
  // Effects
  useEffect(() => {
    // Side effects
  }, [param]);
  
  // Callbacks
  const callback = useCallback(() => {
    // Memoized function
  }, [dependencies]);
  
  // Return hook API
  return {
    state,
    callback
  };
};
```

### Best Practices

#### Dependency Management
```typescript
// Correctly memoize callbacks
const sendMessage = useCallback((message: string, files: string[] = []) => {
  if (ws.current && ws.current.readyState === WebSocket.OPEN) {
    // Send logic
  }
}, []); // Empty deps since ws.current is ref

// Use refs for values that don't need to trigger re-renders
const ws = useRef<WebSocket | null>(null);
```

#### Error Handling
```typescript
const connect = useCallback(() => {
  try {
    ws.current = new WebSocket(url);
    // Connection setup
  } catch (error) {
    console.error('Failed to create WebSocket connection:', error);
    updateStatus({ status: 'error', message: 'Connection error' });
  }
}, [url, updateStatus]);
```

#### Cleanup
```typescript
useEffect(() => {
  connect();
  
  return () => {
    if (ws.current) {
      ws.current.close();
      ws.current = null;
    }
  };
}, [connect]);
```

## Development Guidelines

### Creating New Hooks

#### Hook Template
```typescript
import { useState, useEffect, useCallback } from 'react';

export const useNewHook = (param: string) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  const doSomething = useCallback(async () => {
    setLoading(true);
    setError(null);
    
    try {
      // Hook logic
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, [param]);
  
  return {
    loading,
    error,
    doSomething
  };
};
```

#### Naming Conventions
- Start with `use` prefix (React requirement)
- Use descriptive names: `useWebSocket`, `useFileUpload`, `useAgentStatus`
- Follow camelCase convention
- Be specific about the hook's purpose

#### Parameter Design
```typescript
// Good: Object parameter for multiple options
const useWebSocket = ({ 
  url = 'ws://localhost:8000/chat',
  reconnectDelay = 3000,
  maxReconnectAttempts = 5 
} = {}) => { ... }

// Good: Simple single parameter
const useWebSocket = (url?: string) => { ... }
```

### Testing Hooks

#### Unit Testing with React Testing Library
```typescript
import { renderHook, act } from '@testing-library/react';
import { useWebSocket } from './useWebSocket';

describe('useWebSocket', () => {
  it('should connect to WebSocket', () => {
    const { result } = renderHook(() => useWebSocket());
    
    expect(result.current.isConnected).toBe(false);
    
    // Test connection logic
  });
});
```

#### Integration Testing
- Test with actual WebSocket connections
- Mock WebSocket for predictable testing
- Test error scenarios and edge cases

## Hook Patterns

### State Management Integration
```typescript
// Good: Direct store integration
const { addMessage, updateStatus } = useChatStore();

// Avoid: Passing store methods as parameters
const useWebSocket = (onMessage: (msg) => void) => { ... }
```

### Event Handling
```typescript
// Good: Internal event handling
ws.current.onmessage = (event) => {
  const data = JSON.parse(event.data);
  handleMessage(data);
};

// Avoid: Exposing raw events
return { onMessage: ws.current.onmessage };
```

### Resource Cleanup
```typescript
// Always clean up resources
useEffect(() => {
  const connection = createConnection();
  
  return () => {
    connection.close();
  };
}, []);
```

## Future Hook Ideas

### Planned Hooks
- `useFileUpload` - File upload with progress tracking
- `useAgentStatus` - Agent status monitoring and updates
- `useRouterHistory` - Router persistence and retrieval
- `useVoiceInput` - Speech-to-text integration
- `useTheme` - Dark/light mode management

### Advanced Patterns
```typescript
// Compound hooks
const useChatInterface = () => {
  const websocket = useWebSocket();
  const fileUpload = useFileUpload();
  const status = useAgentStatus();
  
  return {
    ...websocket,
    ...fileUpload,
    ...status
  };
};

// Hook composition
const useRealTimeChat = () => {
  const { messages } = useChatStore();
  const { sendMessage } = useWebSocket();
  const { uploadFile } = useFileUpload();
  
  const sendMessageWithFiles = useCallback(async (message, files) => {
    const uploadedFiles = await Promise.all(
      files.map(file => uploadFile(file))
    );
    sendMessage(message, uploadedFiles.map(f => f.path));
  }, [sendMessage, uploadFile]);
  
  return {
    messages,
    sendMessageWithFiles
  };
};
```

## Performance Considerations

### Optimization Techniques
- Use `useCallback` for functions passed as dependencies
- Use `useMemo` for expensive calculations
- Avoid recreating objects in render cycles
- Consider `useRef` for values that don't trigger re-renders

### Memory Management
- Clean up WebSocket connections
- Remove event listeners on unmount
- Cancel pending requests when component unmounts
- Use weak references where appropriate