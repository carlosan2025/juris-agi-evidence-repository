import apiClient from './client';
import type { Job, PaginatedResponse, JobStatus, JobType } from '../types';

export const jobsApi = {
  list: (params?: {
    page?: number;
    page_size?: number;
    status?: JobStatus;
    job_type?: JobType;
  }) => apiClient.get<PaginatedResponse<Job>>('/jobs', params),

  get: (id: string) => apiClient.get<Job>(`/jobs/${id}`),

  cancel: (id: string) => apiClient.post<Job>(`/jobs/${id}/cancel`),

  retry: (id: string) => apiClient.post<Job>(`/jobs/${id}/retry`),
};
