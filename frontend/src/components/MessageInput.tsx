'use client';

import { useState, useRef, KeyboardEvent } from 'react';
import { cn } from '@/lib/utils';
import { FileAttachment } from './FileAttachment';
import { Button } from './ui/button';
import { Textarea } from './ui/textarea';
import { Send, Paperclip } from 'lucide-react';

interface MessageInputProps {
  onSubmit: (message: string, files: File[]) => Promise<void>;
  disabled?: boolean;
  className?: string;
  placeholder?: string;
}

export const MessageInput: React.FC<MessageInputProps> = ({
  onSubmit,
  disabled = false,
  className,
  placeholder = "Type your message... (Enter to send, Shift+Enter for new line)"
}) => {
  const [inputMessage, setInputMessage] = useState('');
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

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
          fileInputRef={fileInputRef}
        />
        
        {/* Input container with both buttons inside */}
        <div className="relative">
          <label htmlFor="message-input" className="sr-only">
            Type your message
          </label>
          
          <div className="relative flex items-end border border-input rounded-lg bg-background focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-0 focus-within:border-ring">
            {/* Attach button (left side) */}
            <Button
              type="button"
              variant="ghost-subtle"
              size="icon-sm"
              onClick={() => fileInputRef.current?.click()}
              disabled={isFormDisabled}
              className="m-1.5 flex-shrink-0"
              aria-label="Attach files"
            >
              <Paperclip className="h-4 w-4" />
            </Button>

            <Textarea
              id="message-input"
              ref={textareaRef}
              value={inputMessage}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              placeholder={placeholder}
              className="flex-1 resize-none min-h-[44px] max-h-[120px] border-0 bg-transparent focus-visible:ring-0 focus-visible:ring-offset-0 px-2 py-2 pr-12"
              disabled={isFormDisabled}
              rows={1}
              style={{ height: 'auto' }}
            />

            {/* Send button (right side) */}
            <Button
              type="submit"
              disabled={!canSubmit}
              variant={canSubmit ? "icon-filled" : "icon-outline"}
              size="icon-sm"
              className="m-1.5 flex-shrink-0"
              aria-label="Send message"
            >
              {isSubmitting ? (
                <div className="animate-spin rounded-full h-3.5 w-3.5 border-2 border-current border-t-transparent" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </Button>
          </div>
        </div>
      </form>
    </footer>
  );
};