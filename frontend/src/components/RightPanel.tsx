'use client';

import React from 'react';
import { CostCard } from './CostCard';

export const RightPanel: React.FC = () => {
  return (
    <div className="h-full bg-background p-6 overflow-y-auto">
      <div className="space-y-6">
        <CostCard />
        {/* Future components can be added here */}
      </div>
    </div>
  );
};