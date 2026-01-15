import apiClient from './client';
import type { Project, ProjectCreate, ProjectUpdate, PaginatedResponse, ProjectDocument } from '../types';

export const projectsApi = {
  list: (params?: { page?: number; page_size?: number }) =>
    apiClient.get<PaginatedResponse<Project>>('/projects', params),

  get: (id: string) => apiClient.get<Project>(`/projects/${id}`),

  create: (data: ProjectCreate) => apiClient.post<Project>('/projects', data),

  update: (id: string, data: ProjectUpdate) =>
    apiClient.patch<Project>(`/projects/${id}`, data),

  delete: (id: string) => apiClient.delete<void>(`/projects/${id}`),

  // Document attachment - backend returns list[ProjectDocumentResponse], not paginated
  getDocuments: (projectId: string) =>
    apiClient.get<ProjectDocument[]>(`/projects/${projectId}/documents`),

  attachDocument: (projectId: string, documentId: string, pinnedVersionId?: string) =>
    apiClient.post<ProjectDocument>(`/projects/${projectId}/documents`, {
      document_id: documentId,
      pinned_version_id: pinnedVersionId,
    }),

  detachDocument: (projectId: string, documentId: string) =>
    apiClient.delete<void>(`/projects/${projectId}/documents/${documentId}`),
};
