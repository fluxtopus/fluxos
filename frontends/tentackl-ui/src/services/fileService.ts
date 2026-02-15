/**
 * File Service - Den File Storage API
 *
 * Handles file search and retrieval from Den (InkPass file storage).
 * Used for @ mentions in delegation input.
 */

import axios from 'axios';
import { formatDistanceToNow } from 'date-fns';
import api from './api';

// Den API URL (InkPass file storage - part of InkPass service)
const DEN_API_URL = process.env.NEXT_PUBLIC_INKPASS_URL || 'http://localhost:8004';

// Create axios instance for Den API
const denApi = axios.create({
  baseURL: DEN_API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add auth token to requests
denApi.interceptors.request.use((config) => {
  const token = localStorage.getItem('auth_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// === Types ===

export interface DenFile {
  id: string;
  name: string;
  folder_path: string;
  content_type: string;
  size_bytes: number;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface FileReference {
  id: string;
  name: string;
  path: string;
  content_type: string;
}

interface FileListResponse {
  files: DenFile[];
  total: number;
  limit: number;
  offset: number;
}

// === Upload Types ===

export interface UploadProgress {
  loaded: number;
  total: number;
  percentage: number;
}

export interface UploadFileParams {
  file: File;
  folder_path?: string;
  tags?: string[];
  is_public?: boolean;
  onProgress?: (progress: UploadProgress) => void;
}

// === Folder Types ===

export interface FolderTreeNode {
  name: string;
  path: string;
  fileCount: number;
  children: FolderTreeNode[];
}

// === API Functions ===

/**
 * List files with optional folder/search filtering
 * Used for the file explorer modal
 */
export async function listFiles(params: {
  folder_path?: string;
  search?: string;
  limit?: number;
  offset?: number;
} = {}): Promise<{ files: DenFile[]; total: number }> {
  try {
    const { data } = await denApi.get<FileListResponse>('/api/v1/files', {
      params: {
        folder_path: params.folder_path || undefined,
        search: params.search || undefined,
        limit: params.limit ?? 100,
        offset: params.offset ?? 0,
      },
    });
    return { files: data.files, total: data.total };
  } catch (error) {
    console.error('Failed to list files:', error);
    return { files: [], total: 0 };
  }
}

/**
 * Search files by name
 * Used for @ mention autocomplete
 */
export async function searchFiles(query: string, limit: number = 8): Promise<DenFile[]> {
  try {
    const { data } = await denApi.get<FileListResponse>('/api/v1/files', {
      params: {
        search: query || undefined, // Don't send empty string
        limit,
      },
    });
    return data.files;
  } catch (error) {
    console.error('Failed to search files:', error);
    return [];
  }
}

/**
 * List recent files (no search query)
 * Used when user types @ with no query
 */
export async function listRecentFiles(limit: number = 8): Promise<DenFile[]> {
  try {
    const { data } = await denApi.get<FileListResponse>('/api/v1/files', {
      params: { limit },
    });
    return data.files;
  } catch (error) {
    console.error('Failed to list files:', error);
    return [];
  }
}

/**
 * Upload a file to Den storage.
 * Does NOT catch errors — caller handles them for contextual UI feedback.
 */
export async function uploadFile(params: UploadFileParams): Promise<DenFile> {
  const formData = new FormData();
  formData.append('file', params.file);

  const queryParams: Record<string, string> = {};
  if (params.folder_path) queryParams.folder_path = params.folder_path;
  if (params.tags?.length) queryParams.tags = params.tags.join(',');
  if (params.is_public !== undefined) queryParams.is_public = String(params.is_public);

  const { data } = await denApi.post<DenFile>('/api/v1/files', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    params: queryParams,
    onUploadProgress: (event) => {
      if (params.onProgress && event.total) {
        params.onProgress({
          loaded: event.loaded,
          total: event.total,
          percentage: Math.round((event.loaded / event.total) * 100),
        });
      }
    },
  });

  return data;
}

/**
 * Rename a file in Den storage.
 * Uses the move endpoint with only new_name (no folder change).
 */
export async function renameFile(fileId: string, newName: string): Promise<DenFile> {
  const { data } = await denApi.patch<DenFile>(`/api/v1/files/${fileId}/move`, null, {
    params: { new_name: newName },
  });
  return data;
}

/**
 * Delete a file from Den storage.
 */
export async function deleteFile(fileId: string): Promise<void> {
  await denApi.delete(`/api/v1/files/${fileId}`);
}

/**
 * Check if a file is referenced by any active task.
 * Calls the Tentackl API (not Den).
 */
export async function checkFileUsage(fileId: string): Promise<{
  in_use: boolean;
  tasks: Array<{ id: string; goal: string; status: string }>;
}> {
  const { data } = await api.get(`/api/inbox/files/check-usage/${fileId}`);
  return data;
}

// === Download Functions ===

/**
 * Download a file by ID via authenticated Den API.
 * Triggers a browser save dialog.
 */
export async function downloadFile(fileId: string, filename: string): Promise<void> {
  const { data } = await denApi.get(`/api/v1/files/${fileId}/download`, {
    responseType: 'blob',
  });
  const url = URL.createObjectURL(data);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/**
 * Get a blob URL for inline preview (images).
 * Caller must call URL.revokeObjectURL() when done.
 */
export async function getFilePreviewUrl(fileId: string): Promise<string> {
  const { data } = await denApi.get(`/api/v1/files/${fileId}/download`, {
    responseType: 'blob',
  });
  return URL.createObjectURL(data);
}

// === Helpers ===

/**
 * Infer content type from a filename extension.
 */
export function getContentTypeFromName(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  const map: Record<string, string> = {
    jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png',
    gif: 'image/gif', webp: 'image/webp', svg: 'image/svg+xml',
    pdf: 'application/pdf', csv: 'text/csv',
    json: 'application/json', txt: 'text/plain',
    md: 'text/markdown', html: 'text/html',
    xls: 'application/vnd.ms-excel',
    xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  };
  return map[ext] || 'application/octet-stream';
}

/**
 * Get file icon based on content type
 */
export function getFileIcon(contentType: string): string {
  if (contentType.startsWith('image/')) return '🎨';
  if (contentType === 'application/pdf') return '📄';
  if (contentType.includes('spreadsheet') || contentType === 'text/csv') return '📊';
  if (contentType.includes('json')) return '📋';
  if (contentType.startsWith('text/')) return '📝';
  return '📁';
}

/**
 * Format file size for display
 */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * Format relative time for display
 */
export function formatRelativeTime(dateString: string): string {
  return formatDistanceToNow(new Date(dateString), { addSuffix: true });
}

/**
 * Convert DenFile to FileReference for submission
 */
export function toFileReference(file: DenFile): FileReference {
  return {
    id: file.id,
    name: file.name,
    path: file.folder_path,
    content_type: file.content_type,
  };
}

/**
 * Build a folder tree from a flat list of files.
 * Derives folder structure client-side from file `folder_path` fields.
 */
export function buildFolderTree(files: DenFile[]): FolderTreeNode {
  const root: FolderTreeNode = { name: 'All Files', path: '/', fileCount: files.length, children: [] };
  const folderMap = new Map<string, FolderTreeNode>();
  folderMap.set('/', root);

  for (const file of files) {
    const folderPath = file.folder_path || '/';
    if (folderMap.has(folderPath)) continue;

    // Build each segment of the path
    const segments = folderPath.split('/').filter(Boolean);
    let currentPath = '';
    let parent = root;

    for (const segment of segments) {
      currentPath += '/' + segment;
      let node = folderMap.get(currentPath);
      if (!node) {
        node = { name: segment, path: currentPath, fileCount: 0, children: [] };
        folderMap.set(currentPath, node);
        parent.children.push(node);
      }
      parent = node;
    }
  }

  // Count files per folder
  for (const file of files) {
    const folderPath = file.folder_path || '/';
    const node = folderMap.get(folderPath);
    if (node) node.fileCount++;
  }

  // Sort children alphabetically
  const sortChildren = (node: FolderTreeNode) => {
    node.children.sort((a, b) => a.name.localeCompare(b.name));
    node.children.forEach(sortChildren);
  };
  sortChildren(root);

  return root;
}
