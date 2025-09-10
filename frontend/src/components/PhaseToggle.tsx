'use client';

import React from 'react';
import { Brain, Play } from 'lucide-react';
import { cn } from '@/lib/utils';

export type AgentPhase = 'plamarination' | 'execution' | null;

interface PhaseToggleProps {
  phase: AgentPhase;
  onPhaseChange: (phase: 'plamarination' | 'execution') => void; // Only non-null phases can be selected
  disabled?: boolean;
  className?: string;
  isActive?: boolean; // For visual indicators when processing
}

const phaseConfig = {
  plamarination: {
    icon: Brain,
    label: 'Plamarination',
    ariaLabel: 'Plamarination phase - Planning and analysis',
  },
  execution: {
    icon: Play,
    label: 'Execution',
    ariaLabel: 'Execution phase - Task execution',
  },
};

export const PhaseToggle: React.FC<PhaseToggleProps> = ({
  phase,
  onPhaseChange,
  disabled = false,
  className,
  isActive = false,
}) => {
  console.log('PhaseToggle: Rendering with phase:', phase);
  
  // Don't render the component if phase is null (not in agent mode)
  if (phase === null) {
    return null;
  }
  
  const handleButtonClick = (phaseKey: 'plamarination' | 'execution') => {
    console.log('PhaseToggle: Button clicked:', phaseKey);
    console.log('PhaseToggle: Current phase:', phase);
    if (phaseKey !== phase && !disabled) {
      console.log('PhaseToggle: Changing phase from', phase, 'to', phaseKey);
      onPhaseChange(phaseKey);
    }
  };
  
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <span className="text-sm font-medium text-muted-foreground">Phase:</span>
      <div className="inline-flex items-center justify-center gap-1 bg-muted p-1 rounded-lg">
        {(Object.keys(phaseConfig) as ('plamarination' | 'execution')[]).map((phaseKey) => {
          const config = phaseConfig[phaseKey];
          const Icon = config.icon;
          const isSelected = phase === phaseKey;
          const showActivity = isActive && isSelected;
          
          return (
            <button
              key={phaseKey}
              type="button"
              onClick={() => handleButtonClick(phaseKey)}
              disabled={disabled}
              aria-label={config.ariaLabel}
              aria-pressed={isSelected}
              className={cn(
                "inline-flex items-center justify-center text-xs font-medium transition-all",
                "h-8 px-2.5 rounded-md",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                "disabled:pointer-events-none disabled:opacity-50",
                // Selected state styling with shading
                isSelected && "bg-primary text-primary-foreground shadow-sm",
                // Unselected state styling with hover shading
                !isSelected && "bg-transparent hover:bg-muted-foreground/10",
                // Activity background shading
                showActivity && phaseKey === 'plamarination' && "bg-blue-50 dark:bg-blue-950 ring-2 ring-blue-200 dark:ring-blue-800",
                showActivity && phaseKey === 'execution' && "bg-green-50 dark:bg-green-950 ring-2 ring-green-200 dark:ring-green-800"
              )}
            >
              <div className="flex items-center">
                <Icon className="h-3.5 w-3.5 mr-1.5" />
                <span>{config.label}</span>
                {/* Visual activity indicator with pulsing dots for plamarination */}
                {showActivity && phaseKey === 'plamarination' && (
                  <div className="ml-2 flex space-x-0.5">
                    <div className="w-1 h-1 bg-blue-500 rounded-full animate-pulse" style={{ animationDelay: '0ms' }}></div>
                    <div className="w-1 h-1 bg-blue-500 rounded-full animate-pulse" style={{ animationDelay: '200ms' }}></div>
                    <div className="w-1 h-1 bg-blue-500 rounded-full animate-pulse" style={{ animationDelay: '400ms' }}></div>
                  </div>
                )}
                {/* Visual activity indicator with solid dot for execution */}
                {showActivity && phaseKey === 'execution' && (
                  <div className="ml-2 w-2 h-2 bg-green-500 rounded-full"></div>
                )}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
};