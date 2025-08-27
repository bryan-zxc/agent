'use client';

import { cn } from '@/lib/utils';
import { Wifi, WifiOff, Loader2 } from 'lucide-react';
import Image from 'next/image';
import { SidebarTrigger } from './ui/sidebar';
import { Separator } from './ui/separator';
import { useChatStore } from '../stores/chatStore';

interface ChatHeaderProps {
  isConnected: boolean;
  className?: string;
}

export const ChatHeader: React.FC<ChatHeaderProps> = ({ 
  isConnected, 
  className,
}) => {
  const { isConnecting, currentRouterId, isConversationLocked } = useChatStore();
  const isCurrentConversationLocked = isConversationLocked(currentRouterId);
  return (
    <header 
      className={cn(
        "bg-gray-100/90 dark:bg-gray-800/90 backdrop-blur-lg shadow-lg px-4 py-3 sticky top-0 z-10 rounded-b-xl",
        className
      )}
      role="banner"
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1">
          <SidebarTrigger className="-ml-1" />
          <Separator
            orientation="vertical"
            className="mx-1 h-4"
          />
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl overflow-hidden shadow-sm">
              <Image
                src="/bandit-heeler.png"
                alt="Bandit Heeler"
                width={40}
                height={40}
                className="w-full h-full object-cover object-top"
              />
            </div>
            <div>
              <h1 
                className="text-lg font-semibold text-card-foreground"
                id="chat-title"
              >
                Bandit Heeler
              </h1>
              <p className="text-xs text-gray-500 dark:text-gray-400">
                Good friend (or maybe Dora&apos;s good friend&apos;s dad)
              </p>
            </div>
          </div>
        </div>
        
        <div className="flex items-center gap-2">
          {/* Processing indicator */}
          {isCurrentConversationLocked && (
            <div 
              className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-400 transition-colors"
              role="status"
              aria-live="polite"
              aria-label="Processing request"
            >
              <Loader2 className="w-3 h-3 animate-spin" />
              <span className="text-xs font-medium">Processing</span>
            </div>
          )}
          
          {/* Connection status */}
          <div 
            className={cn(
              "flex items-center gap-2 px-3 py-1.5 rounded-full transition-colors",
              isConnected 
                ? "bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400"
                : isConnecting
                ? "bg-yellow-50 text-yellow-700 dark:bg-yellow-900/20 dark:text-yellow-400"
                : "bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400"
            )}
            role="status"
            aria-live="polite"
            aria-label={`Connection status: ${isConnected ? 'Connected' : isConnecting ? 'Connecting' : 'Disconnected'}`}
          >
            {isConnected ? (
              <Wifi className="w-3 h-3" />
            ) : isConnecting ? (
              <Loader2 className="w-3 h-3 animate-spin" />
            ) : (
              <WifiOff className="w-3 h-3" />
            )}
            <span className="text-xs font-medium">
              {isConnected ? 'Online' : isConnecting ? 'Connecting' : 'Offline'}
            </span>
          </div>
        </div>
      </div>
    </header>
  );
};