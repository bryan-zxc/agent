import { useEffect, useRef, useCallback } from 'react';
import { useChatStore } from '../stores/chatStore';
import { ChatMessage } from '../../../shared/types';

export const useWebSocket = (url?: string) => {
  const wsUrl = url || `${process.env.NEXT_PUBLIC_WS_URL}/chat`;
  console.log('useWebSocket called with wsUrl:', wsUrl);
  const ws = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<NodeJS.Timeout | null>(null);
  const shouldReconnect = useRef<boolean>(true);
  const store = useChatStore();

  const connect = useCallback(() => {
    try {
      console.log('Creating WebSocket connection to:', wsUrl);
      console.log('Full WebSocket URL being used:', wsUrl);
      store.setConnecting(true);
      ws.current = new WebSocket(wsUrl);
      
      ws.current.onopen = () => {
        console.log('WebSocket connected to:', wsUrl);
        store.setConnected(true);
        store.updateStatus({ status: 'idle', message: 'Connected to agent' });
      };

      ws.current.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          switch (data.type) {
            case 'connection_established':
              console.log('WebSocket connection established, session:', data.session_id);
              break;
              
            case 'status':
              store.updateStatus({ status: 'processing', message: data.message });
              break;
              
            case 'message':
              const incomingMessage: ChatMessage = {
                id: Date.now().toString(),
                message: data.content,
                sender: data.role,
                timestamp: new Date(),
              };
              store.addMessage(incomingMessage);
              break;
              
            case 'response':
              const assistantMessage: ChatMessage = {
                id: Date.now().toString(),
                message: data.message,
                sender: 'assistant',
                timestamp: new Date(),
              };
              store.addMessage(assistantMessage);
              store.updateStatus({ status: 'idle' });
              break;
              
            case 'conversation_history':
              // Handle conversation history for specific conversation
              const historyMessages = data.messages
                .filter((msg: {role: string; content: string}) => msg.role !== 'system')
                .map((msg: {role: string; content: string}, index: number) => ({
                  id: index.toString(),
                  message: msg.content,
                  sender: msg.role,
                  timestamp: new Date(),
                }));
              
              // Only update messages if this is for the current conversation
              const currentConversationId = useChatStore.getState().currentConversationId;
              if (data.conversation_id === currentConversationId) {
                console.log('Loading conversation history for', data.conversation_id, ':', historyMessages.length, 'messages');
                useChatStore.setState({ messages: historyMessages });
              } else {
                console.log('Ignoring history for different conversation:', data.conversation_id, 'vs current:', currentConversationId);
              }
              break;
              
            case 'error':
              store.updateStatus({ status: 'error', message: data.message });
              break;
              
            case 'input_lock':
              if (data.conversation_id) {
                store.lockConversation(data.conversation_id);
                console.log('Locked conversation:', data.conversation_id);
              }
              break;
              
            case 'input_unlock':
              if (data.conversation_id) {
                store.unlockConversation(data.conversation_id);
                console.log('Unlocked conversation:', data.conversation_id);
              }
              break;
              
            case 'execution_plan_update':
              if (data.data) {
                store.updateExecutionPlan(data.data);
                console.log('Received execution plan update:', data.data);
              }
              break;
              
            default:
              console.log('Unknown message type:', data.type);
          }
        } catch (error) {
          console.error('Error parsing WebSocket message:', error);
        }
      };

      ws.current.onclose = () => {
        console.log('WebSocket disconnected');
        store.setConnected(false);
        store.setConnecting(false);
        store.updateStatus({ status: 'idle', message: 'Disconnected from agent' });
        
        // Only attempt to reconnect if we should and not due to conversation change
        if (shouldReconnect.current) {
          reconnectRef.current = setTimeout(connect, 3000);
        }
      };

      ws.current.onerror = (error) => {
        console.error('WebSocket error details:', {
          error,
          wsUrl,
          readyState: ws.current?.readyState
        });
        store.setConnecting(false);
        store.updateStatus({ status: 'error', message: 'Connection error' });
      };
      
    } catch (error) {
      console.error('Failed to create WebSocket connection:', error);
    }
  }, [wsUrl]); // Remove store functions to prevent recreation

  const sendMessage = useCallback((message: string, files: string[] = [], conversationId?: string) => {
    console.log('sendMessage called, WebSocket readyState:', ws.current?.readyState, 'URL:', ws.current?.url);
    
    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
      const { currentModel, temperature, currentConversationId } = useChatStore.getState();
      const targetConversationId = conversationId || currentConversationId;
      
      const payload = {
        type: 'message',
        message,
        conversation_id: targetConversationId,
        files,
        model: currentModel,
        temperature,
      };
      
      console.log('Sending message via WebSocket:', payload);
      ws.current.send(JSON.stringify(payload));
      
      // Add user message to chat
      const userMessage: ChatMessage = {
        id: Date.now().toString(),
        message,
        sender: 'user',
        timestamp: new Date(),
        files,
        model: currentModel,
        temperature,
      };
      
      store.addMessage(userMessage);
    } else {
      console.error('WebSocket is not connected. ReadyState:', ws.current?.readyState, 'Expected:', WebSocket.OPEN);
      store.updateStatus({ status: 'error', message: 'Not connected to agent' });
    }
  }, []);

  const loadConversation = useCallback((conversationId: string) => {
    console.log('loadConversation called for:', conversationId);
    
    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
      const payload = {
        type: 'load_conversation',
        conversation_id: conversationId,
      };
      
      console.log('Loading conversation via WebSocket:', payload);
      ws.current.send(JSON.stringify(payload));
    } else {
      console.error('WebSocket is not connected for loading conversation');
    }
  }, []);

  const disconnect = useCallback(() => {
    shouldReconnect.current = false;
    if (reconnectRef.current) {
      clearTimeout(reconnectRef.current);
      reconnectRef.current = null;
    }
    if (ws.current) {
      ws.current.close();
      ws.current = null;
    }
  }, []);

  useEffect(() => {
    console.log('useWebSocket useEffect triggered - establishing persistent connection');
    // Clean up any existing connection first
    disconnect();
    
    // Connect immediately for better UX - no delay needed
    shouldReconnect.current = true;
    connect();
    
    return () => {
      disconnect();
    };
  }, []); // Only connect once, no dependencies

  const isWebSocketOpen = useCallback(() => {
    return ws.current?.readyState === WebSocket.OPEN;
  }, []);

  return {
    sendMessage,
    loadConversation,
    disconnect,
    isConnected: ws.current?.readyState === WebSocket.OPEN,
    isWebSocketOpen,
  };
};