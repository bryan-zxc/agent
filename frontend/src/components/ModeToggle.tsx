'use client';

import React from 'react';
import { Zap, Bot, Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils';

export type RouterMode = 'auto' | 'rapid' | 'agent';

interface ModeToggleProps {
  mode: RouterMode;
  onModeChange: (mode: RouterMode) => void;
  disabled?: boolean;
  className?: string;
}

const modeConfig = {
  auto: {
    icon: Sparkles,
    label: 'Auto',
    ariaLabel: 'Auto mode - Intelligent routing',
  },
  rapid: {
    icon: Zap,
    label: 'Rapid',
    ariaLabel: 'Rapid mode - Quick responses',
  },
  agent: {
    icon: Bot,
    label: 'Agent',
    ariaLabel: 'Agent mode - Deep analysis',
  },
};

export const ModeToggle: React.FC<ModeToggleProps> = ({
  mode,
  onModeChange,
  disabled = false,
  className,
}) => {
  console.log('ModeToggle: Rendering with mode:', mode);
  
  const handleButtonClick = (modeKey: RouterMode) => {
    console.log('ModeToggle: Button clicked:', modeKey);
    console.log('ModeToggle: Current mode:', mode);
    if (modeKey !== mode && !disabled) {
      console.log('ModeToggle: Changing mode from', mode, 'to', modeKey);
      onModeChange(modeKey);
    }
  };
  
  return (
    <div className={className}>
      <div className="inline-flex items-center justify-center gap-1 bg-gray-100 dark:bg-gray-800 p-1 rounded-lg">
        {(Object.keys(modeConfig) as RouterMode[]).map((modeKey) => {
          const config = modeConfig[modeKey];
          const Icon = config.icon;
          const isSelected = mode === modeKey;
          
          return (
            <button
              key={modeKey}
              type="button"
              onClick={() => handleButtonClick(modeKey)}
              disabled={disabled}
              aria-label={config.ariaLabel}
              aria-pressed={isSelected}
              className={cn(
                "inline-flex items-center justify-center text-xs font-medium transition-all",
                "h-8 px-2.5 rounded-md",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                "disabled:pointer-events-none disabled:opacity-50",
                // Selected state styling
                isSelected && "bg-white dark:bg-gray-600 shadow-md",
                // Unselected state styling
                !isSelected && "bg-transparent opacity-60 hover:opacity-80",
              )}
            >
              <Icon className="h-3.5 w-3.5 mr-1.5" />
              <span>{config.label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
};