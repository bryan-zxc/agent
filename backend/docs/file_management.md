# File Management System

## Overview

The agent system provides intelligent file management with content-based duplicate detection, user-friendly resolution workflows, and efficient storage handling. Files are processed using SHA-256 content hashing to identify duplicates regardless of filename differences.

## Architecture

### Core Components

- **Frontend Upload Service**: `frontend/src/lib/fileUpload.ts`
- **Duplicate Resolution UI**: `frontend/src/components/DuplicateFileDialog.tsx`
- **Backend API Endpoints**: `/upload` and `/upload/resolve-duplicate`
- **File Utilities**: `backend/src/agent/utils/file_utils.py`
- **Database Storage**: `file_metadata` table with content hashing

### Upload Flow

```
User uploads file → Content hash calculated → Database check for duplicates
   ↓
If duplicate found → Present resolution options → Handle user choice
   ↓
If no duplicate → Save file normally → Store metadata
```

## Duplicate Detection

### Content Hashing

Files are identified using SHA-256 content hashing:
- Calculated in 4KB chunks for memory efficiency
- Hash stored in `file_metadata.content_hash` field
- Indexed for fast duplicate lookups per user

### User Isolation

Duplicate detection operates per user:
- Files are scoped by `user_id` field
- Users only see their own duplicates
- Supports multi-tenant deployments

## Resolution Options

When duplicates are detected, users receive four resolution options:

### 1. Use Existing File
- **Action**: `use_existing`
- **Behaviour**: References the previously uploaded file
- **Use Case**: File content is identical, no need for new copy
- **Storage**: No additional storage consumed

### 2. Overwrite Existing
- **Action**: `overwrite_existing`
- **Behaviour**: Replaces existing file with new version
- **Use Case**: Updated version of same document
- **Storage**: Original file replaced, metadata preserved

### 3. Save as New Copy
- **Action**: `save_as_new_copy`
- **Behaviour**: Saves both files with unique filenames
- **Use Case**: Similar content but both versions needed
- **Storage**: Both files stored independently
- **Naming**: Automatic `_copy_N` suffix generation

### 4. Cancel Upload
- **Action**: `cancel`
- **Behaviour**: Aborts the upload process
- **Use Case**: User decides not to proceed
- **Storage**: No files saved or modified

## API Endpoints

### POST /upload

Initial file upload with duplicate detection.

**Request:**
```
Content-Type: multipart/form-data
file: [binary file data]
```

**Response (No Duplicate):**
```json
{
  "duplicate_found": false,
  "file_id": "a1b2c3d4...",
  "filename": "document.pdf",
  "path": "/app/files/uploads/user123/a1b2c3d4_document.pdf",
  "size": 245760
}
```

**Response (Duplicate Found):**
```json
{
  "duplicate_found": true,
  "existing_file": {
    "file_id": "x1y2z3w4...",
    "original_filename": "old_document.pdf",
    "file_size": 245760,
    "upload_timestamp": "2025-08-10T10:30:00Z"
  },
  "new_filename": "document.pdf",
  "options": ["use_existing", "overwrite_existing", "save_as_new_copy", "cancel"]
}
```

### POST /upload/resolve-duplicate

Handle user's duplicate resolution choice.

**Request:**
```
Content-Type: multipart/form-data
file: [binary file data]
action: "save_as_new_copy"
existing_file_id: "x1y2z3w4..."
new_filename: "document.pdf"
```

**Response:**
```json
{
  "action": "save_as_new_copy",
  "file_id": "a1b2c3d4...",
  "filename": "document_copy_1.pdf",
  "path": "/app/files/uploads/user123/a1b2c3d4_document_copy_1.pdf",
  "size": 245760,
  "files": [
    "/app/files/uploads/user123/x1y2z3w4_old_document.pdf",
    "/app/files/uploads/user123/a1b2c3d4_document_copy_1.pdf"
  ]
}
```

## Database Schema

### file_metadata Table

