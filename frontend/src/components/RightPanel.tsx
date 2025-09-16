'use client';

import React from 'react';
import { CostCard } from './CostCard';
import { FolderContentsCard } from './FolderContentsCard';

export const RightPanel: React.FC = () => {
  return (
    <div className="h-full bg-background pt-1 px-6 pb-2 flex flex-col overflow-hidden min-w-0">
      <CostCard className="flex-shrink-0" />
      <div className="mt-2 flex-1 min-h-0 overflow-hidden">
        <FolderContentsCard className="h-full" />
      </div>
    </div>
  );
};