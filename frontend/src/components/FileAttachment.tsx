'use client';

import { useRef } from 'react';
import { cn } from '@/lib/utils';
import { Paperclip, X } from 'lucide-react';

interface FileAttachmentProps {
  selectedFiles: File[];
  onFileSelect: (files: File[]) => void;
  onFileRemove: (index: number) => void;
  disabled?: boolean;
  className?: string;
}

export const FileAttachment: React.FC<FileAttachmentProps> = ({
  selectedFiles,
  onFileSelect,
  onFileRemove,
  disabled = false,
  className
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      onFileSelect(Array.from(e.target.files));
    }
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
              className="inline-flex items-center gap-2 bg-secondary text-secondary-foreground text-sm px-3 py-1 rounded-md border"
              role="listitem"
            >
              <span className="truncate max-w-[200px]" title={file.name}>
                {file.name}
              </span>
              <button
                type="button"
                onClick={() => onFileRemove(index)}
                className="text-muted-foreground hover:text-foreground transition-colors p-0.5"
                aria-label={`Remove ${file.name}`}
                disabled={disabled}
              >
                <X className="h-3 w-3" />
              </button>
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
      
      {/* File selection button */}
      <button
        type="button"
        onClick={() => fileInputRef.current?.click()}
        disabled={disabled}
        className={cn(
          "inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors",
          "h-10 w-10 bg-secondary text-secondary-foreground hover:bg-secondary/80",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
          "disabled:pointer-events-none disabled:opacity-50",
          disabled && "cursor-not-allowed"
        )}
        aria-label="Attach files"
      >
        <Paperclip className="h-4 w-4" />
      </button>
    </div>
  );
};