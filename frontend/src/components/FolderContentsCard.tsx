'use client';

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from './ui/card';
import { ScrollArea } from './ui/scroll-area';
import { FileTreeItem } from './FileTreeItem';
import { fileSystemService, FileNode } from '@/lib/fileSystemService';
import { Folder, RefreshCw } from 'lucide-react';
import { Button } from './ui/button';
import { cn } from '@/lib/utils';
import { useDynamicTruncate } from '@/hooks/useDynamicTruncate';

interface FolderContentsCardProps {
  className?: string;
}

// Component for selected file with dynamic truncation
const SelectedFileInfo: React.FC<{ selectedFile: FileNode }> = ({ selectedFile }) => {
  // Calculate reserved width for "Selected:" label and file size
  const reservedWidth = useMemo(() => {
    let width = 60; // "Selected:" label
    width += 16; // Gap between elements
    if (selectedFile.type === 'file' && selectedFile.size !== undefined) {
      width += 60; // File size display
    }
    return width;
  }, [selectedFile]);

  const { ref, truncatedText, isTruncated } = useDynamicTruncate(selectedFile.name, {
    reservedWidth,
    minChars: 3,
    fontSize: 12, // text-xs
    debounceMs: 50
  });

  return (
    <div className="border-t border-gray-300 dark:border-gray-600 p-2 bg-gray-100 dark:bg-gray-800">
      <div className="text-xs text-gray-500 dark:text-gray-400 flex items-center gap-2">
        <span className="font-medium flex-shrink-0">Selected:</span>
        <span
          ref={ref as React.RefObject<HTMLSpanElement>}
          className="flex-1 min-w-0"
          title={isTruncated ? selectedFile.name : undefined}
        >
          {truncatedText}
        </span>
        {selectedFile.type === 'file' && selectedFile.size !== undefined && (
          <span className="text-[10px] opacity-75 flex-shrink-0">
            {fileSystemService.formatFileSize(selectedFile.size)}
          </span>
        )}
      </div>
    </div>
  );
};

