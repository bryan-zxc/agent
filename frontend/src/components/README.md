# Components - React UI Components

React components for the chat interface and user interactions.

## Structure

```
components/
└── ChatInterface.tsx   # Main chat interface component
```

## Components Overview

### ChatInterface.tsx
The primary chat component that provides the complete user interface for interacting with the AI agent.

#### Features
- **Real-time messaging** - WebSocket-based chat communication
- **File upload** - Drag-and-drop and click-to-upload functionality
- **Message display** - Scrollable chat history with timestamps
- **Status indicators** - Visual feedback for agent processing states
- **Responsive design** - Works on desktop and mobile devices

#### Props
```typescript
// Currently no props - uses global state via Zustand
export const ChatInterface: React.FC = () => { ... }
```

#### Key Functionality

**Message Management:**
- Displays chat messages from Zustand store
- Auto-scrolls to newest messages
- Shows file attachments as tags
- Timestamps for each message

**File Upload:**
- Supports multiple file selection
- File type validation (images, PDFs, CSVs)
- Upload progress indication
- File preview before sending

**WebSocket Integration:**
- Uses `useWebSocket` hook for real-time communication
- Handles connection status display
- Manages message sending and receiving
- Error handling and recovery

**UI States:**
- Connection indicator (green/red dot)
- Processing status with spinner
- Error states with user-friendly messages
- Empty state when no messages

#### Styling
- **TailwindCSS** utility classes
- **Responsive design** with mobile-first approach
- **Accessible** with proper ARIA labels
- **Dark/light mode** compatible (extensible)

#### Usage Example
```typescript
import { ChatInterface } from '@/components/ChatInterface';

export default function ChatPage() {
  return <ChatInterface />;
}
```

## Design Patterns

### Component Architecture
- **Functional components** with React hooks
- **Global state** via Zustand store
- **Custom hooks** for complex logic (WebSocket)
- **TypeScript** for type safety

### State Management
```typescript
// Uses Zustand store for global state
const { messages, status, isConnected } = useChatStore();
const { sendMessage } = useWebSocket();
```

### Event Handling
```typescript
const handleSubmit = async (e: React.FormEvent) => {
  e.preventDefault();
  // File upload logic
  // Message sending logic
  // State updates
};
```

## Styling Guidelines

### TailwindCSS Classes
- **Layout**: `flex`, `grid`, `space-y-4`
- **Colors**: `bg-blue-500`, `text-white`, `border-gray-300`
- **Responsive**: `sm:text-base`, `lg:max-w-md`
- **States**: `hover:bg-blue-600`, `disabled:bg-gray-300`

### Component Structure
```tsx
<div className="flex flex-col h-screen bg-gray-50">
  {/* Header */}
  <div className="bg-white shadow-sm border-b p-4">
    {/* Header content */}
  </div>
  
  {/* Messages */}
  <div className="flex-1 overflow-y-auto p-4 space-y-4">
    {/* Message list */}
  </div>
  
  {/* Input form */}
  <div className="bg-white border-t p-4">
    {/* Input form */}
  </div>
</div>
```

## Development Guidelines

### Adding New Components
1. Create component file in `src/components/`
2. Use TypeScript with proper interfaces
3. Import shared types from `../../../shared/types`
4. Follow existing naming conventions
5. Add proper TypeScript return types

### Component Template
```typescript
'use client';

import React from 'react';
import { SomeSharedType } from '../../../shared/types';

interface ComponentNameProps {
  prop1: string;
  prop2?: number;
}

export const ComponentName: React.FC<ComponentNameProps> = ({
  prop1,
  prop2 = 0
}) => {
  // Component logic here
  
  return (
    <div className="component-styles">
      {/* Component JSX */}
    </div>
  );
};
```

### Best Practices

#### Performance
- Use `React.memo` for expensive components
- Implement proper dependency arrays in `useEffect`
- Avoid creating objects in render functions
- Use `useCallback` for event handlers when needed

#### Accessibility
- Add `aria-label` and `role` attributes
- Use semantic HTML elements
- Ensure keyboard navigation works
- Test with screen readers

#### Error Handling
```typescript
const [error, setError] = useState<string | null>(null);

try {
  // Component logic
} catch (err) {
  setError(err instanceof Error ? err.message : 'Unknown error');
}
```

## Testing Considerations

### Unit Testing
```typescript
// Example test structure
import { render, screen } from '@testing-library/react';
import { ChatInterface } from './ChatInterface';

describe('ChatInterface', () => {
  it('renders chat interface', () => {
    render(<ChatInterface />);
    expect(screen.getByRole('textbox')).toBeInTheDocument();
  });
});
```

### Integration Testing
- Test WebSocket connection handling
- Test file upload functionality
- Test message sending and receiving
- Test error states and recovery

## Future Enhancements

### Planned Components
- `MessageBubble` - Individual message component
- `FilePreview` - File attachment preview
- `StatusIndicator` - Reusable status display
- `TypingIndicator` - Shows when agent is typing
- `ChatSettings` - Model and temperature controls

### Feature Additions
- **Message reactions** - Like/dislike functionality
- **Message editing** - Edit sent messages
- **Message search** - Search through chat history
- **Export conversation** - Save chat as file
- **Voice input** - Speech-to-text functionality

### Performance Optimizations
- **Virtual scrolling** for large message lists
- **Image lazy loading** for file previews
- **Message pagination** for better performance
- **Debounced input** for real-time features