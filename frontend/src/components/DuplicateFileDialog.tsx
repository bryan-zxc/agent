'use client';

import React from 'react';
import { Button } from './ui/button';
import { 
  Dialog, 
  DialogContent, 
  DialogDescription, 
  DialogFooter, 
  DialogHeader, 
  DialogTitle 
} from './ui/dialog';
import { File, AlertTriangle } from 'lucide-react';

interface DuplicateFile {
  file_id: string;
  original_filename: string;
  file_size: number;
  upload_timestamp: string;
}

interface DuplicateFileInfo {
  duplicate_found: boolean;
  existing_file: DuplicateFile;
  new_filename: string;
  options: string[];
}

interface DuplicateFileDialogProps {
  open: boolean;
  duplicateInfo: DuplicateFileInfo;
  onResolve: (action: string) => void;
  onClose: () => void;
}

export const DuplicateFileDialog: React.FC<DuplicateFileDialogProps> = ({
  open,
  duplicateInfo,
  onResolve,
  onClose
}) => {
  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const formatDate = (isoString: string) => {
    const date = new Date(isoString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { 
      hour: '2-digit', 
      minute: '2-digit' 
    });
  };

  const getActionLabel = (action: string) => {
    switch (action) {
      case 'use_existing':
        return 'Use Existing File';
      case 'overwrite_existing':
        return 'Overwrite Existing';
      case 'save_as_new_copy':
        return 'Save as New Copy';
      case 'cancel':
        return 'Cancel Upload';
      default:
        return action;
    }
  };

  const getActionDescription = (action: string) => {
    switch (action) {
      case 'use_existing':
        return 'Reference the previously uploaded file';
      case 'overwrite_existing':
        return 'Replace the existing file with the new one';
      case 'save_as_new_copy':
        return 'Save both files with unique names';
      case 'cancel':
        return 'Cancel the upload process';
      default:
        return '';
    }
  };

  const getActionVariant = (action: string) => {
    switch (action) {
      case 'use_existing':
        return 'outline';
      case 'overwrite_existing':
        return 'ghost';
      case 'save_as_new_copy':
        return 'ghost';
      case 'cancel':
        return 'ghost';
      default:
        return 'ghost';
    }
  };

  return (
    <Dialog open={open} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md bg-background">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-amber-500" />
            Duplicate File Found
          </DialogTitle>
          <DialogDescription>
            A file with the same content already exists. Choose how you would like to proceed.
          </DialogDescription>
        </DialogHeader>

        {/* File Information */}
        <div className="my-4">
          <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3">
            <div className="flex items-start gap-3">
              <File className="h-4 w-4 text-muted-foreground flex-shrink-0 mt-0.5" />
              <div className="flex-1 min-w-0">
                <p className="font-medium text-sm truncate" title={duplicateInfo.existing_file.original_filename}>
                  {duplicateInfo.existing_file.original_filename}
                </p>
                <div className="flex items-center gap-4 text-xs text-muted-foreground mt-1">
                  <span>{formatFileSize(duplicateInfo.existing_file.file_size)}</span>
                  <span>Uploaded {formatDate(duplicateInfo.existing_file.upload_timestamp)}</span>
                </div>
              </div>
            </div>
          </div>

          {duplicateInfo.new_filename !== duplicateInfo.existing_file.original_filename && (
            <div className="mt-3 text-sm text-muted-foreground">
              New filename: <span className="font-medium">{duplicateInfo.new_filename}</span>
            </div>
          )}
        </div>

        {/* Action Buttons */}
        <DialogFooter className="flex-col gap-2 sm:flex-col">
          <div className="text-sm font-medium mb-2">Choose an action:</div>
          <div className="grid gap-2 w-full">
            {duplicateInfo.options.map((action) => (
              <Button
                key={action}
                variant={getActionVariant(action) as "default" | "destructive" | "outline" | "ghost"}
                size="lg"
                onClick={() => onResolve(action)}
                className="flex flex-col items-start gap-1 h-auto py-3"
              >
                <div className="font-medium">{getActionLabel(action)}</div>
                <div className="text-xs opacity-70">
                  {getActionDescription(action)}
                </div>
              </Button>
            ))}
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};