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
  type: 'message' | 'status' | 'response' | 'error' | 'execution_plan_update';
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

export interface PlannerInfo {
  has_planner: boolean;
  execution_plan: string | null;
  status: string | null;
  planner_id: string | null;
  planner_name?: string | null;
  user_question?: string | null;
}