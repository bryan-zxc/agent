'use client';

import React from 'react';
import { useChatStore } from '../stores/chatStore';
import { useWebSocket } from '../hooks/useWebSocket';
import { ChatHeader } from './ChatHeader';
import { MessageList } from './MessageList';
import { MessageInput } from './MessageInput';
import { ErrorBoundary } from './ErrorBoundary';
import { cn } from '@/lib/utils';

export const ChatInterface: React.FC = () => {
  const { messages, status, isConnected } = useChatStore();
  const { sendMessage } = useWebSocket('default');

  const handleSubmit = async (message: string, files: File[]) => {
    if (!message.trim() || !isConnected) return;

    // Upload files if any
    const filePaths: string[] = [];
    if (files.length > 0) {
      for (const file of files) {
        const formData = new FormData();
        formData.append('file', file);
        
        try {
          const response = await fetch('http://localhost:8000/upload', {
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

    // Send message
    sendMessage(message, filePaths);
  };

  return (
    <ErrorBoundary>
      <div 
        className={cn(
          "flex flex-col h-screen bg-background",
          "min-h-screen w-full"
        )}
        role="application"
        aria-label="Chat Interface"
      >
        <ChatHeader isConnected={isConnected} />
        
        <MessageList 
          messages={messages} 
          status={status}
        />

        <MessageInput 
          onSubmit={handleSubmit}
          disabled={!isConnected}
        />
      </div>
    </ErrorBoundary>
  );
};