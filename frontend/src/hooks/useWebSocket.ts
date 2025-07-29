import { useEffect, useRef, useCallback } from 'react';
import { useChatStore } from '../stores/chatStore';
import { ChatMessage } from '../../../shared/types';

export const useWebSocket = (conversationId: string = 'default', url?: string) => {
  const wsUrl = url || `ws://localhost:8000/chat/${conversationId}`;
  const ws = useRef<WebSocket | null>(null);
  const { addMessage, updateStatus, setConnected } = useChatStore();

  const connect = useCallback(() => {
    try {
      ws.current = new WebSocket(wsUrl);
      
      ws.current.onopen = () => {
        console.log('WebSocket connected');
        setConnected(true);
        updateStatus({ status: 'idle', message: 'Connected to agent' });
      };

      ws.current.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          
          switch (data.type) {
            case 'status':
              updateStatus({ status: 'processing', message: data.message });
              break;
              
            case 'response':
              const assistantMessage: ChatMessage = {
                id: Date.now().toString(),
                message: data.message,
                sender: 'assistant',
                timestamp: new Date(),
              };
              addMessage(assistantMessage);
              updateStatus({ status: 'idle' });
              break;
              
            case 'error':
              updateStatus({ status: 'error', message: data.message });
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
        setConnected(false);
        updateStatus({ status: 'idle', message: 'Disconnected from agent' });
        
        // Attempt to reconnect after 3 seconds
        setTimeout(connect, 3000);
      };

      ws.current.onerror = (error) => {
        console.error('WebSocket error:', error);
        updateStatus({ status: 'error', message: 'Connection error' });
      };
      
    } catch (error) {
      console.error('Failed to create WebSocket connection:', error);
    }
  }, [wsUrl, addMessage, updateStatus, setConnected]);

  const sendMessage = useCallback((message: string, files: string[] = []) => {
    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
      const { currentModel, temperature } = useChatStore.getState();
      
      const payload = {
        message,
        files,
        model: currentModel,
        temperature,
      };
      
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
      
      addMessage(userMessage);
    } else {
      console.error('WebSocket is not connected');
      updateStatus({ status: 'error', message: 'Not connected to agent' });
    }
  }, [addMessage, updateStatus]);

  const disconnect = useCallback(() => {
    if (ws.current) {
      ws.current.close();
      ws.current = null;
    }
  }, []);

  useEffect(() => {
    connect();
    
    return () => {
      disconnect();
    };
  }, [connect, disconnect]);

  return {
    sendMessage,
    disconnect,
    isConnected: ws.current?.readyState === WebSocket.OPEN,
  };
};