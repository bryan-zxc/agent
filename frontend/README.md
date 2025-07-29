# Frontend - Agent Chat Interface

Next.js 14+ application providing a real-time chat interface for the AI agent system.

## Structure

```
frontend/
├── src/
│   ├── app/               # Next.js App Router pages
│   │   ├── page.tsx      # Main chat interface page
│   │   ├── layout.tsx    # Root layout
│   │   └── globals.css   # Global styles
│   ├── components/        # React components
│   │   └── ChatInterface.tsx  # Main chat UI component
│   ├── hooks/            # Custom React hooks
│   │   └── useWebSocket.ts    # WebSocket connection hook
│   ├── stores/           # Zustand state management
│   │   └── chatStore.ts      # Chat state and actions
│   └── types/            # TypeScript type definitions (imports from shared/)
├── package.json          # Node.js dependencies
├── tailwind.config.ts    # TailwindCSS configuration
├── tsconfig.json         # TypeScript configuration
└── Dockerfile           # Container configuration
```

## Features

### Real-time Chat Interface
- **WebSocket communication** - Instant messaging with the agent
- **File upload support** - Drag-and-drop or click to upload images, PDFs, CSVs
- **Status indicators** - Real-time agent processing status
- **Message history** - Persistent conversation display
- **Auto-scroll** - Automatically scrolls to latest messages

### User Experience
- **Responsive design** - Works on desktop and mobile
- **File preview** - Shows selected files before sending
- **Connection status** - Visual indicator of WebSocket connection
- **Error handling** - Graceful error display and recovery
- **Typing indicators** - Shows when agent is processing

## Development Setup

### Prerequisites
- Node.js 20+
- npm or yarn

### Installation

1. **Install dependencies:**
   ```bash
   npm install
   ```

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

## Key Components

### ChatInterface.tsx
Main chat component that handles:
- Message display and scrolling
- File upload and preview
- Form submission and validation
- WebSocket message handling

### useWebSocket.ts Hook
Custom hook that manages:
- WebSocket connection lifecycle
- Message sending and receiving
- Connection status tracking
- Automatic reconnection

### chatStore.ts (Zustand)
Global state management for:
- Chat messages array
- Agent status and processing state
- Connection status
- Model and temperature settings

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

## Styling

### TailwindCSS
- **Utility-first** CSS framework
- **Responsive design** with mobile-first approach
- **Dark mode support** (can be extended)
- **Custom color palette** for chat bubbles and status

### Key Design Elements
- **User messages**: Blue background, right-aligned
- **Agent messages**: White background with border, left-aligned
- **Status indicators**: Animated spinner with status text
- **File attachments**: Small tags showing filenames

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
1. Create component in `src/components/`
2. Import shared types from `../../../shared/types`
3. Use Zustand store for state management
4. Follow existing naming conventions

### Extending Chat Features
1. Update `ChatMessage` interface in shared types
2. Modify `chatStore.ts` for new state
3. Update `ChatInterface.tsx` for UI changes
4. Test WebSocket message handling

### Styling Guidelines
- Use TailwindCSS utility classes
- Follow mobile-first responsive design
- Maintain consistent spacing (4px grid)
- Use semantic color names

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
