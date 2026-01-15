import apiClient from './client';
import type { Document, DocumentVersion, PaginatedResponse, PresignedUploadResponse, ConfirmUploadResponse } from '../types';

// Threshold for using presigned uploads (4MB - below Vercel's 4.5MB limit)
const PRESIGNED_UPLOAD_THRESHOLD = 4 * 1024 * 1024;

export const documentsApi = {
  list: (params?: { page?: number; page_size?: number; extraction_status?: string }) =>
    apiClient.get<PaginatedResponse<Document>>('/documents', params),

  get: (id: string) => apiClient.get<Document>(`/documents/${id}`),

  /**
   * Upload a document - automatically uses presigned URL for large files
   */
  upload: async (file: File, profileCode: string = 'general', metadata?: Record<string, unknown>) => {
    // Use presigned upload for large files to bypass Vercel's 4.5MB limit
    if (file.size > PRESIGNED_UPLOAD_THRESHOLD) {
      return documentsApi.uploadPresigned(file, profileCode);
    }

    // Small files can use direct upload
    const additionalData: Record<string, string> = { profile_code: profileCode };
    if (metadata) {
      additionalData.metadata = JSON.stringify(metadata);
    }
    return apiClient.upload<Document>('/documents', file, additionalData);
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
   * Upload a file using presigned URL (for large files)
   */
  uploadPresigned: async (file: File, profileCode: string = 'general'): Promise<Document> => {
    // Step 1: Get presigned URL
    const presigned = await documentsApi.getPresignedUploadUrl(
      file.name,
      file.type || 'application/octet-stream',
      file.size,
      profileCode
    );

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

    // Step 3: Confirm upload
    await documentsApi.confirmUpload(presigned.document_id, presigned.version_id);

    // Return a Document-like object (the actual document will be created by the backend)
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

  delete: (id: string) => apiClient.delete<void>(`/documents/${id}`),

  getVersions: (id: string) =>
    apiClient.get<DocumentVersion[]>(`/documents/${id}/versions`),

  triggerExtraction: (id: string) =>
    apiClient.post<{ job_id: string }>(`/documents/${id}/extract`),

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
