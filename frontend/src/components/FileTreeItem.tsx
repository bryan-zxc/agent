'use client';

import React, { useCallback, useState } from 'react';
import {
  ChevronRight,
  ChevronDown,
  File,
  FileText,
  Image,
  Folder,
  FolderOpen,
  Video,
  Music,
  Archive,
  Code,
  FileJson,
  Table,
  Trash2
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from './ui/collapsible';
import { FileNode } from '@/lib/fileSystemService';
import { fileSystemService } from '@/lib/fileSystemService';
import { useDynamicTruncate } from '@/hooks/useDynamicTruncate';

interface FileTreeItemProps {
  node: FileNode;
  level: number;
  expanded: boolean;
  onToggle: (path: string) => void;
  onSelect?: (node: FileNode) => void;
  selectedPath?: string;
  onDelete?: (node: FileNode) => void;
}

export const FileTreeItem: React.FC<FileTreeItemProps> = ({
  node,
  level,
  expanded,
  onToggle,
  onSelect,
  selectedPath,
  onDelete
}) => {
  const [isHovered, setIsHovered] = useState(false);
  const isFolder = node.type === 'folder';
  const hasChildren = isFolder && node.children && node.children.length > 0;
  const isSelected = selectedPath === node.path;

  // Custom function to calculate reserved width based on actual element structure
  const getReservedWidth = useCallback((parentElement: HTMLElement) => {
    let reserved = 0;

    // Get all children
    const children = Array.from(parentElement.children);

    children.forEach(child => {
      // Skip the text container
      if (child.classList.contains('name-container')) {
        return;
      }

      // Add width of other elements
      const rect = child.getBoundingClientRect();
      reserved += rect.width;
    });

    // Add gaps between elements (using Tailwind's gap-2 = 8px)
    const visibleChildren = children.filter(c => !c.classList.contains('name-container'));
    reserved += 8 * visibleChildren.length; // gap-2 = 8px

    // Add some buffer for padding
    reserved += 16; // Additional padding buffer

    return reserved;
  }, []);

  // Use the new hook with parent-based measurement
  const { parentRef, textRef, truncatedText, isTruncated } = useDynamicTruncate(node.name, {
    minChars: 3,
    fontSize: 14, // text-sm
    debounceMs: 50,
    getReservedWidth
  });

  // Get appropriate icon based on file type
  const getIcon = () => {
    if (isFolder) {
      if (expanded) {
        return <FolderOpen className="h-4 w-4 text-gray-500 dark:text-gray-400" />;
      }
      return <Folder className="h-4 w-4 text-gray-500 dark:text-gray-400" />;
    }

    // Get icon based on extension
    const iconName = fileSystemService.getFileIcon(node.extension || '');
    const iconProps = "h-4 w-4 text-gray-500 dark:text-gray-400";

    switch (iconName) {
      case 'Image':
        return <Image className={iconProps} />;
      case 'FileText':
        return <FileText className={iconProps} />;
      case 'Video':
        return <Video className={iconProps} />;
      case 'Music':
        return <Music className={iconProps} />;
      case 'Archive':
        return <Archive className={iconProps} />;
      case 'Code':
        return <Code className={iconProps} />;
      case 'FileJson':
        return <FileJson className={iconProps} />;
      case 'Table':
        return <Table className={iconProps} />;
      default:
        return <File className={iconProps} />;
    }
  };

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (isFolder) {
      onToggle(node.path);
    }
    if (onSelect) {
      onSelect(node);
    }
  };

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (onDelete && window.confirm(`Are you sure you want to delete "${node.name}"?`)) {
      onDelete(node);
    }
  };

  const content = (
    <div
      ref={parentRef as React.RefObject<HTMLDivElement>}
      className={cn(
        "flex items-center gap-2 px-2 py-1.5 rounded-md cursor-pointer transition-colors w-full",
        "hover:bg-gray-300 hover:dark:bg-gray-600",
        isSelected && "bg-gray-300 dark:bg-gray-600",
        !isSelected && "bg-transparent"
      )}
      style={{ paddingLeft: `${level * 16 + 8}px` }}
      onClick={handleClick}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      role="button"
      tabIndex={0}
      aria-expanded={isFolder ? expanded : undefined}
      aria-selected={isSelected}
    >
      {/* Chevron for folders */}
      {isFolder && (
        <div className="flex-shrink-0 w-4">
          {hasChildren && (
            expanded ? (
              <ChevronDown className="h-4 w-4 text-gray-500 dark:text-gray-400" />
            ) : (
              <ChevronRight className="h-4 w-4 text-gray-500 dark:text-gray-400" />
            )
          )}
        </div>
      )}

      {/* Icon */}
      <div className="flex-shrink-0">
        {getIcon()}
      </div>

      {/* Name - using flex-1 to fill available space */}
      <div className="flex-1 min-w-0 name-container">
        <span
          ref={textRef as React.RefObject<HTMLSpanElement>}
          className="text-sm text-gray-700 dark:text-gray-300 block"
          title={isTruncated ? node.name : undefined}
        >
          {truncatedText}
        </span>
      </div>

      {/* File size for files */}
      {!isFolder && node.size !== undefined && (
        <span className="text-xs text-gray-500 dark:text-gray-400 flex-shrink-0">
          {fileSystemService.formatFileSize(node.size)}
        </span>
      )}

      {/* Delete button for files - shows on hover */}
      {!isFolder && onDelete && (isHovered || isSelected) && (
        <button
          onClick={handleDelete}
          className="flex-shrink-0 p-1 rounded hover:bg-red-100 dark:hover:bg-red-900/30 transition-colors"
          aria-label={`Delete ${node.name}`}
        >
          <Trash2 className="h-4 w-4 text-red-500 dark:text-red-400" />
        </button>
      )}
    </div>
  );

  if (!isFolder || !hasChildren) {
    return content;
  }

  return (
    <Collapsible open={expanded}>
      <CollapsibleTrigger asChild>
        {content}
      </CollapsibleTrigger>
      <CollapsibleContent>
        {node.children?.map((child) => (
          <FileTreeItem
            key={child.path}
            node={child}
            level={level + 1}
            expanded={false}
            onToggle={onToggle}
            onSelect={onSelect}
            selectedPath={selectedPath}
            onDelete={onDelete}
          />
        ))}
      </CollapsibleContent>
    </Collapsible>
  );
};