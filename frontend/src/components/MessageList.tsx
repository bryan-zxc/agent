'use client';

import { useEffect, useRef } from 'react';
import { cn } from '@/lib/utils';
import { ChatMessage } from '../../../shared/types';
import { AgentStatus } from '../../../shared/types';

interface MessageListProps {
  messages: ChatMessage[];
  status: AgentStatus;
  className?: string;
}

export const MessageList: React.FC<MessageListProps> = ({ 
  messages, 
  status, 
  className 
}) => {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  return (
    <main 
      className={cn(
        "flex-1 overflow-y-auto p-4 space-y-4",
        className
      )}
      role="main"
      aria-labelledby="chat-title"
      aria-live="polite"
    >
      <div className="space-y-4">
        {messages.map((message) => (
          <article
            key={message.id}
            className={cn(
              "flex",
              message.sender === 'user' ? 'justify-end' : 'justify-start'
            )}
            role="article"
            aria-label={`Message from ${message.sender}`}
          >
            <div
              className={cn(
                "max-w-xs sm:max-w-md md:max-w-lg px-4 py-3 rounded-lg shadow-sm transition-colors",
                message.sender === 'user'
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-card text-card-foreground border border-border'
              )}
            >
              <div className="whitespace-pre-wrap text-sm leading-relaxed">
                {message.message}
              </div>
              {message.files && message.files.length > 0 && (
                <div className="mt-2 text-xs opacity-75">
                  <span className="font-medium">Files:</span>{' '}
                  {message.files.map(f => f.split('/').pop()).join(', ')}
                </div>
              )}
              <time 
                className="block text-xs mt-2 opacity-60"
                dateTime={message.timestamp.toISOString()}
              >
                {message.timestamp.toLocaleTimeString()}
              </time>
            </div>
          </article>
        ))}
        
        {/* Status indicator */}
        {status.status !== 'idle' && (
          <div className="flex justify-start" role="status" aria-live="polite">
            <div className="bg-muted text-muted-foreground px-4 py-3 rounded-lg max-w-md border border-border">
              <div className="flex items-center space-x-2">
                <div 
                  className="animate-spin rounded-full h-4 w-4 border-2 border-muted-foreground border-t-transparent"
                  aria-hidden="true"
                />
                <span className="text-sm">
                  {status.message || 'Processing...'}
                </span>
              </div>
            </div>
          </div>
        )}
        
        <div ref={messagesEndRef} aria-hidden="true" />
      </div>
    </main>
  );
};