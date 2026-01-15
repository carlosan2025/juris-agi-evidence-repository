import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { format } from 'date-fns';
import {
  ArrowLeft,
  FileText,
  Download,
  RefreshCw,
  Hash,
  Layers,
  Box,
  CheckCircle,
  XCircle,
  AlertCircle,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { documentsApi } from '../api/documents';
import type { SpanItem } from '../api/documents';
import { Card } from '../components/ui';

export function DocumentDetail() {
  const { documentId } = useParams<{ documentId: string }>();
  const navigate = useNavigate();
  const [showAllSpans, setShowAllSpans] = useState(false);
  const [expandedSpan, setExpandedSpan] = useState<string | null>(null);

  // Fetch document details
  const { data: document, isLoading: docLoading, error: docError } = useQuery({
    queryKey: ['document', documentId],
    queryFn: () => documentsApi.get(documentId!),
    enabled: !!documentId,
  });

  // Fetch document stats
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['document-stats', documentId],
    queryFn: () => documentsApi.getStats(documentId!),
    enabled: !!documentId,
  });

  // Fetch spans
  const { data: spansData, isLoading: spansLoading } = useQuery({
    queryKey: ['document-spans', documentId, showAllSpans],
    queryFn: () => documentsApi.getSpans(documentId!, { limit: showAllSpans ? 500 : 10 }),
    enabled: !!documentId,
  });

  const handleDownload = async () => {
    if (!documentId) return;
    try {
      const blob = await documentsApi.download(documentId);
      const url = window.URL.createObjectURL(blob);
      const a = window.document.createElement('a');
      a.href = url;
      a.download = document?.original_filename || 'document';
      window.document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      window.document.body.removeChild(a);
    } catch (error) {
      console.error('Download failed:', error);
    }
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const getStatusIcon = (status: string | null) => {
    switch (status) {
      case 'completed':
        return <CheckCircle className="h-5 w-5 text-green-500" />;
      case 'failed':
        return <XCircle className="h-5 w-5 text-red-500" />;
      case 'processing':
        return <RefreshCw className="h-5 w-5 text-yellow-500 animate-spin" />;
      default:
        return <AlertCircle className="h-5 w-5 text-gray-400" />;
    }
  };

  const getStatusLabel = (status: string | null) => {
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

  if (docLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <RefreshCw className="h-8 w-8 animate-spin text-gray-400" />
      </div>
    );
  }

  if (docError || !document) {
    return (
      <div className="text-center py-12">
        <XCircle className="h-12 w-12 mx-auto text-red-400 mb-4" />
        <h2 className="text-lg font-medium text-gray-900">Document Not Found</h2>
        <p className="text-gray-500 mt-1">The document you're looking for doesn't exist or was deleted.</p>
        <button
          onClick={() => navigate('/documents')}
          className="mt-4 text-blue-600 hover:text-blue-800"
        >
          Back to Documents
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
            onClick={() => navigate('/documents')}
            className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
          >
            <ArrowLeft className="h-5 w-5 text-gray-600" />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
              <FileText className="h-6 w-6 text-gray-400" />
              {document.original_filename}
            </h1>
            <p className="text-sm text-gray-500 mt-1">
              Uploaded {format(new Date(document.created_at), 'MMMM d, yyyy \'at\' h:mm a')}
            </p>
          </div>
        </div>
        <button
          onClick={handleDownload}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
        >
          <Download className="h-4 w-4" />
          Download Original
        </button>
      </div>

      {/* Status and Stats Overview */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {/* Processing Status */}
        <Card className="p-4">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-gray-500">Status</span>
            {getStatusIcon(stats?.extraction_status ?? document.latest_version?.extraction_status ?? null)}
          </div>
          <p className="text-2xl font-bold text-gray-900 mt-2">
            {getStatusLabel(stats?.extraction_status ?? document.latest_version?.extraction_status ?? null)}
          </p>
          {stats?.extracted_at && (
            <p className="text-xs text-gray-400 mt-1">
              {format(new Date(stats.extracted_at), 'MMM d, h:mm a')}
            </p>
          )}
        </Card>

        {/* Spans Count */}
        <Card className="p-4">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-gray-500">Spans</span>
            <Layers className="h-5 w-5 text-purple-500" />
          </div>
          <p className="text-2xl font-bold text-gray-900 mt-2">
            {statsLoading ? '...' : stats?.spans.total || 0}
          </p>
          <p className="text-xs text-gray-400 mt-1">text chunks extracted</p>
        </Card>

        {/* Embeddings Count */}
        <Card className="p-4">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-gray-500">Embeddings</span>
            <Box className="h-5 w-5 text-blue-500" />
          </div>
          <p className="text-2xl font-bold text-gray-900 mt-2">
            {statsLoading ? '...' : stats?.embeddings.total || 0}
          </p>
          <p className="text-xs text-gray-400 mt-1">vector embeddings</p>
        </Card>

        {/* Text Length */}
        <Card className="p-4">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-gray-500">Content</span>
            <Hash className="h-5 w-5 text-green-500" />
          </div>
          <p className="text-2xl font-bold text-gray-900 mt-2">
            {statsLoading ? '...' : stats?.text_length?.toLocaleString() || 0}
          </p>
          <p className="text-xs text-gray-400 mt-1">characters extracted</p>
        </Card>
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column - Document Info & Metadata */}
        <div className="space-y-6">
          {/* Document Details */}
          <Card className="p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">Document Details</h2>
            <dl className="space-y-3">
              <div>
                <dt className="text-sm text-gray-500">File Type</dt>
                <dd className="text-sm font-medium text-gray-900">{document.content_type}</dd>
              </div>
              <div>
                <dt className="text-sm text-gray-500">File Size</dt>
                <dd className="text-sm font-medium text-gray-900">
                  {document.latest_version ? formatFileSize(document.latest_version.file_size) : '-'}
                </dd>
              </div>
              <div>
                <dt className="text-sm text-gray-500">Profile</dt>
                <dd className="text-sm font-medium text-gray-900 capitalize">{document.profile_code}</dd>
              </div>
              {stats?.page_count && (
                <div>
                  <dt className="text-sm text-gray-500">Pages</dt>
                  <dd className="text-sm font-medium text-gray-900">{stats.page_count}</dd>
                </div>
              )}
              {document.file_hash && (
                <div>
                  <dt className="text-sm text-gray-500">Hash</dt>
                  <dd className="text-xs font-mono text-gray-600 truncate">{document.file_hash}</dd>
                </div>
              )}
            </dl>
          </Card>

          {/* Embedding Config */}
          {stats?.embeddings && (
            <Card className="p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Embedding Configuration</h2>
              <dl className="space-y-3">
                <div>
                  <dt className="text-sm text-gray-500">Model</dt>
                  <dd className="text-sm font-medium text-gray-900">{stats.embeddings.model}</dd>
                </div>
                <div>
                  <dt className="text-sm text-gray-500">Dimensions</dt>
                  <dd className="text-sm font-medium text-gray-900">{stats.embeddings.dimensions}</dd>
                </div>
                <div>
                  <dt className="text-sm text-gray-500">Chunk Size</dt>
                  <dd className="text-sm font-medium text-gray-900">{stats.embeddings.chunk_size} tokens</dd>
                </div>
                <div>
                  <dt className="text-sm text-gray-500">Chunk Overlap</dt>
                  <dd className="text-sm font-medium text-gray-900">{stats.embeddings.chunk_overlap} tokens</dd>
                </div>
              </dl>
            </Card>
          )}

          {/* Metadata */}
          {stats?.metadata && Object.keys(stats.metadata).length > 0 && (
            <Card className="p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Extracted Metadata</h2>
              <pre className="text-xs bg-gray-50 p-3 rounded-lg overflow-auto max-h-64">
                {JSON.stringify(stats.metadata, null, 2)}
              </pre>
            </Card>
          )}
        </div>

        {/* Right Column - Spans */}
        <div className="lg:col-span-2">
          <Card className="p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-900">
                Spans ({spansData?.total || 0})
              </h2>
              {stats?.spans.by_type && Object.keys(stats.spans.by_type).length > 0 && (
                <div className="flex gap-2">
                  {Object.entries(stats.spans.by_type).map(([type, count]) => (
                    <span
                      key={type}
                      className="text-xs px-2 py-1 bg-gray-100 text-gray-600 rounded-full"
                    >
                      {type}: {count}
                    </span>
                  ))}
                </div>
              )}
            </div>

            {spansLoading ? (
              <div className="flex items-center justify-center py-8">
                <RefreshCw className="h-6 w-6 animate-spin text-gray-400" />
              </div>
            ) : spansData?.items.length === 0 ? (
              <div className="text-center py-8 text-gray-500">
                <Layers className="h-12 w-12 mx-auto text-gray-300 mb-3" />
                <p>No spans extracted yet</p>
                <p className="text-sm mt-1">Processing may still be in progress</p>
              </div>
            ) : (
              <div className="space-y-3">
                {spansData?.items.map((span: SpanItem) => (
                  <div
                    key={span.id}
                    className="border rounded-lg p-3 hover:bg-gray-50 transition-colors"
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-xs px-2 py-0.5 bg-purple-100 text-purple-700 rounded-full font-medium">
                            {span.span_type}
                          </span>
                          <span className="text-xs text-gray-400">
                            {span.text_length} chars
                          </span>
                          {span.start_locator?.page !== undefined && (
                            <span className="text-xs text-gray-400">
                              Page {String(span.start_locator.page)}
                            </span>
                          )}
                        </div>
                        <p className={`text-sm text-gray-700 ${expandedSpan === span.id ? '' : 'line-clamp-2'}`}>
                          {span.text_content}
                        </p>
                      </div>
                      <button
                        onClick={() => setExpandedSpan(expandedSpan === span.id ? null : span.id)}
                        className="ml-2 p-1 hover:bg-gray-200 rounded"
                      >
                        {expandedSpan === span.id ? (
                          <ChevronUp className="h-4 w-4 text-gray-400" />
                        ) : (
                          <ChevronDown className="h-4 w-4 text-gray-400" />
                        )}
                      </button>
                    </div>
                  </div>
                ))}

                {spansData && spansData.total > spansData.items.length && !showAllSpans && (
                  <button
                    onClick={() => setShowAllSpans(true)}
                    className="w-full py-2 text-sm text-blue-600 hover:text-blue-800 hover:bg-blue-50 rounded-lg transition-colors"
                  >
                    Show all {spansData.total} spans
                  </button>
                )}
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
