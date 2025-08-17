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
              
              // If this status includes a router_id and we don't have one yet, store it
              if (data.router_id && !store.currentRouterId) {
                console.log('Setting router_id from status message:', data.router_id);
                store.setCurrentConversation(data.router_id);
              }
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
                messageId: data.message_id, // Include database message ID if provided
              };
              store.addMessage(assistantMessage);
              store.updateStatus({ status: 'idle' });
              
              // If this response includes a router_id and we don't have one yet, store it
              if (data.router_id && !store.currentRouterId) {
                console.log('Setting router_id from backend response:', data.router_id);
                store.setCurrentConversation(data.router_id);
              }
              break;
              
            case 'message_history':
              // Handle message history for specific router
              const historyMessages = data.messages
                .filter((msg: {role: string; content: string; message_id?: number}) => msg.role !== 'system')
                .map((msg: {role: string; content: string; message_id?: number}, index: number) => ({
                  id: index.toString(),
                  message: msg.content,
                  sender: msg.role,
                  timestamp: new Date(),
                  messageId: msg.message_id, // Include database message ID if available
                }));
              
              // Only update messages if this is for the current conversation
              const currentRouterId = useChatStore.getState().currentRouterId;
              if (data.router_id === currentRouterId) {
                console.log('Loading conversation history for', data.router_id, ':', historyMessages.length, 'messages');
                useChatStore.setState({ messages: historyMessages });
              } else {
                console.log('Ignoring history for different conversation:', data.router_id, 'vs current:', currentRouterId);
              }
              break;
              
            case 'error':
              store.updateStatus({ status: 'error', message: data.message });
              break;
              
            case 'input_lock':
              if (data.router_id) {
                store.lockConversation(data.router_id);
                console.log('Locked conversation:', data.router_id);
              }
              break;
              
            case 'input_unlock':
              if (data.router_id) {
                store.unlockConversation(data.router_id);
                console.log('Unlocked conversation:', data.router_id);
              }
              break;
              
            // execution_plan_update case removed - now using frontend polling instead
              
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

  const sendMessage = useCallback((message: string, files: string[] = [], routerId?: string) => {
    console.log('sendMessage called, WebSocket readyState:', ws.current?.readyState, 'URL:', ws.current?.url);
    
    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
      const { currentModel, temperature, currentRouterId } = useChatStore.getState();
      const targetRouterId = routerId || currentRouterId;
      
      const payload: any = {
        type: 'message',
        message,
        files,
        model: currentModel,
        temperature,
      };
      
      // Only include router_id if we have one (for continuing conversations)
      if (targetRouterId) {
        payload.router_id = targetRouterId;
      }
      
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

  const loadConversation = useCallback((routerId: string) => {
    console.log('loadConversation called for:', routerId);
    
    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
      const payload = {
        type: 'load_router',
        router_id: routerId,
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