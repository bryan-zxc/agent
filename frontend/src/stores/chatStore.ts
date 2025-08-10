import { create } from 'zustand';
import { ChatMessage, AgentStatus, PlannerInfo } from '../../../shared/types';

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
  currentConversationId: string;
  conversations: Conversation[];
  lockedConversations: Set<string>;
  currentExecutionPlan: PlannerInfo | null;
  
  // Actions
  addMessage: (message: ChatMessage) => void;
  updateStatus: (status: AgentStatus) => void;
  setConnected: (connected: boolean) => void;
  setConnecting: (connecting: boolean) => void;
  setModel: (model: string) => void;
  setTemperature: (temperature: number) => void;
  clearMessages: () => void;
  setCurrentConversation: (conversationId: string) => void;
  setConversations: (conversations: Conversation[]) => void;
  createNewConversation: () => Promise<string>;
  createNewConversationInBackend: () => Promise<string>;
  loadConversation: (conversationId: string, messages: ChatMessage[]) => void;
  lockConversation: (conversationId: string) => void;
  unlockConversation: (conversationId: string) => void;
  isConversationLocked: (conversationId: string) => boolean;
  updateExecutionPlan: (planData: any) => void;
}

const generateConversationId = () => {
  return Date.now().toString(36) + Math.random().toString(36).substr(2);
};

export const useChatStore = create<ChatStore>((set, get) => ({
  messages: [],
  status: { status: 'idle' },
  isConnected: false,
  isConnecting: true, // Start as connecting to avoid showing offline immediately
  currentModel: 'gpt-4',
  temperature: 0.7,
  currentConversationId: generateConversationId(),
  conversations: [],
  lockedConversations: new Set(),
  currentExecutionPlan: null,
  
  addMessage: (message) =>
    set((state) => ({
      messages: [...state.messages, message],
    })),
    
  updateStatus: (status) =>
    set((state) => ({
      status,
      // Clear execution plan when status changes from processing to idle
      currentExecutionPlan: status.status === 'idle' ? null : state.currentExecutionPlan
    })),
    
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
    
  setCurrentConversation: (conversationId) =>
    set({ currentConversationId: conversationId, currentExecutionPlan: null }),
    
  setConversations: (conversations) =>
    set({ conversations }),
    
  createNewConversation: async () => {
    // Generate client-side ID only, don't create in backend yet
    const newId = generateConversationId();
    set({ 
      currentConversationId: newId,
      messages: [],
      currentExecutionPlan: null
    });
    return newId;
  },
  
  createNewConversationInBackend: async () => {
    const currentState = useChatStore.getState();
    try {
      // Call backend to create conversation
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/conversations`, {
        method: 'POST',
      });
      
      if (response.ok) {
        const data = await response.json();
        const newId = data.conversation_id;
        console.log('Creating new conversation in backend - old ID:', currentState.currentConversationId, '-> new ID:', newId);
        set({ 
          currentConversationId: newId,
          messages: [],
          currentExecutionPlan: null
        });
        return newId;
      } else {
        // Fallback to client-side generation
        const newId = generateConversationId();
        set({ 
          currentConversationId: newId,
          messages: [],
          currentExecutionPlan: null
        });
        return newId;
      }
    } catch (error) {
      console.error('Error creating conversation:', error);
      // Fallback to client-side generation
      const newId = generateConversationId();
      set({ 
        currentConversationId: newId,
        messages: [] 
      });
      return newId;
    }
  },
  
  loadConversation: (conversationId, messages) =>
    set({ 
      currentConversationId: conversationId,
      messages,
      currentExecutionPlan: null
    }),
    
  lockConversation: (conversationId) =>
    set((state) => ({
      lockedConversations: new Set(state.lockedConversations).add(conversationId),
    })),
    
  unlockConversation: (conversationId) =>
    set((state) => {
      const newLockedConversations = new Set(state.lockedConversations);
      newLockedConversations.delete(conversationId);
      return { lockedConversations: newLockedConversations };
    }),
    
  isConversationLocked: (conversationId) =>
    get().lockedConversations.has(conversationId),
    
  updateExecutionPlan: (planData) =>
    set({
      currentExecutionPlan: {
        has_planner: true,
        execution_plan: planData.execution_plan,
        status: 'executing', // Since we're receiving updates
        planner_id: planData.planner_id,
        planner_name: null,
        user_question: null
      }
    }),
}));