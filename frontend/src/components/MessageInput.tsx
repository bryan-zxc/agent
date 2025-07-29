'use client';

import { useState, useRef, KeyboardEvent } from 'react';
import { cn } from '@/lib/utils';
import { FileAttachment } from './FileAttachment';
import { Send } from 'lucide-react';

interface MessageInputProps {
  onSubmit: (message: string, files: File[]) => Promise<void>;
  disabled?: boolean;
  className?: string;
}

export const MessageInput: React.FC<MessageInputProps> = ({
  onSubmit,
  disabled = false,
  className
}) => {
  const [inputMessage, setInputMessage] = useState('');
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!inputMessage.trim() || disabled || isSubmitting) return;

    setIsSubmitting(true);
    try {
      await onSubmit(inputMessage, selectedFiles);
      setInputMessage('');
      setSelectedFiles([]);
      // Reset textarea height
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      const formEvent = e as unknown as React.FormEvent;
      handleSubmit(formEvent);
    }
  };

  const handleFileSelect = (files: File[]) => {
    setSelectedFiles(files);
  };

  const handleFileRemove = (index: number) => {
    setSelectedFiles(prev => prev.filter((_, i) => i !== index));
  };

  // Auto-resize textarea
  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputMessage(e.target.value);
    
    // Auto-resize textarea
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
    }
  };

  const isFormDisabled = disabled || isSubmitting;
  const canSubmit = inputMessage.trim() && !isFormDisabled;

  return (
    <footer 
      className={cn(
        "bg-card border-t border-border p-4",
        className
      )}
      role="contentinfo"
    >
      <form onSubmit={handleSubmit} className="space-y-3">
        <FileAttachment
          selectedFiles={selectedFiles}
          onFileSelect={handleFileSelect}
          onFileRemove={handleFileRemove}
          disabled={isFormDisabled}
        />
        
        <div className="flex gap-2 items-end">
          <div className="flex-1 min-w-0">
            <label htmlFor="message-input" className="sr-only">
              Type your message
            </label>
            <textarea
              id="message-input"
              ref={textareaRef}
              value={inputMessage}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              placeholder="Type your message... (Enter to send, Shift+Enter for new line)"
              className={cn(
                "flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm",
                "placeholder:text-muted-foreground resize-none min-h-[44px] max-h-[120px]",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                "disabled:cursor-not-allowed disabled:opacity-50"
              )}
              disabled={isFormDisabled}
              rows={1}
              style={{ height: 'auto' }}
            />
          </div>
          
          <button
            type="submit"
            disabled={!canSubmit}
            className={cn(
              "inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors",
              "h-11 px-4 py-2 bg-primary text-primary-foreground hover:bg-primary/90",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
              "disabled:pointer-events-none disabled:opacity-50",
              !canSubmit && "cursor-not-allowed"
            )}
            aria-label="Send message"
          >
            {isSubmitting ? (
              <div className="animate-spin rounded-full h-4 w-4 border-2 border-primary-foreground border-t-transparent" />
            ) : (
              <Send className="h-4 w-4" />
            )}
            <span className="ml-2 hidden sm:inline">
              {isSubmitting ? 'Sending...' : 'Send'}
            </span>
          </button>
        </div>
      </form>
    </footer>
  );
};