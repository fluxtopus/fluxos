'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import { formatDistanceToNow } from 'date-fns';
import {
  CheckCircleIcon,
  ExclamationTriangleIcon,
  ClockIcon,
  ArrowPathIcon,
  XMarkIcon,
  PlusIcon,
} from '@heroicons/react/24/outline';
import { useAuthStore } from '../../../store/authStore';
import { useTaskStore } from '../../../store/taskStore';
import { approveCheckpoint, rejectCheckpoint } from '../../../services/taskApi';
import type { Task, TaskStatus, Checkpoint } from '../../../types/task';

// Parse timestamp as UTC
function parseAsUTC(timestamp: string): Date {
  if (!timestamp.endsWith('Z') && !timestamp.match(/[+-]\d{2}:\d{2}$/)) {
    return new Date(timestamp + 'Z');
  }
  return new Date(timestamp);
}

// Status configuration
const STATUS_CONFIG: Record<string, { label: string; color: string; borderColor: string }> = {
  planning: { label: 'PLANNING', color: 'text-[var(--accent)]', borderColor: 'border-[var(--accent)]/30' },
  executing: { label: 'RUNNING', color: 'text-[var(--accent)]', borderColor: 'border-[var(--accent)]/30' },
  checkpoint: { label: 'CHECKPOINT', color: 'text-amber-500', borderColor: 'border-amber-500/30' },
  completed: { label: 'DONE', color: 'text-emerald-500', borderColor: 'border-emerald-500/30' },
  failed: { label: 'FAILED', color: 'text-[var(--destructive)]', borderColor: 'border-[var(--destructive)]/30' },
  cancelled: { label: 'CANCELLED', color: 'text-[var(--muted-foreground)]', borderColor: 'border-[var(--border)]' },
  paused: { label: 'PAUSED', color: 'text-[var(--muted-foreground)]', borderColor: 'border-[var(--border)]' },
};

type FilterValue = 'all' | 'running' | 'attention' | 'completed' | 'failed';

/**
 * Activity Page
 *
 * Shows what agents are doing - real-time feed of task executions.
 * Hi-tech terminal aesthetic.
 */
