interface DuplicateFile {
  file_id: string;
  original_filename: string;
  file_size: number;
  upload_timestamp: string;
}

export interface DuplicateFileInfo {
  duplicate_found: boolean;
  existing_file?: DuplicateFile;
  new_filename?: string;
  options?: string[];
}

interface UploadResponse {
  duplicate_found: boolean;
  file_id?: string;
  filename?: string;
  path?: string;
  size?: number;
  // Duplicate info if found
  existing_file?: DuplicateFile;
  new_filename?: string;
  options?: string[];
}

interface ResolutionResponse {
  action: string;
  file_id?: string;
  filename?: string;
  path?: string;
  size?: number;
  files: string[];
}

export class FileUploadService {
  private apiUrl: string;

  constructor(apiUrl: string = process.env.NEXT_PUBLIC_API_URL || '') {
    this.apiUrl = apiUrl;
  }

  /**
   * Check if a file is a duplicate without uploading
   */
  async checkForDuplicate(file: File): Promise<UploadResponse> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('check_only', 'true');
    
    const response = await fetch(`${this.apiUrl}/upload`, {
      method: 'POST',
      body: formData,
    });
    
    if (!response.ok) {
      throw new Error(`Duplicate check failed: ${response.statusText}`);
    }
    
    return response.json();
  }

  /**
   * Upload a file and handle potential duplicates
   */
  async uploadFile(file: File): Promise<UploadResponse> {
    const formData = new FormData();
    formData.append('file', file);
    
    const response = await fetch(`${this.apiUrl}/upload`, {
      method: 'POST',
      body: formData,
    });
    
    if (!response.ok) {
      throw new Error(`Upload failed: ${response.statusText}`);
    }
    
    return response.json();
  }

  /**
   * Resolve duplicate file with user's chosen action
   */
  async resolveDuplicate(
    action: string, 
    existingFileId: string, 
    newFilename: string, 
    file: File
  ): Promise<ResolutionResponse> {
    const formData = new FormData();
    formData.append('file', file);
    
    // Add resolution data as form fields
    formData.append('action', action);
    formData.append('existing_file_id', existingFileId);
    formData.append('new_filename', newFilename);
    
    const response = await fetch(`${this.apiUrl}/upload/resolve-duplicate`, {
      method: 'POST',
      body: formData
    });
    
    if (!response.ok) {
      throw new Error(`Duplicate resolution failed: ${response.statusText}`);
    }
    
    return response.json();
  }

  /**
   * Check multiple files for duplicates immediately
   */
  async checkFilesForDuplicates(
    files: File[],
    onDuplicateFound: (duplicateInfo: DuplicateFileInfo, file: File) => Promise<string>
  ): Promise<{ file: File; isResolved: boolean; resolvedPaths?: string[] }[]> {
    const results: { file: File; isResolved: boolean; resolvedPaths?: string[] }[] = [];
    
    for (const file of files) {
      try {
        const checkResult = await this.checkForDuplicate(file);
        
        if (checkResult.duplicate_found && checkResult.existing_file && checkResult.options) {
          // Handle duplicate immediately - we know existing_file is defined due to the check above
          const duplicateInfo: any = {
            duplicate_found: true,
            existing_file: checkResult.existing_file,
            new_filename: checkResult.new_filename || file.name,
            options: checkResult.options
          };
          
          const action = await onDuplicateFound(duplicateInfo, file);
          
          if (action === 'cancel') {
            // Mark as not resolved
            results.push({ file, isResolved: false });
            continue;
          }
          
          // Resolve duplicate and get the file paths
          const resolutionResult = await this.resolveDuplicate(
            action,
            checkResult.existing_file.file_id,
            checkResult.new_filename || file.name,
            file
          );
          
          results.push({ 
            file, 
            isResolved: true, 
            resolvedPaths: resolutionResult.files 
          });
        } else {
          // No duplicate, file is ready to be uploaded normally
          results.push({ file, isResolved: true });
        }
      } catch (error) {
        console.error('Error checking file for duplicate:', file.name, error);
        // If check fails, treat as no duplicate
        results.push({ file, isResolved: true });
      }
    }
    
    return results;
  }

  /**
   * Upload files that have already been resolved for duplicates
   */
  async uploadResolvedFiles(
    resolvedFiles: { file: File; isResolved: boolean; resolvedPaths?: string[] }[]
  ): Promise<string[]> {
    const filePaths: string[] = [];
    
    for (const resolvedFile of resolvedFiles) {
      if (!resolvedFile.isResolved) {
        continue; // Skip cancelled files
      }
      
      if (resolvedFile.resolvedPaths) {
        // File was already resolved via duplicate handling
        filePaths.push(...resolvedFile.resolvedPaths);
      } else {
        // File needs normal upload (no duplicate found)
        try {
          const uploadResult = await this.uploadFile(resolvedFile.file);
          if (uploadResult.path) {
            filePaths.push(uploadResult.path);
          }
        } catch (error) {
          console.error('Error uploading resolved file:', resolvedFile.file.name, error);
        }
      }
    }
    
    return filePaths;
  }

  /**
   * Upload multiple files and handle duplicates
   */
  async uploadFiles(
    files: File[], 
    onDuplicateFound: (duplicateInfo: DuplicateFileInfo, file: File) => Promise<string>
  ): Promise<string[]> {
    const filePaths: string[] = [];
    
    for (const file of files) {
      try {
        const uploadResult = await this.uploadFile(file);
        
        if (uploadResult.duplicate_found && uploadResult.existing_file && uploadResult.options) {
          // Handle duplicate - we know existing_file is defined due to the check above
          const duplicateInfo: any = {
            duplicate_found: true,
            existing_file: uploadResult.existing_file,
            new_filename: uploadResult.new_filename || file.name,
            options: uploadResult.options
          };
          
          const action = await onDuplicateFound(duplicateInfo, file);
          
          if (action === 'cancel') {
            // Skip this file
            continue;
          }
          
          // Resolve duplicate based on user choice
          const resolutionResult = await this.resolveDuplicate(
            action,
            uploadResult.existing_file.file_id,
            uploadResult.new_filename || file.name,
            file
          );
          
          if (resolutionResult.files.length > 0) {
            filePaths.push(...resolutionResult.files);
          }
        } else {
          // No duplicate, add the uploaded file path
          if (uploadResult.path) {
            filePaths.push(uploadResult.path);
          }
        }
      } catch (error) {
        console.error('Error uploading file:', file.name, error);
        // Continue with other files
      }
    }
    
    return filePaths;
  }
}

export const fileUploadService = new FileUploadService();