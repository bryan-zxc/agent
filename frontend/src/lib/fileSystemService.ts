export interface FileNode {
  name: string;
  type: 'file' | 'folder';
  path: string;
  size?: number;
  extension?: string;
  modified?: string;
  children?: FileNode[];
}

export interface FileMetadata {
  name: string;
  path: string;
  size: number;
  extension: string;
  type: string;
  created: string;
  modified: string;
  accessed: string;
}

class FileSystemService {
  private apiUrl: string;
  private pollingInterval: number = 5000;
  private pollingTimer: NodeJS.Timeout | null = null;

  constructor(apiUrl: string = process.env.NEXT_PUBLIC_API_URL || '') {
    this.apiUrl = apiUrl;
  }

  /**
   * Fetch the file tree structure from the uploads directory
   */
  async fetchFileTree(subPath?: string): Promise<FileNode> {
    try {
      const url = subPath
        ? `${this.apiUrl}/api/files/list?path=${encodeURIComponent(subPath)}`
        : `${this.apiUrl}/api/files/list`;

      const response = await fetch(url);

      if (!response.ok) {
        throw new Error(`Failed to fetch file tree: ${response.statusText}`);
      }

      return await response.json();
    } catch (error) {
      console.error('Error fetching file tree:', error);
      throw error;
    }
  }

  /**
   * Get detailed metadata for a specific file
   */
  async getFileMetadata(filePath: string): Promise<FileMetadata> {
    try {
      const response = await fetch(
        `${this.apiUrl}/api/files/metadata/${encodeURIComponent(filePath)}`
      );

      if (!response.ok) {
        throw new Error(`Failed to fetch file metadata: ${response.statusText}`);
      }

      return await response.json();
    } catch (error) {
      console.error('Error fetching file metadata:', error);
      throw error;
    }
  }

  /**
   * Subscribe to file tree updates with polling
   * Returns an unsubscribe function
   */
  subscribeToUpdates(callback: (tree: FileNode) => void): () => void {
    // Initial fetch
    this.fetchFileTree()
      .then(callback)
      .catch(error => console.error('Error in initial file tree fetch:', error));

    // Set up polling
    this.pollingTimer = setInterval(async () => {
      try {
        const tree = await this.fetchFileTree();
        callback(tree);
      } catch (error) {
        console.error('Error polling file tree:', error);
      }
    }, this.pollingInterval);

    // Return unsubscribe function
    return () => {
      if (this.pollingTimer) {
        clearInterval(this.pollingTimer);
        this.pollingTimer = null;
      }
    };
  }

  /**
   * Delete a file from the system
   */
  async deleteFile(filePath: string): Promise<void> {
    try {
      const response = await fetch(
        `${this.apiUrl}/api/files/delete?file_path=${encodeURIComponent(filePath)}`,
        {
          method: 'DELETE',
        }
      );

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || `Failed to delete file: ${response.statusText}`);
      }

      const result = await response.json();
      console.log('File deleted:', result.message);
    } catch (error) {
      console.error('Error deleting file:', error);
      throw error;
    }
  }

  /**
   * Format file size for display
   */
  formatFileSize(bytes: number): string {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  }

  /**
   * Get appropriate icon name based on file extension
   */
  getFileIcon(extension: string): string {
    const ext = extension.toLowerCase();

    if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'].includes(ext)) {
      return 'Image';
    }
    if (['pdf'].includes(ext)) {
      return 'FileText';
    }
    if (['doc', 'docx', 'txt', 'md'].includes(ext)) {
      return 'FileText';
    }
    if (['zip', 'rar', '7z', 'tar', 'gz'].includes(ext)) {
      return 'Archive';
    }
    if (['mp4', 'avi', 'mov', 'webm', 'mkv'].includes(ext)) {
      return 'Video';
    }
    if (['mp3', 'wav', 'ogg', 'flac'].includes(ext)) {
      return 'Music';
    }
    if (['js', 'ts', 'jsx', 'tsx', 'py', 'java', 'cpp', 'c', 'h'].includes(ext)) {
      return 'Code';
    }
    if (['json', 'xml', 'yaml', 'yml'].includes(ext)) {
      return 'FileJson';
    }
    if (['csv', 'xls', 'xlsx'].includes(ext)) {
      return 'Table';
    }

    return 'File';
  }
}

export const fileSystemService = new FileSystemService();