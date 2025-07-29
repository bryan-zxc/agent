# Frontend - Agent Chat Interface

Next.js 15 application with shadcn/ui components providing a modern, accessible real-time chat interface for the AI agent system.

## Structure

```
frontend/
├── src/
│   ├── app/               # Next.js App Router
│   │   ├── page.tsx      # Main chat interface page
│   │   ├── layout.tsx    # Root layout with fonts
│   │   └── globals.css   # Global styles with CSS variables
│   ├── components/        # Modular React components
│   │   ├── ChatInterface.tsx    # Main orchestrator (70 lines)
│   │   ├── ChatHeader.tsx       # Header with connection status
│   │   ├── MessageList.tsx      # Message display and scrolling
│   │   ├── MessageInput.tsx     # Auto-resizing input with shortcuts
│   │   ├── FileAttachment.tsx   # File upload with drag-and-drop
│   │   └── ErrorBoundary.tsx    # Error handling and recovery
│   ├── hooks/            # Custom React hooks
│   │   └── useWebSocket.ts    # WebSocket connection hook
│   ├── lib/              # Utility functions
│   │   └── utils.ts      # cn helper for Tailwind classes
│   └── stores/           # Zustand state management
│       └── chatStore.ts      # Chat state and actions
├── components.json       # shadcn/ui configuration
├── package.json          # Node.js dependencies with shadcn/ui
├── tailwind.config.ts    # Tailwind with design tokens
├── tsconfig.json         # TypeScript configuration
└── Dockerfile           # Container configuration
```

## Features

### Real-time Chat Interface
- **WebSocket communication** - Instant messaging with automatic reconnection
- **File upload support** - Drag-and-drop or click to upload images, PDFs, CSVs
- **Status indicators** - Real-time agent processing status with animations
- **Message history** - Persistent conversation display with timestamps
- **Auto-scroll** - Automatically scrolls to latest messages with smooth behavior

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
- **Design tokens** - Systematic color, spacing, and typography scales
- **Component modularity** - 6 focused components vs monolithic approach

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
   - shadcn/ui dependencies (@radix-ui/react-slot, class-variance-authority, clsx, tailwind-merge)
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

### ChatInterface.tsx (Main Orchestrator - 70 lines)
Coordinates all components and handles:
- File upload processing and API calls
- WebSocket integration via useWebSocket hook
- Error boundary wrapping
- Component composition and data flow

### ChatHeader.tsx (Header Component - 29 lines)
Header with connection status display:
- Connection indicator (green/red dot with animation)
- Live connection status text
- Proper ARIA labels and semantic header role
- Responsive design with consistent spacing

### MessageList.tsx (Message Display - 79 lines)
Message display and conversation management:
- Auto-scrolling to latest messages
- Message bubbles with proper alignment (user/assistant)
- Timestamp display with proper time formatting
- File attachment indicators
- Status indicators with loading animations
- Semantic article structure for each message

### MessageInput.tsx (Input Component - 99 lines)
Advanced input handling:
- Auto-resizing textarea that grows with content
- Keyboard shortcuts (Enter to send, Shift+Enter for new line)
- File attachment integration
- Send button with loading states
- Form validation and error handling
- Accessibility labels and proper form structure

### FileAttachment.tsx (File Upload - 78 lines)
File upload and management:
- Drag-and-drop file selection
- Multiple file support with preview
- File type validation (images, PDFs, CSVs)
- Individual file removal capability
- Accessible file input with proper labeling
- File size and type display

### ErrorBoundary.tsx (Error Handling - 69 lines)
Comprehensive error handling:
- Catches and displays React component errors
- User-friendly error messages
- Reset functionality to recover from errors
- Development error details (stack traces)
- Accessible error display with proper ARIA roles

### useWebSocket.ts Hook (Custom Hook)
WebSocket connection management:
- Automatic connection lifecycle management
- Message sending and receiving
- Connection status tracking with live updates
- Automatic reconnection on disconnect
- Error handling and status updates

### chatStore.ts (Zustand State)
Global state management:
- Chat messages array with proper typing
- Agent status and processing state
- Connection status tracking
- Model and temperature settings
- TypeScript interfaces for type safety

## State Management

### Chat Store Structure
```typescript
interface ChatStore {
  messages: ChatMessage[];
  status: AgentStatus;
  isConnected: boolean;
  currentModel: string;
  temperature: number;
  
  // Actions
  addMessage: (message: ChatMessage) => void;
  updateStatus: (status: AgentStatus) => void;
  setConnected: (connected: boolean) => void;
  // ... other actions
}
```

### Message Flow
1. User types message and selects files
2. Files uploaded to backend via HTTP POST
3. Message sent via WebSocket with file paths
4. Agent responses received and displayed
5. Status updates shown during processing