export default function ActivityPage() {
  const { isAuthenticated } = useAuthStore();
  const {
    tasks,
    loading,
    loadTasks,
    pendingCheckpoints,
    loadPendingCheckpoints,
  } = useTaskStore();

  // Load data
  useEffect(() => {
    if (isAuthenticated) {
      loadTasks();
      loadPendingCheckpoints();
    }
  }, [isAuthenticated, loadTasks, loadPendingCheckpoints]);

  // Poll for updates
  useEffect(() => {
    if (!isAuthenticated) return;
    const interval = setInterval(() => {
      loadTasks(undefined, { silent: true });
      loadPendingCheckpoints();
    }, 10000);
    return () => clearInterval(interval);
  }, [isAuthenticated, loadTasks, loadPendingCheckpoints]);

  // All tasks are runs (templates are not returned by API)
  const taskRuns = tasks;

  // Categorize tasks
  const runningTasks = taskRuns.filter((t: Task) =>
    t.status === 'executing' || t.status === 'planning'
  );
  const checkpointTasks = taskRuns.filter((t: Task) => t.status === 'checkpoint');
  const recentTasks = taskRuns.filter((t: Task) =>
    t.status === 'completed' || t.status === 'failed' || t.status === 'cancelled'
  ).slice(0, 20);

  const handleApprove = async (taskId: string, stepId: string) => {
    try {
      await approveCheckpoint(taskId, stepId, { learn_preference: true });
      loadTasks();
      loadPendingCheckpoints();
    } catch (error) {
      console.error('Failed to approve:', error);
    }
  };

  const handleReject = async (taskId: string, stepId: string) => {
    try {
      await rejectCheckpoint(taskId, stepId, { reason: 'Rejected', learn_preference: true });
      loadTasks();
      loadPendingCheckpoints();
    } catch (error) {
      console.error('Failed to reject:', error);
    }
  };

  return (
    <div className="min-h-screen">
      {/* Header */}
      <div className="border-b border-[var(--border)] bg-[var(--card)]">
        <div className="max-w-4xl mx-auto px-6 py-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-xl font-bold text-[var(--foreground)] tracking-tight">
                Activity
              </h1>
              <p className="text-xs font-mono text-[var(--muted-foreground)] mt-1 tracking-wider">
                REAL-TIME AGENT STATUS
              </p>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={() => loadTasks()}
                disabled={loading}
                className="p-2 rounded border border-[var(--border)] bg-[var(--background)] text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:border-[var(--accent)] transition-colors disabled:opacity-50"
              >
                <ArrowPathIcon className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              </button>
              <Link
                href="/tasks/new"
                className="flex items-center gap-2 px-3 py-2 text-xs font-mono tracking-wider bg-[var(--accent)] text-[var(--accent-foreground)] rounded-md hover:opacity-90 transition-opacity"
              >
                <PlusIcon className="w-4 h-4" />
                CREATE
              </Link>
            </div>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="max-w-4xl mx-auto px-6 py-8">
        {loading && taskRuns.length === 0 ? (
          <div className="flex items-center justify-center py-20">
            <div className="text-center">
              <div className="w-8 h-8 border-2 border-[var(--accent)] border-t-transparent rounded-full animate-spin mx-auto mb-4" />
              <p className="text-xs font-mono text-[var(--muted-foreground)] tracking-wider">
                LOADING...
              </p>
            </div>
          </div>
        ) : (
          <div className="space-y-8">
            {/* Running Now */}
            {runningTasks.length > 0 && (
              <section>
                <div className="flex items-center gap-2 mb-4">
                  <div className="w-2 h-2 rounded-full bg-[var(--accent)] animate-pulse" />
                  <h2 className="text-xs font-mono tracking-wider text-[var(--accent)]">
                    RUNNING NOW ({runningTasks.length})
                  </h2>
                </div>
                <div className="space-y-2">
                  {runningTasks.map((task) => (
                    <ActivityRow
                      key={task.id}
                      task={task}
                      checkpoint={pendingCheckpoints.find((c) => c.task_id === task.id)}
                      onApprove={handleApprove}
                      onReject={handleReject}
                    />
                  ))}
                </div>
              </section>
            )}

            {/* Needs Attention */}
            {checkpointTasks.length > 0 && (
              <section>
                <div className="flex items-center gap-2 mb-4">
                  <div className="w-2 h-2 rounded-full bg-amber-500" />
                  <h2 className="text-xs font-mono tracking-wider text-amber-500">
                    NEEDS ATTENTION ({checkpointTasks.length})
                  </h2>
                </div>
                <div className="space-y-2">
                  {checkpointTasks.map((task) => (
                    <ActivityRow
                      key={task.id}
                      task={task}
                      checkpoint={pendingCheckpoints.find((c) => c.task_id === task.id)}
                      onApprove={handleApprove}
                      onReject={handleReject}
                    />
                  ))}
                </div>
              </section>
            )}

            {/* Recent */}
            {recentTasks.length > 0 && (
              <section>
                <h2 className="text-xs font-mono tracking-wider text-[var(--muted-foreground)] mb-4">
                  RECENT
                </h2>
                <div className="space-y-2">
                  {recentTasks.map((task) => (
                    <ActivityRow key={task.id} task={task} />
                  ))}
                </div>
              </section>
            )}

            {/* Empty State */}
            {taskRuns.length === 0 && (
              <div className="text-center py-20">
                <div className="inline-block p-4 rounded border border-[var(--border)] mb-4">
                  <div className="w-8 h-8 border border-dashed border-[var(--muted-foreground)] rounded" />
                </div>
                <p className="text-sm text-[var(--muted-foreground)] mb-1">
                  No activity yet
                </p>
                <p className="text-xs font-mono text-[var(--muted-foreground)]/60 mb-6">
                  Create a task to get started
                </p>
                <Link
                  href="/tasks/new"
                  className="inline-flex items-center gap-2 px-4 py-2 text-xs font-mono tracking-wider bg-[var(--accent)] text-[var(--accent-foreground)] rounded-md hover:opacity-90 transition-opacity"
                >
                  <PlusIcon className="w-4 h-4" />
                  CREATE
                </Link>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ============================================
// Activity Row Component
// ============================================

interface ActivityRowProps {
  task: Task;
  checkpoint?: Checkpoint;
  onApprove?: (taskId: string, stepId: string) => void;
  onReject?: (taskId: string, stepId: string) => void;
}

function ActivityRow({ task, checkpoint, onApprove, onReject }: ActivityRowProps) {
  const config = STATUS_CONFIG[task.status] || STATUS_CONFIG.completed;
  const isRunning = task.status === 'executing' || task.status === 'planning';
  const isCheckpoint = task.status === 'checkpoint';

  // Progress
  const completedSteps = task.steps.filter((s) => s.status === 'done').length;
  const currentStep = task.steps.find((s) => s.status === 'running' || s.status === 'pending');

  return (
    <div className={`p-4 rounded border ${config.borderColor} bg-[var(--card)] hover:border-[var(--accent)]/50 transition-colors`}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          {/* Status + Time */}
          <div className="flex items-center gap-3 mb-2">
            <span className={`text-[10px] font-mono tracking-wider ${config.color}`}>
              {isRunning && <span className="inline-block w-1.5 h-1.5 rounded-full bg-current mr-1.5 animate-pulse" />}
              {config.label}
            </span>
            <span className="text-[10px] font-mono text-[var(--muted-foreground)]">
              {formatDistanceToNow(parseAsUTC(task.updated_at), { addSuffix: true })}
            </span>
          </div>

          {/* Goal */}
          <Link href={`/tasks/${task.id}`} className="block">
            <p className="text-sm text-[var(--foreground)] hover:text-[var(--accent)] transition-colors line-clamp-1">
              {task.goal}
            </p>
          </Link>

          {/* Progress for running tasks */}
          {isRunning && task.steps.length > 0 && (
            <div className="mt-3 flex items-center gap-3">
              <div className="flex-1 h-1 bg-[var(--muted)] rounded-full overflow-hidden">
                <div
                  className="h-full bg-[var(--accent)] transition-all duration-500"
                  style={{ width: `${(completedSteps / task.steps.length) * 100}%` }}
                />
              </div>
              <span className="text-[10px] font-mono text-[var(--muted-foreground)] whitespace-nowrap">
                {completedSteps}/{task.steps.length}
              </span>
              {currentStep && (
                <span className="text-[10px] font-mono text-[var(--muted-foreground)] truncate max-w-[150px]">
                  {currentStep.name}
                </span>
              )}
            </div>
          )}

          {/* Checkpoint actions */}
          {isCheckpoint && checkpoint && onApprove && onReject && (
            <div className="mt-3 flex items-center gap-2">
              <span className="text-xs text-[var(--muted-foreground)] mr-2">
                {checkpoint.checkpoint_name || 'Review required'}
              </span>
              <button
                onClick={() => onApprove(task.id, checkpoint.step_id)}
                className="inline-flex items-center gap-1 px-3 py-1.5 text-[10px] font-mono tracking-wider text-emerald-500 rounded border border-emerald-500/30 hover:bg-emerald-500/10 transition-colors"
              >
                <CheckCircleIcon className="w-3 h-3" />
                APPROVE
              </button>
              <button
                onClick={() => onReject(task.id, checkpoint.step_id)}
                className="inline-flex items-center gap-1 px-3 py-1.5 text-[10px] font-mono tracking-wider text-[var(--destructive)] rounded border border-[var(--destructive)]/30 hover:bg-[var(--destructive)]/10 transition-colors"
              >
                <XMarkIcon className="w-3 h-3" />
                REJECT
              </button>
            </div>
          )}

          {/* Error message for failed tasks */}
          {task.status === 'failed' && (
            <p className="mt-2 text-xs font-mono text-[var(--destructive)] line-clamp-1">
              {task.steps.find((s) => s.status === 'failed')?.error_message || 'Task failed'}
            </p>
          )}
        </div>

        {/* Result indicator */}
        <div className="flex-shrink-0">
          {task.status === 'completed' && (
            <CheckCircleIcon className="w-5 h-5 text-emerald-500" />
          )}
          {task.status === 'failed' && (
            <ExclamationTriangleIcon className="w-5 h-5 text-[var(--destructive)]" />
          )}
          {isCheckpoint && (
            <ClockIcon className="w-5 h-5 text-amber-500" />
          )}
        </div>
      </div>
    </div>
  );
}
