'use client';

import { useCallback } from 'react';
import { ArchiveBoxIcon } from '@heroicons/react/24/outline';
import type { InboxItem } from '@/types/inbox';
import type { TaskStatus } from '@/types/task';
import { relativeTime } from '@/utils/relativeTime';
import { useSwipeAction } from '@/hooks/useSwipeAction';
import { hapticLight } from '@/utils/haptics';

// === Status helpers ===

function statusLabel(status: TaskStatus): string {
  const map: Record<string, string> = {
    planning: 'Planning',
    ready: 'Ready',
    executing: 'Running',
    paused: 'Paused',
    checkpoint: 'Checkpoint',
    completed: 'Done',
    failed: 'Failed',
    cancelled: 'Cancelled',
    superseded: 'Superseded',
  };
  return map[status] ?? status;
}

function statusDotColor(status: TaskStatus): string {
  switch (status) {
    case 'completed':
      return 'bg-emerald-400';
    case 'failed':
      return 'bg-red-400';
    case 'executing':
      return 'bg-[var(--accent)] animate-pulse';
    case 'checkpoint':
      return 'bg-amber-400';
    case 'paused':
      return 'bg-yellow-400';
    default:
      return 'bg-[var(--muted-foreground)]';
  }
}

function statusTextColor(status: TaskStatus): string {
  switch (status) {
    case 'completed':
      return 'text-emerald-500';
    case 'failed':
      return 'text-red-400';
    case 'executing':
      return 'text-[var(--accent)]';
    case 'checkpoint':
      return 'text-amber-500';
    case 'paused':
      return 'text-yellow-500';
    default:
      return 'text-[var(--muted-foreground)]';
  }
}

function sourceLabel(source?: string): string | null {
  if (source === 'task') return 'Task';
  if (source === 'inbox') return 'Chat';
  return null;
}

// === Component ===

const SWIPE_THRESHOLD = 80;

interface InboxCardProps {
  item: InboxItem;
  onClick: (conversationId: string) => void;
  onArchive?: (conversationId: string) => void;
  selectable?: boolean;
  selected?: boolean;
  onToggleSelect?: (conversationId: string) => void;
}

export function InboxCard({ item, onClick, onArchive, selectable, selected, onToggleSelect }: InboxCardProps) {
  const isUnread = item.read_status === 'unread';
  const isAttention = item.priority === 'attention';
  const rawTitle = item.title || item.task_goal || item.last_message_text || 'Conversation';
  const title = rawTitle.length > 100 ? rawTitle.slice(0, 100) + '…' : rawTitle;
  const rawPreview = (item.task_goal || item.title) ? item.last_message_text : null;
  const preview = rawPreview && rawPreview.length > 100 ? rawPreview.slice(0, 100) + '…' : rawPreview;
  const badge = sourceLabel(item.source);

  // Swipe-to-archive gesture
  const { offsetX, isSwiping, handlers: swipeHandlers, reset: resetSwipe } = useSwipeAction({
    threshold: SWIPE_THRESHOLD,
    onSwipe: () => {
      hapticLight();
      onArchive?.(item.conversation_id);
    },
  });

  return (
    <div className="relative overflow-hidden">
      {/* Archive action behind the card */}
      {onArchive && (
        <div className="absolute inset-y-0 right-0 flex items-center justify-center w-[120px] bg-amber-600">
          <button
            onClick={(e) => {
              e.stopPropagation();
              onArchive(item.conversation_id);
              resetSwipe();
            }}
            className="flex flex-col items-center gap-1 text-white"
          >
            <ArchiveBoxIcon className="h-5 w-5" />
            <span className="text-xs font-medium">Archive</span>
          </button>
        </div>
      )}

      {/* Swipeable card content */}
      <div
        role="button"
        tabIndex={0}
        onClick={() => {
          if (isSwiping) return;
          if (offsetX !== 0) {
            resetSwipe();
            return;
          }
          if (selectable && onToggleSelect) {
            onToggleSelect(item.conversation_id);
          } else {
            onClick(item.conversation_id);
          }
        }}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            if (selectable && onToggleSelect) {
              onToggleSelect(item.conversation_id);
            } else {
              onClick(item.conversation_id);
            }
          }
        }}
        onTouchStart={onArchive ? swipeHandlers.onTouchStart : undefined}
        onTouchMove={onArchive ? swipeHandlers.onTouchMove : undefined}
        onTouchEnd={onArchive ? swipeHandlers.onTouchEnd : undefined}
        style={{
          transform: `translateX(${offsetX}px)`,
          transition: isSwiping ? 'none' : 'transform 0.2s ease-out',
        }}
        className={[
          'relative flex items-start gap-3 px-4 py-3 cursor-pointer transition-colors bg-[var(--background)]',
          'hover:bg-[var(--muted)]',
        ].join(' ')}
      >
        {/* Checkbox or status indicator */}
        <div className="mt-1.5 flex-shrink-0">
          {selectable ? (
            <div
              className={'h-4 w-4 rounded border-2 flex items-center justify-center transition-colors ' + (selected ? 'bg-[var(--accent)] border-[var(--accent)]' : 'border-[var(--muted-foreground)] bg-transparent')}
            >
              {selected && (
                <svg className="h-3 w-3 text-[var(--accent-foreground)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              )}
            </div>
          ) : (
            <div
              className={'h-2 w-2 rounded-full mt-0.5 ' + (isAttention ? 'bg-amber-500' : isUnread ? 'bg-blue-500' : 'bg-transparent')}
            />
          )}
        </div>

        {/* Main content */}
        <div className="flex-1 min-w-0">
          {/* Title row */}
          <div className="flex items-center justify-between gap-2">
            <p
              className={'text-sm leading-snug truncate ' + (isUnread ? 'font-medium text-[var(--foreground)]' : 'text-[var(--foreground)]/80')}
            >
              {title}
            </p>
            <span className="text-[11px] text-[var(--muted-foreground)]/70 whitespace-nowrap flex-shrink-0">
              {relativeTime(item.last_message_at)}
            </span>
          </div>

          {/* Preview text — lighter, single line */}
          {preview && (
            <p className="text-xs text-[var(--muted-foreground)]/40 truncate mt-0.5">
              {preview}
            </p>
          )}

          {/* Tags row — source badge + task stage */}
          {(badge || item.task_status) && (
            <div className="flex items-center gap-1.5 mt-1.5">
              {badge && (
                <span className="text-[10px] uppercase tracking-wider text-[var(--muted-foreground)]/50 font-medium">
                  {badge}
                </span>
              )}
              {badge && item.task_status && (
                <span className="text-[var(--muted-foreground)]/20">·</span>
              )}
              {item.task_status && (
                <span className={'inline-flex items-center gap-1 text-[11px] ' + statusTextColor(item.task_status)}>
                  <span className={'h-1.5 w-1.5 rounded-full flex-shrink-0 ' + statusDotColor(item.task_status)} />
                  {statusLabel(item.task_status)}
                </span>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
