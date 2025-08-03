'use client';

import React, { Component, ErrorInfo, ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { AlertCircle, RefreshCw } from 'lucide-react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  className?: string;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo);
  }

  private handleReset = () => {
    this.setState({ hasError: false, error: undefined });
  };

  public render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div 
          className={cn(
            "flex flex-col items-center justify-center min-h-[200px] p-6 text-center",
            "bg-card border border-border rounded-lg",
            this.props.className
          )}
          role="alert"
          aria-live="assertive"
        >
          <AlertCircle className="h-12 w-12 text-destructive mb-4" />
          
          <h2 className="text-lg font-semibold text-foreground mb-2">
            Something went wrong
          </h2>
          
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-4 max-w-md">
            An unexpected error occurred. Please try refreshing the page or contact support if the problem persists.
          </p>

          {process.env.NODE_ENV === 'development' && this.state.error && (
            <details className="mt-4 p-3 bg-gray-100 dark:bg-gray-800 rounded text-left max-w-lg overflow-auto">
              <summary className="cursor-pointer text-sm font-mono text-gray-500 dark:text-gray-400">
                Error Details (Development Only)
              </summary>
              <pre className="mt-2 text-xs text-gray-500 dark:text-gray-400 whitespace-pre-wrap">
                {this.state.error.stack}
              </pre>
            </details>
          )}
          
          <button
            onClick={this.handleReset}
            className={cn(
              "inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors",
              "h-10 px-4 py-2 bg-primary text-primary-foreground hover:bg-primary/90",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
              "mt-4"
            )}
            aria-label="Try again"
          >
            <RefreshCw className="h-4 w-4 mr-2" />
            Try Again
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}