| Field | Type | Description |
|-------|------|-------------|
| file_id | VARCHAR(32) | UUID hex string (primary key) |
| content_hash | VARCHAR(64) | SHA-256 content hash (indexed) |
| original_filename | VARCHAR(512) | User-provided filename |
| file_path | TEXT | Physical file location |
| file_size | INTEGER | File size in bytes |
| mime_type | VARCHAR(100) | File content type |
| user_id | VARCHAR(100) | File owner identifier |
| reference_count | INTEGER | Usage reference count |
| upload_timestamp | TIMESTAMP | Upload time |
| last_accessed | TIMESTAMP | Last access time |

### Indexes

- Primary: `file_id`
- Composite: `(content_hash, user_id)` - Fast duplicate detection
- Single: `user_id` - User file queries
- Single: `upload_timestamp` - Chronological ordering

## File Storage

### Directory Structure

```
/app/files/uploads/
├── user123/
│   ├── a1b2c3d4_document.pdf
│   ├── x1y2z3w4_old_document.pdf
│   └── ...
└── user456/
    ├── ...
```

### Naming Convention

Files stored with format: `{file_id}_{original_filename}`
- Ensures uniqueness through UUID prefix
- Preserves original filename for readability
- Supports filename conflict resolution

### Reference Counting

- New files start with `reference_count = 1`
- Increment on additional references
- Enables safe cleanup when count reaches 0
- Prevents premature deletion of shared files

## Frontend Integration

### Upload Service Usage

```typescript
import { fileUploadService, DuplicateFileInfo } from '@/lib/fileUpload';

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

const filePaths = await fileUploadService.uploadFiles(files, handleDuplicate);
```

### Dialog Component

The `DuplicateFileDialog` provides:
- Clear duplicate file information
- Visual file details (size, upload date)
- Action buttons with descriptions
- Responsive design for mobile/desktop

## Security Considerations

### Content Validation

- File content hashed before processing
- MIME type validation
- File size limits enforced
- Malicious file detection (future enhancement)

### User Isolation

- All file operations scoped by `user_id`
- No cross-user file access
- Secure file path handling
- Directory traversal prevention

### Data Integrity

- Atomic file operations
- Database transaction consistency
- Rollback on upload failures
- Comprehensive error handling

## Performance Optimizations

### Hashing Efficiency

- 4KB chunk processing for large files
- Minimal memory footprint
- Streaming hash calculation
- Early duplicate detection

### Database Performance

- Indexed content hash lookups
- Composite index for user-scoped queries
- Query optimisation for file listings
- Connection pooling for concurrent uploads

### Storage Efficiency

- Content-based deduplication
- Reference counting prevents orphaned files
- Lazy cleanup of unreferenced files
- Compressed storage options (configurable)

## Error Handling

### Upload Failures

- Comprehensive exception catching
- Detailed error logging
- User-friendly error messages
- Graceful degradation

### Database Errors

- Transaction rollback on failures
- Retry logic for transient errors
- Connection pool management
- Data consistency guarantees

### File System Errors

- Permission error handling
- Disk space monitoring
- Backup file cleanup
- Recovery procedures

## Future Enhancements

### Planned Features

- File versioning system
- Automatic file cleanup scheduling
- Advanced file type detection
- Thumbnail generation for images
- File compression and optimization
- Audit trail for file operations

### Scalability Improvements

- Distributed file storage support
- Horizontal database scaling
- CDN integration for file delivery
- Background processing queues
- Microservice architecture migration

## Troubleshooting

### Common Issues

1. **Duplicate detection not working**
   - Check `content_hash` index exists
   - Verify user isolation logic
   - Examine file hash calculation

2. **Upload failures**
   - Check file permissions
   - Verify disk space availability
   - Review error logs

3. **Performance issues**
   - Monitor database query performance
   - Check file system I/O metrics
   - Review concurrent upload limits

### Debugging Tools

- Database query analysis
- File system monitoring
- Error log aggregation
- Performance profiling
- User action tracking

## Monitoring and Metrics

### Key Metrics

- Upload success/failure rates
- Duplicate detection accuracy
- File storage utilisation
- User resolution choice patterns
- API response times

### Alerting

- Failed upload threshold alerts
- Storage capacity warnings
- Database performance alerts
- Error rate monitoring
- User experience metrics