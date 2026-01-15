import { useParams, useNavigate, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { format } from 'date-fns';
import {
  ArrowLeft,
  FolderOpen,
  FileText,
  RefreshCw,
  XCircle,
  CheckCircle,
  AlertCircle,
  Calendar,
  Hash,
} from 'lucide-react';
import { projectsApi } from '../api';
import { Card } from '../components/ui';
import type { ProjectDocument, ExtractionStatus } from '../types';

export function ProjectDetail() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();

  // Fetch project details
  const { data: project, isLoading: projectLoading, error: projectError } = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => projectsApi.get(projectId!),
    enabled: !!projectId,
  });

  // Fetch project documents
  const { data: documents, isLoading: docsLoading } = useQuery({
    queryKey: ['project-documents', projectId],
    queryFn: () => projectsApi.getDocuments(projectId!),
    enabled: !!projectId,
  });

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const getStatusIcon = (status: ExtractionStatus | null | undefined) => {
    switch (status) {
      case 'completed':
        return <CheckCircle className="h-4 w-4 text-green-500" />;
      case 'failed':
        return <XCircle className="h-4 w-4 text-red-500" />;
      case 'processing':
        return <RefreshCw className="h-4 w-4 text-yellow-500 animate-spin" />;
      default:
        return <AlertCircle className="h-4 w-4 text-gray-400" />;
    }
  };

  const getStatusLabel = (status: ExtractionStatus | null | undefined) => {
    switch (status) {
      case 'completed':
        return 'Complete';
      case 'failed':
        return 'Failed';
      case 'processing':
        return 'Processing';
      default:
        return 'Pending';
    }
  };

  if (projectLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="h-8 w-8 animate-spin text-gray-400" />
      </div>
    );
  }

  if (projectError || !project) {
    return (
      <div className="text-center py-12">
        <XCircle className="h-12 w-12 mx-auto text-red-400 mb-4" />
        <h2 className="text-lg font-medium text-gray-900">Project Not Found</h2>
        <p className="text-gray-500 mt-1">The project you're looking for doesn't exist or was deleted.</p>
        <button
          onClick={() => navigate('/projects')}
          className="mt-4 text-blue-600 hover:text-blue-800"
        >
          Back to Projects
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <button
            onClick={() => navigate('/projects')}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <ArrowLeft className="h-5 w-5 text-gray-600" />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <FolderOpen className="h-6 w-6 text-purple-500" />
              {project.name}
            </h1>
            {project.description && (
              <p className="text-sm text-gray-500 mt-1">{project.description}</p>
            )}
          </div>
        </div>
      </div>

      {/* Project Info */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card className="p-4">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-gray-500">Documents</span>
            <FileText className="h-5 w-5 text-blue-500" />
          </div>
          <p className="text-2xl font-bold text-gray-900 mt-2">
            {docsLoading ? '...' : documents?.length ?? 0}
          </p>
          <p className="text-xs text-gray-400 mt-1">attached to project</p>
        </Card>

        {project.case_ref && (
          <Card className="p-4">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-gray-500">Case Reference</span>
              <Hash className="h-5 w-5 text-green-500" />
            </div>
            <p className="text-lg font-bold text-gray-900 mt-2 truncate">
              {project.case_ref}
            </p>
          </Card>
        )}

        <Card className="p-4">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-gray-500">Created</span>
            <Calendar className="h-5 w-5 text-purple-500" />
          </div>
          <p className="text-lg font-bold text-gray-900 mt-2">
            {format(new Date(project.created_at), 'MMM d, yyyy')}
          </p>
          <p className="text-xs text-gray-400 mt-1">
            {format(new Date(project.created_at), 'h:mm a')}
          </p>
        </Card>
      </div>

      {/* Documents List */}
      <Card className="p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          Project Documents
        </h2>

        {docsLoading ? (
          <div className="flex items-center justify-center py-8">
            <RefreshCw className="h-6 w-6 animate-spin text-gray-400" />
          </div>
        ) : !documents || documents.length === 0 ? (
          <div className="text-center py-8 text-gray-500">
            <FileText className="h-12 w-12 mx-auto text-gray-300 mb-3" />
            <p>No documents attached to this project</p>
            <p className="text-sm mt-1">
              Attach documents from the Documents page
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {documents.map((pd: ProjectDocument) => {
              const doc = pd.document;
              if (!doc) return null;

              const version = doc.latest_version;
              const status = version?.extraction_status;

              return (
                <Link
                  key={pd.id}
                  to={`/documents/${doc.id}`}
                  className="block border rounded-lg p-4 hover:bg-gray-50 transition-colors"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3 min-w-0">
                      <FileText className="h-5 w-5 text-gray-400 flex-shrink-0" />
                      <div className="min-w-0">
                        <p className="font-medium text-gray-900 truncate">
                          {doc.original_filename}
                        </p>
                        <div className="flex items-center gap-3 mt-1 text-xs text-gray-500">
                          <span>{doc.content_type}</span>
                          {version && (
                            <span>{formatFileSize(version.file_size)}</span>
                          )}
                          <span>
                            Attached {format(new Date(pd.attached_at), 'MMM d, yyyy')}
                          </span>
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0 ml-4">
                      {getStatusIcon(status)}
                      <span className={`text-sm ${
                        status === 'completed' ? 'text-green-600' :
                        status === 'failed' ? 'text-red-600' :
                        status === 'processing' ? 'text-yellow-600' :
                        'text-gray-500'
                      }`}>
                        {getStatusLabel(status)}
                      </span>
                    </div>
                  </div>
                  {pd.notes && (
                    <p className="mt-2 text-sm text-gray-600 pl-8">
                      {pd.notes}
                    </p>
                  )}
                </Link>
              );
            })}
          </div>
        )}
      </Card>
    </div>
  );
}
