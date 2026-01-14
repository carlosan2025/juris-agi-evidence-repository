import apiClient from './client';
import type {
  IntegrationKey,
  IntegrationKeyWithValue,
  IntegrationKeyCreate,
  IntegrationKeyUpdate,
  IntegrationKeyListResponse,
  IntegrationStatusResponse,
  IntegrationProvider,
} from '../types';

export const adminApi = {
  // Integration status
  getIntegrationStatus: () =>
    apiClient.get<IntegrationStatusResponse>('/admin/integrations/status'),

  // Integration keys
  listKeys: (params?: { provider?: IntegrationProvider; is_active?: boolean }) =>
    apiClient.get<IntegrationKeyListResponse>('/admin/integrations/keys', params),

  getKey: (id: string) =>
    apiClient.get<IntegrationKey>(`/admin/integrations/keys/${id}`),

  revealKey: (id: string) =>
    apiClient.get<IntegrationKeyWithValue>(`/admin/integrations/keys/${id}/reveal`),

  createKey: (data: IntegrationKeyCreate) =>
    apiClient.post<IntegrationKey>('/admin/integrations/keys', data),

  updateKey: (id: string, data: IntegrationKeyUpdate) =>
    apiClient.patch<IntegrationKey>(`/admin/integrations/keys/${id}`, data),

  deleteKey: (id: string) =>
    apiClient.delete<void>(`/admin/integrations/keys/${id}`),

  testIntegration: (provider: IntegrationProvider) =>
    apiClient.post<{ provider: string; success: boolean; message: string; details?: Record<string, unknown> }>(
      '/admin/integrations/test',
      { provider }
    ),
};
