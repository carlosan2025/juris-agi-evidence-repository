import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Activity,
  CheckCircle,
  AlertCircle,
  Clock,
  XCircle,
  RefreshCw,
  RotateCcw,
} from 'lucide-react';
import { format, formatDistanceToNow } from 'date-fns';
import {
  Card,
  Button,
  Badge,
  Select,
  Modal,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '../components/ui';
import { jobsApi } from '../api';
import type { Job, JobStatus, JobType } from '../types';

const statusOptions = [
  { value: '', label: 'All Statuses' },
  { value: 'queued', label: 'Queued' },
  { value: 'running', label: 'Running' },
  { value: 'succeeded', label: 'Succeeded' },
  { value: 'failed', label: 'Failed' },
  { value: 'canceled', label: 'Canceled' },
];

const typeOptions = [
  { value: '', label: 'All Types' },
  { value: 'extraction', label: 'Extraction' },
  { value: 'embedding', label: 'Embedding' },
  { value: 'ingestion', label: 'Ingestion' },
  { value: 'analysis', label: 'Analysis' },
  { value: 'multi_level_extraction', label: 'Multi-Level Extraction' },
];

export function Jobs() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<JobStatus | ''>('');
  const [typeFilter, setTypeFilter] = useState<JobType | ''>('');
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['jobs', { page, page_size: 20, status: statusFilter || undefined, job_type: typeFilter || undefined }],
    queryFn: () =>
      jobsApi.list({
        page,
        page_size: 20,
        status: statusFilter || undefined,
        job_type: typeFilter || undefined,
      }),
    refetchInterval: 5000, // Poll every 5 seconds
  });

  const cancelMutation = useMutation({
    mutationFn: (id: string) => jobsApi.cancel(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] });
    },
  });

  const retryMutation = useMutation({
    mutationFn: (id: string) => jobsApi.retry(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] });
    },
  });

  const getStatusIcon = (status: JobStatus) => {
    switch (status) {
      case 'succeeded':
        return <CheckCircle className="h-5 w-5 text-green-500" />;
      case 'failed':
        return <AlertCircle className="h-5 w-5 text-red-500" />;
      case 'running':
        return <Activity className="h-5 w-5 text-blue-500 animate-pulse" />;
      case 'canceled':
        return <XCircle className="h-5 w-5 text-gray-500" />;
      case 'retrying':
        return <RotateCcw className="h-5 w-5 text-orange-500" />;
      default:
        return <Clock className="h-5 w-5 text-gray-400" />;
    }
  };

  const getStatusBadge = (status: JobStatus) => {
    switch (status) {
      case 'succeeded':
        return <Badge variant="success">Succeeded</Badge>;
      case 'failed':
        return <Badge variant="danger">Failed</Badge>;
      case 'running':
        return <Badge variant="info">Running</Badge>;
      case 'canceled':
        return <Badge variant="default">Canceled</Badge>;
      case 'retrying':
        return <Badge variant="warning">Retrying</Badge>;
      default:
        return <Badge variant="default">Queued</Badge>;
    }
  };

  const getTypeBadge = (type: JobType) => {
    const colors: Record<string, string> = {
      extraction: 'bg-purple-100 text-purple-700',
      embedding: 'bg-blue-100 text-blue-700',
      ingestion: 'bg-green-100 text-green-700',
      analysis: 'bg-orange-100 text-orange-700',
      multi_level_extraction: 'bg-pink-100 text-pink-700',
    };
    return (
      <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${colors[type] || 'bg-gray-100 text-gray-700'}`}>
        {type.replace('_', ' ')}
      </span>
    );
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Jobs</h1>
        <Button variant="secondary" onClick={() => refetch()}>
          <RefreshCw className="h-4 w-4" />
          Refresh
        </Button>
      </div>

      {/* Filters */}
      <Card>
        <div className="flex flex-wrap gap-4">
          <div className="w-48">
            <Select
              label="Status"
              options={statusOptions}
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value as JobStatus | '');
                setPage(1);
              }}
            />
          </div>
          <div className="w-48">
            <Select
              label="Type"
              options={typeOptions}
              value={typeFilter}
              onChange={(e) => {
                setTypeFilter(e.target.value as JobType | '');
                setPage(1);
              }}
            />
          </div>
        </div>
      </Card>

      <Card padding="none">
        {isLoading ? (
          <div className="p-8 text-center text-gray-500">Loading jobs...</div>
        ) : data?.items.length === 0 ? (
          <div className="p-8 text-center">
            <Activity className="h-12 w-12 text-gray-300 mx-auto mb-4" />
            <p className="text-gray-500">No jobs found</p>
          </div>
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Status</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead>Duration</TableHead>
                  <TableHead>Attempts</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data?.items.map((job) => (
                  <TableRow key={job.id} onClick={() => setSelectedJob(job)}>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        {getStatusIcon(job.status)}
                        {getStatusBadge(job.status)}
                      </div>
                    </TableCell>
                    <TableCell>{getTypeBadge(job.job_type)}</TableCell>
                    <TableCell>
                      <span className="text-sm text-gray-500">
                        {formatDistanceToNow(new Date(job.created_at), { addSuffix: true })}
                      </span>
                    </TableCell>
                    <TableCell>
                      {job.started_at && job.completed_at ? (
                        <span className="text-sm">
                          {Math.round(
                            (new Date(job.completed_at).getTime() -
                              new Date(job.started_at).getTime()) /
                              1000
                          )}
                          s
                        </span>
                      ) : job.started_at ? (
                        <span className="text-sm text-blue-500">Running...</span>
                      ) : (
                        <span className="text-sm text-gray-400">-</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <span className="text-sm">
                        {job.attempts}/{job.max_attempts}
                      </span>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-2">
                        {(job.status === 'queued' || job.status === 'running') && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation();
                              cancelMutation.mutate(job.id);
                            }}
                          >
                            <XCircle className="h-4 w-4 text-red-500" />
                          </Button>
                        )}
                        {job.status === 'failed' && job.attempts < job.max_attempts && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={(e) => {
                              e.stopPropagation();
                              retryMutation.mutate(job.id);
                            }}
                          >
                            <RotateCcw className="h-4 w-4 text-blue-500" />
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>

            {data && data.pages > 1 && (
              <div className="flex items-center justify-between px-6 py-4 border-t border-gray-200">
                <span className="text-sm text-gray-500">
                  Page {page} of {data.pages} ({data.total} jobs)
                </span>
                <div className="flex gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page === 1}
                  >
                    Previous
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => setPage((p) => Math.min(data.pages, p + 1))}
                    disabled={page === data.pages}
                  >
                    Next
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </Card>

      {/* Job Details Modal */}
      <Modal
        isOpen={!!selectedJob}
        onClose={() => setSelectedJob(null)}
        title="Job Details"
        size="lg"
      >
        {selectedJob && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-sm font-medium text-gray-500">Status</label>
                <p className="mt-1">{getStatusBadge(selectedJob.status)}</p>
              </div>
              <div>
                <label className="text-sm font-medium text-gray-500">Type</label>
                <p className="mt-1">{getTypeBadge(selectedJob.job_type)}</p>
              </div>
              <div>
                <label className="text-sm font-medium text-gray-500">Created</label>
                <p className="text-gray-900">
                  {format(new Date(selectedJob.created_at), 'PPpp')}
                </p>
              </div>
              <div>
                <label className="text-sm font-medium text-gray-500">Attempts</label>
                <p className="text-gray-900">
                  {selectedJob.attempts} / {selectedJob.max_attempts}
                </p>
              </div>
              {selectedJob.started_at && (
                <div>
                  <label className="text-sm font-medium text-gray-500">Started</label>
                  <p className="text-gray-900">
                    {format(new Date(selectedJob.started_at), 'PPpp')}
                  </p>
                </div>
              )}
              {selectedJob.completed_at && (
                <div>
                  <label className="text-sm font-medium text-gray-500">Completed</label>
                  <p className="text-gray-900">
                    {format(new Date(selectedJob.completed_at), 'PPpp')}
                  </p>
                </div>
              )}
            </div>

            {selectedJob.error_message && (
              <div>
                <label className="text-sm font-medium text-gray-500">Error</label>
                <pre className="mt-1 p-3 bg-red-50 text-red-700 rounded-lg text-sm overflow-auto">
                  {selectedJob.error_message}
                </pre>
              </div>
            )}

            {selectedJob.parameters && Object.keys(selectedJob.parameters).length > 0 && (
              <div>
                <label className="text-sm font-medium text-gray-500">Parameters</label>
                <pre className="mt-1 p-3 bg-gray-50 rounded-lg text-sm overflow-auto">
                  {JSON.stringify(selectedJob.parameters, null, 2)}
                </pre>
              </div>
            )}

            {selectedJob.result && Object.keys(selectedJob.result).length > 0 && (
              <div>
                <label className="text-sm font-medium text-gray-500">Result</label>
                <pre className="mt-1 p-3 bg-gray-50 rounded-lg text-sm overflow-auto">
                  {JSON.stringify(selectedJob.result, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}
