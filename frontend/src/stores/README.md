# Stores - State Management with Zustand

Zustand-based state management for global application state.

## Structure

```
stores/
└── chatStore.ts        # Chat state and actions
```

## Store Overview

### chatStore.ts
Global state management for the chat interface using Zustand, a lightweight state management library.

#### Purpose
- **Centralized State** - Single source of truth for chat data
- **React Integration** - Seamless integration with React components
- **Type Safety** - Full TypeScript support with proper interfaces
- **Performance** - Minimal re-renders and efficient updates

#### Store Structure
```typescript
interface ChatStore {
  // State
  messages: ChatMessage[];
  status: AgentStatus;
  isConnected: boolean;
  currentModel: string;
  temperature: number;
  
  // Actions
  addMessage: (message: ChatMessage) => void;
  updateStatus: (status: AgentStatus) => void;
  setConnected: (connected: boolean) => void;
  setModel: (model: string) => void;
  setTemperature: (temperature: number) => void;
  clearMessages: () => void;
}
```

#### State Properties

**messages: ChatMessage[]**
- Array of all chat messages
- Includes both user and assistant messages
- Persisted throughout the session
- Used for chat history display

**status: AgentStatus**
- Current agent processing status
- Shows when agent is idle, processing, analyzing, or has errors
- Used for loading indicators and status messages

**isConnected: boolean**
- WebSocket connection status
- Used to enable/disable UI elements
- Shows connection indicator in header

**currentModel: string**
- Selected AI model (e.g., 'gpt-4', 'gpt-3.5-turbo')
- Affects response quality and processing speed
- Configurable by user

**temperature: number**
- Model temperature setting (0.0 - 1.0)
- Controls response randomness/creativity
- Default: 0.7

#### Actions

**addMessage(message: ChatMessage)**
- Adds new message to the messages array
- Called when user sends message or agent responds
- Automatically triggers UI updates

**updateStatus(status: AgentStatus)**
- Updates agent processing status
- Used by WebSocket hook to show processing states
- Triggers status indicator updates

**setConnected(connected: boolean)**
- Updates WebSocket connection status
- Enables/disables message sending
- Shows connection status in UI

**setModel(model: string)**
- Changes the AI model selection
- Affects subsequent agent responses
- Persisted in store for consistency

**setTemperature(temperature: number)**
- Updates model temperature setting
- Controls response creativity/randomness
- Validated to be between 0.0 and 1.0

**clearMessages()**
- Clears all messages from chat history
- Used for "new conversation" functionality
- Resets conversation state

#### Usage Examples

**In Components:**
```typescript
import { useChatStore } from '../stores/chatStore';

const ChatComponent = () => {
  const { 
    messages, 
    status, 
    isConnected, 
    addMessage, 
    updateStatus 
  } = useChatStore();
  
  const handleNewMessage = (text: string) => {
    const message: ChatMessage = {
      id: Date.now().toString(),
      message: text,
      sender: 'user',
      timestamp: new Date()
    };
    addMessage(message);
  };
  
  return (
    <div>
      {messages.map(msg => (
        <div key={msg.id}>{msg.message}</div>
      ))}
      {status.status === 'processing' && <div>Processing...</div>}
    </div>
  );
};
```

**In Hooks:**
```typescript
import { useChatStore } from '../stores/chatStore';

const useWebSocket = () => {
  const { addMessage, updateStatus, setConnected } = useChatStore();
  
  const handleMessage = (data: any) => {
    switch (data.type) {
      case 'response':
        const assistantMessage: ChatMessage = {
          id: Date.now().toString(),
          message: data.message,
          sender: 'assistant',
          timestamp: new Date()
        };
        addMessage(assistantMessage);
        updateStatus({ status: 'idle' });
        break;
    }
  };
  
  return { /* hook methods */ };
};
```

## Zustand Patterns

### Store Creation
```typescript
import { create } from 'zustand';

export const useChatStore = create<ChatStore>((set, get) => ({
  // Initial state
  messages: [],
  status: { status: 'idle' },
  
  // Actions with state updates
  addMessage: (message) =>
    set((state) => ({
      messages: [...state.messages, message],
    })),
    
  // Actions with complex logic
  clearMessages: () =>
    set({ messages: [] }),
}));
```

### State Updates
```typescript
// Simple state update
setConnected: (connected) => set({ isConnected: connected }),

// Complex state update with previous state
addMessage: (message) =>
  set((state) => ({
    messages: [...state.messages, message],
  })),

// Conditional updates
updateStatus: (status) =>
  set((state) => ({
    status: { ...state.status, ...status }
  })),
```

