import apiClient from './client';
import type { Document, DocumentVersion, PaginatedResponse } from '../types';

export const documentsApi = {
  list: (params?: { page?: number; page_size?: number; extraction_status?: string }) =>
    apiClient.get<PaginatedResponse<Document>>('/documents', params),

  get: (id: string) => apiClient.get<Document>(`/documents/${id}`),

  upload: (file: File, profileCode: string = 'general', metadata?: Record<string, unknown>) => {
    const additionalData: Record<string, string> = { profile_code: profileCode };
    if (metadata) {
      additionalData.metadata = JSON.stringify(metadata);
    }
    return apiClient.upload<Document>('/documents', file, additionalData);
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
};
