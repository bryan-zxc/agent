import { useState, useEffect, useCallback } from 'react';
import { PlannerInfo } from '../../../shared/types';
import { useWebSocket } from './useWebSocket';
import { useChatStore } from '../stores/chatStore';

interface UsePlannerInfoResult {
  plannerInfo: PlannerInfo | null;
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

export const usePlannerInfo = (
  messageId: number | null,
  shouldPoll: boolean = true
): UsePlannerInfoResult => {
  const [plannerInfo, setPlannerInfo] = useState<PlannerInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasCalledCompletion, setHasCalledCompletion] = useState(false);
  const [hasRefreshedMessages, setHasRefreshedMessages] = useState(false);
  
  // Get WebSocket and store access for conversation refresh
  const { loadConversation } = useWebSocket();
  const currentRouterId = useChatStore(state => state.currentRouterId);

  const fetchPlannerInfo = useCallback(async () => {
    if (!messageId) {
      setPlannerInfo(null);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/messages/${messageId}/planner-info`
      );

      if (!response.ok) {
        throw new Error('Failed to fetch planner information');
      }

      const data: PlannerInfo = await response.json();
      setPlannerInfo(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error occurred');
      setPlannerInfo(null);
    } finally {
      setLoading(false);
    }
  }, [messageId]);

  useEffect(() => {
    // Always fetch from API since we should always have a messageId
    if (messageId) {
      fetchPlannerInfo();
      setHasCalledCompletion(false); // Reset completion flag for new message
      setHasRefreshedMessages(false); // Reset refresh flag for new message
    } else {
      setPlannerInfo(null);
    }
  }, [messageId]);

  // Poll for planner updates until completion
  useEffect(() => {
    if (!messageId) return;
    
    // Don't poll unless explicitly requested
    if (!shouldPoll) return;
    
    // Don't poll if planner is already completed or completion handler already called
    if (plannerInfo?.status === 'completed' || hasCalledCompletion) return;

    console.log(`[FRONTEND] Starting polling for planner updates - message ${messageId}`);
    
    const pollInterval = setInterval(async () => {
      console.log(`[FRONTEND] Polling for planner updates - message ${messageId}, current status: ${plannerInfo?.status}, completion called: ${hasCalledCompletion}`);
      
      try {
        const response = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL}/messages/${messageId}/planner-info`
        );
        
        if (response.ok) {
          const data: PlannerInfo = await response.json();
          setPlannerInfo(data);
          
          // PHASE 1: Simplified completion detection with message refresh
          if (data.status === 'completed') {
            console.log(`[FRONTEND] Planner ${data.planner_id} completed - refreshing messages and stopping polling`);
            
            // Refresh conversation messages if we haven't already and have router ID
            if (!hasRefreshedMessages && currentRouterId && loadConversation) {
              console.log(`[FRONTEND] Triggering conversation refresh for router ${currentRouterId}`);
              loadConversation(currentRouterId);
              setHasRefreshedMessages(true);
            }
            
            // Set completion flag and stop polling
            setHasCalledCompletion(true);
            clearInterval(pollInterval);
            return;
          }
        }
      } catch (error) {
        console.error(`[FRONTEND] Error polling for planner updates:`, error);
      }
    }, 2000); // Poll every 2 seconds

    // Cleanup polling on unmount
    return () => {
      console.log(`[FRONTEND] Stopping polling for message ${messageId}`);
      clearInterval(pollInterval);
    };
  }, [messageId, shouldPoll, hasCalledCompletion, hasRefreshedMessages, currentRouterId, loadConversation]);

  return {
    plannerInfo,
    loading,
    error,
    refetch: fetchPlannerInfo,
  };
};