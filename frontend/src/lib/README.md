# Lib - Utility Functions and Services

Core utility functions and services for the frontend application, including shadcn/ui integration and file upload handling.

## Files Overview

### `utils.ts` - shadcn/ui Utilities
Core utility functions for styling and class name management.

#### Functions

**`cn(...inputs: ClassValue[])`**
- Conditional class name merging utility powered by `clsx` and `tailwind-merge`
- **Purpose**: Combine multiple class names with conditional logic and resolve Tailwind conflicts
- **Parameters**: Variable number of class values (strings, objects, arrays)
- **Returns**: Merged and deduplicated class name string
- **Usage**: Primary utility for component styling throughout the application

**Implementation:**
```typescript
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
```

**Common Usage Patterns:**
```typescript
// Basic conditional classes
cn("base-class", isActive && "active-class", className)

// Object-based conditionals
cn("btn", {
  "btn-primary": variant === "primary",
  "btn-secondary": variant === "secondary"
})

// Array-based classes
cn(["flex", "items-center"], spacing && `gap-${spacing}`)

// Tailwind conflict resolution
cn("px-4 py-2", "p-8") // Results in "p-8" (twMerge resolves conflict)
```

### `fileUpload.ts` - File Upload Service
Comprehensive file upload service with intelligent duplicate detection and resolution.

#### Classes

**`FileUploadService`**
- Singleton service for handling file uploads with duplicate detection
- **Features**: 
  - Multi-file upload support
  - Content-based duplicate detection
  - User-friendly resolution workflows
  - Error handling and recovery
  - TypeScript interfaces for type safety

#### Key Methods

**`uploadFile(file: File): Promise<UploadResponse>`**
- Upload single file with automatic duplicate detection
- **Process**: File → SHA-256 hash → Database check → Response with duplicate info if found
- **Returns**: Upload response with file info or duplicate resolution options

**`resolveDuplicate(action, existingFileId, newFilename, file): Promise<ResolutionResponse>`**
- Handle user's duplicate resolution choice
- **Actions**: `use_existing`, `overwrite_existing`, `save_as_new_copy`, `cancel`
- **Returns**: Resolution result with final file paths

**`uploadFiles(files, onDuplicateFound): Promise<string[]>`**
- Batch upload multiple files with duplicate handling callback
- **Features**: 
  - Sequential processing with duplicate interruption
  - Callback-based duplicate resolution UI integration
  - Error recovery for individual files
- **Returns**: Array of successfully uploaded file paths

#### TypeScript Interfaces

**`DuplicateFile`**
```typescript
interface DuplicateFile {
  file_id: string;
  original_filename: string;
  file_size: number;
  upload_timestamp: string;
}
```

**`DuplicateFileInfo`**
```typescript
interface DuplicateFileInfo {
  duplicate_found: boolean;
  existing_file?: DuplicateFile;
  new_filename?: string;
  options?: string[];
}
```

**`UploadResponse`**
```typescript
interface UploadResponse {
  duplicate_found: boolean;
  file_id?: string;
  filename?: string;
  path?: string;
  size?: number;
  // Duplicate-specific fields
  existing_file?: DuplicateFile;
  new_filename?: string;
  options?: string[];
}
```

**`ResolutionResponse`**
```typescript
interface ResolutionResponse {
  action: string;
  file_id?: string;
  filename?: string;
  path?: string;
  size?: number;
  files: string[];
}
```

## Usage Patterns

### Styling with cn() Utility
```typescript
import { cn } from '@/lib/utils';

// Component with conditional styling
export const Button = ({ variant, size, disabled, className, ...props }) => {
  return (
    <button
      className={cn(
        // Base styles
        "inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        "disabled:pointer-events-none disabled:opacity-50",
        
        // Variant styles
        {
          "bg-primary text-primary-foreground hover:bg-primary/90": variant === "default",
          "bg-destructive text-destructive-foreground hover:bg-destructive/90": variant === "destructive",
          "border border-input bg-background hover:bg-accent": variant === "outline",
        },
        
        // Size styles
        {
          "h-10 px-4 py-2": size === "default",
          "h-9 rounded-md px-3": size === "sm",
          "h-11 rounded-md px-8": size === "lg",
        },
        
        // Additional classes from props
        className
      )}
      disabled={disabled}
      {...props}
    />
  );
};
```

