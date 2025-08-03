'use client';

import { useRef } from 'react';
import { cn } from '@/lib/utils';
import { Button } from './ui/button';
import { Paperclip, X, File, Image } from 'lucide-react';

interface FileAttachmentProps {
  selectedFiles: File[];
  onFileSelect: (files: File[]) => void;
  onFileRemove: (index: number) => void;
  disabled?: boolean;
  className?: string;
  fileInputRef?: React.RefObject<HTMLInputElement | null>;
}

export const FileAttachment: React.FC<FileAttachmentProps> = ({
  selectedFiles,
  onFileSelect,
  onFileRemove,
  disabled = false,
  className,
  fileInputRef: externalFileInputRef
}) => {
  const internalFileInputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = externalFileInputRef || internalFileInputRef;

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      onFileSelect(Array.from(e.target.files));
    }
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
              className="inline-flex items-center gap-2 bg-muted text-muted-foreground text-xs px-3 py-2 rounded-lg border border-border hover:bg-muted/80 transition-colors"
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