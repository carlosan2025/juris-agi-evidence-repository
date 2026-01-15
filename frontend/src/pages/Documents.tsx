import { useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Upload, FileText, Trash2, Download, RefreshCw, Eye, FolderPlus } from 'lucide-react';
import { format } from 'date-fns';
import {
  Card,
  Button,
  Badge,
  Modal,
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '../components/ui';
import { documentsApi, projectsApi } from '../api';
import type { Document, ProfileCode, Project } from '../types';
import { PROFILE_OPTIONS } from '../types';

export function Documents() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [uploadModalOpen, setUploadModalOpen] = useState(false);
  const [selectedDoc, setSelectedDoc] = useState<Document | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [selectedProfile, setSelectedProfile] = useState<ProfileCode>('vc');
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [projectModalOpen, setProjectModalOpen] = useState(false);
  const [projectModalDoc, setProjectModalDoc] = useState<Document | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['documents', { page, page_size: 20 }],
    queryFn: () => documentsApi.list({ page, page_size: 20 }),
  });

  // Fetch all projects for the project association modal
  const { data: projectsData } = useQuery({
    queryKey: ['projects', { page: 1, page_size: 100 }],
    queryFn: () => projectsApi.list({ page: 1, page_size: 100 }),
  });

  // Fetch projects for a specific document when the modal is open
  const { data: documentProjects, refetch: refetchDocumentProjects } = useQuery({
    queryKey: ['document-projects', projectModalDoc?.id],
    queryFn: async () => {
      if (!projectModalDoc) return [];
      // We need to check each project's documents - the API returns ProjectDocument[]
      // We'll track which projects this document belongs to
      const projectIds: string[] = [];
      for (const project of projectsData?.items || []) {
        try {
          const projectDocs = await projectsApi.getDocuments(project.id);
          // Backend returns array of ProjectDocument, check document_id field
          if (projectDocs?.some((pd) => pd.document_id === projectModalDoc.id)) {
            projectIds.push(project.id);
          }
        } catch {
          // Project may not have any documents
        }
      }
      return projectIds;
    },
    enabled: !!projectModalDoc && !!projectsData?.items,
  });

  const uploadMutation = useMutation({
    mutationFn: ({ file, profileCode }: { file: File; profileCode: ProfileCode }) =>
      documentsApi.upload(file, profileCode),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents'] });
      setUploadModalOpen(false);
      setPendingFile(null);
      setSelectedProfile('vc');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => documentsApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents'] });
    },
  });

  const extractMutation = useMutation({
    mutationFn: (id: string) => documentsApi.triggerExtraction(id),
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

  const handleDrag = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setPendingFile(e.dataTransfer.files[0]);
    }
  }, []);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setPendingFile(e.target.files[0]);
    }
  };

  const handleUpload = () => {
    if (pendingFile) {
      uploadMutation.mutate({ file: pendingFile, profileCode: selectedProfile });
    }
  };

  const handleCloseUploadModal = () => {
    setUploadModalOpen(false);
    setPendingFile(null);
    setSelectedProfile('vc');
  };

  const handleOpenProjectModal = (doc: Document) => {
    setProjectModalDoc(doc);
    setProjectModalOpen(true);
  };

  const handleCloseProjectModal = () => {
    setProjectModalOpen(false);
    setProjectModalDoc(null);
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

  const handleDownload = async (doc: Document) => {
    try {
      const blob = await documentsApi.download(doc.id);
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = doc.filename;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (error) {
      console.error('Download failed:', error);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'completed':
        return <Badge variant="success">Completed</Badge>;
      case 'processing':
        return <Badge variant="info">Processing</Badge>;
      case 'failed':
        return <Badge variant="danger">Failed</Badge>;
      default:
        return <Badge variant="default">Pending</Badge>;
    }
  };

  const getProfileBadge = (profileCode: string) => {
    const profile = PROFILE_OPTIONS.find((p) => p.value === profileCode);
    const colors: Record<string, string> = {
      vc: 'bg-purple-100 text-purple-800',
      pharma: 'bg-green-100 text-green-800',
      insurance: 'bg-blue-100 text-blue-800',
      general: 'bg-gray-100 text-gray-800',
    };
    return (
      <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${colors[profileCode] || colors.general}`}>
        {profile?.label || profileCode}
      </span>
    );
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Documents</h1>
        <Button onClick={() => setUploadModalOpen(true)}>
          <Upload className="h-4 w-4" />
          Upload Document
        </Button>
      </div>

      <Card padding="none">
        {isLoading ? (
          <div className="p-8 text-center text-gray-500">Loading documents...</div>
        ) : data?.items.length === 0 ? (
          <div className="p-8 text-center">
            <FileText className="h-12 w-12 text-gray-300 mx-auto mb-4" />
            <p className="text-gray-500">No documents uploaded yet</p>
            <Button
              variant="secondary"
              className="mt-4"
              onClick={() => setUploadModalOpen(true)}
            >
              Upload your first document
            </Button>
          </div>
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Industry</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Size</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data?.items.map((doc) => (
                  <TableRow key={doc.id}>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <FileText className="h-4 w-4 text-gray-400" />
                        <span className="font-medium">{doc.filename}</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      {getProfileBadge(doc.profile_code || 'general')}
                    </TableCell>
                    <TableCell>
                      <span className="text-gray-500">{doc.content_type}</span>
                    </TableCell>
                    <TableCell>{doc.latest_version ? formatFileSize(doc.latest_version.file_size) : '-'}</TableCell>
                    <TableCell>{getStatusBadge(doc.latest_version?.extraction_status || 'pending')}</TableCell>
                    <TableCell>
                      {format(new Date(doc.created_at), 'MMM d, yyyy')}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setSelectedDoc(doc)}
                          title="View details"
                        >
                          <Eye className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleOpenProjectModal(doc)}
                          title="Manage projects"
                        >
                          <FolderPlus className="h-4 w-4 text-purple-500" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleDownload(doc)}
                          title="Download"
                        >
                          <Download className="h-4 w-4" />
                        </Button>
                        {doc.latest_version?.extraction_status !== 'completed' && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => extractMutation.mutate(doc.id)}
                            disabled={extractMutation.isPending}
                            title="Re-extract"
                          >
                            <RefreshCw className="h-4 w-4" />
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            if (confirm('Are you sure you want to delete this document?')) {
                              deleteMutation.mutate(doc.id);
                            }
                          }}
                          title="Delete"
                        >
                          <Trash2 className="h-4 w-4 text-red-500" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>

            {/* Pagination */}
            {data && data.pages > 1 && (
              <div className="flex items-center justify-between px-6 py-4 border-t border-gray-200">
                <span className="text-sm text-gray-500">
                  Page {page} of {data.pages} ({data.total} documents)
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

      {/* Upload Modal */}
      <Modal
        isOpen={uploadModalOpen}
        onClose={handleCloseUploadModal}
        title="Upload Document"
      >
        <div className="space-y-6">
          {/* Industry Profile Selection */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-3">
              Select Industry Profile
            </label>
            <div className="grid grid-cols-2 gap-3">
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
                  <div className="font-medium text-gray-900">{profile.label}</div>
                  <div className="text-xs text-gray-500 mt-1">{profile.description}</div>
                </button>
              ))}
            </div>
          </div>

          {/* File Drop Zone */}
          <div
            className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
              dragActive ? 'border-blue-500 bg-blue-50' : 'border-gray-300'
            } ${pendingFile ? 'bg-green-50 border-green-300' : ''}`}
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
          >
            {pendingFile ? (
              <div>
                <FileText className="h-12 w-12 text-green-500 mx-auto mb-4" />
                <p className="text-gray-900 font-medium">{pendingFile.name}</p>
                <p className="text-sm text-gray-500">{formatFileSize(pendingFile.size)}</p>
                <button
                  type="button"
                  onClick={() => setPendingFile(null)}
                  className="mt-2 text-sm text-red-600 hover:text-red-700"
                >
                  Remove
                </button>
              </div>
            ) : (
              <>
                <Upload className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                <p className="text-gray-600 mb-2">
                  Drag and drop a file here, or click to select
                </p>
                <input
                  type="file"
                  className="hidden"
                  id="file-upload"
                  onChange={handleFileSelect}
                  accept=".pdf,.txt,.md,.csv,.xlsx,.png,.jpg,.jpeg,.webp"
                />
                <label htmlFor="file-upload">
                  <span className="inline-flex items-center justify-center font-medium rounded-lg transition-colors px-4 py-2 text-sm gap-2 bg-gray-100 text-gray-900 hover:bg-gray-200 cursor-pointer">
                    Select File
                  </span>
                </label>
                <p className="text-xs text-gray-400 mt-4">
                  Supported: PDF, TXT, MD, CSV, XLSX, PNG, JPG, WEBP
                </p>
              </>
            )}
          </div>

          {/* Upload Button */}
          <div className="flex justify-end gap-3">
            <Button variant="secondary" onClick={handleCloseUploadModal}>
              Cancel
            </Button>
            <Button
              onClick={handleUpload}
              disabled={!pendingFile || uploadMutation.isPending}
            >
              {uploadMutation.isPending ? 'Uploading...' : `Upload as ${PROFILE_OPTIONS.find(p => p.value === selectedProfile)?.label}`}
            </Button>
          </div>
        </div>
      </Modal>

      {/* Document Details Modal */}
      <Modal
        isOpen={!!selectedDoc}
        onClose={() => setSelectedDoc(null)}
        title="Document Details"
        size="lg"
      >
        {selectedDoc && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="text-sm font-medium text-gray-500">Filename</label>
                <p className="text-gray-900">{selectedDoc.filename}</p>
              </div>
              <div>
                <label className="text-sm font-medium text-gray-500">Industry Profile</label>
                <p className="mt-1">{getProfileBadge(selectedDoc.profile_code || 'general')}</p>
              </div>
              <div>
                <label className="text-sm font-medium text-gray-500">Content Type</label>
                <p className="text-gray-900">{selectedDoc.content_type}</p>
              </div>
              <div>
                <label className="text-sm font-medium text-gray-500">Size</label>
                <p className="text-gray-900">{selectedDoc.latest_version ? formatFileSize(selectedDoc.latest_version.file_size) : '-'}</p>
              </div>
              <div>
                <label className="text-sm font-medium text-gray-500">Status</label>
                <p>{getStatusBadge(selectedDoc.latest_version?.extraction_status || 'pending')}</p>
              </div>
              <div>
                <label className="text-sm font-medium text-gray-500">Created</label>
                <p className="text-gray-900">
                  {format(new Date(selectedDoc.created_at), 'PPpp')}
                </p>
              </div>
              <div className="col-span-2">
                <label className="text-sm font-medium text-gray-500">Hash</label>
                <p className="text-gray-900 font-mono text-sm truncate">
                  {selectedDoc.file_hash}
                </p>
              </div>
            </div>
            {selectedDoc.metadata && Object.keys(selectedDoc.metadata).length > 0 && (
              <div>
                <label className="text-sm font-medium text-gray-500">Metadata</label>
                <pre className="mt-1 p-3 bg-gray-50 rounded-lg text-sm overflow-auto">
                  {JSON.stringify(selectedDoc.metadata, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}
      </Modal>

      {/* Project Assignment Modal */}
      <Modal
        isOpen={projectModalOpen}
        onClose={handleCloseProjectModal}
        title="Assign to Projects"
      >
        {projectModalDoc && (
          <div className="space-y-4">
            <div className="flex items-center gap-2 pb-4 border-b border-gray-200">
              <FileText className="h-5 w-5 text-gray-400" />
              <span className="font-medium text-gray-900">{projectModalDoc.filename}</span>
            </div>

            {!projectsData?.items?.length ? (
              <div className="py-8 text-center">
                <FolderPlus className="h-12 w-12 text-gray-300 mx-auto mb-4" />
                <p className="text-gray-500">No projects available</p>
                <p className="text-sm text-gray-400 mt-1">Create a project first to assign documents</p>
              </div>
            ) : (
              <div className="space-y-2 max-h-96 overflow-y-auto">
                <p className="text-sm text-gray-500 mb-3">
                  Select projects to associate with this document:
                </p>
                {projectsData.items.map((project: Project) => {
                  const isAttached = documentProjects?.includes(project.id);
                  const isPending =
                    (attachToProjectMutation.isPending && attachToProjectMutation.variables?.projectId === project.id) ||
                    (detachFromProjectMutation.isPending && detachFromProjectMutation.variables?.projectId === project.id);

                  return (
                    <button
                      key={project.id}
                      type="button"
                      onClick={() => handleToggleProject(project.id)}
                      disabled={isPending}
                      className={`w-full flex items-center justify-between p-3 rounded-lg border-2 text-left transition-all ${
                        isAttached
                          ? 'border-purple-500 bg-purple-50'
                          : 'border-gray-200 hover:border-gray-300'
                      } ${isPending ? 'opacity-50 cursor-wait' : ''}`}
                    >
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-gray-900">{project.name}</div>
                        {project.description && (
                          <div className="text-xs text-gray-500 truncate mt-0.5">
                            {project.description}
                          </div>
                        )}
                        {project.case_ref && (
                          <div className="text-xs text-gray-400 mt-0.5">
                            Ref: {project.case_ref}
                          </div>
                        )}
                      </div>
                      {isAttached && (
                        <div className="ml-3 flex-shrink-0">
                          <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-purple-100 text-purple-800">
                            Assigned
                          </span>
                        </div>
                      )}
                    </button>
                  );
                })}
              </div>
            )}

            <div className="flex justify-end pt-4 border-t border-gray-200">
              <Button variant="secondary" onClick={handleCloseProjectModal}>
                Done
              </Button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