### State Access
```typescript
// Multiple state values
const { messages, status, isConnected } = useChatStore();

// Single state value (prevents unnecessary re-renders)
const messages = useChatStore(state => state.messages);

// Derived state with selector
const messageCount = useChatStore(state => state.messages.length);
```

## Development Guidelines

### Creating New Stores

#### Store Template
```typescript
import { create } from 'zustand';

interface NewStore {
  // State properties
  data: SomeType[];
  loading: boolean;
  error: string | null;
  
  // Actions
  setData: (data: SomeType[]) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  reset: () => void;
}

export const useNewStore = create<NewStore>((set) => ({
  // Initial state
  data: [],
  loading: false,
  error: null,
  
  // Actions
  setData: (data) => set({ data }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
  reset: () => set({ data: [], loading: false, error: null }),
}));
```

#### Best Practices

**State Structure:**
- Keep state flat and normalized
- Use TypeScript interfaces for type safety
- Group related state together
- Avoid deeply nested objects

**Actions:**
- Use descriptive action names
- Keep actions pure (no side effects)
- Handle complex updates with proper immutability
- Validate input parameters when necessary

**Performance:**
```typescript
// Good: Specific selectors prevent unnecessary re-renders
const messages = useChatStore(state => state.messages);

// Avoid: Taking entire store causes re-renders on any change
const store = useChatStore();
```

### Advanced Patterns

#### Middleware Integration
```typescript
import { subscribeWithSelector } from 'zustand/middleware';

export const useChatStore = create(
  subscribeWithSelector<ChatStore>((set) => ({
    // Store implementation
  }))
);

// Subscribe to specific changes
useChatStore.subscribe(
  (state) => state.messages,
  (messages) => {
    // React to message changes
    localStorage.setItem('messages', JSON.stringify(messages));
  }
);
```

#### Computed Values
```typescript
// Computed properties as getters
export const useChatStore = create<ChatStore>((set, get) => ({
  messages: [],
  
  // Computed property
  get lastMessage() {
    const { messages } = get();
    return messages[messages.length - 1];
  },
  
  // Computed selector
  getMessagesByUser: (userId: string) => {
    const { messages } = get();
    return messages.filter(msg => msg.sender === userId);
  },
}));
```

#### Async Actions
```typescript
interface AsyncStore {
  data: any[];
  loading: boolean;
  
  fetchData: () => Promise<void>;
}

export const useAsyncStore = create<AsyncStore>((set, get) => ({
  data: [],
  loading: false,
  
  fetchData: async () => {
    set({ loading: true });
    
    try {
      const response = await fetch('/api/data');
      const data = await response.json();
      set({ data, loading: false });
    } catch (error) {
      set({ loading: false });
      // Handle error
    }
  },
}));
```

## Testing Stores

### Unit Testing
```typescript
import { act, renderHook } from '@testing-library/react';
import { useChatStore } from './chatStore';

describe('chatStore', () => {
  beforeEach(() => {
    // Reset store state before each test
    useChatStore.getState().clearMessages();
  });
  
  it('should add message', () => {
    const { result } = renderHook(() => useChatStore());
    
    const message: ChatMessage = {
      id: '1',
      message: 'Hello',
      sender: 'user',
      timestamp: new Date()
    };
    
    act(() => {
      result.current.addMessage(message);
    });
    
    expect(result.current.messages).toHaveLength(1);
    expect(result.current.messages[0]).toEqual(message);
  });
});
```

### Integration Testing
- Test store interactions with components
- Test async actions and side effects
- Test store persistence (if implemented)

## Future Enhancements

### Planned Stores
- `useSettingsStore` - User preferences and configuration
- `useFileStore` - File upload and management state
- `useHistoryStore` - Conversation history persistence
- `useThemeStore` - UI theme and appearance settings

### Advanced Features
```typescript
// Persistence middleware
import { persist } from 'zustand/middleware';

export const useChatStore = create(
  persist<ChatStore>(
    (set) => ({
      // Store implementation
    }),
    {
      name: 'chat-storage',
      getStorage: () => localStorage,
    }
  )
);

// DevTools integration
import { devtools } from 'zustand/middleware';

export const useChatStore = create(
  devtools<ChatStore>((set) => ({
    // Store implementation
  }))
);
```

## Performance Optimization

### Selector Optimization
```typescript
// Good: Memoized selectors
const messageCount = useChatStore(
  useCallback(state => state.messages.length, [])
);

// Good: Shallow comparison for objects
const status = useChatStore(state => state.status, shallow);
```

### State Updates
```typescript
// Efficient batch updates
const updateMultiple = () => {
  useChatStore.setState((state) => ({
    messages: [...state.messages, newMessage],
    status: { status: 'idle' },
    isConnected: true
  }));
};
```