'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import {
  CpuChipIcon,
  UserIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  CheckCircleIcon,
  XCircleIcon,
} from '@heroicons/react/24/outline';
import { ChatInput } from './ChatInput';
import { InboxMarkdown } from './InboxMarkdown';
import type { InboxThread as InboxThreadType, InboxMessage } from '@/types/inbox';
import type { TaskStatus } from '@/types/task';
import type { FileReference } from '@/services/fileService';
import { getFileIcon, getContentTypeFromName, downloadFile, getFilePreviewUrl, formatFileSize } from '@/services/fileService';
import { ArrowDownTrayIcon } from '@heroicons/react/24/outline';
import { approveCheckpoint, rejectCheckpoint } from '@/services/taskApi';
import { hapticSuccess, hapticError } from '@/utils/haptics';
import { relativeTime } from '@/utils/relativeTime';

function statusLabel(status: TaskStatus): string {
  const map: Record<string, string> = {
    planning: 'Planning',
    ready: 'Ready',
    executing: 'Running',
    paused: 'Paused',
    checkpoint: 'Checkpoint',
    completed: 'Completed',
    failed: 'Failed',
    cancelled: 'Cancelled',
    superseded: 'Superseded',
  };
  return map[status] ?? status;
}

function statusColor(status: TaskStatus): string {
  switch (status) {
    case 'completed':
      return 'text-green-500 border-green-500/30 bg-green-500/10';
    case 'failed':
      return 'text-[var(--destructive)] border-[var(--destructive)]/30 bg-[var(--destructive)]/10';
    case 'executing':
      return 'text-[var(--accent)] border-[var(--accent)]/30 bg-[var(--accent)]/10';
    case 'checkpoint':
      return 'text-amber-500 border-amber-500/30 bg-amber-500/10';
    case 'paused':
      return 'text-yellow-500 border-yellow-500/30 bg-yellow-500/10';
    default:
      return 'text-[var(--muted-foreground)] border-[var(--border)] bg-[var(--muted)]';
  }
}

function isCheckpointMessage(message: InboxMessage): boolean {
  return !!(message.content_data && 'checkpoint_type' in message.content_data);
}

function hasResultData(message: InboxMessage): boolean {
  if (!message.content_data) return false;
  const data = message.content_data;
  return !!data.step_outputs || !!data.findings || !!data.result;
}

function isUserMessage(message: InboxMessage): boolean {
  return message.role === 'user';
}

// === Skeleton Loader ===

