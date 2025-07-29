'use client';

import { cn } from '@/lib/utils';

interface ChatHeaderProps {
  isConnected: boolean;
  className?: string;
}

export const ChatHeader: React.FC<ChatHeaderProps> = ({ 
  isConnected, 
  className 
}) => {
  return (
    <header 
      className={cn(
        "bg-card shadow-sm border-b p-4",
        className
      )}
      role="banner"
    >
      <div className="flex items-center justify-between">
        <h1 
          className="text-xl font-semibold text-card-foreground"
          id="chat-title"
        >
          Agent Chat
        </h1>
        <div 
          className="flex items-center space-x-2"
          role="status"
          aria-live="polite"
          aria-label={`Connection status: ${isConnected ? 'Connected' : 'Disconnected'}`}
        >
          <div 
            className={cn(
              "w-3 h-3 rounded-full transition-colors",
              isConnected ? 'bg-green-500' : 'bg-destructive'
            )}
            aria-hidden="true"
          />
          <span className="text-sm text-muted-foreground">
            {isConnected ? 'Connected' : 'Disconnected'}
          </span>
        </div>
      </div>
    </header>
  );
};