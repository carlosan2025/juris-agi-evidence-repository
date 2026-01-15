import apiClient from './client';
import type { Document, DocumentVersion, PaginatedResponse, PresignedUploadResponse, ConfirmUploadResponse } from '../types';

export const documentsApi = {
  list: (params?: { page?: number; page_size?: number; extraction_status?: string }) =>
    apiClient.get<PaginatedResponse<Document>>('/documents', params),

  get: (id: string) => apiClient.get<Document>(`/documents/${id}`),

  /**
   * Upload a document using presigned URL (Agent-K optimistic pattern)
   *
   * Flow:
   * 1. Presign (fast) → Create DB record, get upload URL → Document appears in list!
   * 2. Upload (medium) → Client uploads directly to R2 (bypasses server)
   * 3. Confirm (fast) → Trigger worker fire-and-forget
   * → Background processing starts async, polling updates UI
   */
  upload: async (
    file: File,
    profileCode: string = 'general',
    _metadata?: Record<string, unknown>,
    onPresigned?: (documentId: string) => void
  ) => {
    // Always use presigned upload for consistent flow (Agent-K pattern)
    return documentsApi.uploadPresigned(file, profileCode, onPresigned);
  },

  /**
   * Get a presigned URL for direct upload to storage
   */
  getPresignedUploadUrl: (filename: string, contentType: string, fileSize: number, profileCode: string = 'general') =>
    apiClient.post<PresignedUploadResponse>('/documents/presigned-upload', {
      filename,
      content_type: contentType,
      file_size: fileSize,
      profile_code: profileCode,
    }),

  /**
   * Confirm that a presigned upload completed
   */
  confirmUpload: (documentId: string, versionId: string) =>
    apiClient.post<ConfirmUploadResponse>('/documents/confirm-upload', {
      document_id: documentId,
      version_id: versionId,
    }),

  /**
   * Upload a file using presigned URL (Agent-K optimistic pattern)
   *
   * The document record is created at Step 1 with upload_status=PENDING,
   * so it appears in the list immediately while upload continues.
   */
  uploadPresigned: async (
    file: File,
    profileCode: string = 'general',
    onPresigned?: (documentId: string) => void
  ): Promise<Document> => {
    // Step 1: Get presigned URL (creates DB record with upload_status=PENDING)
    const presigned = await documentsApi.getPresignedUploadUrl(
      file.name,
      file.type || 'application/octet-stream',
      file.size,
      profileCode
    );

    // Notify caller that document is now in DB (for optimistic UI refresh)
    if (onPresigned) {
      onPresigned(presigned.document_id);
    }

    // Step 2: Upload directly to storage (bypasses Vercel)
    const uploadResponse = await fetch(presigned.upload_url, {
      method: 'PUT',
      body: file,
      headers: {
        'Content-Type': presigned.content_type,
      },
    });

    if (!uploadResponse.ok) {
      throw new Error(`Upload to storage failed: ${uploadResponse.statusText}`);
    }

    // Step 3: Confirm upload (triggers background processing)
    await documentsApi.confirmUpload(presigned.document_id, presigned.version_id);

    // Return document info
    return {
      id: presigned.document_id,
      filename: file.name,
      original_filename: file.name,
      content_type: file.type || 'application/octet-stream',
      file_hash: null,
      profile_code: profileCode,
      metadata: {},
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      deleted_at: null,
      latest_version: null,
    };
  },

  /**
   * Delete a document (triggers safe cascading deletion)
   * Returns deletion task info instead of void
   */
  delete: (id: string) => apiClient.delete<DeleteResponse>(`/documents/${id}`),

  /**
   * Get deletion status for a document
   */
  getDeletionStatus: (id: string) => apiClient.get<DeletionStatusResponse>(`/documents/${id}/deletion-status`),

  /**
   * Retry a failed deletion
   */
  retryDeletion: (id: string) => apiClient.post<DeleteResponse>(`/documents/${id}/retry-deletion`),

  getVersions: (id: string) =>
    apiClient.get<DocumentVersion[]>(`/documents/${id}/versions`),

  triggerExtraction: (id: string) =>
    apiClient.post<{ job_id: string }>(`/documents/${id}/extract`),

  /**
   * Retry processing a failed or stuck document
   */
  retry: (id: string, force: boolean = false) =>
    apiClient.post<RetryResponse>(`/documents/${id}/retry${force ? '?force=true' : ''}`),

  /**
   * Get detailed processing status for a document version
   */
  getVersionStatus: (versionId: string) =>
    apiClient.get<VersionStatusResponse>(`/worker/version/${versionId}/status`),

  download: (id: string, versionId?: string) => {
    const url = versionId
      ? `/documents/${id}/versions/${versionId}/download`
      : `/documents/${id}/download`;
    return apiClient.download(url);
  },

  getStats: (id: string) =>
    apiClient.get<DocumentStats>(`/documents/${id}/stats`),

  getSpans: (id: string, params?: { limit?: number; offset?: number }) =>
    apiClient.get<SpanListResponse>(`/documents/${id}/spans`, params),
};

// Document statistics response type
export interface DocumentStats {
  document_id: string;
  version_id: string;
  filename: string;
  extraction_status: string | null;
  extracted_at: string | null;
  text_length: number;
  page_count: number | null;
  spans: {
    total: number;
    by_type: Record<string, number>;
  };
  embeddings: {
    total: number;
    model: string;
    dimensions: number;
    chunk_size: number;
    chunk_overlap: number;
  };
  metadata: Record<string, unknown>;
  version_metadata: Record<string, unknown>;
}

// Span list response type
export interface SpanListResponse {
  items: SpanItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface SpanItem {
  id: string;
  span_type: string;
  text_content: string;
  text_length: number;
  start_locator: Record<string, unknown>;
  end_locator: Record<string, unknown> | null;
  metadata: Record<string, unknown>;
  created_at: string | null;
}

// Response type for document retry
export interface RetryResponse {
  status: string;
  message: string;
  document_id: string;
  version_id: string;
}

// Response type for version processing status
export interface VersionStatusResponse {
  version_id: string;
  document_id: string;
  filename: string | null;
  status: string;
  processing_step: string;
  processing_step_label: string;
  upload_status: string | null;
  error: string | null;
  page_count: number | null;
  text_length: number | null;
  spans_count: number;
  embeddings_count: number;
  created_at: string;
  updated_at: string;
}

// Response type for document deletion
export interface DeleteResponse {
  status: string;
  document_id: string;
  filename: string;
  task_count: number;
  message: string;
}

// Response type for deletion status
export interface DeletionStatusResponse {
  document_id: string;
  filename: string;
  deletion_status: string;
  deletion_requested_at: string | null;
  deletion_requested_by: string | null;
  deletion_completed_at: string | null;
  deletion_error: string | null;
  task_summary: {
    total: number;
    pending: number;
    in_progress: number;
    completed: number;
    failed: number;
    skipped: number;
  };
  tasks: DeletionTask[];
}

export interface DeletionTask {
  id: string;
  type: string;
  resource_id: string;
  resource_count: number;
  status: string;
  error_message: string | null;
  retry_count: number;
  processing_order: number;
}
