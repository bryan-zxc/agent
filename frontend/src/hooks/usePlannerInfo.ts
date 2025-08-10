import { useState, useEffect, useCallback } from 'react';
import { PlannerInfo } from '../../../shared/types';
import { useChatStore } from '../stores/chatStore';

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
  
  // Get real-time execution plan from store
  const currentExecutionPlan = useChatStore((state) => state.currentExecutionPlan);

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
    // Prioritise real-time data from WebSocket updates if it matches this message
    if (currentExecutionPlan && 
        currentExecutionPlan.execution_plan && 
        currentExecutionPlan.planner_id) {
      // For real-time updates, we don't have message ID context, so accept it
      setPlannerInfo(currentExecutionPlan);
      setError(null);
      return;
    }
    
    // Fallback to API fetching for specific message
    if (messageId) {
      fetchPlannerInfo();
    } else {
      setPlannerInfo(null);
    }
  }, [messageId, currentExecutionPlan]);

  return {
    plannerInfo,
    loading,
    error,
    refetch: fetchPlannerInfo,
  };
};