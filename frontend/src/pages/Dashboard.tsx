import { useQuery } from '@tanstack/react-query';
import { FileText, FolderOpen, Activity, CheckCircle, AlertCircle, Clock } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Card, CardTitle, Badge } from '../components/ui';
import { documentsApi, projectsApi, jobsApi, healthApi } from '../api';

export function Dashboard() {
  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: healthApi.check,
    refetchInterval: 30000,
  });

  const { data: documents } = useQuery({
    queryKey: ['documents', { page: 1, page_size: 5 }],
    queryFn: () => documentsApi.list({ page: 1, page_size: 5 }),
  });

  const { data: projects } = useQuery({
    queryKey: ['projects', { page: 1, page_size: 5 }],
    queryFn: () => projectsApi.list({ page: 1, page_size: 5 }),
  });

  const { data: jobs } = useQuery({
    queryKey: ['jobs', { page: 1, page_size: 5 }],
    queryFn: () => jobsApi.list({ page: 1, page_size: 5 }),
  });

  const stats = [
    {
      name: 'Total Documents',
      value: documents?.total ?? 0,
      icon: FileText,
      href: '/documents',
      color: 'text-blue-600 bg-blue-100',
    },
    {
      name: 'Active Projects',
      value: projects?.total ?? 0,
      icon: FolderOpen,
      href: '/projects',
      color: 'text-purple-600 bg-purple-100',
    },
    {
      name: 'Pending Jobs',
      value: jobs?.jobs?.filter((j) => j.status === 'queued' || j.status === 'running').length ?? 0,
      icon: Activity,
      href: '/jobs',
      color: 'text-orange-600 bg-orange-100',
    },
  ];

  const getHealthBadge = () => {
    if (!health) return <Badge variant="default">Unknown</Badge>;
    switch (health.status) {
      case 'healthy':
        return <Badge variant="success">Healthy</Badge>;
      case 'degraded':
        return <Badge variant="warning">Degraded</Badge>;
      case 'unhealthy':
        return <Badge variant="danger">Unhealthy</Badge>;
      default:
        return <Badge variant="default">Unknown</Badge>;
    }
  };

  const getJobStatusIcon = (status: string) => {
    switch (status) {
      case 'succeeded':
        return <CheckCircle className="h-4 w-4 text-green-500" />;
      case 'failed':
        return <AlertCircle className="h-4 w-4 text-red-500" />;
      case 'running':
        return <Activity className="h-4 w-4 text-blue-500 animate-pulse" />;
      default:
        return <Clock className="h-4 w-4 text-gray-400" />;
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-500">System Status:</span>
          {getHealthBadge()}
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {stats.map((stat) => (
          <Link key={stat.name} to={stat.href}>
            <Card className="hover:shadow-md transition-shadow">
              <div className="flex items-center gap-4">
                <div className={`p-3 rounded-lg ${stat.color}`}>
                  <stat.icon className="h-6 w-6" />
                </div>
                <div>
                  <p className="text-sm text-gray-500">{stat.name}</p>
                  <p className="text-2xl font-bold text-gray-900">{stat.value}</p>
                </div>
              </div>
            </Card>
          </Link>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Documents */}
        <Card>
          <div className="flex items-center justify-between mb-4">
            <CardTitle>Recent Documents</CardTitle>
            <Link to="/documents" className="text-sm text-blue-600 hover:text-blue-700">
              View all
            </Link>
          </div>
          <div className="space-y-3">
            {(documents?.items?.length ?? 0) === 0 && (
              <p className="text-sm text-gray-500 text-center py-4">No documents yet</p>
            )}
            {documents?.items?.map((doc) => (
              <div
                key={doc.id}
                className="flex items-center gap-3 p-3 rounded-lg hover:bg-gray-50"
              >
                <FileText className="h-5 w-5 text-gray-400" />
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900 truncate">
                    {doc.filename}
                  </p>
                  <p className="text-xs text-gray-500">
                    {doc.latest_version ? (doc.latest_version.file_size / 1024).toFixed(1) : '0'} KB
                  </p>
                </div>
                <Badge
                  variant={
                    doc.latest_version?.extraction_status === 'completed'
                      ? 'success'
                      : doc.latest_version?.extraction_status === 'failed'
                      ? 'danger'
                      : 'default'
                  }
                >
                  {doc.latest_version?.extraction_status || 'pending'}
                </Badge>
              </div>
            ))}
          </div>
        </Card>

        {/* Recent Jobs */}
        <Card>
          <div className="flex items-center justify-between mb-4">
            <CardTitle>Recent Jobs</CardTitle>
            <Link to="/jobs" className="text-sm text-blue-600 hover:text-blue-700">
              View all
            </Link>
          </div>
          <div className="space-y-3">
            {(jobs?.jobs?.length ?? 0) === 0 && (
              <p className="text-sm text-gray-500 text-center py-4">No jobs yet</p>
            )}
            {jobs?.jobs?.map((job) => (
              <div
                key={job.job_id}
                className="flex items-center gap-3 p-3 rounded-lg hover:bg-gray-50"
              >
                {getJobStatusIcon(job.status)}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900 truncate">
                    {job.job_type}
                  </p>
                  <p className="text-xs text-gray-500">
                    {job.created_at ? new Date(job.created_at).toLocaleString() : '-'}
                  </p>
                </div>
                <Badge
                  variant={
                    job.status === 'succeeded'
                      ? 'success'
                      : job.status === 'failed'
                      ? 'danger'
                      : job.status === 'running'
                      ? 'info'
                      : 'default'
                  }
                >
                  {job.status}
                </Badge>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
