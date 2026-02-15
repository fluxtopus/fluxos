'use client';

import Link from 'next/link';
import { useCallback } from 'react';
import { formatDistanceToNow } from 'date-fns';
import {
  PlayIcon,
  PauseIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  ClockIcon,
  ArrowPathIcon,
  ArchiveBoxIcon,
} from '@heroicons/react/24/outline';
import type { Task, TaskStatus } from '../../types/task';
import { useSwipeAction } from '../../hooks/useSwipeAction';
import { hapticLight } from '../../utils/haptics';

/**
 * Parse timestamp as UTC. Server returns timestamps without 'Z' suffix,
 * which JavaScript interprets as local time. This function ensures UTC interpretation.
 */
function parseAsUTC(timestamp: string): Date {
  // If timestamp doesn't end with Z or timezone offset, append Z to force UTC
  if (!timestamp.endsWith('Z') && !timestamp.match(/[+-]\d{2}:\d{2}$/)) {
    return new Date(timestamp + 'Z');
  }
  return new Date(timestamp);
}

interface TaskCardProps {
  task: Task;
  onArchive?: (taskId: string) => void;
}

const statusConfig: Record<TaskStatus, {
  label: string;
  icon: typeof PlayIcon;
  color: string;
  bgColor: string;
  borderColor: string;
}> = {
  planning: {
    label: 'PLANNING',
    icon: ArrowPathIcon,
    color: 'text-[var(--accent)]',
    bgColor: 'bg-[var(--accent)]/10',
    borderColor: 'border-[var(--accent)]/30',
  },
  ready: {
    label: 'READY',
    icon: PlayIcon,
    color: 'text-[var(--muted-foreground)]',
    bgColor: 'bg-[var(--muted)]',
    borderColor: 'border-[var(--border)]',
  },
  executing: {
    label: 'RUNNING',
    icon: ArrowPathIcon,
    color: 'text-[var(--accent)]',
    bgColor: 'bg-[var(--accent)]/10',
    borderColor: 'border-[var(--accent)]/30',
  },
  paused: {
    label: 'PAUSED',
    icon: PauseIcon,
    color: 'text-[var(--muted-foreground)]',
    bgColor: 'bg-[var(--muted)]',
    borderColor: 'border-[var(--border)]',
  },
  checkpoint: {
    label: 'NEEDS DECISION',
    icon: ClockIcon,
    color: 'text-amber-500',
    bgColor: 'bg-amber-500/10',
    borderColor: 'border-amber-500/30',
  },
  completed: {
    label: 'DONE',
    icon: CheckCircleIcon,
    color: 'text-emerald-500',
    bgColor: 'bg-emerald-500/10',
    borderColor: 'border-emerald-500/30',
  },
  failed: {
    label: 'FAILED',
    icon: ExclamationTriangleIcon,
    color: 'text-[var(--destructive)]',
    bgColor: 'bg-[var(--destructive)]/10',
    borderColor: 'border-[var(--destructive)]/30',
  },
  cancelled: {
    label: 'CANCELLED',
    icon: ExclamationTriangleIcon,
    color: 'text-[var(--muted-foreground)]',
    bgColor: 'bg-[var(--muted)]',
    borderColor: 'border-[var(--border)]',
  },
  superseded: {
    label: 'SUPERSEDED',
    icon: ArrowPathIcon,
    color: 'text-[var(--muted-foreground)]',
    bgColor: 'bg-[var(--muted)]',
    borderColor: 'border-[var(--border)]',
  },
};

/**
 * TaskCard - Shows a single delegation summary.
 * Not a ticket, not a task - a delegation. Shows goal and results, not steps.
 */
