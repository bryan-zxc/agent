# Components - Modular React UI Components

Modern, accessible React components built with shadcn/ui and Tailwind CSS for the chat interface.

## Architecture Overview

The frontend uses a **component-driven architecture** with 6 focused components instead of a monolithic approach. Each component has a single responsibility and stays under 100 lines when possible.

```
components/
├── ChatInterface.tsx      # Main orchestrator (70 lines)
├── ChatHeader.tsx         # Header with connection status (29 lines)
├── MessageList.tsx        # Message display and scrolling (79 lines)
├── MessageInput.tsx       # Auto-resizing input with shortcuts (99 lines)
├── FileAttachment.tsx     # File upload with drag-and-drop (78 lines)
└── ErrorBoundary.tsx      # Error handling and recovery (69 lines)
```

## Component Details

### ChatInterface.tsx - Main Orchestrator
**Purpose**: Coordinates all components and manages data flow  
**Size**: 70 lines  
**Responsibilities**:
- File upload processing and API calls to backend
- WebSocket integration via `useWebSocket` hook
- Error boundary wrapping for fault tolerance
- Component composition and prop passing

**Key Features**:
```typescript
export const ChatInterface: React.FC = () => {
  const { messages, status, isConnected } = useChatStore();
  const { sendMessage } = useWebSocket();

  const handleSubmit = async (message: string, files: File[]) => {
    // File upload logic
    // Message sending via WebSocket
  };

  return (
    <ErrorBoundary>
      <div className="flex flex-col h-screen bg-background">
        <ChatHeader isConnected={isConnected} />
        <MessageList messages={messages} status={status} />
        <MessageInput onSubmit={handleSubmit} disabled={!isConnected} />
      </div>
    </ErrorBoundary>
  );
};
```

### ChatHeader.tsx - Connection Status Header
**Purpose**: Display connection status and app title  
**Size**: 29 lines  
**Accessibility**: Full ARIA support, semantic header role

**Features**:
- Animated connection indicator (green/red dot)
- Live connection status text
- Responsive design with consistent spacing
- Proper semantic HTML structure

**Implementation**:
```typescript
export const ChatHeader: React.FC<ChatHeaderProps> = ({ isConnected }) => {
  return (
    <header className="bg-card shadow-sm border-b p-4" role="banner">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-card-foreground">Agent Chat</h1>
        <div role="status" aria-live="polite">
          <div className={cn("w-3 h-3 rounded-full", isConnected ? 'bg-green-500' : 'bg-destructive')} />
          <span>{isConnected ? 'Connected' : 'Disconnected'}</span>
        </div>
      </div>
    </header>
  );
};
```

### MessageList.tsx - Message Display
**Purpose**: Display chat messages with auto-scrolling and expandable execution plans  
**Size**: ~250 lines  
**Accessibility**: Article structure, screen reader support, collapsible content

**Features**:
- Auto-scrolling to latest messages with smooth behavior
- Message bubbles with proper alignment (user right, assistant left)
- Timestamp display with proper time formatting
- File attachment indicators with accessible labels
- Status indicators with loading animations
- **Expandable execution plans** when planner agent is active
- **"Agents assemble!" message detection** with special UI treatment
- **Message-specific execution plan display** using shadcn Collapsible
- Semantic article structure for each message
- Real-time and historical execution plan access

**Special Message Handling**:
The component includes special handling for "Agents assemble!" messages that indicate planner activation:

```typescript
// Helper function to detect special messages
const isAgentsAssembleMessage = (message: ChatMessage) => {
  return message.sender === 'assistant' && 
         message.message === 'Agents assemble!' && 
         message.messageId;
};

// Separate component for execution plans (no longer nested in message bubbles)
const ExecutionPlanDisplay: React.FC<{
  messageId: number;
  isExpanded: boolean;
  onToggleExpansion: () => void;
}> = ({ messageId, isExpanded, onToggleExpansion }) => {
  const { plannerInfo, loading } = usePlannerInfo(messageId);
  
  if (!plannerInfo?.has_planner || !plannerInfo.execution_plan) {
    return null;
  }
  
  return (
    <article className="w-full">
      <Collapsible open={isExpanded} onOpenChange={onToggleExpansion}>
        <CollapsibleTrigger className="flex items-center space-x-2 p-3">
          {isExpanded ? <ChevronUp /> : <ChevronDown />}
          <span>{isExpanded ? 'Hide' : 'Show'} execution plan</span>
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className="bg-muted/50 rounded-md p-4 w-full">
            <div className="text-muted-foreground mb-2 font-medium">
              Execution Plan:
            </div>
            <RichMarkdownRenderer content={plannerInfo.execution_plan} />
          </div>
        </CollapsibleContent>
      </Collapsible>
    </article>
  );
};
```

