'use client';

import React, { useState, useEffect } from 'react';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from './ui/card';

interface UsageStats {
  today: number;
  week: number;
  month: number;
  total: number;
}

export const CostCard: React.FC = () => {
  const [stats, setStats] = useState<UsageStats>({
    today: 0,
    week: 0,
    month: 0,
    total: 0,
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchUsageStats = async () => {
    try {
      setLoading(true);
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/usage`);
      if (!response.ok) {
        throw new Error('Failed to fetch usage stats');
      }
      const data = await response.json();
      setStats(data);
      setError(null);
    } catch (error) {
      console.error('Error fetching usage stats:', error);
      setError('Failed to load usage data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsageStats();
    // Refresh data every 30 seconds
    const interval = setInterval(fetchUsageStats, 30000);
    return () => clearInterval(interval);
  }, []);

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(amount);
  };

  if (loading) {
    return (
      <Card className="w-full bg-gray-200 dark:bg-gray-700 border-0 shadow-lg rounded-2xl">
        <CardHeader className="rounded-t-2xl">
          <CardTitle>Usage Costs</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            <div className="animate-pulse">
              <div className="h-4 bg-gray-100 dark:bg-gray-800 rounded w-3/4 mb-2"></div>
              <div className="h-6 bg-gray-100 dark:bg-gray-800 rounded w-1/2"></div>
            </div>
            <div className="animate-pulse">
              <div className="h-4 bg-gray-100 dark:bg-gray-800 rounded w-3/4 mb-2"></div>
              <div className="h-6 bg-gray-100 dark:bg-gray-800 rounded w-1/2"></div>
            </div>
            <div className="animate-pulse">
              <div className="h-4 bg-gray-100 dark:bg-gray-800 rounded w-3/4 mb-2"></div>
              <div className="h-6 bg-gray-100 dark:bg-gray-800 rounded w-1/2"></div>
            </div>
            <div className="animate-pulse">
              <div className="h-4 bg-gray-100 dark:bg-gray-800 rounded w-3/4 mb-2"></div>
              <div className="h-6 bg-gray-100 dark:bg-gray-800 rounded w-1/2"></div>
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className="w-full bg-gray-200 dark:bg-gray-700 border-0 shadow-lg rounded-2xl">
        <CardHeader className="rounded-t-2xl">
          <CardTitle>Usage Costs</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-destructive text-sm">{error}</div>
          <button 
            onClick={fetchUsageStats}
            className="mt-2 text-sm text-gray-500 dark:text-gray-400 hover:text-foreground underline"
          >
            Retry
          </button>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="w-full min-w-0 bg-gray-200 dark:bg-gray-700 border-0 shadow-lg rounded-2xl overflow-hidden">
      <CardHeader className="rounded-t-2xl">
        <CardTitle className="text-lg font-semibold">Usage Costs</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4 min-w-0">
          <div className="flex justify-between items-center min-w-0">
            <span className="text-sm text-gray-500 dark:text-gray-400 flex-shrink-0">Today</span>
            <span className="font-medium text-right break-all ml-2">{formatCurrency(stats.today)}</span>
          </div>
          
          <div className="flex justify-between items-center min-w-0">
            <span className="text-sm text-gray-500 dark:text-gray-400 flex-shrink-0">This Week</span>
            <span className="font-medium text-right break-all ml-2">{formatCurrency(stats.week)}</span>
          </div>
          
          <div className="flex justify-between items-center min-w-0">
            <span className="text-sm text-gray-500 dark:text-gray-400 flex-shrink-0">This Month</span>
            <span className="font-medium text-right break-all ml-2">{formatCurrency(stats.month)}</span>
          </div>
          
          <div className="border-t pt-4">
            <div className="flex justify-between items-center min-w-0">
              <span className="text-sm font-medium flex-shrink-0">Total</span>
              <span className="font-semibold text-lg text-right break-all ml-2">{formatCurrency(stats.total)}</span>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};