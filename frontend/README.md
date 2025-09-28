# Frontend - Agent Chat Interface

Next.js 15 application with shadcn/ui components providing a modern, accessible real-time chat interface for the AI agent system with frontend-orchestrated execution.

## Structure

```
frontend/
├── src/
│   ├── app/               # Next.js App Router
│   │   ├── page.tsx      # Main chat interface page
│   │   ├── layout.tsx    # Root layout with fonts
│   │   └── globals.css   # Global styles with CSS variables
│   ├── components/        # Modular React components
│   │   ├── ChatInterface.tsx    # Main orchestrator
│   │   ├── ChatHeader.tsx       # Header with connection status
│   │   ├── MessageList.tsx      # Message display and scrolling
│   │   ├── MessageInput.tsx     # Auto-resizing input with shortcuts
│   │   ├── FileAttachment.tsx   # File upload with drag-and-drop
│   │   ├── ErrorBoundary.tsx    # Error handling and recovery
│   │   └── ModeToggle.tsx       # Mode selector (auto/agent)
│   ├── hooks/            # Custom React hooks
│   │   └── useWebSocket.ts    # WebSocket connection hook
│   ├── lib/              # Utility functions
│   │   └── utils.ts      # cn helper for Tailwind classes
│   └── stores/           # Zustand state management
│       └── chatStore.ts      # Chat state and actions
├── components.json       # shadcn/ui configuration
├── package.json          # Node.js dependencies
├── tailwind.config.ts    # Tailwind with design tokens
├── tsconfig.json         # TypeScript configuration
└── Dockerfile           # Container configuration
```

## Architecture Overview

### Frontend-Orchestrated Execution
The frontend controls the entire execution flow:
1. Sends messages to backend via WebSocket
2. Receives status updates and tool requests
3. Orchestrates MCP tool execution
4. Displays real-time progress and results

### Key Changes from Previous Architecture
- No planner entities or planner display components
- No background task queue polling
- Direct synchronous execution through MCP tools
- Simplified state management without planner tracking

## Features

### Real-time Chat Interface
- **WebSocket communication** - Instant messaging with automatic reconnection
- **File upload support** - Drag-and-drop or click to upload images, PDFs, CSVs
- **Status indicators** - Real-time agent processing status
- **Message history** - Persistent router display with timestamps
- **Auto-scroll** - Automatically scrolls to latest messages
- **Mode selection** - Choose between auto and agent processing modes

### Modern User Experience
- **Mobile-first responsive design** - Progressive enhancement from mobile to desktop
- **Accessibility-first** - Screen reader support, keyboard navigation, ARIA labels
- **File preview** - Shows selected files with removal capability
- **Connection status** - Visual indicator with live updates
- **Error boundaries** - Graceful error display and recovery options
- **Auto-resizing input** - Textarea grows with content, keyboard shortcuts
- **Loading states** - Proper loading indicators and disabled states
- **Semantic HTML** - Header, main, footer structure with proper roles

### Design System
- **shadcn/ui components** - Modern, accessible component library
- **CSS variables** - Consistent theming with dark/light mode support
- **Design tokens** - Systematic colour, spacing, and typography scales
- **Component modularity** - Focused components vs monolithic approach
- **Shading-based UI** - Uses background colours instead of borders

### Processing Modes
The interface supports two primary processing modes:

#### Auto Mode (Default)
- Intelligently routes between simple and complex processing
- Simple queries get immediate responses
- Complex queries trigger agent mode with MCP tools

#### Agent Mode
- Advanced processing with MCP tool execution
- Frontend orchestrates tool calls
- Real-time status updates during execution
- Direct synchronous processing

## Development Setup

### Prerequisites
- Node.js 20+
- npm or yarn

### Installation

1. **Install dependencies:**
   ```bash
   npm install
   ```

   This installs:
   - Next.js 15 with App Router
   - shadcn/ui dependencies (@radix-ui components)
   - Lucide React icons
   - Zustand for state management

2. **Set environment variables (optional):**
   Create `.env.local`:
   ```bash
   NEXT_PUBLIC_API_URL=http://localhost:8000
   NEXT_PUBLIC_WS_URL=ws://localhost:8000
   ```

### Running the Development Server

```bash
npm run dev
```

Application will be available at http://localhost:3000

### Build for Production

```bash
npm run build
npm start
```

## Component Architecture

### ChatInterface.tsx (Main Orchestrator)
Coordinates all components and handles:
- File upload processing and API calls
- WebSocket integration via useWebSocket hook
- Error boundary wrapping
- Component composition and data flow
- MCP tool orchestration

### ChatHeader.tsx (Header Component)
Header with connection status display:
- Connection indicator (green/red dot)
- Live connection status text
- Proper ARIA labels and semantic header role

### MessageList.tsx (Message Display)
Message display and router management:
- Auto-scrolling to latest messages
- Message bubbles with proper alignment
- Timestamp display
- File attachment indicators
- Status indicators with loading animations

### MessageInput.tsx (Input Component)
Advanced input handling:
- Auto-resizing textarea
- File attachment display
- Keyboard shortcuts (Enter to send)
- Disabled state during processing

### FileAttachment.tsx (File Handler)
File upload management:
- Drag-and-drop support
- File type validation
- Preview of selected files
- Remove file capability

### ModeToggle.tsx (Mode Selector)
Processing mode selection:
- Toggle between auto and agent modes
- Visual mode indicators
- Status-aware disabling

## State Management

### Zustand Store (chatStore.ts)
Centralised state management for:
- Messages array
- Router ID
- Connection status
- Processing status
- Selected files
- Current mode

### WebSocket Hook (useWebSocket.ts)
Manages WebSocket lifecycle:
- Automatic connection on mount
- Reconnection logic
- Message handling
- Status updates
- Tool execution coordination

## WebSocket Protocol

### Message Types
```typescript
// User message
{
  type: "message",
  message: string,
  files?: string[],
  router_id?: string
}

// Status update
{
  type: "status",
  status: "thinking" | "executing" | "active",
  router_id: string
}

// Tool execution request
{
  type: "tool_call",
  tool: string,
  arguments: object,
  router_id: string
}

// Mode update
{
  type: "mode_updated",
  mode: "auto" | "agent",
  router_id: string
}
```

## Testing

Run the test suite:
```bash
npm test
```

Run linting:
```bash
npm run lint
```

## Performance Optimisations

- Component memoisation where appropriate
- Virtual scrolling for long message lists (future)
- Debounced input handling
- Lazy loading of components
- Image optimisation with Next.js Image

## Accessibility

- ARIA labels on all interactive elements
- Keyboard navigation support
- Screen reader announcements
- Focus management
- Semantic HTML structure
- Colour contrast compliance

## Browser Support

- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

## Future Enhancements

- Execution plan display UI (when router.execution_plan is available)
- Message search and filtering
- Export conversation history
- Voice input/output
- Mobile application