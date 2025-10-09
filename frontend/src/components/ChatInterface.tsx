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
import { PlanApprovalCard } from './PlanApprovalCard';
import { ResizablePanelGroup, ResizablePanel, ResizableHandle } from './ui/resizable';
import { SidebarProvider, SidebarInset } from './ui/sidebar';
import { fileUploadService, DuplicateFileInfo } from '../lib/fileUpload';
import { ChatMessage } from '../../../shared/types';

export const ChatInterface: React.FC = () => {
  const { messages, status, currentRouterId, currentMode, currentPhase, phaseActive, setMode, setPhase, createNewConversation, isConversationLocked, pendingApproval, addMessage, setPendingApproval } = useChatStore();
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
  const { sendMessage, loadConversation, updateMode, updatePhase, sendApprovalResponse, isConnected: wsConnected, isWebSocketOpen } = useWebSocket();

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
      console.log('Starting new conversation...');
      setConversationStarted(true);
      
      // Upload files directly - they've already been validated during attachment
      const filePaths: string[] = [];
      if (files.length > 0) {
        try {
          const uploadedPaths = await fileUploadService.uploadFilesDirectly(files);
          filePaths.push(...uploadedPaths);
        } catch (error) {
          console.error('Error handling files:', error);
        }
      }

      // Wait for WebSocket connection before sending message
      console.log('Waiting for WebSocket connection...');
      await waitForWebSocketConnection();
      console.log('WebSocket connection ready!');

      // Send first message via WebSocket with no router_id - backend will create router
      console.log('Sending first message via WebSocket...');
      sendMessage(message, filePaths, undefined); // undefined router_id for new conversation
      
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

    // Upload files directly - they've already been validated during attachment
    const filePaths: string[] = [];
    if (files.length > 0) {
      try {
        const uploadedPaths = await fileUploadService.uploadFilesDirectly(files);
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

  const handleApprovalApprove = async (routerId: string) => {
    try {
      // Immediately update ALL UI state for responsive UX
      setPendingApproval(null);
      setPhase('execution');  // Update dial to execution immediately

      // Send approval to backend (backend just starts execution, no UI updates needed)
      sendApprovalResponse(routerId, true);
    } catch (error) {
      console.error('Error approving plan:', error);
    }
  };

  const handleApprovalRevise = async (routerId: string, feedback: string) => {
    try {
      // Immediately add feedback as user message to chat
      if (feedback && feedback.trim()) {
        const userMessage: ChatMessage = {
          id: Date.now().toString(),
          message: feedback,
          sender: 'user',
          timestamp: new Date(),
        };
        addMessage(userMessage);
      }

      // Immediately clear modal
      setPendingApproval(null);

      // Send revision request to backend asynchronously
      sendApprovalResponse(routerId, false, feedback);
    } catch (error) {
      console.error('Error requesting plan revision:', error);
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
            <ResizablePanelGroup direction="horizontal" className="h-full">
              {/* Landing Page Panel */}
              <ResizablePanel defaultSize={80} minSize={50}>
                <div className="flex flex-col h-full">
                  {/* Chat Header - Now inside the main panel only */}
                  <ChatHeader isConnected={wsConnected} />
                  <div className="flex-1 overflow-hidden">
                    <LandingPage
                      onFirstMessage={handleFirstMessage}
                      onDuplicateFound={handleDuplicateFound}
                      isConnected={wsConnected}
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
            
            {/* Approval UI Components */}
            {/* <PlamarinationStatus status={plamarinationStatus} /> */}
            
            {/* Plan Approval Card */}
            {pendingApproval && (
              <div className="fixed inset-0 bg-black/20 dark:bg-black/40 backdrop-blur-sm z-40 flex items-centre justify-centre p-4">
                <div className="w-full max-w-4xl max-h-[80vh] overflow-y-auto">
                  <PlanApprovalCard
                    data={{
                      plan: pendingApproval.plan,
                      template: pendingApproval.template,
                      routerId: pendingApproval.router_id,
                    }}
                    onApprove={handleApprovalApprove}
                    onRevise={handleApprovalRevise}
                  />
                </div>
              </div>
            )}
            
            {/* Duplicate File Dialog */}
            {duplicateDialog.open && duplicateDialog.duplicateInfo && duplicateDialog.duplicateInfo.existing_file && (
              <DuplicateFileDialog
                open={duplicateDialog.open}
                duplicateInfo={{
                  ...duplicateDialog.duplicateInfo,
                  existing_file: duplicateDialog.duplicateInfo.existing_file,
                  new_filename: duplicateDialog.duplicateInfo.new_filename || '',
                  options: duplicateDialog.duplicateInfo.options || []
                }}
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
          <ResizablePanelGroup direction="horizontal" className="h-full w-full">
            {/* Main Chat Panel */}
            <ResizablePanel defaultSize={80} minSize={50}>
              <div
                className="flex flex-col h-full min-w-0 overflow-hidden"
                role="application"
                aria-label="Chat Interface"
              >
                {/* Chat Header - Now inside the main chat panel only */}
                <ChatHeader isConnected={wsConnected} />

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
                    mode={currentMode}
                    onModeChange={(mode) => {
                      setMode(mode);
                      // Update mode in backend for existing conversations
                      if (currentRouterId) {
                        updateMode(mode, currentRouterId);
                      }
                    }}
                    phase={currentPhase}
                    onPhaseChange={(phase) => {
                      setPhase(phase);
                      // Update phase in backend for existing conversations
                      if (currentRouterId) {
                        updatePhase(phase, currentRouterId);
                      }
                    }}
                    phaseActive={phaseActive}
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
          
          {/* Approval UI Components */}
          {/* <PlamarinationStatus status={plamarinationStatus} /> */}
          
          {/* Plan Approval Card */}
          {pendingApproval && (
            <div className="fixed inset-0 bg-black/20 dark:bg-black/40 backdrop-blur-sm z-40 flex items-centre justify-centre p-4">
              <div className="w-full max-w-4xl max-h-[80vh] overflow-y-auto">
                <PlanApprovalCard
                  data={{
                    plan: pendingApproval.plan,
                    template: pendingApproval.template,
                    findings: pendingApproval.findings,
                    routerId: pendingApproval.router_id,
                  }}
                  onApprove={handleApprovalApprove}
                  onRevise={handleApprovalRevise}
                />
              </div>
            </div>
          )}
          
          {/* Duplicate File Dialog */}
          {duplicateDialog.open && duplicateDialog.duplicateInfo && duplicateDialog.duplicateInfo.existing_file && (
            <DuplicateFileDialog
              open={duplicateDialog.open}
              duplicateInfo={{
                ...duplicateDialog.duplicateInfo,
                existing_file: duplicateDialog.duplicateInfo.existing_file,
                new_filename: duplicateDialog.duplicateInfo.new_filename || '',
                options: duplicateDialog.duplicateInfo.options || []
              }}
              onResolve={handleDuplicateResolve}
              onClose={handleDuplicateClose}
            />
          )}
        </SidebarInset>
      </SidebarProvider>
    </ErrorBoundary>
  );
};