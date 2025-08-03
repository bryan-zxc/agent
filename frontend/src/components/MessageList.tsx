'use client';

import { useEffect, useRef } from 'react';
import { cn } from '@/lib/utils';
import { ChatMessage } from '../../../shared/types';
import { AgentStatus } from '../../../shared/types';
import { Skeleton } from './ui/skeleton';
import { ThinkingDots } from './ui/thinking-dots';
import { User } from 'lucide-react';
import Image from 'next/image';
import { RichMarkdownRenderer } from './RichMarkdownRenderer';

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
  const containerRef = useRef<HTMLElement>(null);

  const scrollToBottom = () => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  return (
    <main 
      ref={containerRef}
      className={cn(
        "h-full overflow-y-auto p-4 space-y-4",
        className
      )}
      role="main"
      aria-labelledby="chat-title"
      aria-live="polite"
    >
      <div className="space-y-6">
        {messages.map((message) => (
          <article
            key={message.id}
            className="flex gap-3 w-full"
            role="article"
            aria-label={`Message from ${message.sender}`}
          >
            <div className="flex-shrink-0 w-8 h-8 rounded-full overflow-hidden shadow-sm">
              {message.sender === 'assistant' ? (
                <Image
                  src="/bandit-heeler.png"
                  alt="Bandit Heeler"
                  width={32}
                  height={32}
                  className="w-full h-full object-cover object-top"
                />
              ) : (
                <div className="w-full h-full bg-secondary rounded-full flex items-center justify-center">
                  <User className="w-4 h-4 text-secondary-foreground" />
                </div>
              )}
            </div>
            
            <div
              className={cn(
                "flex-1 px-4 py-3 transition-all duration-200",
                message.sender === 'user'
                  ? 'bg-card text-card-foreground rounded-lg shadow-sm hover:shadow-md'
                  : 'bg-transparent'
              )}
            >
              {message.sender === 'assistant' ? (
                <RichMarkdownRenderer content={message.message} />
              ) : (
                <div className="whitespace-pre-wrap text-sm leading-relaxed">
                  {message.message}
                </div>
              )}
              {message.files && message.files.length > 0 && (
                <div className="mt-3 p-2 rounded-lg bg-black/5 dark:bg-white/5">
                  <div className="text-xs font-medium opacity-75 mb-1">Attachments:</div>
                  <div className="text-xs opacity-60 space-y-1">
                    {message.files.map((file, index) => (
                      <div key={index} className="flex items-center gap-1">
                        <div className="w-1 h-1 rounded-full bg-current opacity-50" />
                        {file.split('/').pop()}
                      </div>
                    ))}
                  </div>
                </div>
              )}
              <time 
                className="block text-xs mt-2 opacity-50"
                dateTime={message.timestamp.toISOString()}
              >
                {message.timestamp.toLocaleTimeString()}
              </time>
            </div>

          </article>
        ))}
        
        {/* Status indicator with typing animation */}
        {status.status !== 'idle' && (
          <article className="flex gap-3 justify-start" role="status" aria-live="polite">
            <div className="flex-shrink-0 w-8 h-8 rounded-full overflow-hidden shadow-sm">
              <Image
                src="/bandit-heeler.png"
                alt="Bandit Heeler"
                width={32}
                height={32}
                className="w-full h-full object-cover object-top"
              />
            </div>
            
            <div className="bg-card text-card-foreground px-4 py-3 rounded-xl rounded-bl-md shadow-sm max-w-md">
              <div className="flex items-center space-x-2">
                <div 
                  className="animate-spin rounded-full h-4 w-4 border-2 border-primary border-t-transparent"
                  aria-hidden="true"
                />
                <span className="text-sm text-gray-500 dark:text-gray-400">
                  {status.message || 'Thinking'}<ThinkingDots />
                </span>
              </div>
              
              {/* Typing dots animation */}
              <div className="flex space-x-1 mt-2">
                <div className="w-1.5 h-1.5 bg-gray-500 dark:bg-gray-400 rounded-full animate-bounce [animation-delay:-0.3s]"></div>
                <div className="w-1.5 h-1.5 bg-gray-500 dark:bg-gray-400 rounded-full animate-bounce [animation-delay:-0.15s]"></div>
                <div className="w-1.5 h-1.5 bg-gray-500 dark:bg-gray-400 rounded-full animate-bounce"></div>
              </div>
            </div>
          </article>
        )}
        
        <div ref={messagesEndRef} aria-hidden="true" />
      </div>
    </main>
  );
};