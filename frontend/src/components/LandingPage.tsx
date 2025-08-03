'use client';

import React from 'react';
import { MessageInput } from './MessageInput';
import { useChatStore } from '../stores/chatStore';
import { cn } from '@/lib/utils';

interface LandingPageProps {
  onFirstMessage: (message: string, files: File[]) => Promise<void>;
  isConnected: boolean;
}

export const LandingPage: React.FC<LandingPageProps> = ({
  onFirstMessage,
  isConnected,
}) => {
  return (
    <div 
      className={cn(
        "flex flex-col h-full min-w-0",
        "max-w-4xl mx-auto w-full"
      )}
      role="application"
      aria-label="Landing Page"
    >
      {/* Main Content - Centered */}
      <div className="flex-1 flex flex-col items-center justify-center px-6 min-h-0">
        {/* Title */}
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold text-foreground mb-2">
            G'day Mate!
          </h1>
          <p className="text-gray-600 dark:text-gray-400 text-lg">
            Ready for a chat? What fun adventure shall we dive into today?
          </p>
        </div>

        {/* Centered Message Input */}
        <div className="w-full max-w-2xl">
          <div className="bg-gray-100/70 dark:bg-gray-800/70 rounded-2xl backdrop-blur-md shadow-xl border-0">
            <MessageInput 
              onSubmit={onFirstMessage}
              disabled={!isConnected}
              className="border-0 bg-transparent rounded-2xl"
              placeholder="Type your message to start a conversation..."
            />
          </div>
        </div>
      </div>
    </div>
  );
};