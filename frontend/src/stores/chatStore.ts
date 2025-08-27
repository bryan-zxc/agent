import { create } from 'zustand';
import { ChatMessage, AgentStatus } from '../../../shared/types';

interface Conversation {
  id: string;
  title: string;
  preview: string;
  timestamp: string;
}

interface ChatStore {
  messages: ChatMessage[];
  status: AgentStatus;
  isConnected: boolean;
  isConnecting: boolean;
  currentModel: string;
  temperature: number;
  currentRouterId: string;
  conversations: Conversation[];
  lockedConversations: Set<string>;
  
  // Actions
  addMessage: (message: ChatMessage) => void;
  updateStatus: (status: AgentStatus) => void;
  setConnected: (connected: boolean) => void;
  setConnecting: (connecting: boolean) => void;
  setModel: (model: string) => void;
  setTemperature: (temperature: number) => void;
  clearMessages: () => void;
  setCurrentConversation: (routerId: string) => void;
  setConversations: (conversations: Conversation[]) => void;
  createNewConversation: () => Promise<string>;
  loadConversation: (routerId: string, messages: ChatMessage[]) => void;
  lockConversation: (routerId: string) => void;
  unlockConversation: (routerId: string) => void;
  isConversationLocked: (routerId: string) => boolean;
}


export const useChatStore = create<ChatStore>((set, get) => ({
  messages: [],
  status: { status: 'idle' },
  isConnected: false,
  isConnecting: true, // Start as connecting to avoid showing offline immediately
  currentModel: 'gpt-4',
  temperature: 0.7,
  currentRouterId: '', // Start with empty router_id - backend will provide one
  conversations: [],
  lockedConversations: new Set(),
  
  addMessage: (message) =>
    set((state) => ({
      messages: [...state.messages, message],
    })),
    
  updateStatus: (status) =>
    set({ status }),
    
  setConnected: (connected) =>
    set({ isConnected: connected, isConnecting: false }),
    
  setConnecting: (connecting) =>
    set({ isConnecting: connecting }),
    
  setModel: (model) =>
    set({ currentModel: model }),
    
  setTemperature: (temperature) =>
    set({ temperature }),
    
  clearMessages: () =>
    set({ messages: [] }),
    
  setCurrentConversation: (routerId) =>
    set({ currentRouterId: routerId }),
    
  setConversations: (conversations) =>
    set({ conversations }),
    
  createNewConversation: async () => {
    // Clear current conversation - backend will provide router_id when first message is sent
    set({ 
      currentRouterId: '',
      messages: []
    });
    return ''; // Backend will provide the actual router_id
  },
  
  
  loadConversation: (routerId, messages) =>
    set({ 
      currentRouterId: routerId,
      messages
    }),
    
  lockConversation: (routerId) =>
    set((state) => ({
      lockedConversations: new Set(state.lockedConversations).add(routerId),
    })),
    
  unlockConversation: (routerId) =>
    set((state) => {
      const newLockedConversations = new Set(state.lockedConversations);
      newLockedConversations.delete(routerId);
      return { lockedConversations: newLockedConversations };
    }),
    
  isConversationLocked: (routerId) =>
    get().lockedConversations.has(routerId),
    
}));