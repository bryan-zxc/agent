'use client';

import { useRef } from 'react';
import { cn } from '@/lib/utils';
import { Button } from './ui/button';
import { X, File, Image } from 'lucide-react';
import { fileUploadService, DuplicateFileInfo } from '@/lib/fileUpload';

interface FileAttachmentProps {
  selectedFiles: File[];
  onFileSelect: (files: File[]) => void;
  onFileRemove: (index: number) => void;
  onDuplicateFound?: (duplicateInfo: DuplicateFileInfo, file: File) => Promise<string>;
  disabled?: boolean;
  className?: string;
  fileInputRef?: React.RefObject<HTMLInputElement | null>;
}

export const FileAttachment: React.FC<FileAttachmentProps> = ({
  selectedFiles,
  onFileSelect,
  onFileRemove,
  onDuplicateFound,
  disabled = false,
  className,
  fileInputRef: externalFileInputRef
}) => {
  const internalFileInputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = externalFileInputRef || internalFileInputRef;

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const newFiles = Array.from(e.target.files);
      
      if (onDuplicateFound) {
        // Check for duplicates immediately
        try {
          const resolvedFiles = await fileUploadService.checkFilesForDuplicates(
            newFiles,
            onDuplicateFound
          );
          
          // Only add files that weren't cancelled
          const filesToAdd = resolvedFiles
            .filter(resolved => resolved.isResolved)
            .map(resolved => resolved.file);
          
          onFileSelect(filesToAdd);
        } catch (error) {
          console.error('Error checking for duplicates:', error);
          // Fallback to normal behaviour
          onFileSelect(newFiles);
        }
      } else {
        // No duplicate checking, proceed normally
        onFileSelect(newFiles);
      }
    }
    
    // Reset the input value so the same file can be selected again if needed
    e.target.value = '';
  };

  const getFileIcon = (fileName: string) => {
    const extension = fileName.split('.').pop()?.toLowerCase();
    if (['png', 'jpg', 'jpeg', 'gif', 'webp'].includes(extension || '')) {
      return <Image className="h-3 w-3" />;
    }
    return <File className="h-3 w-3" />;
  };

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  return (
    <div className={cn("space-y-2", className)}>
      {/* File selection display */}
      {selectedFiles.length > 0 && (
        <div 
          className="flex flex-wrap gap-2"
          role="list"
          aria-label="Selected files"
        >
          {selectedFiles.map((file, index) => (
            <div
              key={index}
              className="inline-flex items-center gap-2 bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 text-xs px-3 py-2 rounded-lg hover:bg-gray-300 hover:dark:bg-gray-600 transition-colors"
              role="listitem"
            >
              {getFileIcon(file.name)}
              <div className="flex flex-col gap-0.5">
                <span className="truncate max-w-[180px] font-medium" title={file.name}>
                  {file.name}
                </span>
                <span className="text-xs opacity-60">
                  {formatFileSize(file.size)}
                </span>
              </div>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => onFileRemove(index)}
                className="h-6 w-6 hover:bg-destructive/10 hover:text-destructive"
                aria-label={`Remove ${file.name}`}
                disabled={disabled}
              >
                <X className="h-3 w-3" />
              </Button>
            </div>
          ))}
        </div>
      )}

      {/* Hidden file input */}
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileSelect}
        multiple
        className="sr-only"
        accept=".png,.jpg,.jpeg,.pdf,.csv,.txt"
        disabled={disabled}
        aria-label="Select files to attach"
      />
      
    </div>
  );
};