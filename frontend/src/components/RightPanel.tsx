'use client';

import React from 'react';
import { CostCard } from './CostCard';

export const RightPanel: React.FC = () => {
  return (
    <div className="h-full bg-background p-6 overflow-y-auto overflow-x-hidden min-w-0">
      <div className="space-y-6 min-w-0">
        <CostCard />
        {/* Future components can be added here */}
      </div>
    </div>
  );
};