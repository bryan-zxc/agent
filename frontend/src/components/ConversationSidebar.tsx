'use client';

import React, { useEffect, useState } from 'react';
import { useChatStore } from '../stores/chatStore';
import { Button } from './ui/button';
import { Sidebar, SidebarContent, SidebarHeader, SidebarMenu, SidebarMenuItem, SidebarMenuButton } from './ui/sidebar';
import { Plus, MessageSquare } from 'lucide-react';

interface ConversationSidebarProps {
  onNewConversation?: () => void;
  onConversationSelect?: (routerId: string, hasMessages: boolean) => void;
  refreshTrigger?: number; // Used to trigger refresh from parent
}

export const ConversationSidebar: React.FC<ConversationSidebarProps> = ({
  onNewConversation,
  onConversationSelect,
  refreshTrigger,
}) => {
  
  const {
    currentRouterId,
    conversations,
    setConversations,
    createNewConversation,
    setCurrentConversation,
  } = useChatStore();
  
  console.log('Current conversations from store:', conversations.length);
  
  const [loading, setLoading] = useState(false);
  const [isInitialLoad, setIsInitialLoad] = useState(true);

  const fetchConversations = async (silent: boolean = false) => {
    console.log('fetchConversations called, silent:', silent);
    
    // Only show loading for initial load or explicit non-silent calls
    if (!silent) {
      setLoading(true);
    }
    
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/routers`);
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
  };

  const handleSelectConversation = async (routerId: string) => {
    if (routerId === currentRouterId) {
      return;
    }

    try {
      // Get conversation metadata to check if it has messages
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/routers/${routerId}`);
      if (response.ok) {
        const data = await response.json();
        const hasMessages = data.messages.filter((msg: {role: string; content: string}) => msg.role !== 'system').length > 0;
        
        // Set the conversation in store
        setCurrentConversation(routerId);
        
        // Notify parent about conversation selection (this will trigger WebSocket loading)
        if (onConversationSelect) {
          onConversationSelect(routerId, hasMessages);
        }
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
    <Sidebar>
      <SidebarHeader>
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Conversations</h2>
        </div>
        
        {/* New Conversation Button */}
        <Button
          onClick={handleNewConversation}
          className="w-full justify-start gap-2"
          variant="outline"
        >
          <Plus className="h-4 w-4" />
          New Conversation
        </Button>
      </SidebarHeader>

      <SidebarContent>
        {loading && isInitialLoad ? (
          <div className="p-4 text-center text-gray-500 dark:text-gray-400">
            Loading conversations...
          </div>
        ) : conversations.length === 0 ? (
          <div className="p-4 text-center text-gray-500 dark:text-gray-400">
            No conversations yet
          </div>
        ) : (
          <SidebarMenu>
            {conversations.map((conversation) => (
              <SidebarMenuItem key={conversation.id}>
                <Button
                  onClick={() => handleSelectConversation(conversation.id)}
                  variant={currentRouterId === conversation.id ? "secondary" : "ghost"}
                  className="h-auto p-3 w-full justify-start"
                >
                  <div className="flex items-start gap-3 w-full">
                    <MessageSquare className="h-4 w-4 mt-1 text-gray-500 dark:text-gray-400 flex-shrink-0" />
                    <div className="flex-1 min-w-0 text-left">
                      <div className="font-medium text-sm truncate">
                        {conversation.title}
                      </div>
                      <div className="text-xs text-gray-500 dark:text-gray-400 mt-1 truncate">
                        {conversation.preview}
                      </div>
                      <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                        {formatTimestamp(conversation.timestamp)}
                      </div>
                    </div>
                  </div>
                </Button>
              </SidebarMenuItem>
            ))}
          </SidebarMenu>
        )}
      </SidebarContent>
    </Sidebar>
  );
};