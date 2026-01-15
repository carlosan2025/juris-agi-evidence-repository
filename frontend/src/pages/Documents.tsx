import { useState, useCallback, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  FileText,
  Trash2,
  Download,
  RefreshCw,
  FolderOpen,
  Loader2,
  File,
  FileImage,
  FileSpreadsheet,
  CheckCircle2,
  AlertCircle,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { format } from 'date-fns';
import { Button, Modal } from '../components/ui';
import { documentsApi, projectsApi } from '../api';
import type { Document, ProfileCode, Project } from '../types';
import { PROFILE_OPTIONS } from '../types';

// Max file size - presigned uploads bypass Vercel's limit for larger files
const MAX_FILE_SIZE_MB = 100;
const MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024;

// Processing step labels for inline status display
const PROCESSING_STEP_LABELS: Record<string, string> = {
  pending: 'Queued',
  uploaded: 'Uploading',
  extracted: 'Extracting text',
  spans_built: 'Building sections',
  embedded: 'Creating embeddings',
  facts_extracted: 'Extracting metadata',
  quality_checked: 'Complete',
  failed: 'Failed',
};

// Deletion status labels
const DELETION_STATUS_LABELS: Record<string, string> = {
  marked: 'Deleting...',
  deleting: 'Deleting...',
  failed: 'Deletion Failed',
  deleted: 'Deleted',
};

// File type icons based on content type
function getFileIcon(contentType: string, className: string = 'h-5 w-5') {
  if (contentType.includes('pdf')) {
    return <FileText className={`${className} text-red-500`} />;
  }
  if (contentType.includes('image')) {
    return <FileImage className={`${className} text-blue-500`} />;
  }
  if (contentType.includes('spreadsheet') || contentType.includes('excel') || contentType.includes('csv')) {
    return <FileSpreadsheet className={`${className} text-green-500`} />;
  }
  if (contentType.includes('text') || contentType.includes('markdown')) {
    return <FileText className={`${className} text-gray-500`} />;
  }
  return <File className={`${className} text-gray-400`} />;
}

export function Documents() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [dragActive, setDragActive] = useState(false);
  const [selectedProfile, setSelectedProfile] = useState<ProfileCode>('general');
  const [profileModalOpen, setProfileModalOpen] = useState(false);
  const [filesToUpload, setFilesToUpload] = useState<File[]>([]);
  const [projectModalOpen, setProjectModalOpen] = useState(false);
  const [projectModalDoc, setProjectModalDoc] = useState<Document | null>(null);

  // Track document project counts
  const [documentProjectCounts, setDocumentProjectCounts] = useState<Record<string, number>>({});

  const { data, isLoading } = useQuery({
    queryKey: ['documents', { page, page_size: 50 }],
    queryFn: () => documentsApi.list({ page, page_size: 50 }),
    // Poll every 2 seconds if any document is still processing or being deleted
    refetchInterval: (query) => {
      const docs = query.state.data?.items || [];
      const hasProcessing = docs.some((doc) => {
        const deletionStatus = (doc as any).deletion_status;
        return (
          doc.latest_version?.upload_status === 'pending' ||
          doc.latest_version?.extraction_status === 'pending' ||
          doc.latest_version?.extraction_status === 'processing' ||
          deletionStatus === 'marked' ||
          deletionStatus === 'deleting'
        );
      });
      return hasProcessing ? 2000 : false;
    },
  });

  // Fetch all projects to count document associations
  const { data: projectsData } = useQuery({
    queryKey: ['projects', { page: 1, page_size: 100 }],
    queryFn: () => projectsApi.list({ page: 1, page_size: 100 }),
  });

  // Count projects per document
  useEffect(() => {
    async function countProjects() {
      if (!data?.items || !projectsData?.items) return;

      const counts: Record<string, number> = {};
      for (const doc of data.items) {
        counts[doc.id] = 0;
      }

      for (const project of projectsData.items) {
        try {
          const projectDocs = await projectsApi.getDocuments(project.id);
          for (const pd of projectDocs || []) {
            if (counts[pd.document_id] !== undefined) {
              counts[pd.document_id]++;
            }
          }
        } catch {
          // Ignore errors
        }
      }

      setDocumentProjectCounts(counts);
    }

    countProjects();
  }, [data?.items, projectsData?.items]);

  // Fetch projects for project modal
  const { data: documentProjects, refetch: refetchDocumentProjects } = useQuery({
    queryKey: ['document-projects', projectModalDoc?.id],
    queryFn: async () => {
      if (!projectModalDoc) return [];
      const projectIds: string[] = [];
      for (const project of projectsData?.items || []) {
        try {
          const projectDocs = await projectsApi.getDocuments(project.id);
          if (projectDocs?.some((pd) => pd.document_id === projectModalDoc.id)) {
            projectIds.push(project.id);
          }
        } catch {
          // Ignore
        }
      }
      return projectIds;
    },
    enabled: !!projectModalDoc && !!projectsData?.items,
  });

  const uploadMutation = useMutation({
    mutationFn: ({ file, profileCode }: { file: File; profileCode: ProfileCode }) =>
      documentsApi.upload(file, profileCode, undefined, () => {
        queryClient.invalidateQueries({ queryKey: ['documents'] });
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents'] });
    },
    onError: (error) => {
      console.error('Upload failed:', error);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => documentsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents'] });
    },
  });

  const retryMutation = useMutation({
    mutationFn: (id: string) => documentsApi.retry(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents'] });
    },
  });

  const retryDeletionMutation = useMutation({
    mutationFn: (id: string) => documentsApi.retryDeletion(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents'] });
    },
  });

  const attachToProjectMutation = useMutation({
    mutationFn: ({ projectId, documentId }: { projectId: string; documentId: string }) =>
      projectsApi.attachDocument(projectId, documentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] });
      refetchDocumentProjects();
    },
  });

  const detachFromProjectMutation = useMutation({
    mutationFn: ({ projectId, documentId }: { projectId: string; documentId: string }) =>
      projectsApi.detachDocument(projectId, documentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] });
      refetchDocumentProjects();
    },
  });

  // Handle drag events for entire page
  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      // Only set inactive if leaving the window
      const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
      if (
        e.clientX <= rect.left ||
        e.clientX >= rect.right ||
        e.clientY <= rect.top ||
        e.clientY >= rect.bottom
      ) {
        setDragActive(false);
      }
    }
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    const files = Array.from(e.dataTransfer.files).filter(
      (file) => file.size <= MAX_FILE_SIZE_BYTES
    );

    if (files.length > 0) {
      setFilesToUpload(files);
      setProfileModalOpen(true);
    }
  }, []);

  const handleUploadFiles = () => {
    // Start uploading all files
    for (const file of filesToUpload) {
      uploadMutation.mutate({ file, profileCode: selectedProfile });
    }
    setProfileModalOpen(false);
    setFilesToUpload([]);
    setSelectedProfile('general');
  };

  const handleDownload = async (doc: Document, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      const blob = await documentsApi.download(doc.id);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = doc.original_filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (error) {
      console.error('Download failed:', error);
    }
  };

  const handleToggleProject = (projectId: string) => {
    if (!projectModalDoc) return;
    const isAttached = documentProjects?.includes(projectId);
    if (isAttached) {
      detachFromProjectMutation.mutate({ projectId, documentId: projectModalDoc.id });
    } else {
      attachToProjectMutation.mutate({ projectId, documentId: projectModalDoc.id });
    }
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  // Get status display for a document
  const getStatusDisplay = (doc: Document) => {
    // Check deletion status first
    const deletionStatus = (doc as any).deletion_status;
    if (deletionStatus && deletionStatus !== 'active') {
      if (deletionStatus === 'marked' || deletionStatus === 'deleting') {
        return (
          <span className="flex items-center gap-1.5 text-orange-600 text-xs">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            <span>{DELETION_STATUS_LABELS[deletionStatus]}</span>
          </span>
        );
      }
      if (deletionStatus === 'failed') {
        return (
          <span className="flex items-center gap-1.5 text-red-600 text-xs">
            <AlertCircle className="h-3.5 w-3.5" />
            <span>Deletion Failed</span>
          </span>
        );
      }
    }

    const version = doc.latest_version;
    if (!version) return null;

    const uploadStatus = version.upload_status;
    const extractionStatus = version.extraction_status;
    const processingStatus = version.processing_status;

    // Upload pending
    if (uploadStatus === 'pending') {
      return (
        <span className="flex items-center gap-1.5 text-amber-600 text-xs">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          <span>Uploading</span>
        </span>
      );
    }

    // Upload failed
    if (uploadStatus === 'failed') {
      return (
        <span className="flex items-center gap-1.5 text-red-600 text-xs">
          <AlertCircle className="h-3.5 w-3.5" />
          <span>Upload Failed</span>
        </span>
      );
    }

    // Failed (check processing_status too, as extraction_status may not be updated yet)
    if (extractionStatus === 'failed' || processingStatus === 'failed') {
      return (
        <span className="flex items-center gap-1.5 text-red-600 text-xs">
          <AlertCircle className="h-3.5 w-3.5" />
          <span>Failed</span>
        </span>
      );
    }

    // Processing
    if (extractionStatus === 'pending' || extractionStatus === 'processing') {
      const stepLabel = PROCESSING_STEP_LABELS[processingStatus || 'pending'] || 'Processing';
      return (
        <span className="flex items-center gap-1.5 text-blue-600 text-xs">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          <span>{stepLabel}</span>
        </span>
      );
    }

    // Complete
    if (extractionStatus === 'completed') {
      return (
        <span className="flex items-center gap-1.5 text-green-600 text-xs">
          <CheckCircle2 className="h-3.5 w-3.5" />
        </span>
      );
    }

    return null;
  };

  // Check if document needs retry button (processing or deletion failure)
  const needsRetry = (doc: Document) => {
    const version = doc.latest_version;
    const deletionStatus = (doc as any).deletion_status;
    return (
      version?.extraction_status === 'failed' ||
      version?.upload_status === 'failed' ||
      version?.processing_status === 'failed' ||
      deletionStatus === 'failed'
    );
  };

  // Check if it's a deletion failure specifically
  const isDeletionFailed = (doc: Document) => {
    return (doc as any).deletion_status === 'failed';
  };

  return (
    <div
      className="min-h-[calc(100vh-8rem)] relative"
      onDragEnter={handleDrag}
      onDragLeave={handleDrag}
      onDragOver={handleDrag}
      onDrop={handleDrop}
    >
      {/* Drop overlay */}
      {dragActive && (
        <div className="absolute inset-0 z-50 bg-blue-50/90 border-2 border-dashed border-blue-400 rounded-lg flex items-center justify-center pointer-events-none">
          <div className="text-center">
            <FileText className="h-16 w-16 text-blue-500 mx-auto mb-4" />
            <p className="text-xl font-medium text-blue-700">Drop files to upload</p>
            <p className="text-sm text-blue-500 mt-1">Multiple files supported</p>
          </div>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold text-gray-900">Documents</h1>
        <span className="text-sm text-gray-500">
          {data?.total || 0} files • Drag files anywhere to upload
        </span>
      </div>

      {/* File browser */}
      <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
        {/* Column headers */}
        <div className="grid grid-cols-12 gap-4 px-4 py-2 bg-gray-50 border-b border-gray-200 text-xs font-medium text-gray-500 uppercase tracking-wide">
          <div className="col-span-5">Name</div>
          <div className="col-span-2 text-right">Size</div>
          <div className="col-span-2">Date Added</div>
          <div className="col-span-1 text-center">Projects</div>
          <div className="col-span-2 text-right">Actions</div>
        </div>

        {/* File list */}
        <div className="divide-y divide-gray-100">
          {isLoading ? (
            <div className="px-4 py-12 text-center text-gray-500">
              <Loader2 className="h-6 w-6 animate-spin mx-auto mb-2" />
              Loading documents...
            </div>
          ) : data?.items.length === 0 ? (
            <div className="px-4 py-16 text-center">
              <FileText className="h-12 w-12 text-gray-300 mx-auto mb-4" />
              <p className="text-gray-500 mb-2">No documents yet</p>
              <p className="text-sm text-gray-400">Drag and drop files anywhere to upload</p>
            </div>
          ) : (
            data?.items.map((doc) => (
              <div
                key={doc.id}
                className="grid grid-cols-12 gap-4 px-4 py-3 hover:bg-gray-50 cursor-pointer transition-colors items-center group"
                onClick={() => navigate(`/documents/${doc.id}`)}
              >
                {/* Name + Status */}
                <div className="col-span-5 flex items-center gap-3 min-w-0">
                  {getFileIcon(doc.content_type)}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-gray-900 truncate">
                        {doc.original_filename}
                      </span>
                      {getStatusDisplay(doc)}
                    </div>
                  </div>
                </div>

                {/* Size */}
                <div className="col-span-2 text-right text-sm text-gray-500">
                  {doc.latest_version ? formatFileSize(doc.latest_version.file_size) : '-'}
                </div>

                {/* Date */}
                <div className="col-span-2 text-sm text-gray-500">
                  {format(new Date(doc.created_at), 'MMM d, yyyy')}
                </div>

                {/* Projects count */}
                <div className="col-span-1 text-center">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setProjectModalDoc(doc);
                      setProjectModalOpen(true);
                    }}
                    className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-purple-600 transition-colors"
                  >
                    <FolderOpen className="h-4 w-4" />
                    <span>{documentProjectCounts[doc.id] || 0}</span>
                  </button>
                </div>

                {/* Actions */}
                <div className="col-span-2 flex items-center justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  {needsRetry(doc) && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        if (isDeletionFailed(doc)) {
                          retryDeletionMutation.mutate(doc.id);
                        } else {
                          retryMutation.mutate(doc.id);
                        }
                      }}
                      disabled={retryMutation.isPending || retryDeletionMutation.isPending}
                      className="p-1.5 text-gray-400 hover:text-blue-600 hover:bg-blue-50 rounded transition-colors"
                      title={isDeletionFailed(doc) ? 'Retry deletion' : 'Retry processing'}
                    >
                      <RefreshCw className={`h-4 w-4 ${retryMutation.isPending || retryDeletionMutation.isPending ? 'animate-spin' : ''}`} />
                    </button>
                  )}
                  <button
                    onClick={(e) => handleDownload(doc, e)}
                    className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded transition-colors"
                    title="Download"
                  >
                    <Download className="h-4 w-4" />
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      if (confirm('Delete this document?')) {
                        deleteMutation.mutate(doc.id);
                      }
                    }}
                    className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded transition-colors"
                    title="Delete"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Pagination */}
        {data && data.pages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-gray-200 bg-gray-50">
            <span className="text-sm text-gray-500">
              Page {page} of {data.pages}
            </span>
            <div className="flex gap-1">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <button
                onClick={() => setPage((p) => Math.min(data.pages, p + 1))}
                disabled={page === data.pages}
                className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Profile Selection Modal (for uploads) */}
      <Modal
        isOpen={profileModalOpen}
        onClose={() => {
          setProfileModalOpen(false);
          setFilesToUpload([]);
        }}
        title={`Upload ${filesToUpload.length} file${filesToUpload.length !== 1 ? 's' : ''}`}
      >
        <div className="space-y-4">
          <div>
            <p className="text-sm text-gray-600 mb-3">
              Select an industry profile for better metadata extraction:
            </p>
            <div className="grid grid-cols-2 gap-2">
              {PROFILE_OPTIONS.map((profile) => (
                <button
                  key={profile.value}
                  type="button"
                  onClick={() => setSelectedProfile(profile.value)}
                  className={`p-3 rounded-lg border-2 text-left transition-all ${
                    selectedProfile === profile.value
                      ? 'border-blue-500 bg-blue-50'
                      : 'border-gray-200 hover:border-gray-300'
                  }`}
                >
                  <div className="font-medium text-gray-900 text-sm">{profile.label}</div>
                  <div className="text-xs text-gray-500 mt-0.5">{profile.description}</div>
                </button>
              ))}
            </div>
          </div>

          {/* File list preview */}
          <div className="border border-gray-200 rounded-lg divide-y divide-gray-100 max-h-40 overflow-y-auto">
            {filesToUpload.map((file, i) => (
              <div key={i} className="flex items-center gap-2 px-3 py-2 text-sm">
                {getFileIcon(file.type, 'h-4 w-4')}
                <span className="truncate flex-1">{file.name}</span>
                <span className="text-gray-400 text-xs">{formatFileSize(file.size)}</span>
              </div>
            ))}
          </div>

          <div className="flex justify-end gap-2">
            <Button
              variant="secondary"
              onClick={() => {
                setProfileModalOpen(false);
                setFilesToUpload([]);
              }}
            >
              Cancel
            </Button>
            <Button onClick={handleUploadFiles}>
              Upload {filesToUpload.length} file{filesToUpload.length !== 1 ? 's' : ''}
            </Button>
          </div>
        </div>
      </Modal>

      {/* Project Assignment Modal */}
      <Modal
        isOpen={projectModalOpen}
        onClose={() => {
          setProjectModalOpen(false);
          setProjectModalDoc(null);
        }}
        title="Assign to Projects"
      >
        {projectModalDoc && (
          <div className="space-y-4">
            <div className="flex items-center gap-2 pb-3 border-b border-gray-200">
              {getFileIcon(projectModalDoc.content_type)}
              <span className="font-medium text-gray-900 truncate">
                {projectModalDoc.original_filename}
              </span>
            </div>

            {!projectsData?.items?.length ? (
              <div className="py-8 text-center">
                <FolderOpen className="h-10 w-10 text-gray-300 mx-auto mb-3" />
                <p className="text-gray-500 text-sm">No projects available</p>
              </div>
            ) : (
              <div className="space-y-1 max-h-64 overflow-y-auto">
                {projectsData.items.map((project: Project) => {
                  const isAttached = documentProjects?.includes(project.id);
                  const isPending =
                    (attachToProjectMutation.isPending &&
                      attachToProjectMutation.variables?.projectId === project.id) ||
                    (detachFromProjectMutation.isPending &&
                      detachFromProjectMutation.variables?.projectId === project.id);

                  return (
                    <button
                      key={project.id}
                      type="button"
                      onClick={() => handleToggleProject(project.id)}
                      disabled={isPending}
                      className={`w-full flex items-center justify-between p-2.5 rounded-lg border text-left transition-all ${
                        isAttached
                          ? 'border-purple-400 bg-purple-50'
                          : 'border-gray-200 hover:border-gray-300'
                      } ${isPending ? 'opacity-50' : ''}`}
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <FolderOpen
                          className={`h-4 w-4 flex-shrink-0 ${
                            isAttached ? 'text-purple-500' : 'text-gray-400'
                          }`}
                        />
                        <span className="font-medium text-sm text-gray-900 truncate">
                          {project.name}
                        </span>
                      </div>
                      {isAttached && (
                        <CheckCircle2 className="h-4 w-4 text-purple-500 flex-shrink-0" />
                      )}
                    </button>
                  );
                })}
              </div>
            )}

            <div className="flex justify-end pt-3 border-t border-gray-200">
              <Button
                variant="secondary"
                onClick={() => {
                  setProjectModalOpen(false);
                  setProjectModalDoc(null);
                }}
              >
                Done
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
