import apiClient from './client';
import type { HealthResponse } from '../types';

export const healthApi = {
  check: () => apiClient.get<HealthResponse>('/health'),
};
