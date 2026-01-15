import apiClient from './client';
import type { Job, JobListResponse, JobStatus, JobType } from '../types';

export const jobsApi = {
  list: (params?: {
    page?: number;
    page_size?: number;
    status?: JobStatus;
    job_type?: JobType;
  }) => {
    // Backend uses limit/offset instead of page/page_size
    const limit = params?.page_size || 50;
    const offset = params?.page ? (params.page - 1) * limit : 0;
    return apiClient.get<JobListResponse>('/jobs', {
      limit,
      offset,
      status: params?.status,
      job_type: params?.job_type,
    });
  },

  get: (id: string) => apiClient.get<Job>(`/jobs/${id}`),

  // Cancel a queued job
  cancel: (id: string) => apiClient.post<void>(`/jobs/${id}/cancel`),

  // Delete a job from the database
  delete: (id: string) => apiClient.delete<void>(`/jobs/${id}`),

  // Note: retry endpoint doesn't exist in backend - this is a placeholder
  retry: (id: string) => apiClient.post<Job>(`/jobs/${id}/retry`),

  // Cleanup stale jobs
  cleanupStale: (maxAgeHours: number = 24) =>
    apiClient.delete<{ deleted: number; message: string }>(`/jobs/cleanup/stale?max_age_hours=${maxAgeHours}`),

  // Cleanup old completed jobs
  cleanupOld: (maxAgeDays: number = 7) =>
    apiClient.delete<{ deleted: number; message: string }>(`/jobs/cleanup/old?max_age_days=${maxAgeDays}`),
};
