import { useState, useEffect, useCallback } from 'react';
import { PlannerInfo } from '../../../shared/types';

interface UsePlannerInfoResult {
  plannerInfo: PlannerInfo | null;
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

export const usePlannerInfo = (
  messageId: number | null
): UsePlannerInfoResult => {
  const [plannerInfo, setPlannerInfo] = useState<PlannerInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  

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
    } else {
      setPlannerInfo(null);
    }
  }, [messageId]);

  // Poll for planner updates until completion
  useEffect(() => {
    if (!messageId) return;
    
    // Don't poll if planner is already completed
    if (plannerInfo?.status === 'completed') return;

    console.log(`[FRONTEND] Starting polling for planner updates - message ${messageId}`);
    
    const pollInterval = setInterval(async () => {
      console.log(`[FRONTEND] Polling for planner updates - message ${messageId}, current status: ${plannerInfo?.status}`);
      
      try {
        const response = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL}/messages/${messageId}/planner-info`
        );
        
        if (response.ok) {
          const data: PlannerInfo = await response.json();
          setPlannerInfo(data);
          
          // If planner is completed, trigger completion handler and stop polling
          if (data.status === 'completed' && data.planner_id) {
            console.log(`[FRONTEND] Planner ${data.planner_id} completed - triggering completion handler`);
            
            // Call router completion API
            try {
              const completionResponse = await fetch(
                `${process.env.NEXT_PUBLIC_API_URL}/routers/${data.planner_id}/handle-planner-completion`,
                {
                  method: 'POST',
                  headers: {
                    'Content-Type': 'application/json',
                  },
                }
              );
              
              if (completionResponse.ok) {
                console.log(`[FRONTEND] Planner completion handler called successfully`);
              } else {
                console.error(`[FRONTEND] Failed to call planner completion handler:`, completionResponse.statusText);
              }
            } catch (completionError) {
              console.error(`[FRONTEND] Error calling planner completion handler:`, completionError);
            }
            
            return; // Stop polling
          }
        }
      } catch (error) {
        console.error(`[FRONTEND] Error polling for planner updates:`, error);
      }
    }, 2000); // Poll every 2 seconds

    // Cleanup polling on unmount or when planner is completed
    return () => {
      console.log(`[FRONTEND] Stopping polling for message ${messageId}`);
      clearInterval(pollInterval);
    };
  }, [messageId, plannerInfo?.status]);

  return {
    plannerInfo,
    loading,
    error,
    refetch: fetchPlannerInfo,
  };
};