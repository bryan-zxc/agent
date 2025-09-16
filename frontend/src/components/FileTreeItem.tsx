'use client';

import React from 'react';
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
  Table
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from './ui/collapsible';
import { FileNode } from '@/lib/fileSystemService';
import { fileSystemService } from '@/lib/fileSystemService';

interface FileTreeItemProps {
  node: FileNode;
  level: number;
  expanded: boolean;
  onToggle: (path: string) => void;
  onSelect?: (node: FileNode) => void;
  selectedPath?: string;
}

export const FileTreeItem: React.FC<FileTreeItemProps> = ({
  node,
  level,
  expanded,
  onToggle,
  onSelect,
  selectedPath
}) => {
  const isFolder = node.type === 'folder';
  const hasChildren = isFolder && node.children && node.children.length > 0;
  const isSelected = selectedPath === node.path;

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

  const content = (
    <div
      className={cn(
        "flex items-center gap-2 px-2 py-1.5 rounded-md cursor-pointer transition-colors",
        "hover:bg-gray-300 hover:dark:bg-gray-600",
        isSelected && "bg-gray-300 dark:bg-gray-600",
        !isSelected && "bg-transparent"
      )}
      style={{ paddingLeft: `${level * 16 + 8}px` }}
      onClick={handleClick}
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

      {/* Name */}
      <span className="flex-1 text-sm truncate text-gray-700 dark:text-gray-300">
        {node.name}
      </span>

      {/* File size for files */}
      {!isFolder && node.size !== undefined && (
        <span className="text-xs text-gray-500 dark:text-gray-400 flex-shrink-0">
          {fileSystemService.formatFileSize(node.size)}
        </span>
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
          />
        ))}
      </CollapsibleContent>
    </Collapsible>
  );
};