**Message Structure**:
```typescript
<main className="flex-1 overflow-y-auto p-4" role="main" aria-live="polite">
  {messages.map((message) => {
    const isAgentsAssemble = isAgentsAssembleMessage(message);
    
    return (
      <div key={message.id} className="space-y-4">
        {/* All messages now render as regular messages */}
        <article role="article" aria-label={`Message from ${message.sender}`}>
          <div className={cn(
            "message-bubble", 
            message.sender === 'user' ? 'user-styles' : 
            isAgentsAssemble ? 'agents-assemble-styles' : 'assistant-styles'
          )}>
            <RichMarkdownRenderer content={message.message} />
            <time dateTime={message.timestamp.toISOString()}>
              {message.timestamp.toLocaleTimeString()}
            </time>
          </div>
        </article>
        
        {/* Execution plan rendered separately after agents assemble messages */}
        {isAgentsAssemble && message.messageId && (
          <ExecutionPlanDisplay
            messageId={message.messageId}
            isExpanded={expandedMessages.has(message.id)}
            onToggleExpansion={() => toggleMessageExpansion(message.id)}
          />
        )}
      </div>
    );
  })}
</main>
```

### MessageInput.tsx - Advanced Input Component
**Purpose**: Handle message input with file attachment support  
**Size**: 99 lines  
**Accessibility**: Full keyboard navigation, ARIA labels

**Advanced Features**:
- **Auto-resizing textarea** that grows with content (min 44px, max 120px)
- **Keyboard shortcuts**: Enter to send, Shift+Enter for new line
- **File attachment integration** with FileAttachment component
- **Loading states** with proper disabled states
- **Form validation** and submission handling
- **Accessibility** with proper labels and form structure

**Key Implementation**:
```typescript
const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    handleSubmit(e as unknown as React.FormEvent);
  }
};

// Auto-resize logic
const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
  setInputMessage(e.target.value);
  if (textareaRef.current) {
    textareaRef.current.style.height = 'auto';
    textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
  }
};
```

### FileAttachment.tsx - File Upload Management
**Purpose**: Handle file selection, preview, and removal  
**Size**: 78 lines  
**Accessibility**: Screen reader support, keyboard navigation

**Features**:
- **Multiple file selection** with drag-and-drop support
- **File type validation** (images, PDFs, CSVs, text files)
- **File preview** with individual removal capability
- **Accessible file input** with proper labeling
- **File size and type display** with truncated names
- **Disabled states** during form submission

**Component Structure**:
```typescript
export const FileAttachment: React.FC<FileAttachmentProps> = ({
  selectedFiles, onFileSelect, onFileRemove, disabled
}) => {
  return (
    <div className="space-y-2">
      {/* File preview list */}
      {selectedFiles.length > 0 && (
        <div role="list" aria-label="Selected files">
          {selectedFiles.map((file, index) => (
            <div key={index} role="listitem" className="file-tag">
              <span title={file.name}>{file.name}</span>
              <button onClick={() => onFileRemove(index)} aria-label={`Remove ${file.name}`}>
                <X className="h-3 w-3" />
              </button>
            </div>
          ))}
        </div>
      )}
      
      {/* Hidden file input */}
      <input type="file" ref={fileInputRef} className="sr-only" multiple />
      <button onClick={() => fileInputRef.current?.click()} aria-label="Attach files">
        <Paperclip className="h-4 w-4" />
      </button>
    </div>
  );
};
```

### Collapsible.tsx - Collapsible UI Component
**Purpose**: Provides expandable/collapsible content sections  
**Size**: 30 lines  
**Accessibility**: Full ARIA support from Radix UI primitives

**Features**:
- Smooth expand/collapse animations
- Keyboard navigation support  
- ARIA attributes for screen readers
- Composable trigger and content components
- Used for execution plan expansion in MessageList

**Usage**:
```typescript
<Collapsible open={isOpen} onOpenChange={setIsOpen}>
  <CollapsibleTrigger>Toggle content</CollapsibleTrigger>
  <CollapsibleContent>Expandable content here</CollapsibleContent>
</Collapsible>
```

### ErrorBoundary.tsx - Error Handling Component
**Purpose**: Catch and handle React component errors gracefully  
**Size**: 69 lines  
**Accessibility**: Proper error display with ARIA roles

**Features**:
- **Error catching** for all child components
- **User-friendly error messages** with recovery options
- **Development error details** (stack traces in dev mode)
- **Reset functionality** to recover from errors
- **Accessible error display** with proper ARIA roles and live regions

**Error Boundary Implementation**:
```typescript
export class ErrorBoundary extends Component<Props, State> {
  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div className="error-container" role="alert" aria-live="assertive">
          <AlertCircle className="h-12 w-12 text-destructive mb-4" />
          <h2>Something went wrong</h2>
          <p>An unexpected error occurred. Please try refreshing the page.</p>
          <button onClick={this.handleReset}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Try Again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
```

## Design Patterns