### File Upload Integration
```typescript
import { fileUploadService, DuplicateFileInfo } from '@/lib/fileUpload';

// Component using file upload service
const ChatInterface = () => {
  const [duplicateDialog, setDuplicateDialog] = useState({
    open: false,
    duplicateInfo: null,
    file: null,
    resolve: () => {}
  });

  // Duplicate handling callback
  const handleDuplicate = async (duplicateInfo: DuplicateFileInfo, file: File): Promise<string> => {
    return new Promise((resolve) => {
      setDuplicateDialog({
        open: true,
        duplicateInfo,
        file,
        resolve
      });
    });
  };

  // File upload process
  const handleFileUpload = async (files: File[]) => {
    try {
      const filePaths = await fileUploadService.uploadFiles(files, handleDuplicate);
      console.log('Uploaded files:', filePaths);
    } catch (error) {
      console.error('Upload failed:', error);
    }
  };

  // Duplicate resolution handler
  const handleDuplicateResolve = (action: string) => {
    duplicateDialog.resolve(action);
    setDuplicateDialog({ ...duplicateDialog, open: false });
  };

  return (
    <>
      {/* File upload UI */}
      <FileUpload onUpload={handleFileUpload} />
      
      {/* Duplicate resolution dialog */}
      <DuplicateFileDialog
        open={duplicateDialog.open}
        duplicateInfo={duplicateDialog.duplicateInfo}
        onResolve={handleDuplicateResolve}
        onClose={() => setDuplicateDialog({ ...duplicateDialog, open: false })}
      />
    </>
  );
};
```

## Integration with shadcn/ui

### Theme Integration
The utilities integrate seamlessly with the shadcn/ui theme system:
- `cn()` resolves Tailwind conflicts with theme variables
- File upload service works with shadcn/ui dialog components
- TypeScript interfaces provide type safety for UI components

### Component Enhancement
```typescript
// Enhanced shadcn/ui component with custom utilities
export const CustomDialog = ({ className, ...props }) => {
  return (
    <Dialog
      className={cn(
        // shadcn/ui base styles
        "fixed inset-0 z-50 bg-background/80 backdrop-blur-sm",
        // Custom enhancements
        "data-[state=open]:animate-in data-[state=closed]:animate-out",
        // Prop-based overrides
        className
      )}
      {...props}
    />
  );
};
```

## Error Handling

### File Upload Error Recovery
```typescript
// Robust error handling in file upload service
try {
  const uploadResult = await this.uploadFile(file);
  // Process result
} catch (error) {
  console.error('Error uploading file:', file.name, error);
  // Continue with other files in batch
}
```

### Utility Function Safety
```typescript
// Safe class name merging with fallbacks
const className = cn(
  "default-styles",
  dynamicCondition && "conditional-styles",
  userClassName // May be undefined, cn() handles gracefully
);
```

## Performance Considerations

### Class Name Optimisation
- `twMerge` eliminates redundant Tailwind classes
- `clsx` provides efficient conditional logic
- Result caching for repeated class combinations

### File Upload Efficiency
- Single service instance (singleton pattern)
- Efficient batch processing with individual error handling
- Memory-conscious file processing with streams

## Best Practices

### Styling Guidelines
1. **Always use cn()** for conditional classes in components
2. **Base styles first**, then conditionals, then prop overrides
3. **Consistent naming** for variant and size conditionals
4. **Theme variables** instead of hardcoded colours

### File Upload Guidelines
1. **Handle duplicates gracefully** with user-friendly UI
2. **Provide progress feedback** during uploads
3. **Error boundaries** around file upload components
4. **Type safety** with provided interfaces

### Code Organisation
```typescript
// Import order
import React from 'react';           // React imports first
import { cn } from '@/lib/utils';    // Local utilities
import { Button } from '@/components/ui/button';  // UI components
```

## Testing Considerations

### Utility Testing
```typescript
import { cn } from '@/lib/utils';

describe('cn utility', () => {
  it('merges classes correctly', () => {
    expect(cn('px-4', 'px-6')).toBe('px-6'); // Tailwind conflict resolution
  });
  
  it('handles conditional classes', () => {
    expect(cn('base', true && 'active')).toBe('base active');
    expect(cn('base', false && 'active')).toBe('base');
  });
});
```

### File Upload Testing
```typescript
import { fileUploadService } from '@/lib/fileUpload';

describe('FileUploadService', () => {
  it('handles duplicate detection', async () => {
    const mockFile = new File(['content'], 'test.txt');
    const result = await fileUploadService.uploadFile(mockFile);
    expect(result.duplicate_found).toBeDefined();
  });
});
```

The lib directory provides the foundation for consistent styling and reliable file handling throughout the application, supporting both the shadcn/ui design system and complex business logic requirements.