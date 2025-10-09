'use client';

import React from 'react';
import { Brain } from 'lucide-react';
import { cn } from '@/lib/utils';

export type PlamarinationStatusType = 'planning' | 'waiting_approval' | 'approved' | null;

interface PlamarinationStatusProps {
  status: PlamarinationStatusType;
  className?: string;
}

const statusConfig = {
  planning: {
    label: 'Planning in Progress',
    description: 'Analysing requirements and generating execution plan',
    dotColour: 'bg-blue-500',
    containerColour: 'bg-blue-500/10 border-blue-200/20 dark:bg-blue-950/20 dark:border-blue-800/20',
    textColour: 'text-blue-700 dark:text-blue-300',
    animation: 'animate-pulse',
  },
  waiting_approval: {
    label: 'Awaiting Approval',
    description: 'Plan ready for your review and approval',
    dotColour: 'bg-amber-500',
    containerColour: 'bg-amber-500/10 border-amber-200/20 dark:bg-amber-950/20 dark:border-amber-800/20',
    textColour: 'text-amber-700 dark:text-amber-300',
    animation: 'animate-bounce',
  },
  approved: {
    label: 'Plan Approved',
    description: 'Ready to proceed with execution',
    dotColour: 'bg-green-500',
    containerColour: 'bg-green-500/10 border-green-200/20 dark:bg-green-950/20 dark:border-green-800/20',
    textColour: 'text-green-700 dark:text-green-300',
    animation: '',
  },
};

export const PlamarinationStatus: React.FC<PlamarinationStatusProps> = ({
  status,
  className,
}) => {
  // Don't render if no status
  if (!status) return null;

  const config = statusConfig[status];

  return (
    <div className={cn(
      // Floating shaded indicator with translucent backgrounds
      "fixed top-20 right-6 z-50",
      // Smooth entry/exit animations
      "animate-in fade-in-0 slide-in-from-right-4 duration-500",
      // Container with shaded background - NO borders or subtle borders only
      "rounded-lg p-4 shadow-lg backdrop-blur-sm",
      config.containerColour,
      // Responsive behaviour
      "max-w-xs sm:max-w-sm",
      className
    )}>
      <div className="flex items-start gap-3">
        {/* Status icon with pulsing animation */}
        <div className="flex-shrink-0 mt-0.5">
          <Brain className={cn("h-4 w-4", config.textColour)} />
        </div>
        
        <div className="flex-1 min-w-0">
          {/* Status label with appropriate colour */}
          <div className={cn("flex items-centre gap-2", config.textColour)}>
            <span className="font-medium text-sm">{config.label}</span>
            {/* Pulsing status dot */}
            <div className={cn(
              "w-2 h-2 rounded-full",
              config.dotColour,
              config.animation
            )} />
          </div>
          
          {/* Status description */}
          <p className={cn(
            "text-xs mt-1 opacity-80",
            config.textColour
          )}>
            {config.description}
          </p>
        </div>
      </div>
    </div>
  );
};