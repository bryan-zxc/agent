import { create } from 'zustand';
import { ChatMessage, AgentStatus } from '../../../shared/types';

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
  setModel: (model: string) => void;
  setTemperature: (temperature: number) => void;
  clearMessages: () => void;
}

export const useChatStore = create<ChatStore>((set) => ({
  messages: [],
  status: { status: 'idle' },
  isConnected: false,
  currentModel: 'gpt-4',
  temperature: 0.7,
  
  addMessage: (message) =>
    set((state) => ({
      messages: [...state.messages, message],
    })),
    
  updateStatus: (status) =>
    set({ status }),
    
  setConnected: (connected) =>
    set({ isConnected: connected }),
    
  setModel: (model) =>
    set({ currentModel: model }),
    
  setTemperature: (temperature) =>
    set({ temperature }),
    
  clearMessages: () =>
    set({ messages: [] }),
}));