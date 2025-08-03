'use client';

import React, { useEffect, useState } from 'react';
import { useChatStore } from '../stores/chatStore';
import { Button } from './ui/button';
import { cn } from '@/lib/utils';
import { Plus, MessageSquare, X } from 'lucide-react';

interface ConversationSidebarProps {
  isOpen: boolean;
  onClose: () => void;
  onNewConversation?: () => void;
  onConversationSelect?: (conversationId: string, hasMessages: boolean) => void;
  refreshTrigger?: number; // Used to trigger refresh from parent
}

export const ConversationSidebar: React.FC<ConversationSidebarProps> = ({
  isOpen,
  onClose,
  onNewConversation,
  onConversationSelect,
  refreshTrigger,
}) => {
  console.log('ConversationSidebar component rendered, isOpen:', isOpen);
  
  const {
    currentConversationId,
    conversations,
    setConversations,
    createNewConversation,
    setCurrentConversation,
  } = useChatStore();
  
  console.log('Current conversations from store:', conversations.length);
  
  const [loading, setLoading] = useState(false);
  const [isInitialLoad, setIsInitialLoad] = useState(true);

  const fetchConversations = async (silent: boolean = false) => {
    console.log('fetchConversations called - isOpen:', isOpen, 'silent:', silent);
    
    // Only show loading for initial load or explicit non-silent calls
    if (!silent) {
      setLoading(true);
    }
    
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/conversations`);
      console.log('fetchConversations response status:', response.status);
      if (response.ok) {
        const data = await response.json();
        console.log('fetchConversations received data:', data.length, 'conversations');
        
        // Only update conversations after we have the data
        setConversations(data);
        
        if (isInitialLoad) {
          setIsInitialLoad(false);
        }
      } else {
        console.error('fetchConversations failed with status:', response.status);
      }
    } catch (error) {
      console.error('Error fetching conversations:', error);
    } finally {
      if (!silent) {
        setLoading(false);
      }
    }
  };

  // Removed direct call to prevent infinite loop

  useEffect(() => {
    // Load conversations immediately when component mounts
    console.log('ConversationSidebar useEffect running - about to call fetchConversations');
    fetchConversations();
  }, []); // Run only once on mount

  useEffect(() => {
    // Optionally refresh conversations when sidebar opens
    if (isOpen && !isInitialLoad) {
      // Use silent loading to avoid flickering when opening sidebar
      fetchConversations(true);
    }
  }, [isOpen]);

  useEffect(() => {
    // Refresh conversations when refreshTrigger changes (e.g., new conversation created)
    if (refreshTrigger !== undefined && refreshTrigger > 0) {
      // Use silent loading to avoid flickering when new conversations are added
      fetchConversations(true);
    }
  }, [refreshTrigger]);

  const handleNewConversation = () => {
    console.log('handleNewConversation clicked');
    if (onNewConversation) {
      onNewConversation();
    } else {
      // Fallback to old behavior if prop not provided
      createNewConversation();
    }
    onClose();
  };

  const handleSelectConversation = async (conversationId: string) => {
    if (conversationId === currentConversationId) {
      onClose();
      return;
    }

    try {
      // Get conversation metadata to check if it has messages
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/conversations/${conversationId}`);
      if (response.ok) {
        const data = await response.json();
        const hasMessages = data.messages.filter((msg: {role: string; content: string}) => msg.role !== 'system').length > 0;
        
        // Set the conversation in store
        setCurrentConversation(conversationId);
        
        // Notify parent about conversation selection (this will trigger WebSocket loading)
        if (onConversationSelect) {
          onConversationSelect(conversationId, hasMessages);
        }
        
        onClose();
      }
    } catch (error) {
      console.error('Error loading conversation:', error);
    }
  };

  const formatTimestamp = (timestamp: string) => {
    // Parse the UTC timestamp and create a Date object
    const date = new Date(timestamp + (timestamp.endsWith('Z') ? '' : 'Z'));
    const now = new Date();
    const diffInMs = now.getTime() - date.getTime();
    const diffInHours = diffInMs / (1000 * 60 * 60);
    const diffInDays = diffInMs / (1000 * 60 * 60 * 24);

    if (diffInHours < 1) {
      return 'Just now';
    } else if (diffInHours < 24) {
      return `${Math.floor(diffInHours)}h ago`;
    } else if (diffInDays < 7) {
      return `${Math.floor(diffInDays)}d ago`;
    } else {
      return date.toLocaleDateString();
    }
  };

  return (
    <>
      {/* Backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={onClose}
        />
      )}
      
      {/* Sidebar */}
      <div
        className={cn(
          "fixed left-0 top-0 h-full w-80 bg-card border-r shadow-lg z-50 transform transition-transform duration-200 ease-in-out",
          "flex flex-col",
          isOpen ? "translate-x-0" : "-translate-x-full",
          "lg:relative lg:translate-x-0 lg:shadow-none"
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b">
          <h2 className="text-lg font-semibold">Conversations</h2>
          <Button
            variant="ghost"
            size="sm"
            onClick={onClose}
            className="lg:hidden"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        {/* New Conversation Button */}
        <div className="p-4">
          <Button
            onClick={handleNewConversation}
            className="w-full justify-start gap-2"
            variant="outline"
          >
            <Plus className="h-4 w-4" />
            New Conversation
          </Button>
        </div>

        {/* Conversations List */}
        <div className="flex-1 overflow-y-auto">
          {loading && isInitialLoad ? (
            <div className="p-4 text-center text-muted-foreground">
              Loading conversations...
            </div>
          ) : conversations.length === 0 ? (
            <div className="p-4 text-center text-muted-foreground">
              No conversations yet
            </div>
          ) : (
            <div className="space-y-1 p-2">
              {conversations.map((conversation) => (
                <Button
                  key={conversation.id}
                  onClick={() => handleSelectConversation(conversation.id)}
                  variant={currentConversationId === conversation.id ? "secondary" : "ghost"}
                  className={cn(
                    "w-full justify-start text-left p-3 h-auto",
                    currentConversationId === conversation.id && 
                      "opacity-100 hover:opacity-100 hover:bg-muted/80 cursor-default"
                  )}
                >
                  <div className="flex items-start gap-3">
                    <MessageSquare className="h-4 w-4 mt-1 text-muted-foreground flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-sm truncate">
                        {conversation.title}
                      </div>
                      <div className="text-xs text-muted-foreground mt-1 truncate">
                        {conversation.preview}
                      </div>
                      <div className="text-xs text-muted-foreground mt-1">
                        {formatTimestamp(conversation.timestamp)}
                      </div>
                    </div>
                  </div>
                </Button>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
};