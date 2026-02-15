'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { XMarkIcon, FolderIcon, FolderOpenIcon, MagnifyingGlassIcon, CheckIcon, ArrowUpTrayIcon, ArrowDownTrayIcon, PencilSquareIcon, TrashIcon } from '@heroicons/react/24/outline';
import { MobileSheet } from '../MobileSheet';
import {
  listFiles,
  uploadFile,
  downloadFile,
  renameFile,
  deleteFile,
  checkFileUsage,
  buildFolderTree,
  getFileIcon,
  formatFileSize,
  formatRelativeTime,
  type DenFile,
  type FolderTreeNode,
} from '../../services/fileService';

interface UploadingFile {
  id: string;
  name: string;
  progress: number;
  status: 'uploading' | 'done' | 'error';
  error?: string;
}

interface FileExplorerModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelect: (files: DenFile[]) => void;
  selectedFileIds?: Set<string>;
}

/**
 * FileExplorerModal - Visual file browser for selecting files to attach.
 * Shows a folder tree on the left and file list on the right with search.
 */
export function FileExplorerModal({
  isOpen,
  onClose,
  onSelect,
  selectedFileIds,
}: FileExplorerModalProps) {
  const [allFiles, setAllFiles] = useState<DenFile[]>([]);
  const [folderTree, setFolderTree] = useState<FolderTreeNode | null>(null);
  const [currentFolder, setCurrentFolder] = useState<string>('/');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedFiles, setSelectedFiles] = useState<Map<string, DenFile>>(new Map());
  const [isLoading, setIsLoading] = useState(false);
  const [uploadingFiles, setUploadingFiles] = useState<UploadingFile[]>([]);
  const [isDragOver, setIsDragOver] = useState(false);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dragCounterRef = useRef(0);
  const debounceRef = useRef<NodeJS.Timeout | null>(null);

  // Load all files on open
  useEffect(() => {
    if (!isOpen) return;

    const loadFiles = async () => {
      setIsLoading(true);
      try {
        const { files } = await listFiles({ limit: 500 });
        setAllFiles(files);
        setFolderTree(buildFolderTree(files));
      } finally {
        setIsLoading(false);
      }
    };

    loadFiles();
    setCurrentFolder('/');
    setSearchQuery('');
    setSelectedFiles(new Map());

    // Focus search input after render
    requestAnimationFrame(() => searchInputRef.current?.focus());
  }, [isOpen]);

  // Close on Escape
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // Prevent body scroll
  useEffect(() => {
    if (!isOpen) return;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = ''; };
  }, [isOpen]);

  // Filter files for display
  const displayedFiles = (() => {
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      return allFiles.filter(f => f.name.toLowerCase().includes(q));
    }
    if (currentFolder === '/') return allFiles;
    return allFiles.filter(f => (f.folder_path || '/') === currentFolder);
  })();

  // Build breadcrumb segments
  const breadcrumbs = (() => {
    if (searchQuery.trim()) return [{ name: 'Search Results', path: '' }];
    if (currentFolder === '/') return [{ name: 'All Files', path: '/' }];
    const segments = currentFolder.split('/').filter(Boolean);
    const crumbs = [{ name: 'All Files', path: '/' }];
    let path = '';
    for (const seg of segments) {
      path += '/' + seg;
      crumbs.push({ name: seg, path });
    }
    return crumbs;
  })();

  const toggleFile = useCallback((file: DenFile) => {
    setSelectedFiles(prev => {
      const next = new Map(prev);
      if (next.has(file.id)) {
        next.delete(file.id);
      } else {
        next.set(file.id, file);
      }
      return next;
    });
  }, []);

  const handleAttach = useCallback(() => {
    onSelect(Array.from(selectedFiles.values()));
    onClose();
  }, [selectedFiles, onSelect, onClose]);

  const handleSearchChange = useCallback((value: string) => {
    setSearchQuery(value);
    if (value.trim()) {
      setCurrentFolder('/'); // clear folder selection when searching
    }
  }, []);

  const handleFolderClick = useCallback((path: string) => {
    setCurrentFolder(path);
    setSearchQuery(''); // clear search when navigating folders
  }, []);

  const handleUploadFiles = useCallback(async (files: FileList | File[]) => {
    const fileArray = Array.from(files);
    if (fileArray.length === 0) return;

    // Create tracking entries
    const entries: UploadingFile[] = fileArray.map((f, i) => ({
      id: `upload-${Date.now()}-${i}`,
      name: f.name,
      progress: 0,
      status: 'uploading' as const,
    }));
    setUploadingFiles(prev => [...prev, ...entries]);

    const uploadedFiles: DenFile[] = [];

    await Promise.all(
      fileArray.map(async (file, i) => {
        const entryId = entries[i].id;
        try {
          const result = await uploadFile({
            file,
            folder_path: currentFolder === '/' ? undefined : currentFolder,
            onProgress: (progress) => {
              setUploadingFiles(prev =>
                prev.map(u => u.id === entryId ? { ...u, progress: progress.percentage } : u)
              );
            },
          });
          uploadedFiles.push(result);
          setUploadingFiles(prev =>
            prev.map(u => u.id === entryId ? { ...u, status: 'done', progress: 100 } : u)
          );
        } catch (err: unknown) {
          const axiosErr = err as { response?: { status?: number; data?: { detail?: string } } };
          const message = axiosErr.response?.status === 413
            ? 'File too large'
            : axiosErr.response?.data?.detail || 'Upload failed';
          setUploadingFiles(prev =>
            prev.map(u => u.id === entryId ? { ...u, status: 'error', error: message } : u)
          );
        }
      })
    );

    // Refresh file list and auto-select uploaded files
    if (uploadedFiles.length > 0) {
      const { files: freshFiles } = await listFiles({ limit: 500 });
      setAllFiles(freshFiles);
      setFolderTree(buildFolderTree(freshFiles));
      setSelectedFiles(prev => {
        const next = new Map(prev);
        for (const f of uploadedFiles) next.set(f.id, f);
        return next;
      });
    }

    // Clear completed/errored entries after delay
    setTimeout(() => {
      setUploadingFiles(prev => prev.filter(u => u.status === 'uploading'));
    }, 1500);
  }, [currentFolder]);

  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current++;
    if (dragCounterRef.current === 1) setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current--;
    if (dragCounterRef.current === 0) setIsDragOver(false);
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCounterRef.current = 0;
    setIsDragOver(false);
    if (e.dataTransfer.files.length > 0) {
      handleUploadFiles(e.dataTransfer.files);
    }
  }, [handleUploadFiles]);

  const handleRename = useCallback(async (file: DenFile, newName: string) => {
    const trimmed = newName.trim();
    if (!trimmed || trimmed === file.name) return;
    try {
      const updated = await renameFile(file.id, trimmed);
      setAllFiles(prev => {
        const next = prev.map(f => f.id === file.id ? { ...f, name: updated.name } : f);
        setFolderTree(buildFolderTree(next));
        return next;
      });
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      const message = axiosErr.response?.data?.detail || 'Rename failed';
      throw new Error(message);
    }
  }, []);

  const handleDelete = useCallback(async (file: DenFile) => {
    try {
      await deleteFile(file.id);
      setAllFiles(prev => {
        const next = prev.filter(f => f.id !== file.id);
        setFolderTree(buildFolderTree(next));
        return next;
      });
      // Also remove from selection if selected
      setSelectedFiles(prev => {
        const next = new Map(prev);
        next.delete(file.id);
        return next;
      });
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      const message = axiosErr.response?.data?.detail || 'Delete failed';
      throw new Error(message);
    }
  }, []);

  const [isDownloading, setIsDownloading] = useState(false);

  const handleDownloadSelected = useCallback(async () => {
    const files = Array.from(selectedFiles.values());
    if (files.length === 0) return;
    setIsDownloading(true);
    try {
      for (const file of files) {
        await downloadFile(file.id, file.name);
      }
    } catch (err) {
      console.error('Download failed:', err);
    } finally {
      setIsDownloading(false);
    }
  }, [selectedFiles]);

  const isFileSelected = useCallback((fileId: string) => {
    return selectedFiles.has(fileId) || (selectedFileIds?.has(fileId) ?? false);
  }, [selectedFiles, selectedFileIds]);

  if (!isOpen) return null;

  return (
    <MobileSheet isOpen={isOpen} onClose={onClose} title="Browse Files" desktopMaxWidth="max-w-3xl">
      <div className="w-full h-[70dvh] sm:h-[600px] sm:max-h-[80dvh] mx-auto bg-[var(--card)] rounded-2xl shadow-xl border border-[var(--border)] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--border)] shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-[oklch(0.65_0.25_180/0.1)] flex items-center justify-center">
              <FolderOpenIcon className="w-4 h-4 text-[oklch(0.65_0.25_180)]" />
            </div>
            <h2 className="text-sm font-semibold text-[var(--foreground)]">
              Browse Files
            </h2>
          </div>
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={handleDownloadSelected}
              disabled={selectedFiles.size === 0 || isDownloading}
              className={`flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium rounded-lg transition-colors ${
                selectedFiles.size > 0
                  ? 'text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--muted)]'
                  : 'text-[var(--muted-foreground)]/40 cursor-not-allowed'
              }`}
            >
              <ArrowDownTrayIcon className="w-3.5 h-3.5" />
              {isDownloading ? 'Downloading...' : 'Download'}
            </button>
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--muted)] rounded-lg transition-colors"
            >
              <ArrowUpTrayIcon className="w-3.5 h-3.5" />
              Upload
            </button>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={(e) => {
                if (e.target.files?.length) handleUploadFiles(e.target.files);
                e.target.value = '';
              }}
            />
          <button
            onClick={onClose}
            className="p-1.5 text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--muted)] rounded-lg transition-colors"
          >
            <XMarkIcon className="w-5 h-5" />
          </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex flex-1 min-h-0">
          {/* Sidebar - Folder tree (hidden on mobile) */}
          <div className="hidden sm:block w-[200px] border-r border-[var(--border)] overflow-y-auto shrink-0 py-1">
            {folderTree && (
              <FolderTreePanel
                node={folderTree}
                currentFolder={currentFolder}
                onSelect={handleFolderClick}
                depth={0}
              />
            )}
          </div>

          {/* Main area */}
          <div className="flex-1 flex flex-col min-w-0">
            {/* Search */}
            <div className="px-3 pt-3 pb-2 shrink-0">
              <div className="relative">
                <MagnifyingGlassIcon className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--muted-foreground)]" />
                <input
                  ref={searchInputRef}
                  type="text"
                  value={searchQuery}
                  onChange={e => handleSearchChange(e.target.value)}
                  placeholder="Search files..."
                  className="w-full pl-8 pr-3 py-1.5 text-sm bg-[var(--muted)] border border-[var(--border)] rounded-lg text-[var(--foreground)] placeholder-[var(--muted-foreground)] focus:outline-none focus:border-[oklch(0.65_0.25_180/0.5)]"
                />
              </div>
            </div>

            {/* Breadcrumb */}
            <div className="px-3 pb-2 shrink-0">
              <nav className="flex items-center gap-1 text-xs text-[var(--muted-foreground)]">
                {breadcrumbs.map((crumb, i) => (
                  <span key={crumb.path || i} className="flex items-center gap-1">
                    {i > 0 && <span className="text-[var(--muted-foreground)]/50">/</span>}
                    {crumb.path ? (
                      <button
                        type="button"
                        onClick={() => handleFolderClick(crumb.path)}
                        className="hover:text-[var(--foreground)] transition-colors"
                      >
                        {crumb.name}
                      </button>
                    ) : (
                      <span>{crumb.name}</span>
                    )}
                  </span>
                ))}
              </nav>
            </div>

            {/* Upload progress */}
            {uploadingFiles.length > 0 && (
              <div className="px-3 pb-2 shrink-0 space-y-1">
                {uploadingFiles.map(u => (
                  <div key={u.id} className="flex items-center gap-2 text-xs py-1 px-2 rounded-md bg-[var(--muted)]">
                    {u.status === 'uploading' && (
                      <svg className="w-3.5 h-3.5 animate-spin text-[oklch(0.65_0.25_180)] flex-shrink-0" viewBox="0 0 24 24" fill="none">
                        <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" className="opacity-25" />
                        <path d="M12 2a10 10 0 019.95 9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" className="opacity-75" />
                      </svg>
                    )}
                    {u.status === 'done' && (
                      <CheckIcon className="w-3.5 h-3.5 text-[oklch(0.65_0.2_150)] flex-shrink-0" />
                    )}
                    {u.status === 'error' && (
                      <XMarkIcon className="w-3.5 h-3.5 text-[oklch(0.65_0.25_25)] flex-shrink-0" />
                    )}
                    <span className="truncate text-[var(--foreground)] flex-1 min-w-0">{u.name}</span>
                    {u.status === 'uploading' && (
                      <span className="text-[var(--muted-foreground)] tabular-nums flex-shrink-0">{u.progress}%</span>
                    )}
                    {u.status === 'error' && (
                      <span className="text-[oklch(0.65_0.25_25)] flex-shrink-0">{u.error}</span>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* File list */}
            <div
              className="flex-1 overflow-y-auto px-1 relative"
              onDragEnter={handleDragEnter}
              onDragLeave={handleDragLeave}
              onDragOver={handleDragOver}
              onDrop={handleDrop}
            >
              {/* Drag overlay */}
              {isDragOver && (
                <div className="absolute inset-0 z-10 flex items-center justify-center bg-[oklch(0.65_0.25_180/0.05)] border-2 border-dashed border-[oklch(0.65_0.25_180/0.4)] rounded-lg m-1 pointer-events-none">
                  <div className="flex items-center gap-2 text-sm text-[oklch(0.5_0.2_180)] font-medium">
                    <ArrowUpTrayIcon className="w-5 h-5" />
                    Drop files to upload
                  </div>
                </div>
              )}

              {isLoading ? (
                <div className="flex items-center justify-center h-full text-sm text-[var(--muted-foreground)]">
                  Loading files...
                </div>
              ) : displayedFiles.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full gap-1 text-sm text-[var(--muted-foreground)]">
                  <span>{searchQuery ? 'No files match your search' : 'No files in this folder'}</span>
                  {!searchQuery && (
                    <span className="text-xs">Drag files here or click Upload to add files</span>
                  )}
                </div>
              ) : (
                <ul>
                  {displayedFiles.map(file => (
                    <FileRow
                      key={file.id}
                      file={file}
                      isSelected={isFileSelected(file.id)}
                      onToggle={() => toggleFile(file)}
                      onRename={handleRename}
                      onDelete={handleDelete}
                    />
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-4 py-3 border-t border-[var(--border)] shrink-0 bg-[var(--muted)]">
          <span className="text-xs text-[var(--muted-foreground)]">
            {selectedFiles.size === 0
              ? 'Select files to attach'
              : `${selectedFiles.size} file${selectedFiles.size === 1 ? '' : 's'} selected`}
          </span>
          <button
            type="button"
            onClick={handleAttach}
            disabled={selectedFiles.size === 0}
            className={`
              px-4 py-1.5 text-sm font-medium rounded-lg transition-colors
              ${selectedFiles.size > 0
                ? 'delegation-cta text-white'
                : 'bg-[var(--border)] text-[var(--muted-foreground)] cursor-not-allowed'
              }
            `}
          >
            Attach Files
          </button>
        </div>
      </div>
    </MobileSheet>
  );
}

// === Subcomponents ===

function FolderTreePanel({
  node,
  currentFolder,
  onSelect,
  depth,
}: {
  node: FolderTreeNode;
  currentFolder: string;
  onSelect: (path: string) => void;
  depth: number;
}) {
  const isActive = currentFolder === node.path;

  return (
    <>
      <button
        type="button"
        onClick={() => onSelect(node.path)}
        className={`
          w-full flex items-center gap-1.5 px-2 py-1.5 text-left text-xs transition-colors
          ${isActive
            ? 'bg-[oklch(0.65_0.25_180/0.1)] text-[oklch(0.5_0.2_180)] font-medium'
            : 'text-[var(--foreground)] hover:bg-[var(--muted)]'
          }
        `}
        style={{ paddingLeft: `${8 + depth * 12}px` }}
      >
        {isActive ? (
          <FolderOpenIcon className="w-3.5 h-3.5 flex-shrink-0" />
        ) : (
          <FolderIcon className="w-3.5 h-3.5 flex-shrink-0 text-[var(--muted-foreground)]" />
        )}
        <span className="truncate">{node.name}</span>
        <span className="ml-auto text-[10px] text-[var(--muted-foreground)] tabular-nums">
          {node.fileCount}
        </span>
      </button>
      {node.children.map(child => (
        <FolderTreePanel
          key={child.path}
          node={child}
          currentFolder={currentFolder}
          onSelect={onSelect}
          depth={depth + 1}
        />
      ))}
    </>
  );
}

function FileRow({
  file,
  isSelected,
  onToggle,
  onRename,
  onDelete,
}: {
  file: DenFile;
  isSelected: boolean;
  onToggle: () => void;
  onRename: (file: DenFile, newName: string) => Promise<void>;
  onDelete: (file: DenFile) => Promise<void>;
}) {
  const [isEditing, setIsEditing] = useState(false);
  const [editName, setEditName] = useState(file.name);
  const [renameError, setRenameError] = useState<string | null>(null);
  const [deleteState, setDeleteState] = useState<'idle' | 'confirming' | 'checking' | 'blocked'>(
    'idle',
  );
  const [blockReason, setBlockReason] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const startEditing = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setEditName(file.name);
    setRenameError(null);
    setIsEditing(true);
  }, [file.name]);

  useEffect(() => {
    if (!isEditing || !inputRef.current) return;
    inputRef.current.focus();
    const dotIndex = file.name.lastIndexOf('.');
    if (dotIndex > 0) {
      inputRef.current.setSelectionRange(0, dotIndex);
    } else {
      inputRef.current.select();
    }
  }, [isEditing, file.name]);

  const commitRename = useCallback(async () => {
    const trimmed = editName.trim();
    if (!trimmed || trimmed === file.name) {
      setIsEditing(false);
      return;
    }
    try {
      await onRename(file, trimmed);
      setIsEditing(false);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Rename failed';
      setRenameError(message);
      setEditName(file.name);
      setIsEditing(false);
      setTimeout(() => setRenameError(null), 2000);
    }
  }, [editName, file, onRename]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      commitRename();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      e.nativeEvent.stopImmediatePropagation();
      setEditName(file.name);
      setIsEditing(false);
    }
  }, [commitRename, file.name]);

  const startDelete = useCallback(async (e: React.MouseEvent) => {
    e.stopPropagation();
    setDeleteState('checking');
    try {
      const usage = await checkFileUsage(file.id);
      if (usage.in_use) {
        const taskCount = usage.tasks.length;
        setBlockReason(`Used by ${taskCount} active task${taskCount > 1 ? 's' : ''}`);
        setDeleteState('blocked');
        setTimeout(() => { setDeleteState('idle'); setBlockReason(null); }, 4000);
      } else {
        setDeleteState('confirming');
      }
    } catch {
      // If usage check fails, still allow confirming
      setDeleteState('confirming');
    }
  }, [file.id]);

  const confirmDelete = useCallback(async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await onDelete(file);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Delete failed';
      setBlockReason(message);
      setDeleteState('blocked');
      setTimeout(() => { setDeleteState('idle'); setBlockReason(null); }, 3000);
    }
  }, [file, onDelete]);

  const cancelDelete = useCallback((e: React.MouseEvent) => {
    e.stopPropagation();
    setDeleteState('idle');
  }, []);

  // Show inline confirmation/blocked state
  if (deleteState === 'confirming') {
    return (
      <li>
        <div className="w-full flex items-center gap-3 px-3 py-2 rounded-lg mx-1 bg-[oklch(0.65_0.25_25/0.06)]" style={{ width: 'calc(100% - 8px)' }}>
          <span className="text-sm text-[var(--foreground)]">Delete &ldquo;{file.name}&rdquo;?</span>
          <div className="ml-auto flex items-center gap-2">
            <div
              role="button"
              tabIndex={0}
              onClick={confirmDelete}
              onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') confirmDelete(e as unknown as React.MouseEvent); }}
              className="text-xs font-medium text-[oklch(0.65_0.25_25)] hover:text-[oklch(0.55_0.25_25)] cursor-pointer"
            >
              Delete
            </div>
            <div
              role="button"
              tabIndex={0}
              onClick={cancelDelete}
              onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') cancelDelete(e as unknown as React.MouseEvent); }}
              className="text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)] cursor-pointer"
            >
              Cancel
            </div>
          </div>
        </div>
      </li>
    );
  }

  return (
    <li>
      <button
        type="button"
        onClick={onToggle}
        className={`
          group w-full flex items-center gap-3 px-3 py-2 text-left transition-colors rounded-lg mx-1
          ${isSelected ? 'bg-[oklch(0.65_0.25_180/0.08)]' : 'hover:bg-[var(--muted)]'}
        `}
        style={{ width: 'calc(100% - 8px)' }}
      >
        {/* Checkbox */}
        <div className={`
          w-4 h-4 rounded border flex items-center justify-center flex-shrink-0 transition-colors
          ${isSelected
            ? 'bg-[oklch(0.65_0.25_180)] border-[oklch(0.65_0.25_180)]'
            : 'border-[var(--border)] bg-transparent'
          }
        `}>
          {isSelected && <CheckIcon className="w-3 h-3 text-white" />}
        </div>

        {/* File icon */}
        <span className="text-base flex-shrink-0">{getFileIcon(file.content_type)}</span>

        {/* File info */}
        <div className="flex-1 min-w-0">
          {isEditing ? (
            <input
              ref={inputRef}
              type="text"
              value={editName}
              onChange={e => setEditName(e.target.value)}
              onKeyDown={handleKeyDown}
              onBlur={commitRename}
              onClick={e => e.stopPropagation()}
              className="w-full text-sm bg-[var(--muted)] border border-[oklch(0.65_0.25_180/0.5)] rounded px-1.5 py-0.5 text-[var(--foreground)] focus:outline-none"
            />
          ) : (
            <div className="text-sm text-[var(--foreground)] truncate">
              {file.name}
              {renameError && (
                <span className="ml-2 text-xs text-[oklch(0.65_0.25_25)]">{renameError}</span>
              )}
              {deleteState === 'blocked' && blockReason && (
                <span className="ml-2 text-xs text-[oklch(0.65_0.25_25)]">{blockReason}</span>
              )}
            </div>
          )}
        </div>

        {/* Action buttons — uses div to avoid nested <button> hydration error */}
        {!isEditing && (
          <>
            <div
              role="button"
              tabIndex={0}
              onClick={startEditing}
              onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); startEditing(e as unknown as React.MouseEvent); } }}
              className="p-0.5 text-[var(--muted-foreground)] hover:text-[var(--foreground)] opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0 cursor-pointer"
              title="Rename file"
            >
              <PencilSquareIcon className="w-3.5 h-3.5" />
            </div>
            <div
              role="button"
              tabIndex={0}
              onClick={startDelete}
              onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); startDelete(e as unknown as React.MouseEvent); } }}
              className={`p-0.5 hover:text-[oklch(0.65_0.25_25)] opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0 cursor-pointer ${deleteState === 'checking' ? 'opacity-50 pointer-events-none' : 'text-[var(--muted-foreground)]'}`}
              title="Delete file"
            >
              <TrashIcon className="w-3.5 h-3.5" />
            </div>
          </>
        )}

        {/* Meta */}
        <span className="text-xs text-[var(--muted-foreground)] tabular-nums flex-shrink-0">
          {formatFileSize(file.size_bytes)}
        </span>
        <span className="text-xs text-[var(--muted-foreground)] flex-shrink-0 w-16 text-right hidden sm:inline">
          {formatRelativeTime(file.updated_at)}
        </span>
      </button>
    </li>
  );
}
