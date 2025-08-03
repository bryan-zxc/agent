'use client';

import React from 'react';
import { MessageInput } from './MessageInput';
import { ChatHeader } from './ChatHeader';
import { useChatStore } from '../stores/chatStore';
import { cn } from '@/lib/utils';

interface LandingPageProps {
  onFirstMessage: (message: string, files: File[]) => Promise<void>;
  isConnected: boolean;
  onMenuClick?: () => void;
}

export const LandingPage: React.FC<LandingPageProps> = ({
  onFirstMessage,
  isConnected,
  onMenuClick,
}) => {
  return (
    <div 
      className={cn(
        "flex flex-col flex-1 min-w-0",
        "max-w-4xl mx-auto w-full"
      )}
      role="application"
      aria-label="Landing Page"
    >
      {/* Header with Bandit Profile */}
      <ChatHeader 
        isConnected={isConnected}
        onMenuClick={onMenuClick}
      />

      {/* Main Content - Centered */}
      <div className="flex-1 flex flex-col items-center justify-center px-6">
        {/* Title */}
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold text-foreground mb-2">
            G'day Mate!
          </h1>
          <p className="text-muted-foreground text-lg">
            Ready for a chat? What fun adventure shall we dive into today?
          </p>
        </div>

        {/* Centered Message Input */}
        <div className="w-full max-w-2xl">
          <div className="border rounded-lg bg-card/50 backdrop-blur-sm shadow-lg">
            <MessageInput 
              onSubmit={onFirstMessage}
              disabled={!isConnected}
              className="border-0 bg-transparent"
              placeholder="Type your message to start a conversation..."
            />
          </div>
        </div>
      </div>
    </div>
  );
};