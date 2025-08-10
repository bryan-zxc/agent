'use client';

import { useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import { ChatMessage } from '../../../shared/types';
import { AgentStatus } from '../../../shared/types';
import { Skeleton } from './ui/skeleton';
import { ThinkingDots } from './ui/thinking-dots';
import { User, ChevronDown, ChevronUp } from 'lucide-react';
import Image from 'next/image';
import { RichMarkdownRenderer } from './RichMarkdownRenderer';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from './ui/collapsible';
import { useChatStore } from '../stores/chatStore';
import { usePlannerInfo } from '../hooks/usePlannerInfo';

// Component for rendering "Agents assemble!" messages with execution plan
const AgentsAssembleMessage: React.FC<{
  message: ChatMessage;
  isExpanded: boolean;
  onToggleExpansion: () => void;
}> = ({ message, isExpanded, onToggleExpansion }) => {
  const { plannerInfo, loading } = usePlannerInfo(message.messageId || null);
  
  return (
    <article className="flex gap-3 justify-start min-w-0" role="article">
      <div className="flex-shrink-0 w-8 h-8 rounded-full overflow-hidden shadow-sm">
        <Image
          src="/bandit-heeler.png"
          alt="Bandit Heeler"
          width={32}
          height={32}
          className="w-full h-full object-cover object-top"
        />
      </div>
      
      <div className="bg-card text-card-foreground px-3 py-2 sm:px-4 sm:py-3 rounded-xl rounded-bl-md shadow-sm flex-1 max-w-[calc(100vw-5rem)] sm:max-w-md min-w-0">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-primary">
            {message.message}
          </span>
          <time className="text-xs text-muted-foreground ml-2 flex-shrink-0">
            {message.timestamp.toLocaleTimeString()}
          </time>
        </div>
        
        {/* Expandable execution plan section */}
        {plannerInfo?.has_planner && plannerInfo.execution_plan && (
          <Collapsible
            open={isExpanded}
            onOpenChange={onToggleExpansion}
            className="mt-3"
          >
            <CollapsibleTrigger className="flex items-center space-x-2 text-xs text-muted-foreground hover:text-foreground focus-visible:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 transition-colors w-full justify-start p-2 border-0 bg-transparent rounded-md min-h-[44px] sm:min-h-auto sm:p-0 -mx-2 sm:mx-0">
              {isExpanded ? (
                <ChevronUp className="h-3 w-3" />
              ) : (
                <ChevronDown className="h-3 w-3" />
              )}
              <span>
                {isExpanded ? 'Hide' : 'Show'} execution plan
              </span>
            </CollapsibleTrigger>
            
            <CollapsibleContent className="mt-2">
              <div className="bg-muted/50 rounded-md p-3 text-xs">
                <div className="text-muted-foreground mb-2 font-medium">
                  Execution Plan:
                </div>
                <div className="prose prose-xs max-w-none dark:prose-invert">
                  <RichMarkdownRenderer content={plannerInfo.execution_plan} />
                </div>
              </div>
            </CollapsibleContent>
          </Collapsible>
        )}
        
        {loading && (
          <div className="mt-2 text-xs text-muted-foreground">
            Loading execution plan...
          </div>
        )}
      </div>
    </article>
  );
};

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
  const [expandedMessages, setExpandedMessages] = useState<Set<string>>(new Set());
  
  // Helper function to check if message is "Agents assemble!" and has planner
  const isAgentsAssembleMessage = (message: ChatMessage) => {
    return message.sender === 'assistant' && 
           message.message === 'Agents assemble!' && 
           message.messageId;
  };
  
  // Helper function to toggle expansion of a message
  const toggleMessageExpansion = (messageId: string) => {
    setExpandedMessages(prev => {
      const newSet = new Set(prev);
      if (newSet.has(messageId)) {
        newSet.delete(messageId);
      } else {
        newSet.add(messageId);
      }
      return newSet;
    });
  };

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
        "h-full overflow-y-auto overflow-x-hidden p-4 space-y-4 min-w-0",
        className
      )}
      role="main"
      aria-labelledby="chat-title"
      aria-live="polite"
    >
      <div className="space-y-6">
        {messages.map((message) => {
          // Special handling for "Agents assemble!" messages
          if (isAgentsAssembleMessage(message)) {
            return (
              <AgentsAssembleMessage
                key={message.id}
                message={message}
                isExpanded={expandedMessages.has(message.id)}
                onToggleExpansion={() => toggleMessageExpansion(message.id)}
              />
            );
          }
          
          // Regular message rendering
          return (
            <article
              key={message.id}
              className="flex gap-3 w-full min-w-0"
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
                  "flex-1 px-3 py-2 sm:px-4 sm:py-3 transition-all duration-200 min-w-0",
                  message.sender === 'user'
                    ? 'bg-card text-card-foreground rounded-lg shadow-sm hover:shadow-md max-w-[calc(100vw-5rem)] sm:max-w-none'
                    : 'bg-transparent'
                )}
              >
                {message.sender === 'assistant' ? (
                  <RichMarkdownRenderer content={message.message} />
                ) : (
                  <div className="whitespace-pre-wrap text-sm leading-relaxed break-words overflow-wrap-anywhere">
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
          );
        })}
        
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
            
            <div className="bg-card text-card-foreground px-3 py-2 sm:px-4 sm:py-3 rounded-xl rounded-bl-md shadow-sm max-w-[calc(100vw-5rem)] sm:max-w-md min-w-0">
              <div className="flex items-center space-x-2">
                <div 
                  className="animate-spin rounded-full h-4 w-4 border-2 border-primary border-t-transparent"
                  aria-hidden="true"
                />
                <span className="text-sm text-gray-500 dark:text-gray-400">
                  {status.message || 'Thinking'}<ThinkingDots />
                </span>
              </div>
            </div>
          </article>
        )}
        
        <div ref={messagesEndRef} aria-hidden="true" />
      </div>
    </main>
  );
};