import { create } from 'zustand';
import { ChatMessage, AgentStatus, ApprovalRequest, PlamarinationStatus } from '../../../shared/types';

export type RouterMode = 'auto' | 'rapid' | 'agent';
export type AgentPhase = 'plamarination' | 'execution' | null;

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
  temperature: number;
  currentRouterId: string;
  currentMode: RouterMode;
  currentPhase: AgentPhase;
  phaseActive: boolean; // For visual indicators when processing
  conversations: Conversation[];
  lockedConversations: Set<string>;
  
  // Approval state
  pendingApproval: ApprovalRequest | null;
  plamarinationStatus: PlamarinationStatus;
  
  // Actions
  addMessage: (message: ChatMessage) => void;
  updateStatus: (status: AgentStatus) => void;
  setConnected: (connected: boolean) => void;
  setConnecting: (connecting: boolean) => void;
  setTemperature: (temperature: number) => void;
  setMode: (mode: RouterMode) => void;
  setPhase: (phase: AgentPhase) => void;
  setPhaseActive: (active: boolean) => void;
  clearMessages: () => void;
  setCurrentConversation: (routerId: string) => void;
  setConversations: (conversations: Conversation[]) => void;
  createNewConversation: () => Promise<string>;
  loadConversation: (routerId: string, messages: ChatMessage[]) => void;
  lockConversation: (routerId: string) => void;
  unlockConversation: (routerId: string) => void;
  isConversationLocked: (routerId: string) => boolean;
  
  // Approval actions
  setPendingApproval: (approval: ApprovalRequest | null) => void;
  setPlamarinationStatus: (status: PlamarinationStatus) => void;
}


export const useChatStore = create<ChatStore>((set, get) => ({
  messages: [],
  status: { status: 'idle' },
  isConnected: false,
  isConnecting: true, // Start as connecting to avoid showing offline immediately
  temperature: 0.7,
  currentRouterId: '', // Start with empty router_id - backend will provide one
  currentMode: 'auto', // Default to auto mode
  currentPhase: null, // Phase defaults to null - only set when in agent mode
  phaseActive: false, // Not processing initially
  conversations: [],
  lockedConversations: new Set(),
  
  // Approval state
  pendingApproval: null,
  plamarinationStatus: null,
  
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
    
  setTemperature: (temperature) =>
    set({ temperature }),
    
  setMode: (mode) => 
    set((state) => {
      console.log('ChatStore: setMode changing from', state.currentMode, 'to', mode);
      // When switching to agent mode, set phase to 'plamarination'
      // When switching away from agent mode, clear phase to null
      let newPhase = state.currentPhase;
      if (mode === 'agent' && state.currentMode !== 'agent') {
        newPhase = 'plamarination';
      } else if (mode !== 'agent') {
        newPhase = null;
      }
      return { currentMode: mode, currentPhase: newPhase };
    }),
    
  setPhase: (phase) => 
    set((state) => {
      console.log('ChatStore: setPhase changing from', state.currentPhase, 'to', phase);
      return { currentPhase: phase };
    }),
    
  setPhaseActive: (active) =>
    set({ phaseActive: active }),
    
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
  
  // Approval actions
  setPendingApproval: (approval) =>
    set({ pendingApproval: approval }),
    
  setPlamarinationStatus: (status) =>
    set({ plamarinationStatus: status }),
    
}));