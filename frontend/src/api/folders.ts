import apiClient from './client';
import type {
  Folder,
  FolderCreate,
  FolderUpdate,
  FolderTreeResponse,
  MoveDocumentRequest,
  MoveFolderRequest,
  BulkMoveDocumentsRequest,
  ProjectDocument,
} from '../types';

export const foldersApi = {
  // List folders (flat list)
  list: (projectId: string) =>
    apiClient.get<Folder[]>(`/projects/${projectId}/folders`),

  // Get folder tree (hierarchical)
  getTree: (projectId: string) =>
    apiClient.get<FolderTreeResponse>(`/projects/${projectId}/folders/tree`),

  // Get single folder
  get: (projectId: string, folderId: string) =>
    apiClient.get<Folder>(`/projects/${projectId}/folders/${folderId}`),

  // Create folder
  create: (projectId: string, data: FolderCreate) =>
    apiClient.post<Folder>(`/projects/${projectId}/folders`, data),

  // Update folder
  update: (projectId: string, folderId: string, data: FolderUpdate) =>
    apiClient.patch<Folder>(`/projects/${projectId}/folders/${folderId}`, data),

  // Delete folder (soft delete)
  delete: (projectId: string, folderId: string) =>
    apiClient.delete<void>(`/projects/${projectId}/folders/${folderId}`),

  // Move a document to a folder (or root if folder_id is null)
  moveDocument: (projectId: string, documentId: string, data: MoveDocumentRequest) =>
    apiClient.patch<ProjectDocument>(
      `/projects/${projectId}/documents/${documentId}/folder`,
      data
    ),

  // Bulk move documents to a folder
  bulkMoveDocuments: (projectId: string, data: BulkMoveDocumentsRequest) =>
    apiClient.post<{ moved_count: number; document_ids: string[] }>(
      `/projects/${projectId}/folders/bulk-move-documents`,
      data
    ),

  // Move a folder to a new parent (or root if parent_folder_id is null)
  moveFolder: (projectId: string, folderId: string, data: MoveFolderRequest) =>
    apiClient.patch<Folder>(
      `/projects/${projectId}/folders/${folderId}/move`,
      data
    ),
};
