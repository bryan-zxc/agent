// Shared types between frontend and backend
export interface ChatMessage {
  id: string;
  message: string;
  sender: 'user' | 'assistant';
  timestamp: Date;
  files?: string[];
  model?: string;
  temperature?: number;
  messageId?: number; // Database message ID for planner linking
}

export interface WebSocketMessage {
  type: 'message' | 'status' | 'response' | 'error' | 'message_history' | 'load_router' | 'approval_request' | 'approval_response' | 'plamarination_status';
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

export interface ApprovalRequest {
  request_id: string;
  plan: string;
  template?: string;
  findings?: string;
  router_id: string;
}

export interface ApprovalResponse {
  request_id: string;
  approved: boolean;
  feedback?: string;
}

export type PlamarinationStatus = 'planning' | 'waiting_approval' | 'revising' | 'approved' | null;