export const FolderContentsCard: React.FC<FolderContentsCardProps> = ({ className }) => {
  const [fileTree, setFileTree] = useState<FileNode | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedFolders, setExpandedFolders] = useState<Set<string>>(() => {
    // Load expanded state from localStorage
    try {
      const saved = localStorage.getItem('expandedFolders');
      return new Set(saved ? JSON.parse(saved) : []);
    } catch {
      return new Set();
    }
  });
  const [selectedFile, setSelectedFile] = useState<FileNode | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Save expanded state to localStorage whenever it changes
  useEffect(() => {
    localStorage.setItem('expandedFolders', JSON.stringify(Array.from(expandedFolders)));
  }, [expandedFolders]);

  // Fetch file tree
  const fetchFileTree = useCallback(async () => {
    try {
      setError(null);
      const tree = await fileSystemService.fetchFileTree();
      setFileTree(tree);
      setLoading(false);
    } catch (error) {
      console.error('Error fetching file tree:', error);
      setError('Failed to load folder contents');
      setLoading(false);
    }
  }, []);

  // Initial load and set up polling
  useEffect(() => {
    fetchFileTree();

    // Set up polling for updates
    const unsubscribe = fileSystemService.subscribeToUpdates((tree) => {
      setFileTree(tree);
      setError(null);
    });

    return () => {
      unsubscribe();
    };
  }, [fetchFileTree]);

  // Toggle folder expansion
  const handleToggle = useCallback((path: string) => {
    setExpandedFolders(prev => {
      const newSet = new Set(prev);
      if (newSet.has(path)) {
        newSet.delete(path);
      } else {
        newSet.add(path);
      }
      return newSet;
    });
  }, []);

  // Handle file selection
  const handleSelect = useCallback((node: FileNode) => {
    setSelectedFile(node);
    // You can add additional actions here like opening a preview
  }, []);

  // Manual refresh
  const handleRefresh = async () => {
    setIsRefreshing(true);
    await fetchFileTree();
    setTimeout(() => setIsRefreshing(false), 500);
  };

  // Recursive function to check if a folder should be expanded
  const isExpanded = (path: string) => expandedFolders.has(path);

  // Render loading state
  if (loading) {
    return (
      <Card className="w-full bg-gray-200 dark:bg-gray-700 border-0 shadow-lg rounded-2xl">
        <CardHeader className="rounded-t-2xl">
          <CardTitle className="text-lg font-semibold flex items-center gap-2">
            <Folder className="h-5 w-5" />
            Folder Contents
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            <div className="animate-pulse">
              <div className="h-4 bg-gray-100 dark:bg-gray-800 rounded w-3/4 mb-2"></div>
              <div className="h-4 bg-gray-100 dark:bg-gray-800 rounded w-1/2 ml-4"></div>
            </div>
            <div className="animate-pulse">
              <div className="h-4 bg-gray-100 dark:bg-gray-800 rounded w-3/4 mb-2"></div>
              <div className="h-4 bg-gray-100 dark:bg-gray-800 rounded w-1/2 ml-4"></div>
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }

  // Render error state
  if (error) {
    return (
      <Card className="w-full bg-gray-200 dark:bg-gray-700 border-0 shadow-lg rounded-2xl">
        <CardHeader className="rounded-t-2xl">
          <CardTitle className="text-lg font-semibold flex items-center gap-2">
            <Folder className="h-5 w-5" />
            Folder Contents
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-destructive text-sm">{error}</div>
          <Button
            onClick={fetchFileTree}
            variant="ghost"
            size="sm"
            className="mt-2"
          >
            Retry
          </Button>
        </CardContent>
      </Card>
    );
  }

  // Render empty state
  if (!fileTree || (fileTree.children && fileTree.children.length === 0)) {
    return (
      <Card className="w-full bg-gray-200 dark:bg-gray-700 border-0 shadow-lg rounded-2xl">
        <CardHeader className="rounded-t-2xl flex flex-row items-center justify-between">
          <CardTitle className="text-lg font-semibold flex items-center gap-2">
            <Folder className="h-5 w-5" />
            Folder Contents
          </CardTitle>
          <Button
            onClick={handleRefresh}
            variant="ghost"
            size="icon"
            className={cn(
              "h-8 w-8",
              isRefreshing && "animate-spin"
            )}
            aria-label="Refresh folder contents"
          >
            <RefreshCw className="h-4 w-4" />
          </Button>
        </CardHeader>
        <CardContent>
          <div className="text-sm text-gray-500 dark:text-gray-400 text-center py-8">
            No files uploaded yet
          </div>
        </CardContent>
      </Card>
    );
  }

  // Render file tree
  return (
    <Card className={cn("w-full min-w-0 bg-gray-200 dark:bg-gray-700 border-0 shadow-lg rounded-2xl overflow-hidden flex flex-col", className)}>
      <CardHeader className="rounded-t-2xl flex flex-row items-center justify-between">
        <CardTitle className="text-lg font-semibold flex items-center gap-2">
          <Folder className="h-5 w-5" />
          Folder Contents
        </CardTitle>
        <Button
          onClick={handleRefresh}
          variant="ghost"
          size="icon"
          className={cn(
            "h-8 w-8",
            isRefreshing && "animate-spin"
          )}
          aria-label="Refresh folder contents"
        >
          <RefreshCw className="h-4 w-4" />
        </Button>
      </CardHeader>
      <CardContent className="p-0 flex-1 min-h-0 overflow-hidden">
        <ScrollArea className="h-full w-full">
          <div className="p-4 space-y-1 min-w-0">
            {/* Render root folder contents */}
            {fileTree.children?.map((child) => (
              <FileTreeItem
                key={child.path}
                node={child}
                level={0}
                expanded={isExpanded(child.path)}
                onToggle={handleToggle}
                onSelect={handleSelect}
                selectedPath={selectedFile?.path}
              />
            ))}
          </div>
        </ScrollArea>

        {/* Selected file info - compact version */}
        {selectedFile && (
          <SelectedFileInfo
            selectedFile={selectedFile}
          />
        )}
      </CardContent>
    </Card>
  );
};