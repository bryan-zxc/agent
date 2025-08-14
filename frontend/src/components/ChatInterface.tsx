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
import { RightPanel } from './RightPanel';
import { DuplicateFileDialog } from './DuplicateFileDialog';
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from './ui/resizable';
import { SidebarProvider, SidebarInset } from './ui/sidebar';
import { fileUploadService, DuplicateFileInfo } from '../lib/fileUpload';

export const ChatInterface: React.FC = () => {
  const { messages, status, currentRouterId, createNewConversationInBackend, createNewConversation, setCurrentConversation, isConversationLocked } = useChatStore();
  console.log('ChatInterface render - currentRouterId:', currentRouterId);
  const [conversationStarted, setConversationStarted] = useState(false);
  const [, setPendingRouterId] = useState<string | null>(null);
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [duplicateDialog, setDuplicateDialog] = useState<{
    open: boolean;
    duplicateInfo: DuplicateFileInfo | null;
    file: File | null;
    resolve: (action: string) => void;
  }>({
    open: false,
    duplicateInfo: null,
    file: null,
    resolve: () => {}
  });
  
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

  const handleDuplicateFound = (duplicateInfo: DuplicateFileInfo, file: File): Promise<string> => {
    return new Promise((resolve) => {
      setDuplicateDialog({
        open: true,
        duplicateInfo,
        file,
        resolve
      });
    });
  };

  const handleDuplicateResolve = (action: string) => {
    duplicateDialog.resolve(action);
    setDuplicateDialog({
      open: false,
      duplicateInfo: null,
      file: null,
      resolve: () => {}
    });
  };

  const handleDuplicateClose = () => {
    duplicateDialog.resolve('cancel');
    setDuplicateDialog({
      open: false,
      duplicateInfo: null,
      file: null,
      resolve: () => {}
    });
  };

  const handleFirstMessage = async (message: string, files: File[]) => {
    console.log('handleFirstMessage called with message:', message);
    if (!message.trim()) return;

    try {
      console.log('Creating new conversation in backend...');
      // Create new conversation in backend first
      const newRouterId = await createNewConversationInBackend();
      console.log('New router created:', newRouterId);
      
      setPendingRouterId(newRouterId);
      setCurrentConversation(newRouterId);
      setConversationStarted(true);
      
      // Upload files using the optimised method that handles resolved duplicates
      const filePaths: string[] = [];
      if (files.length > 0) {
        try {
          const resolvedFiles = await fileUploadService.checkFilesForDuplicates(files, handleDuplicateFound);
          const uploadedPaths = await fileUploadService.uploadResolvedFiles(resolvedFiles);
          filePaths.push(...uploadedPaths);
        } catch (error) {
          console.error('Error handling files:', error);
        }
      }

      // Wait for WebSocket connection before sending message
      console.log('Waiting for WebSocket connection...');
      await waitForWebSocketConnection();
      console.log('WebSocket connection ready!');

      // Send first message via WebSocket instead of REST API
      console.log('Sending first message via WebSocket...');
      sendMessage(message, filePaths, newRouterId);
      
      // Trigger title update asynchronously (fire and forget)
      setTimeout(() => {
        fetch(`${process.env.NEXT_PUBLIC_API_URL}/routers/${newRouterId}/update-title`, {
          method: 'POST',
        }).catch(error => {
          console.warn('Failed to update conversation title:', error);
        });
      }, 2000); // Wait 2 seconds for the conversation to be established
      
      // Trigger sidebar refresh to show new conversation
      setRefreshTrigger(prev => prev + 1);
    } catch (error) {
      console.error('Error in handleFirstMessage:', error);
      // Reset state on error
      setConversationStarted(false);
      setPendingRouterId(null);
    }
  };

  const handleMessageSubmit = async (message: string, files: File[]) => {
    if (!message.trim() || !isWebSocketOpen()) return;

    // Upload files using the optimised method that handles resolved duplicates
    const filePaths: string[] = [];
    if (files.length > 0) {
      try {
        const resolvedFiles = await fileUploadService.checkFilesForDuplicates(files, handleDuplicateFound);
        const uploadedPaths = await fileUploadService.uploadResolvedFiles(resolvedFiles);
        filePaths.push(...uploadedPaths);
      } catch (error) {
        console.error('Error handling files:', error);
      }
    }

    // Send message with current conversation ID
    sendMessage(message, filePaths, currentRouterId);
  };

  const handleNewConversation = () => {
    setConversationStarted(false);
    setPendingRouterId(null);
    // Generate client-side conversation ID only, don't create in backend yet
    createNewConversation();
  };

  const handleConversationSelect = (routerId: string, hasMessages: boolean) => {
    setConversationStarted(hasMessages);
    setPendingRouterId(hasMessages ? null : routerId);
    
    // Load conversation via WebSocket
    if (hasMessages) {
      loadConversation(routerId);
    }
  };

  // Show landing page if conversation hasn't started
  if (!conversationStarted) {
    return (
      <ErrorBoundary>
        <SidebarProvider defaultOpen={true}>
          <ConversationSidebar 
            onNewConversation={handleNewConversation}
            onConversationSelect={handleConversationSelect}
            refreshTrigger={refreshTrigger}
          />
          <SidebarInset className="h-screen">
            <ChatHeader isConnected={wsConnected} />
            <ResizablePanelGroup direction="horizontal" className="h-full">
              {/* Landing Page Panel */}
              <ResizablePanel defaultSize={80} minSize={50}>
                <LandingPage 
                  onFirstMessage={handleFirstMessage}
                  onDuplicateFound={handleDuplicateFound}
                  isConnected={wsConnected}
                />
              </ResizablePanel>
              
              {/* Resizable Handle */}
              <ResizableHandle withHandle />
              
              {/* Right Panel */}
              <ResizablePanel defaultSize={20} minSize={20} maxSize={50}>
                <RightPanel />
              </ResizablePanel>
            </ResizablePanelGroup>
            
            {/* Duplicate File Dialog */}
            {duplicateDialog.open && duplicateDialog.duplicateInfo && (
              <DuplicateFileDialog
                open={duplicateDialog.open}
                duplicateInfo={duplicateDialog.duplicateInfo}
                onResolve={handleDuplicateResolve}
                onClose={handleDuplicateClose}
              />
            )}
          </SidebarInset>
        </SidebarProvider>
      </ErrorBoundary>
    );
  }

  return (
    <ErrorBoundary>
      <SidebarProvider defaultOpen={true}>
        <ConversationSidebar 
          onNewConversation={handleNewConversation}
          onConversationSelect={handleConversationSelect}
          refreshTrigger={refreshTrigger}
        />
        <SidebarInset className="h-screen w-full overflow-hidden">
          <ChatHeader isConnected={wsConnected} />
          <ResizablePanelGroup direction="horizontal" className="h-full w-full">
            {/* Main Chat Panel */}
            <ResizablePanel defaultSize={80} minSize={50}>
              <div 
                className="flex flex-col h-full min-w-0 overflow-hidden"
                role="application"
                aria-label="Chat Interface"
              >
                <div className="flex-1 min-h-0 overflow-hidden">
                  <MessageList 
                    messages={messages} 
                    status={status}
                    className="h-full"
                  />
                </div>

                <div className="flex-shrink-0 bg-muted/30 backdrop-blur-sm">
                  <MessageInput 
                    onSubmit={handleMessageSubmit}
                    onDuplicateFound={handleDuplicateFound}
                    disabled={!wsConnected || isConversationLocked(currentRouterId)}
                    className="border-0 bg-transparent"
                    placeholder={isConversationLocked(currentRouterId) ? "Processing... Please wait" : "Type your message... (Enter to send, Shift+Enter for new line)"}
                  />
                </div>
              </div>
            </ResizablePanel>
            
            {/* Resizable Handle */}
            <ResizableHandle withHandle />
            
            {/* Right Panel */}
            <ResizablePanel defaultSize={20} minSize={20} maxSize={50}>
              <RightPanel />
            </ResizablePanel>
          </ResizablePanelGroup>
          
          {/* Duplicate File Dialog */}
          {duplicateDialog.open && duplicateDialog.duplicateInfo && (
            <DuplicateFileDialog
              open={duplicateDialog.open}
              duplicateInfo={duplicateDialog.duplicateInfo}
              onResolve={handleDuplicateResolve}
              onClose={handleDuplicateClose}
            />
          )}
        </SidebarInset>
      </SidebarProvider>
    </ErrorBoundary>
  );
};