export function TaskCard({ task, onArchive }: TaskCardProps) {
  const config = statusConfig[task.status];
  const StatusIcon = config.icon;
  const isActive = task.status === 'executing' || task.status === 'planning';

  // Count completed steps for progress
  const completedSteps = task.steps.filter(s => s.status === 'done').length;
  const totalSteps = task.steps.length;

  const handleSwipe = useCallback(() => {
    hapticLight();
    onArchive?.(task.id);
  }, [onArchive, task.id]);

  const { offsetX, isSwiping, handlers: swipeHandlers } = useSwipeAction({
    onSwipe: handleSwipe,
  });

  const card = (
    <Link
      href={`/tasks/${task.id}`}
      className="block group"
      onClick={(e) => { if (isSwiping || offsetX !== 0) e.preventDefault(); }}
    >
      <div className="p-5 rounded-lg border border-[var(--border)] bg-[var(--card)] hover:border-[var(--accent)]/50 transition-all duration-300">
        {/* Header: Status + Time */}
        <div className="flex items-center justify-between mb-4">
          <span className={`
            inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-[10px] font-mono tracking-wider border
            ${config.color} ${config.bgColor} ${config.borderColor}
          `}>
            <StatusIcon className={`w-3 h-3 ${isActive ? 'animate-spin' : ''}`} />
            {config.label}
          </span>
          <span className="text-xs font-mono text-[var(--muted-foreground)]">
            {formatDistanceToNow(parseAsUTC(task.updated_at), { addSuffix: true })}
          </span>
        </div>

        {/* Goal */}
        <h3 className="text-base font-semibold text-[var(--foreground)] line-clamp-2 mb-2 group-hover:text-[var(--accent)] transition-colors">
          {task.goal}
        </h3>

        {/* Progress bar for executing tasks */}
        {(task.status === 'executing' || task.status === 'planning') && (
          <div className="mt-4">
            <div className="flex items-center justify-between text-xs font-mono text-[var(--muted-foreground)] mb-2">
              <span>PROGRESS</span>
              <span className="text-[var(--accent)]">{Math.round(task.progress_percentage)}%</span>
            </div>
            <div className="h-1 bg-[var(--muted)] rounded-full overflow-hidden">
              <div
                className={`h-full bg-[var(--accent)] transition-all duration-500 ${task.progress_percentage === 0 ? 'animate-pulse w-full opacity-30' : ''}`}
                style={task.progress_percentage > 0 ? { width: `${task.progress_percentage}%` } : undefined}
              />
            </div>
          </div>
        )}

        {/* Completed summary — show last step output preview or fallback to step count */}
        {task.status === 'completed' && (
          <div className="mt-3 text-xs font-mono text-[var(--muted-foreground)] line-clamp-1">
            {(() => {
              const lastDone = [...task.steps].reverse().find(s => s.status === 'done' && s.outputs);
              if (lastDone?.outputs) {
                const summary = (lastDone.outputs as Record<string, unknown>).summary
                  || (lastDone.outputs as Record<string, unknown>).result
                  || (lastDone.outputs as Record<string, unknown>).message;
                if (typeof summary === 'string') {
                  return summary.length > 80 ? summary.substring(0, 80) + '…' : summary;
                }
              }
              return `${completedSteps}/${totalSteps} STEPS COMPLETED`;
            })()}
          </div>
        )}

        {/* Checkpoint indicator */}
        {task.status === 'checkpoint' && (
          <div className="mt-3 flex items-center gap-2 text-xs font-mono text-amber-500">
            <ClockIcon className="w-3.5 h-3.5" />
            <span>WAITING FOR YOUR DECISION</span>
          </div>
        )}

        {/* Failed summary - show which step failed and why */}
        {task.status === 'failed' && (
          <div className="mt-3 text-xs font-mono text-[var(--destructive)]">
            {(() => {
              const failedStep = task.steps.find(s => s.status === 'failed');
              if (failedStep) {
                const errorPreview = failedStep.error_message
                  ? failedStep.error_message.substring(0, 60) + (failedStep.error_message.length > 60 ? '...' : '')
                  : `Step "${failedStep.name}" failed`;
                return errorPreview;
              }
              return 'Task failed';
            })()}
          </div>
        )}

        {/* Hover hint */}
        <div className="mt-4 pt-3 border-t border-[var(--border)] opacity-0 group-hover:opacity-100 transition-opacity">
          <span className="text-xs font-mono text-[var(--accent)]">
            {task.status === 'checkpoint' ? 'REVIEW DECISION →' :
             task.status === 'failed' ? 'RETRY →' :
             'VIEW DETAILS →'}
          </span>
        </div>
      </div>
    </Link>
  );

  if (!onArchive) return card;

  return (
    <div className="relative overflow-hidden rounded-lg">
      {/* Archive action behind the card */}
      <div className="absolute inset-y-0 right-0 flex items-center justify-center w-[120px] bg-amber-600 rounded-r-lg">
        <div className="flex flex-col items-center gap-1 text-white">
          <ArchiveBoxIcon className="h-5 w-5" />
          <span className="text-xs font-medium">Archive</span>
        </div>
      </div>
      <div
        {...swipeHandlers}
        style={{
          transform: `translateX(${offsetX}px)`,
          transition: isSwiping ? 'none' : 'transform 0.2s ease-out',
        }}
      >
        {card}
      </div>
    </div>
  );
}
