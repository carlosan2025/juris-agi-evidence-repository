import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ChevronRight,
  ChevronDown,
  Folder,
  FolderOpen,
  FolderPlus,
  Pencil,
  Trash2,
  FileText,
  MoreHorizontal,
} from 'lucide-react';
import { foldersApi } from '../api/folders';
import { Button } from './ui/Button';
import { Input } from './ui/Input';
import { Modal } from './ui/Modal';
import type { FolderTreeNode, FolderCreate, FolderUpdate } from '../types';

interface FolderTreeProps {
  projectId: string;
  folders: FolderTreeNode[];
  selectedFolderId: string | null;
  rootDocumentCount: number;
  onSelectFolder: (folderId: string | null) => void;
}

interface FolderNodeProps {
  projectId: string;
  node: FolderTreeNode;
  level: number;
  selectedFolderId: string | null;
  onSelectFolder: (folderId: string | null) => void;
  onCreateSubfolder: (parentId: string) => void;
  onEditFolder: (folder: FolderTreeNode) => void;
  onDeleteFolder: (folderId: string) => void;
}

function FolderNode({
  projectId,
  node,
  level,
  selectedFolderId,
  onSelectFolder,
  onCreateSubfolder,
  onEditFolder,
  onDeleteFolder,
}: FolderNodeProps) {
  const [isExpanded, setIsExpanded] = useState(level === 0);
  const [showActions, setShowActions] = useState(false);
  const hasChildren = node.children && node.children.length > 0;
  const isSelected = selectedFolderId === node.id;

  const handleToggle = (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsExpanded(!isExpanded);
  };

  const handleSelect = () => {
    onSelectFolder(node.id);
  };

  return (
    <div>
      <div
        className={`group flex items-center gap-1 py-1.5 px-2 rounded-md cursor-pointer transition-colors ${
          isSelected
            ? 'bg-blue-100 text-blue-800'
            : 'hover:bg-gray-100 text-gray-700'
        }`}
        style={{ paddingLeft: `${level * 12 + 8}px` }}
        onClick={handleSelect}
        onMouseEnter={() => setShowActions(true)}
        onMouseLeave={() => setShowActions(false)}
      >
        {/* Expand/collapse toggle */}
        <button
          onClick={handleToggle}
          className={`p-0.5 rounded hover:bg-gray-200 ${
            !hasChildren ? 'invisible' : ''
          }`}
        >
          {isExpanded ? (
            <ChevronDown className="h-3.5 w-3.5" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5" />
          )}
        </button>

        {/* Folder icon */}
        {isExpanded && hasChildren ? (
          <FolderOpen
            className="h-4 w-4 flex-shrink-0"
            style={{ color: node.color || undefined }}
          />
        ) : (
          <Folder
            className="h-4 w-4 flex-shrink-0"
            style={{ color: node.color || undefined }}
          />
        )}

        {/* Folder name */}
        <span className="flex-1 text-sm truncate">{node.name}</span>

        {/* Document count badge */}
        {node.document_count > 0 && (
          <span className="text-xs text-gray-500 px-1.5 py-0.5 bg-gray-100 rounded">
            {node.document_count}
          </span>
        )}

        {/* Action buttons */}
        {showActions && (
          <div className="flex items-center gap-0.5">
            <button
              onClick={(e) => {
                e.stopPropagation();
                onCreateSubfolder(node.id);
              }}
              className="p-1 rounded hover:bg-gray-200 text-gray-500 hover:text-gray-700"
              title="Create subfolder"
            >
              <FolderPlus className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={(e) => {
                e.stopPropagation();
                onEditFolder(node);
              }}
              className="p-1 rounded hover:bg-gray-200 text-gray-500 hover:text-gray-700"
              title="Edit folder"
            >
              <Pencil className="h-3.5 w-3.5" />
            </button>
            <button
              onClick={(e) => {
                e.stopPropagation();
                onDeleteFolder(node.id);
              }}
              className="p-1 rounded hover:bg-red-100 text-gray-500 hover:text-red-600"
              title="Delete folder"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
        )}
      </div>

      {/* Children */}
      {isExpanded && hasChildren && (
        <div>
          {node.children.map((child) => (
            <FolderNode
              key={child.id}
              projectId={projectId}
              node={child}
              level={level + 1}
              selectedFolderId={selectedFolderId}
              onSelectFolder={onSelectFolder}
              onCreateSubfolder={onCreateSubfolder}
              onEditFolder={onEditFolder}
              onDeleteFolder={onDeleteFolder}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function FolderTree({
  projectId,
  folders,
  selectedFolderId,
  rootDocumentCount,
  onSelectFolder,
}: FolderTreeProps) {
  const queryClient = useQueryClient();
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [parentFolderId, setParentFolderId] = useState<string | null>(null);
  const [editingFolder, setEditingFolder] = useState<FolderTreeNode | null>(null);
  const [deletingFolderId, setDeletingFolderId] = useState<string | null>(null);
  const [folderName, setFolderName] = useState('');
  const [folderDescription, setFolderDescription] = useState('');

  // Create folder mutation
  const createMutation = useMutation({
    mutationFn: (data: FolderCreate) => foldersApi.create(projectId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['folder-tree', projectId] });
      setIsCreateModalOpen(false);
      resetForm();
    },
  });

  // Update folder mutation
  const updateMutation = useMutation({
    mutationFn: ({ folderId, data }: { folderId: string; data: FolderUpdate }) =>
      foldersApi.update(projectId, folderId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['folder-tree', projectId] });
      setIsEditModalOpen(false);
      resetForm();
    },
  });

  // Delete folder mutation
  const deleteMutation = useMutation({
    mutationFn: (folderId: string) => foldersApi.delete(projectId, folderId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['folder-tree', projectId] });
      queryClient.invalidateQueries({ queryKey: ['project-documents', projectId] });
      setIsDeleteModalOpen(false);
      setDeletingFolderId(null);
      // If the deleted folder was selected, go back to root
      if (selectedFolderId === deletingFolderId) {
        onSelectFolder(null);
      }
    },
  });

  const resetForm = () => {
    setFolderName('');
    setFolderDescription('');
    setParentFolderId(null);
    setEditingFolder(null);
  };

  const handleCreateRootFolder = () => {
    setParentFolderId(null);
    setIsCreateModalOpen(true);
  };

  const handleCreateSubfolder = (parentId: string) => {
    setParentFolderId(parentId);
    setIsCreateModalOpen(true);
  };

  const handleEditFolder = (folder: FolderTreeNode) => {
    setEditingFolder(folder);
    setFolderName(folder.name);
    setFolderDescription(folder.description || '');
    setIsEditModalOpen(true);
  };

  const handleDeleteFolder = (folderId: string) => {
    setDeletingFolderId(folderId);
    setIsDeleteModalOpen(true);
  };

  const handleCreateSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!folderName.trim()) return;
    createMutation.mutate({
      name: folderName.trim(),
      description: folderDescription.trim() || undefined,
      parent_folder_id: parentFolderId || undefined,
    });
  };

  const handleEditSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!folderName.trim() || !editingFolder) return;
    updateMutation.mutate({
      folderId: editingFolder.id,
      data: {
        name: folderName.trim(),
        description: folderDescription.trim() || undefined,
      },
    });
  };

  const handleDeleteConfirm = () => {
    if (deletingFolderId) {
      deleteMutation.mutate(deletingFolderId);
    }
  };

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-gray-200">
        <span className="text-sm font-medium text-gray-700">Folders</span>
        <button
          onClick={handleCreateRootFolder}
          className="p-1 rounded hover:bg-gray-100 text-gray-500 hover:text-gray-700"
          title="Create folder"
        >
          <FolderPlus className="h-4 w-4" />
        </button>
      </div>

      {/* Root level (All Documents) */}
      <div className="flex-1 overflow-y-auto py-2">
        <div
          className={`flex items-center gap-2 py-1.5 px-3 cursor-pointer transition-colors ${
            selectedFolderId === null
              ? 'bg-blue-100 text-blue-800'
              : 'hover:bg-gray-100 text-gray-700'
          }`}
          onClick={() => onSelectFolder(null)}
        >
          <FileText className="h-4 w-4 flex-shrink-0" />
          <span className="flex-1 text-sm font-medium">All Documents</span>
          {rootDocumentCount > 0 && (
            <span className="text-xs text-gray-500 px-1.5 py-0.5 bg-gray-100 rounded">
              {rootDocumentCount}
            </span>
          )}
        </div>

        {/* Folder tree */}
        <div className="mt-1">
          {folders.map((folder) => (
            <FolderNode
              key={folder.id}
              projectId={projectId}
              node={folder}
              level={0}
              selectedFolderId={selectedFolderId}
              onSelectFolder={onSelectFolder}
              onCreateSubfolder={handleCreateSubfolder}
              onEditFolder={handleEditFolder}
              onDeleteFolder={handleDeleteFolder}
            />
          ))}
        </div>

        {folders.length === 0 && (
          <div className="px-3 py-4 text-center">
            <Folder className="h-8 w-8 mx-auto text-gray-300 mb-2" />
            <p className="text-sm text-gray-500">No folders yet</p>
            <button
              onClick={handleCreateRootFolder}
              className="mt-2 text-sm text-blue-600 hover:text-blue-800"
            >
              Create your first folder
            </button>
          </div>
        )}
      </div>

      {/* Create Folder Modal */}
      <Modal
        isOpen={isCreateModalOpen}
        onClose={() => {
          setIsCreateModalOpen(false);
          resetForm();
        }}
        title={parentFolderId ? 'Create Subfolder' : 'Create Folder'}
        size="sm"
      >
        <form onSubmit={handleCreateSubmit} className="space-y-4">
          <Input
            label="Folder Name"
            value={folderName}
            onChange={(e) => setFolderName(e.target.value)}
            placeholder="Enter folder name"
            autoFocus
          />
          <Input
            label="Description (optional)"
            value={folderDescription}
            onChange={(e) => setFolderDescription(e.target.value)}
            placeholder="Enter description"
          />
          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="secondary"
              onClick={() => {
                setIsCreateModalOpen(false);
                resetForm();
              }}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              loading={createMutation.isPending}
              disabled={!folderName.trim()}
            >
              Create
            </Button>
          </div>
        </form>
      </Modal>

      {/* Edit Folder Modal */}
      <Modal
        isOpen={isEditModalOpen}
        onClose={() => {
          setIsEditModalOpen(false);
          resetForm();
        }}
        title="Edit Folder"
        size="sm"
      >
        <form onSubmit={handleEditSubmit} className="space-y-4">
          <Input
            label="Folder Name"
            value={folderName}
            onChange={(e) => setFolderName(e.target.value)}
            placeholder="Enter folder name"
            autoFocus
          />
          <Input
            label="Description (optional)"
            value={folderDescription}
            onChange={(e) => setFolderDescription(e.target.value)}
            placeholder="Enter description"
          />
          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="secondary"
              onClick={() => {
                setIsEditModalOpen(false);
                resetForm();
              }}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              loading={updateMutation.isPending}
              disabled={!folderName.trim()}
            >
              Save
            </Button>
          </div>
        </form>
      </Modal>

      {/* Delete Confirmation Modal */}
      <Modal
        isOpen={isDeleteModalOpen}
        onClose={() => {
          setIsDeleteModalOpen(false);
          setDeletingFolderId(null);
        }}
        title="Delete Folder"
        size="sm"
      >
        <div className="space-y-4">
          <p className="text-gray-600">
            Are you sure you want to delete this folder? Documents inside will be moved to the project root.
          </p>
          <div className="flex justify-end gap-2">
            <Button
              variant="secondary"
              onClick={() => {
                setIsDeleteModalOpen(false);
                setDeletingFolderId(null);
              }}
            >
              Cancel
            </Button>
            <Button
              variant="danger"
              onClick={handleDeleteConfirm}
              loading={deleteMutation.isPending}
            >
              Delete
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
