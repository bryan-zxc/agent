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
  createNewConversationInBackend: () => Promise<string>;
  loadConversation: (routerId: string, messages: ChatMessage[]) => void;
  lockConversation: (routerId: string) => void;
  unlockConversation: (routerId: string) => void;
  isConversationLocked: (routerId: string) => boolean;
}

const generateRouterId = () => {
  return Date.now().toString(36) + Math.random().toString(36).substr(2);
};

export const useChatStore = create<ChatStore>((set, get) => ({
  messages: [],
  status: { status: 'idle' },
  isConnected: false,
  isConnecting: true, // Start as connecting to avoid showing offline immediately
  currentModel: 'gpt-4',
  temperature: 0.7,
  currentRouterId: generateRouterId(),
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
    // Generate client-side ID only, don't create in backend yet
    const newId = generateRouterId();
    set({ 
      currentRouterId: newId,
      messages: []
    });
    return newId;
  },
  
  createNewConversationInBackend: async () => {
    const currentState = useChatStore.getState();
    try {
      // Call backend to create conversation
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/routers`, {
        method: 'POST',
      });
      
      if (response.ok) {
        const data = await response.json();
        const newId = data.router_id;
        console.log('Creating new conversation in backend - old ID:', currentState.currentRouterId, '-> new ID:', newId);
        set({ 
          currentRouterId: newId,
          messages: []
        });
        return newId;
      } else {
        // Fallback to client-side generation
        const newId = generateRouterId();
        set({ 
          currentRouterId: newId,
          messages: []
        });
        return newId;
      }
    } catch (error) {
      console.error('Error creating conversation:', error);
      // Fallback to client-side generation
      const newId = generateRouterId();
      set({ 
        currentRouterId: newId,
        messages: [] 
      });
      return newId;
    }
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