'use client';

import { cn } from '@/lib/utils';
import { Wifi, WifiOff, Menu, Loader2 } from 'lucide-react';
import Image from 'next/image';
import { Button } from './ui/button';
import { useChatStore } from '../stores/chatStore';

interface ChatHeaderProps {
  isConnected: boolean;
  className?: string;
  onMenuClick?: () => void;
}

export const ChatHeader: React.FC<ChatHeaderProps> = ({ 
  isConnected, 
  className,
  onMenuClick
}) => {
  const { isConnecting } = useChatStore();
  return (
    <header 
      className={cn(
        "bg-card/95 backdrop-blur-sm shadow-sm border-b p-4 sticky top-0 z-10",
        className
      )}
      role="banner"
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="sm"
            onClick={onMenuClick}
            className="lg:hidden"
          >
            <Menu className="h-4 w-4" />
          </Button>
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
            <p className="text-xs text-muted-foreground">
              Good friend (or maybe Dora&apos;s good friend&apos;s dad)
            </p>
          </div>
        </div>
        
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
    </header>
  );
};