function ThreadSkeleton() {
  return (
    <div className="flex flex-col h-full animate-pulse">
      <div className="flex-1 px-3 py-3 space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="flex gap-3">
            <div className="h-8 w-8 bg-[var(--muted)] rounded-full flex-shrink-0" />
            <div className="flex-1 space-y-2">
              <div className="h-3 w-20 bg-[var(--muted)] rounded" />
              <div className="h-4 w-full bg-[var(--muted)] rounded" />
              <div className="h-4 w-2/3 bg-[var(--muted)] rounded" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// === Streaming Message Indicator ===

interface StreamingMessageProps {
  content: string;
  status: string | null;
}

function StreamingMessage({ content, status }: StreamingMessageProps) {
  return (
    <div className="flex gap-3">
      <div className="flex-shrink-0 mt-0.5">
        <div className="h-8 w-8 rounded-full bg-[var(--accent)]/10 flex items-center justify-center">
          <CpuChipIcon className="h-4 w-4 text-[var(--accent)]" />
        </div>
      </div>
      <div className="flex-1 min-w-0 border-l-2 border-[var(--accent)]/40 pl-3">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-xs font-medium text-[var(--accent)]">
            Flux
          </span>
          {status === 'thinking' && (
            <span className="text-xs text-[var(--muted-foreground)] animate-pulse">
              Thinking...
            </span>
          )}
          {status === 'tool_execution' && (
            <span className="text-xs text-amber-500 animate-pulse">
              Executing tool...
            </span>
          )}
        </div>
        {content ? (
          <div className="text-sm text-[var(--foreground)]">
            <InboxMarkdown content={content} />
          </div>
        ) : (
          <div className="flex items-center gap-1">
            <span className="w-1.5 h-1.5 bg-[var(--accent)] rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
            <span className="w-1.5 h-1.5 bg-[var(--accent)] rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
            <span className="w-1.5 h-1.5 bg-[var(--accent)] rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
          </div>
        )}
      </div>
    </div>
  );
}

// === File tag helpers ===

function extractFileTags(text: string): { cleanText: string; files: string[] } {
  const regex = /#([^\s#]+\.[a-zA-Z0-9]+)/g;
  const files: string[] = [];
  let match;
  while ((match = regex.exec(text)) !== null) {
    files.push(match[1]);
  }
  const cleanText = text.replace(regex, '').trim();
  return { cleanText, files };
}

// === File result helpers ===

interface FileResult {
  file_id: string;
  filename: string;
  content_type?: string;
  size_bytes?: number;
}

/**
 * Recursively walk content_data to find objects with a `file_id` field.
 * These are Den file upload results from agent steps.
 */
function extractFileResults(data: unknown): FileResult[] {
  const results: FileResult[] = [];
  const seen = new Set<string>();

  function walk(obj: unknown) {
    if (!obj || typeof obj !== 'object') return;
    if (Array.isArray(obj)) {
      for (const item of obj) walk(item);
      return;
    }
    const rec = obj as Record<string, unknown>;
    if (typeof rec.file_id === 'string' && rec.file_id && !seen.has(rec.file_id)) {
      seen.add(rec.file_id);
      results.push({
        file_id: rec.file_id,
        filename: (rec.filename as string) || (rec.name as string) || 'file',
        content_type: (rec.content_type as string) || undefined,
        size_bytes: typeof rec.size_bytes === 'number' ? rec.size_bytes : undefined,
      });
    }
    for (const val of Object.values(rec)) walk(val);
  }

  walk(data);
  return results;
}

function FileResultCard({ file }: { file: FileResult }) {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [previewError, setPreviewError] = useState(false);
  const isImage = file.content_type?.startsWith('image/') ?? false;

  useEffect(() => {
    if (!isImage) return;
    let revoked = false;
    getFilePreviewUrl(file.file_id)
      .then((url) => {
        if (!revoked) setPreviewUrl(url);
      })
      .catch(() => setPreviewError(true));
    return () => {
      revoked = true;
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
    // Only run on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file.file_id, isImage]);

  const handleDownload = async () => {
    setDownloading(true);
    try {
      await downloadFile(file.file_id, file.filename);
    } catch (err) {
      console.error('Download failed:', err);
    } finally {
      setDownloading(false);
    }
  };

  if (isImage) {
    return (
      <div className="mt-2 rounded-lg overflow-hidden border border-[var(--border)] bg-[var(--muted)]">
        {previewUrl && !previewError ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={previewUrl}
            alt={file.filename}
            className="max-w-full max-h-80 object-contain mx-auto"
            onError={() => setPreviewError(true)}
          />
        ) : previewError ? (
          <div className="p-4 text-center text-xs text-[var(--muted-foreground)]">
            Preview unavailable
          </div>
        ) : (
          <div className="p-4 text-center text-xs text-[var(--muted-foreground)] animate-pulse">
            Loading preview...
          </div>
        )}
        <div className="flex items-center justify-between px-3 py-2 border-t border-[var(--border)]">
          <span className="text-xs text-[var(--muted-foreground)] truncate">{file.filename}</span>
          <button
            onClick={handleDownload}
            disabled={downloading}
            className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-[var(--accent)] bg-[var(--accent)]/10 rounded hover:bg-[var(--accent)]/20 transition-colors disabled:opacity-50"
          >
            <ArrowDownTrayIcon className="h-3.5 w-3.5" />
            {downloading ? 'Saving...' : 'Download'}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="mt-2 flex items-center gap-3 p-3 bg-[var(--muted)] rounded-lg border border-[var(--border)]">
      <span className="text-lg flex-shrink-0">{getFileIcon(file.content_type || '')}</span>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-[var(--foreground)] truncate">{file.filename}</p>
        {file.size_bytes != null && (
          <p className="text-xs text-[var(--muted-foreground)]">{formatFileSize(file.size_bytes)}</p>
        )}
      </div>
      <button
        onClick={handleDownload}
        disabled={downloading}
        className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-[var(--accent)] bg-[var(--accent)]/10 rounded hover:bg-[var(--accent)]/20 transition-colors disabled:opacity-50"
      >
        <ArrowDownTrayIcon className="h-3.5 w-3.5" />
        {downloading ? 'Saving...' : 'Download'}
      </button>
    </div>
  );
}

// === Message Component ===

interface MessageItemProps {
  message: InboxMessage;
  taskId?: string;
}

function MessageItem({ message, taskId }: MessageItemProps) {
  const [expanded, setExpanded] = useState(false);
  const [resolving, setResolving] = useState(false);
  const [resolution, setResolution] = useState<'approved' | 'rejected' | null>(null);
  const [rejectionReason, setRejectionReason] = useState('');
  const [showRejectInput, setShowRejectInput] = useState(false);
  const [rejectedReason, setRejectedReason] = useState('');

  const isUser = isUserMessage(message);
  const isAgent = message.role === 'assistant';
  const isCheckpoint = isCheckpointMessage(message);
  const hasData = hasResultData(message);
  // Check if checkpoint is already resolved from server data
  const existingDecision = message.content_data?.decision as string | undefined;
  const existingReason = message.content_data?.rejection_reason as string | undefined;
  const alreadyResolved = !!existingDecision;
  const isResolved = alreadyResolved || resolution !== null;

  const handleApprove = useCallback(async () => {
    if (!message.content_data || !taskId) return;
    const stepId = message.content_data.step_id as string;
    if (!stepId) return;

    setResolving(true);
    try {
      await approveCheckpoint(taskId, stepId);
      hapticSuccess();
      setResolution('approved');
    } catch (err) {
      console.error('Failed to approve checkpoint:', err);
    } finally {
      setResolving(false);
    }
  }, [taskId, message.content_data]);

  const handleReject = useCallback(async () => {
    if (!message.content_data || !taskId) return;
    const stepId = message.content_data.step_id as string;
    if (!stepId) return;

    setResolving(true);
    try {
      const reason = rejectionReason.trim() || 'Rejected from inbox';
      await rejectCheckpoint(taskId, stepId, { reason });
      hapticError();
      setResolution('rejected');
      setRejectedReason(reason);
      setShowRejectInput(false);
    } catch (err) {
      console.error('Failed to reject checkpoint:', err);
    } finally {
      setResolving(false);
    }
  }, [taskId, message.content_data, rejectionReason]);

  // User messages: right-aligned bubble
  if (isUser) {
    const { cleanText, files } = extractFileTags(message.content_text || '');
    return (
      <div className="flex gap-3 justify-end">
        <div className="max-w-[75%]">
          <div className="flex items-center gap-2 mb-1 justify-end">
            <span className="text-xs text-[var(--muted-foreground)]">
              {relativeTime(message.timestamp)}
            </span>
            <span className="text-xs font-medium text-[var(--muted-foreground)]">
              You
            </span>
          </div>
          <div className="bg-[var(--accent)]/10 border border-[var(--accent)]/20 rounded-lg rounded-br-sm px-3 py-2 text-sm text-[var(--foreground)] whitespace-pre-wrap">
            {cleanText || '(No content)'}
          </div>
          {files.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-1.5 justify-end">
              {files.map((name) => {
                const ct = getContentTypeFromName(name);
                const ext = name.split('.').pop()?.toUpperCase() || '';
                return (
                  <span
                    key={name}
                    className="inline-flex items-center gap-1.5 px-2 py-1 text-xs rounded-full bg-[var(--muted)] border border-[var(--border)]"
                  >
                    <span>{getFileIcon(ct)}</span>
                    <span className="font-medium text-[var(--foreground)]">{name}</span>
                    <span className="text-[10px] text-[var(--muted-foreground)] font-mono">{ext}</span>
                  </span>
                );
              })}
            </div>
          )}
        </div>
        <div className="flex-shrink-0 mt-0.5">
          <div className="h-8 w-8 rounded-full bg-[var(--muted)] flex items-center justify-center">
            <UserIcon className="h-4 w-4 text-[var(--muted-foreground)]" />
          </div>
        </div>
      </div>
    );
  }

  // Agent messages
  return (
    <div className="flex gap-3">
      {isAgent && (
        <div className="flex-shrink-0 mt-0.5">
          <div className="h-8 w-8 rounded-full bg-[var(--accent)]/10 flex items-center justify-center">
            <CpuChipIcon className="h-4 w-4 text-[var(--accent)]" />
          </div>
        </div>
      )}

      <div className={`flex-1 min-w-0 ${isAgent ? 'border-l-2 border-[var(--accent)]/20 pl-3' : ''}`}>
        <div className="flex items-center gap-2 mb-1">
          <span className="text-xs font-medium text-[var(--muted-foreground)]">
            Flux
          </span>
          <span className="text-xs text-[var(--muted-foreground)]">
            {relativeTime(message.timestamp)}
          </span>
        </div>

        <div className="text-sm text-[var(--foreground)]">
          {message.content_text ? (
            <InboxMarkdown content={message.content_text} />
          ) : (
            <span className="text-[var(--muted-foreground)]">(No content)</span>
          )}
        </div>

        {/* File results from agent step outputs */}
        {(() => {
          const fileResults = message.content_data ? extractFileResults(message.content_data) : [];
          if (fileResults.length === 0) return null;
          return (
            <div className="space-y-1">
              {fileResults.map((f) => (
                <FileResultCard key={f.file_id} file={f} />
              ))}
            </div>
          );
        })()}

        {/* Checkpoint actions */}
        {isCheckpoint && !isResolved && taskId && (
          <div className="mt-2 space-y-2">
            <div className="flex gap-2">
              <button
                onClick={handleApprove}
                disabled={resolving}
                className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-lg bg-green-500/10 text-green-500 border border-green-500/30 hover:bg-green-500/20 transition-colors disabled:opacity-50"
              >
                {resolving ? (
                  <svg className="animate-spin h-3.5 w-3.5" viewBox="0 0 24 24" fill="none"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>
                ) : (
                  <CheckCircleIcon className="h-3.5 w-3.5" />
                )}
                Approve
              </button>
              <button
                onClick={() => setShowRejectInput(!showRejectInput)}
                disabled={resolving}
                className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium rounded-lg bg-[var(--destructive)]/10 text-[var(--destructive)] border border-[var(--destructive)]/30 hover:bg-[var(--destructive)]/20 transition-colors disabled:opacity-50"
              >
                <XCircleIcon className="h-3.5 w-3.5" />
                Reject
              </button>
            </div>
            {showRejectInput && (
              <div className="flex gap-2">
                <input
                  type="text"
                  value={rejectionReason}
                  onChange={(e) => setRejectionReason(e.target.value)}
                  placeholder="Reason for rejection (optional)"
                  className="flex-1 px-2 py-1.5 text-xs rounded-lg border border-[var(--border)] bg-[var(--background)] text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleReject();
                  }}
                />
                <button
                  onClick={handleReject}
                  disabled={resolving}
                  className="px-3 py-1.5 text-xs font-medium rounded-lg bg-[var(--destructive)] text-white hover:bg-[var(--destructive)]/90 transition-colors disabled:opacity-50"
                >
                  {resolving ? 'Rejecting...' : 'Confirm'}
                </button>
              </div>
            )}
          </div>
        )}

        {isCheckpoint && isResolved && (
          <p className="text-xs mt-2 italic">
            {alreadyResolved ? (
              existingDecision === 'approved' ? (
                <span className="text-green-500">Approved</span>
              ) : (
                <span className="text-[var(--destructive)]">
                  Rejected{existingReason ? `: ${existingReason}` : ''}
                </span>
              )
            ) : resolution === 'approved' ? (
              <span className="text-green-500">Approved</span>
            ) : (
              <span className="text-[var(--destructive)]">
                Rejected{rejectedReason ? `: ${rejectedReason}` : ''}
              </span>
            )}
          </p>
        )}

        {/* Expandable result data */}
        {hasData && (
          <div className="mt-2">
            <button
              onClick={() => setExpanded(!expanded)}
              className="inline-flex items-center gap-1 text-xs font-medium text-[var(--accent)] hover:opacity-80 transition-opacity"
            >
              {expanded ? (
                <ChevronDownIcon className="h-3.5 w-3.5" />
              ) : (
                <ChevronRightIcon className="h-3.5 w-3.5" />
              )}
              View Result Data
            </button>
            {expanded && (
              <pre className="mt-2 p-3 rounded-lg bg-[var(--muted)] border border-[var(--border)] text-xs text-[var(--foreground)] overflow-x-auto max-h-64 overflow-y-auto">
                {JSON.stringify(message.content_data, null, 2)}
              </pre>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// === Main Component ===

interface InboxThreadProps {
  thread: InboxThreadType | null;
  loading: boolean;
  onSendMessage: (text: string, fileReferences?: FileReference[]) => Promise<void>;
  isStreaming?: boolean;
  streamingContent?: string;
  streamingStatus?: string | null;
}

export function InboxThread({
  thread,
  loading,
  onSendMessage,
  isStreaming = false,
  streamingContent = '',
  streamingStatus = null,
}: InboxThreadProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Scroll to bottom when messages change or streaming updates
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [thread?.messages.length, streamingContent]);

  if (loading) {
    return <ThreadSkeleton />;
  }

  if (!thread) {
    return null;
  }

  const hasTask = thread.task !== null;
  const primaryTaskId = thread.task?.id;

  return (
    <div className="flex flex-col h-full">
      {/* Compact header — only show status badge when a task exists */}
      {hasTask && (
        <div className="px-3 py-2 flex items-center gap-2">
          <span
            className={`inline-block text-xs font-mono px-1.5 py-0.5 rounded border ${statusColor(thread.task!.status)}`}
          >
            {statusLabel(thread.task!.status)}
          </span>
          <span className="text-xs text-[var(--muted-foreground)] truncate">
            {thread.task!.goal}
          </span>
        </div>
      )}

      {/* Message list */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-5">
        {thread.messages.map((message) => (
          <MessageItem
            key={message.id}
            message={message}
            taskId={primaryTaskId}
          />
        ))}

        {/* Streaming response */}
        {isStreaming && (
          <StreamingMessage content={streamingContent} status={streamingStatus} />
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Bottom input */}
      <div
        className="px-3 pt-2 pb-2"
        onFocus={() => {
          // When keyboard opens on mobile, scroll messages to bottom
          setTimeout(() => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }), 300);
        }}
      >
        <ChatInput
          onSubmit={onSendMessage}
          disabled={isStreaming}
          placeholder={hasTask ? 'Follow up or ask a question...' : 'Type a message...'}
        />
      </div>
    </div>
  );
}
