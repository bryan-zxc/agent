'use client';

import React, { useState } from 'react';
import { useChatStore } from '../stores/chatStore';
import { useWebSocket } from '../hooks/useWebSocket';
import { ChatHeader } from './ChatHeader';
import { MessageList } from './MessageList';
import { MessageInput } from './MessageInput';
import { ConversationSidebar } from './ConversationSidebar';
import { LandingPage } from './LandingPage';
import { ErrorBoundary } from './ErrorBoundary';
import { cn } from '@/lib/utils';
import { ChatMessage } from '../../../shared/types';

export const ChatInterface: React.FC = () => {
  const { messages, status, currentConversationId, createNewConversationInBackend, createNewConversation, setCurrentConversation, addMessage } = useChatStore();
  console.log('ChatInterface render - currentConversationId:', currentConversationId);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [conversationStarted, setConversationStarted] = useState(false);
  const [pendingConversationId, setPendingConversationId] = useState<string | null>(null);
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  
  // Use single persistent WebSocket connection
  const { sendMessage, loadConversation, isConnected: wsConnected, isWebSocketOpen } = useWebSocket();

  const waitForWebSocketConnection = (): Promise<void> => {
    return new Promise((resolve, reject) => {
      const checkConnection = () => {
        if (isWebSocketOpen()) {
          resolve();
        } else {
          setTimeout(checkConnection, 100);
        }
      };
      
      // Start checking immediately
      checkConnection();
      
      // Set a timeout to prevent infinite waiting
      setTimeout(() => {
        reject(new Error('WebSocket connection timeout'));
      }, 5000);
    });
  };

  const handleFirstMessage = async (message: string, files: File[]) => {
    console.log('handleFirstMessage called with message:', message);
    if (!message.trim()) return;

    try {
      console.log('Creating new conversation in backend...');
      // Create new conversation in backend first
      const newConversationId = await createNewConversationInBackend();
      console.log('New conversation created:', newConversationId);
      
      setPendingConversationId(newConversationId);
      setCurrentConversation(newConversationId);
      setConversationStarted(true);
      
      // Upload files if any
      const filePaths: string[] = [];
      if (files.length > 0) {
        for (const file of files) {
          const formData = new FormData();
          formData.append('file', file);
          
          try {
            const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/upload`, {
              method: 'POST',
              body: formData,
            });
            
            if (response.ok) {
              const result = await response.json();
              filePaths.push(result.path);
            }
          } catch (error) {
            console.error('Error uploading file:', error);
          }
        }
      }

      // Activate conversation with first message
      console.log('Activating conversation...');
      const activateResponse = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/conversations/${newConversationId}/activate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: message,
          files: filePaths,
        }),
      });

      if (!activateResponse.ok) {
        throw new Error('Failed to activate conversation');
      }

      const activateResult = await activateResponse.json();
      
      // Add the user's message to the UI
      const userMessage: ChatMessage = {
        id: Date.now().toString(),
        message: message,
        sender: 'user',
        timestamp: new Date(),
      };
      addMessage(userMessage);

      // Add the assistant's response to the UI
      if (activateResult.response) {
        const assistantMessage: ChatMessage = {
          id: (Date.now() + 1).toString(),
          message: activateResult.response,
          sender: 'assistant',
          timestamp: new Date(),
        };
        addMessage(assistantMessage);
        
        // Trigger title update asynchronously (fire and forget)
        fetch(`${process.env.NEXT_PUBLIC_API_URL}/conversations/${newConversationId}/update-title`, {
          method: 'POST',
        }).catch(error => {
          console.warn('Failed to update conversation title:', error);
        });
      }

      // Wait for WebSocket connection
      console.log('Waiting for WebSocket connection...');
      await waitForWebSocketConnection();
      console.log('WebSocket connection ready!');
      
      // Trigger sidebar refresh to show new conversation
      setRefreshTrigger(prev => prev + 1);
    } catch (error) {
      console.error('Error in handleFirstMessage:', error);
      // Reset state on error
      setConversationStarted(false);
      setPendingConversationId(null);
    }
  };

  const handleMessageSubmit = async (message: string, files: File[]) => {
    if (!message.trim() || !isWebSocketOpen()) return;

    // Upload files if any
    const filePaths: string[] = [];
    if (files.length > 0) {
      for (const file of files) {
        const formData = new FormData();
        formData.append('file', file);
        
        try {
          const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/upload`, {
            method: 'POST',
            body: formData,
          });
          
          if (response.ok) {
            const result = await response.json();
            filePaths.push(result.path);
          }
        } catch (error) {
          console.error('Error uploading file:', error);
        }
      }
    }

    // Send message with current conversation ID
    sendMessage(message, filePaths, currentConversationId);
  };

  const handleNewConversation = () => {
    setConversationStarted(false);
    setPendingConversationId(null);
    // Generate client-side conversation ID only, don't create in backend yet
    createNewConversation();
  };

  const handleConversationSelect = (conversationId: string, hasMessages: boolean) => {
    setConversationStarted(hasMessages);
    setPendingConversationId(hasMessages ? null : conversationId);
    
    // Load conversation via WebSocket
    if (hasMessages) {
      loadConversation(conversationId);
    }
  };

  // Show landing page if conversation hasn't started
  if (!conversationStarted) {
    return (
      <ErrorBoundary>
        <div className="flex h-screen bg-background">
          {/* Sidebar */}
          <ConversationSidebar 
            isOpen={sidebarOpen} 
            onClose={() => setSidebarOpen(false)}
            onNewConversation={handleNewConversation}
            onConversationSelect={handleConversationSelect}
            refreshTrigger={refreshTrigger}
          />
          
          {/* Landing Page */}
          <LandingPage 
            onFirstMessage={handleFirstMessage}
            isConnected={wsConnected}
            onMenuClick={() => setSidebarOpen(true)}
          />
        </div>
      </ErrorBoundary>
    );
  }

  return (
    <ErrorBoundary>
      <div className="flex h-screen bg-background">
        {/* Sidebar */}
        <ConversationSidebar 
          isOpen={sidebarOpen} 
          onClose={() => setSidebarOpen(false)}
          onNewConversation={handleNewConversation}
          onConversationSelect={handleConversationSelect}
          refreshTrigger={refreshTrigger}
        />
        
        {/* Main Chat Area */}
        <div 
          className={cn(
            "flex flex-col flex-1 min-w-0",
            "max-w-4xl mx-auto w-full"
          )}
          role="application"
          aria-label="Chat Interface"
        >
          <ChatHeader 
            isConnected={wsConnected} 
            onMenuClick={() => setSidebarOpen(true)}
          />
          
          <div className="flex-1 overflow-hidden">
            <MessageList 
              messages={messages} 
              status={status}
              className="h-full"
            />
          </div>

          <div className="border-t bg-card/50 backdrop-blur-sm">
            <MessageInput 
              onSubmit={handleMessageSubmit}
              disabled={!wsConnected}
              className="border-0 bg-transparent"
            />
          </div>
        </div>
      </div>
    </ErrorBoundary>
  );
};