// Shared types between frontend and backend
export interface ChatMessage {
  id: string;
  message: string;
  sender: 'user' | 'assistant';
  timestamp: Date;
  files?: string[];
  model?: string;
  temperature?: number;
}

export interface WebSocketMessage {
  type: 'message' | 'status' | 'response' | 'error';
  data: any;
  timestamp?: Date;
}

export interface FileUpload {
  filename: string;
  path: string;
  size: number;
  type: string;
}

export interface AgentStatus {
  status: 'idle' | 'processing' | 'analyzing' | 'error';
  message?: string;
  progress?: number;
}

export interface ConversationHistory {
  id: string;
  messages: ChatMessage[];
  createdAt: Date;
  updatedAt: Date;
}