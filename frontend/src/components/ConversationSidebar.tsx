'use client';

import React, { useEffect, useState } from 'react';
import { useChatStore } from '../stores/chatStore';
import { Button } from './ui/button';
import { Sidebar, SidebarContent, SidebarHeader, SidebarMenu, SidebarMenuItem, SidebarMenuButton } from './ui/sidebar';
import { Plus, MessageSquare, Loader2 } from 'lucide-react';

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
  const [loadingConversationId, setLoadingConversationId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchConversations = async (silent: boolean = false) => {
    console.log('fetchConversations called, silent:', silent);
    console.log('API URL from environment:', process.env.NEXT_PUBLIC_API_URL);
    
    // Clear any previous errors
    setError(null);
    
    // Only show loading for initial load or explicit non-silent calls
    if (!silent) {
      setLoading(true);
    }
    
    try {
      // Check API URL configuration with fallback
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';
      if (!process.env.NEXT_PUBLIC_API_URL) {
        console.warn('NEXT_PUBLIC_API_URL environment variable is not set, using fallback:', apiUrl);
      }
      
      const requestUrl = `${apiUrl}/routers`;
      console.log('Making API request to:', requestUrl);
      
      const response = await fetch(requestUrl);
      console.log('fetchConversations response status:', response.status);
      console.log('fetchConversations response ok:', response.ok);
      
      if (response.ok) {
        const data = await response.json();
        console.log('fetchConversations received data:', data.length, 'conversations');
        console.log('Conversation data structure sample:', data.length > 0 ? data[0] : 'No conversations');
        
        // Validate response structure
        if (!Array.isArray(data)) {
          console.error('Invalid response structure - expected array, got:', typeof data);
          throw new Error('Invalid response format from server');
        }
        
        // Validate each conversation object
        const invalidConversations = data.filter(conv => !conv.id || !conv.title);
        if (invalidConversations.length > 0) {
          console.warn('Found invalid conversation objects:', invalidConversations);
        }
        
        // Only update conversations after we have the data
        setConversations(data);
        
        if (isInitialLoad) {
          console.log('Initial load completed');
          setIsInitialLoad(false);
        }
      } else {
        console.error('fetchConversations failed with status:', response.status);
        const errorText = await response.text();
        console.error('API error response:', errorText);
        throw new Error(`Failed to fetch conversations: ${response.status} ${response.statusText}`);
      }
    } catch (error) {
      console.error('Error fetching conversations:', error);
      console.error('Full error details:', {
        message: error instanceof Error ? error.message : 'Unknown error',
        apiUrl: process.env.NEXT_PUBLIC_API_URL,
        silent
      });
      
      // Set error state for user feedback
      const errorMessage = error instanceof Error ? error.message : 'Failed to load conversations';
      setError(`Error loading conversations: ${errorMessage}`);
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
    console.log('handleSelectConversation called with routerId:', routerId);
    console.log('Current routerId:', currentRouterId);
    
    if (routerId === currentRouterId) {
      console.log('Conversation already selected, returning early');
      return;
    }

    // Check if another conversation is already loading
    if (loadingConversationId) {
      console.log('Another conversation is loading, ignoring click:', loadingConversationId);
      return;
    }

    console.log('Attempting to select conversation:', routerId);
    setLoadingConversationId(routerId);
    setError(null); // Clear any previous errors
    
    try {
      // Check API URL configuration with fallback
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';
      if (!process.env.NEXT_PUBLIC_API_URL) {
        console.warn('NEXT_PUBLIC_API_URL environment variable is not set, using fallback:', apiUrl);
      }
      
      const requestUrl = `${apiUrl}/routers/${routerId}`;
      console.log('Making API request to:', requestUrl);
      
      // Get conversation metadata to check if it has messages
      const response = await fetch(requestUrl);
      console.log('API response status:', response.status);
      console.log('API response ok:', response.ok);
      
      if (response.ok) {
        const data = await response.json();
        console.log('API response data:', data);
        
        // Validate response structure
        if (!data.messages || !Array.isArray(data.messages)) {
          console.error('Invalid API response structure:', data);
          throw new Error('Invalid response format from server');
        }
        
        const hasMessages = data.messages.filter((msg: {role: string; content: string}) => msg.role !== 'system').length > 0;
        console.log('Conversation hasMessages:', hasMessages, 'Total messages:', data.messages.length);
        
        // Set the conversation in store
        console.log('Setting current conversation to:', routerId);
        setCurrentConversation(routerId);
        
        // Notify parent about conversation selection (this will trigger WebSocket loading)
        if (onConversationSelect) {
          console.log('Calling onConversationSelect with:', routerId, hasMessages);
          onConversationSelect(routerId, hasMessages);
        } else {
          console.warn('onConversationSelect callback not provided');
        }
        
        console.log('Conversation selection completed successfully');
      } else {
        console.error('API request failed with status:', response.status);
        const errorText = await response.text();
        console.error('API error response:', errorText);
        throw new Error(`Failed to load conversation: ${response.status} ${response.statusText}`);
      }
    } catch (error) {
      console.error('Error loading conversation:', error);
      console.error('Full error details:', {
        message: error instanceof Error ? error.message : 'Unknown error',
        routerId,
        apiUrl: process.env.NEXT_PUBLIC_API_URL
      });
      
      // Set error state for user feedback
      const errorMessage = error instanceof Error ? error.message : 'Failed to load conversation';
      setError(`Error selecting conversation: ${errorMessage}`);
    } finally {
      setLoadingConversationId(null);
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
        {error && (
          <div className="p-4 text-center text-red-500 dark:text-red-400 text-sm">
            {error}
            <Button
              onClick={() => fetchConversations()}
              variant="outline"
              size="sm"
              className="mt-2 w-full"
            >
              Retry
            </Button>
          </div>
        )}
        
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
            {conversations.map((conversation) => {
              const isLoading = loadingConversationId === conversation.id;
              const isSelected = currentRouterId === conversation.id;
              
              return (
                <SidebarMenuItem key={conversation.id}>
                  <Button
                    onClick={() => handleSelectConversation(conversation.id)}
                    variant={isSelected ? "secondary" : "ghost"}
                    className="h-auto p-3 w-full justify-start"
                    disabled={isLoading || (loadingConversationId !== null && !isLoading)}
                  >
                    <div className="flex items-start gap-3 w-full">
                      {isLoading ? (
                        <Loader2 className="h-4 w-4 mt-1 animate-spin text-primary flex-shrink-0" />
                      ) : (
                        <MessageSquare className="h-4 w-4 mt-1 text-gray-500 dark:text-gray-400 flex-shrink-0" />
                      )}
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
              );
            })}
          </SidebarMenu>
        )}
      </SidebarContent>
    </Sidebar>
  );
};