## Design System

### shadcn/ui + Tailwind CSS
- **Component library**: shadcn/ui for consistent, accessible components
- **Design tokens**: CSS variables for systematic theming
- **Utility-first**: Tailwind CSS for rapid styling
- **Mobile-first**: Progressive enhancement from mobile to desktop
- **Accessibility**: WCAG-compliant components with proper ARIA support

### CSS Variable System
```css
:root {
  --background: 0 0% 100%;           /* Base background */
  --foreground: 222.2 84% 4.9%;      /* Text color */
  --primary: 221.2 83.2% 53.3%;      /* Primary brand color */
  --secondary: 210 40% 96%;          /* Secondary backgrounds */
  --muted: 210 40% 96%;              /* Muted content */
  --border: 214.3 31.8% 91.4%;      /* Border colors */
  /* ... additional design tokens */
}
```

### Component Styling Patterns
- **User messages**: Primary color background, right-aligned with proper contrast
- **Agent messages**: Card background with border, left-aligned with semantic structure
- **Status indicators**: Animated spinner with accessible loading states
- **File attachments**: Secondary background tags with removal buttons
- **Interactive elements**: Focus rings, hover states, disabled states
- **Responsive breakpoints**: sm, md, lg classes for progressive enhancement

### Accessibility Features
- **Semantic HTML**: Proper header, main, footer, article structure
- **ARIA labels**: Screen reader support for all interactive elements
- **Focus management**: Visible focus rings and logical tab order
- **Color contrast**: WCAG AA compliant color combinations
- **Keyboard navigation**: Full keyboard accessibility

## API Integration

### WebSocket Messages
Sends JSON to `ws://localhost:8000/ws`:
```typescript
{
  message: string;
  files: string[];
  model: string;
  temperature: number;
}
```

### File Upload
HTTP POST to `/upload` endpoint:
```typescript
const formData = new FormData();
formData.append('file', file);
fetch('/upload', { method: 'POST', body: formData });
```

## Configuration

### Environment Variables
- `NEXT_PUBLIC_API_URL` - Backend HTTP URL (default: http://localhost:8000)
- `NEXT_PUBLIC_WS_URL` - Backend WebSocket URL (default: ws://localhost:8000)
- `NODE_ENV` - Environment (development/production)

### TypeScript Configuration
- **Strict mode enabled** for type safety
- **Path aliases** configured (@/* for src/*)
- **Shared types** imported from ../shared/types

## Development Workflow

### Adding New Components
1. Create component in `src/components/` following the pattern:
   ```typescript
   'use client';
   
   import { cn } from '@/lib/utils';
   import { ComponentProps } from '../../../shared/types';
   
   export const NewComponent: React.FC<ComponentProps> = ({ className, ...props }) => {
     return (
       <div className={cn("base-styles", className)} {...props}>
         {/* Component content */}
       </div>
     );
   };
   ```

2. Use shadcn/ui patterns and TypeScript interfaces
3. Implement proper accessibility (ARIA labels, semantic HTML)
4. Follow component size guidelines (< 100 lines when possible)

### Extending Chat Features
1. Update shared types in `../../../shared/types/index.ts`
2. Modify `chatStore.ts` for new state management
3. Create focused components for new features (don't extend existing ones)
4. Add error boundaries around new functionality
5. Test accessibility and responsive design

### Styling Guidelines
- **Use shadcn/ui components** as foundation, extend with Tailwind utilities
- **CSS variables**: Prefer design tokens over hardcoded colors
- **Mobile-first**: Start with mobile styles, enhance for larger screens
- **Accessibility**: Always include focus states, ARIA labels, semantic HTML
- **Component patterns**: Use `cn()` helper for conditional classes

## Docker Development

Build and run with Docker:
```bash
docker build -t agent-frontend .
docker run -p 3000:3000 agent-frontend
```

Or use docker-compose from the root directory:
```bash
docker-compose up frontend
```

## Available Scripts

- `npm run dev` - Start development server
- `npm run build` - Build for production
- `npm run start` - Start production server
- `npm run lint` - Run ESLint
- `npm run type-check` - Run TypeScript compiler check

## Troubleshooting

### Common Issues
1. **WebSocket connection fails** - Check backend is running on port 8000
2. **File upload errors** - Verify CORS settings on backend
3. **Type errors** - Ensure shared types are properly imported
4. **Styling issues** - Check TailwindCSS configuration

### Hot Reload
Next.js automatically reloads on file changes. If it stops working:
```bash
rm -rf .next
npm run dev
```

### Network Issues
Check browser console for WebSocket connection errors:
- Ensure backend WebSocket endpoint is accessible
- Verify no firewall blocking connections
- Check browser WebSocket support
