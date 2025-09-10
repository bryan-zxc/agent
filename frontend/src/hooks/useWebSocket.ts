import { useEffect, useRef, useCallback } from 'react';
import { useChatStore } from '../stores/chatStore';
import { ChatMessage, ApprovalRequest } from '../../../shared/types';

export const useWebSocket = (url?: string) => {
  const wsUrl = url || `${process.env.NEXT_PUBLIC_WS_URL}/chat`;
  console.log('useWebSocket called with wsUrl:', wsUrl);
  const ws = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<NodeJS.Timeout | null>(null);
  const connectionTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const shouldReconnect = useRef<boolean>(true);
  const store = useChatStore();

  const connect = useCallback(() => {
    try {
      // Validate WebSocket URL before attempting connection
      if (!wsUrl || !wsUrl.startsWith('ws://') && !wsUrl.startsWith('wss://')) {
        const errorMsg = `Invalid WebSocket URL: ${wsUrl}. Expected format: ws://hostname:port/path`;
        console.error(errorMsg);
        store.setConnecting(false);
        store.updateStatus({ status: 'error', message: 'Invalid WebSocket URL configuration' });
        return;
      }
      
      console.log('Creating WebSocket connection to:', wsUrl);
      console.log('Full WebSocket URL being used:', wsUrl);
      store.setConnecting(true);
      ws.current = new WebSocket(wsUrl);
      
      // Set up connection timeout (10 seconds)
      connectionTimeoutRef.current = setTimeout(() => {
        if (ws.current && ws.current.readyState === WebSocket.CONNECTING) {
          console.error('WebSocket connection timeout after 10 seconds');
          ws.current.close();
          store.setConnecting(false);
          store.updateStatus({ status: 'error', message: 'Connection timeout - backend may be unreachable' });
        }
      }, 10000);
      
      ws.current.onopen = () => {
        console.log('WebSocket connected to:', wsUrl);
        
        // Clear connection timeout on successful connection
        if (connectionTimeoutRef.current) {
          clearTimeout(connectionTimeoutRef.current);
          connectionTimeoutRef.current = null;
        }
        
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
              // Debug logging for Agents assemble messages
              if (data.message === 'Agents assemble!') {
                console.log('[DEBUG] Agents assemble WebSocket response:', {
                  message_id: data.message_id,
                  message_id_type: typeof data.message_id,
                  has_message_id: data.hasOwnProperty('message_id'),
                  full_data: data
                });
              }
              
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
              
            case 'continue_plamarination_signal':
              // Auto-send continuation request for plamarination
              console.log('Received plamarination continuation signal, auto-continuing...');
              setTimeout(() => {
                if (ws.current && ws.current.readyState === WebSocket.OPEN) {
                  ws.current.send(JSON.stringify({
                    type: 'continue_plamarination',
                    router_id: data.router_id
                  }));
                }
              }, 100);  // Small delay to let UI update
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
              
            case 'mode_updated':
              if (data.mode) {
                store.setMode(data.mode);
                console.log('Mode updated to:', data.mode);
              }
              break;
              
            case 'phase_updated':
              if (data.agent_phase !== undefined) {
                store.setPhase(data.agent_phase);
                console.log('Phase updated to:', data.agent_phase);
              }
              break;
              
            case 'approval_request':
              // Handle plamarination approval requests
              const approvalRequest: ApprovalRequest = {
                request_id: data.request_id,
                plan: data.plan,
                template: data.template,
                findings: data.findings,
                router_id: data.router_id,
              };
              store.setPendingApproval(approvalRequest);
              store.setPlamarinationStatus('waiting_approval');
              console.log('Approval request received:', approvalRequest.request_id);
              break;
              
            case 'approval_response':
              // Clear pending approval when response is processed
              if (data.approved) {
                store.setPlamarinationStatus('approved');
                console.log('Plan approved, proceeding to execution');
              } else {
                store.setPlamarinationStatus('revising');
                console.log('Plan revision requested');
              }
              // Clear the pending approval after a brief delay to show status
              setTimeout(() => {
                store.setPendingApproval(null);
                if (data.approved) {
                  store.setPlamarinationStatus(null); // Clear status when moving to execution
                }
              }, 2000);
              break;
              
            case 'plamarination_status':
              // Handle plamarination status updates
              store.setPlamarinationStatus(data.status);
              console.log('Plamarination status updated:', data.status);
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
        
        // Clear connection timeout
        if (connectionTimeoutRef.current) {
          clearTimeout(connectionTimeoutRef.current);
          connectionTimeoutRef.current = null;
        }
        
        store.setConnected(false);
        store.setConnecting(false);
        store.updateStatus({ status: 'idle', message: 'Disconnected from agent' });
        
        // Only attempt to reconnect if we should and not due to conversation change
        if (shouldReconnect.current) {
          reconnectRef.current = setTimeout(connect, 3000);
        }
      };

      ws.current.onerror = (error) => {
        // Only log errors when connection actually fails (not during normal connection)
        const readyState = ws.current?.readyState;
        
        // Don't log errors during normal connection establishment
        if (readyState === WebSocket.CONNECTING) {
          console.log('WebSocket connecting to:', wsUrl);
          return;
        }
        
        // Log actual connection failures
        const errorType = error instanceof Event ? error.type : 'unknown';
        const readyStateText = readyState === WebSocket.OPEN ? 'OPEN' :
                              readyState === WebSocket.CLOSING ? 'CLOSING' :
                              readyState === WebSocket.CLOSED ? 'CLOSED' : 'UNKNOWN';
        
        console.error(`WebSocket connection failed: ${errorType}`);
        console.error(`URL: ${wsUrl}`);
        console.error(`ReadyState: ${readyStateText} (${readyState})`);
        console.error('Check if backend is running on port 8001');
        
        // Clear connection timeout on error
        if (connectionTimeoutRef.current) {
          clearTimeout(connectionTimeoutRef.current);
          connectionTimeoutRef.current = null;
        }
        
        store.setConnecting(false);
        store.updateStatus({ status: 'error', message: 'Connection error - check if backend is running' });
      };
      
    } catch (error) {
      console.error('Failed to create WebSocket connection:', {
        error: error instanceof Error ? {
          name: error.name,
          message: error.message,
          stack: error.stack
        } : error,
        wsUrl,
        timestamp: new Date().toISOString()
      });
      store.setConnecting(false);
      store.updateStatus({ status: 'error', message: 'Failed to initialise WebSocket connection' });
    }
  }, [wsUrl]); // Remove store functions to prevent recreation

  const sendMessage = useCallback((message: string, files: string[] = [], routerId?: string) => {
    console.log('sendMessage called, WebSocket readyState:', ws.current?.readyState, 'URL:', ws.current?.url);
    
    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
      const { temperature, currentRouterId, currentMode } = useChatStore.getState();
      const targetRouterId = routerId || currentRouterId;
      
      const payload: any = {
        type: 'message',
        message,
        files,
        temperature,
        mode: currentMode, // Include current mode in message
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
    if (connectionTimeoutRef.current) {
      clearTimeout(connectionTimeoutRef.current);
      connectionTimeoutRef.current = null;
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

  const updateMode = useCallback((mode: string, routerId?: string) => {
    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
      const { currentRouterId } = useChatStore.getState();
      const targetRouterId = routerId || currentRouterId;
      
      if (targetRouterId) {
        const payload = {
          type: 'update_mode',
          router_id: targetRouterId,
          mode: mode,
        };
        
        console.log('Updating router mode via WebSocket:', payload);
        ws.current.send(JSON.stringify(payload));
      }
    }
  }, []);

  const updatePhase = useCallback((phase: 'plamarination' | 'execution', routerId?: string) => {
    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
      const { currentRouterId } = useChatStore.getState();
      const targetRouterId = routerId || currentRouterId;
      
      if (targetRouterId) {
        const payload = {
          type: 'update_phase',
          router_id: targetRouterId,
          agent_phase: phase,
        };
        
        console.log('Updating router phase via WebSocket:', payload);
        ws.current.send(JSON.stringify(payload));
      }
    }
  }, []);

  const sendApprovalResponse = useCallback((requestId: string, approved: boolean, feedback?: string) => {
    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
      const payload = {
        type: 'approval_response',
        request_id: requestId,
        approved,
        feedback,
      };
      
      console.log('Sending approval response via WebSocket:', payload);
      ws.current.send(JSON.stringify(payload));
    } else {
      console.error('WebSocket is not connected for sending approval response');
    }
  }, []);

  return {
    sendMessage,
    loadConversation,
    disconnect,
    updateMode,
    updatePhase,
    sendApprovalResponse,
    isConnected: ws.current?.readyState === WebSocket.OPEN,
    isWebSocketOpen,
  };
};