### Component Architecture Principles
1. **Single Responsibility**: Each component has one clear purpose
2. **Composition over Inheritance**: Components compose together cleanly
3. **Props Interface**: Well-defined TypeScript interfaces for all props
4. **Error Boundaries**: Fault tolerance at component level
5. **Accessibility First**: ARIA labels, semantic HTML, keyboard navigation

### State Management Pattern
```typescript
// Global state via Zustand
const { messages, status, isConnected } = useChatStore();

// Local component state for UI-specific data
const [inputMessage, setInputMessage] = useState('');
const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
```

### Styling Pattern with shadcn/ui
```typescript
import { cn } from '@/lib/utils';

// Conditional styling with cn() helper
className={cn(
  "base-styles",
  isActive && "active-styles",
  className // Allow prop-based overrides
)}
```

## Development Guidelines

### Adding New Components

1. **Create component file** in `src/components/`:
```typescript
'use client';

import React from 'react';
import { cn } from '@/lib/utils';

interface NewComponentProps {
  children?: React.ReactNode;
  className?: string;
  // ... other props
}

export const NewComponent: React.FC<NewComponentProps> = ({
  children,
  className,
  ...props
}) => {
  return (
    <div className={cn("base-styles", className)} {...props}>
      {children}
    </div>
  );
};
```

2. **Follow accessibility guidelines**:
   - Use semantic HTML elements
   - Add ARIA labels and roles
   - Ensure keyboard navigation works
   - Test with screen readers

3. **Keep components focused**:
   - Single responsibility principle
   - Under 100 lines when possible
   - Clear prop interfaces
   - Proper error handling

### Component Testing Strategy

```typescript
// Unit test structure
import { render, screen } from '@testing-library/react';
import { NewComponent } from './NewComponent';

describe('NewComponent', () => {
  it('renders with accessibility features', () => {
    render(<NewComponent aria-label="Test component" />);
    expect(screen.getByLabelText('Test component')).toBeInTheDocument();
  });

  it('handles user interactions', async () => {
    const handleClick = jest.fn();
    render(<NewComponent onClick={handleClick} />);
    // Test interactions
  });
});
```

### Performance Considerations

1. **React.memo** for expensive components:
```typescript
export const ExpensiveComponent = React.memo<Props>(({ data }) => {
  // Component implementation
});
```

2. **useCallback** for event handlers:
```typescript
const handleSubmit = useCallback(async (data: FormData) => {
  // Handle submission
}, [dependency]);
```

3. **Proper dependency arrays** in useEffect:
```typescript
useEffect(() => {
  // Effect logic
}, [specificDependency]); // Not []
```

## Hooks Integration

The components integrate with custom React hooks for enhanced functionality:

### usePlannerInfo Hook
**Purpose**: Fetch and manage planner information for specific messages  
**Location**: `src/hooks/usePlannerInfo.ts`  
**Features**:
- Message-specific planner data fetching from `/messages/{messageId}/planner-info`
- Real-time WebSocket updates prioritised over API calls
- Loading states and error handling
- Automatic refetch capability

**Usage in Components**:
```typescript
const ExecutionPlanDisplay = ({ messageId }) => {
  const { plannerInfo, loading, error, refetch } = usePlannerInfo(messageId);
  
  // Display execution plan if available
  if (plannerInfo?.has_planner && plannerInfo.execution_plan) {
    return (
      <div className="bg-muted/50 rounded-md p-4">
        <RichMarkdownRenderer content={plannerInfo.execution_plan} />
      </div>
    );
  }
  return null;
};
```

**Hook Implementation**:
```typescript
export const usePlannerInfo = (messageId: number | null): UsePlannerInfoResult => {
  const [plannerInfo, setPlannerInfo] = useState<PlannerInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const currentExecutionPlan = useChatStore((state) => state.currentExecutionPlan);

  // Prioritise real-time WebSocket data
  useEffect(() => {
    if (currentExecutionPlan?.execution_plan) {
      setPlannerInfo(currentExecutionPlan);
      return;
    }
    
    // Fallback to API for specific message
    if (messageId) fetchPlannerInfo();
  }, [messageId, currentExecutionPlan]);

  return { plannerInfo, loading, error, refetch: fetchPlannerInfo };
};
```

## Future Enhancements

### Planned Component Additions
- **MessageBubble**: Extracted individual message component
- **TypingIndicator**: Real-time typing status display
- **ChatSettings**: Model and temperature controls
- **RouterList**: Multiple router management
- **VoiceInput**: Speech-to-text functionality

### Component Improvements
- **Virtual scrolling** for large message lists
- **Message reactions** (like/dislike functionality)
- **Message editing** capabilities
- **Export functionality** for routers
- **Advanced file preview** with thumbnails

### Accessibility Enhancements
- **High contrast mode** support
- **Reduced motion** preferences
- **Voice navigation** improvements
- **Screen reader** optimizations
- **Keyboard shortcut** customization

The component architecture provides a solid foundation for these future enhancements while maintaining code quality and accessibility standards.