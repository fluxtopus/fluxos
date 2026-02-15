'use client';

import { useEffect, useState, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  ArrowLeftIcon,
  ArrowPathIcon,
  CheckCircleIcon,
  ExclamationCircleIcon,
  PauseCircleIcon,
  PlayCircleIcon,
  TrashIcon,
  ClockIcon,
} from '@heroicons/react/24/outline';
import { motion } from 'framer-motion';
import { useAuthStore } from '../../../../store/authStore';
import {
  getAutomation,
  pauseAutomation,
  resumeAutomation,
  runAutomationNow,
  deleteAutomation,
} from '../../../../services/automationApi';
import type { AutomationDetail, ExecutionSummary } from '../../../../types/automation';

/**
 * Format cron expression to human-readable schedule
 */
function formatSchedule(cron: string): string {
  const parts = cron.split(' ');
  if (parts.length !== 5) return cron;

  const [minute, hour, dayOfMonth, month, dayOfWeek] = parts;

  if (dayOfMonth === '*' && month === '*' && dayOfWeek === '*') {
    const hourNum = parseInt(hour);
    const minuteNum = parseInt(minute);
    const period = hourNum >= 12 ? 'PM' : 'AM';
    const displayHour = hourNum === 0 ? 12 : hourNum > 12 ? hourNum - 12 : hourNum;
    const displayMinute = minuteNum.toString().padStart(2, '0');
    return `Every day at ${displayHour}:${displayMinute} ${period}`;
  }

  if (dayOfMonth === '*' && month === '*' && dayOfWeek !== '*') {
    const days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
    const dayNum = parseInt(dayOfWeek);
    const hourNum = parseInt(hour);
    const period = hourNum >= 12 ? 'PM' : 'AM';
    const displayHour = hourNum === 0 ? 12 : hourNum > 12 ? hourNum - 12 : hourNum;
    return `Every ${days[dayNum]} at ${displayHour}:00 ${period}`;
  }

  return cron;
}

/**
 * Format duration in seconds to readable string
 */
function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${mins}m ${secs}s`;
}

/**
 * Format datetime for display
 */
function formatDateTime(dateString: string | null): string {
  if (!dateString) return 'N/A';
  const date = new Date(dateString);
  return date.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });
}

/**
 * Format relative time for next run
 */
function formatRelativeTime(dateString: string | null): string {
  if (!dateString) return 'Not scheduled';

  const date = new Date(dateString);
  const now = new Date();
  const diffMs = date.getTime() - now.getTime();
  const diffMins = Math.floor(diffMs / (1000 * 60));
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffMins < 0) return 'Overdue';
  if (diffMins < 60) return `in ${diffMins} min`;
  if (diffHours < 24) return `in ${diffHours} hour${diffHours > 1 ? 's' : ''}`;
  if (diffDays === 1) return 'Tomorrow';
  return `in ${diffDays} days`;
}

/**
 * Execution Row Component
 */
function ExecutionRow({ execution }: { execution: ExecutionSummary }) {
  const isSuccess = execution.status === 'completed';
  const isFailed = execution.status === 'failed';
  const isRunning = execution.status === 'executing';

  return (
    <Link href={`/tasks/${execution.id}`}>
      <div className="flex items-center justify-between p-3 rounded-lg border border-[var(--border)] bg-[var(--card)] hover:border-[var(--accent)] transition-all cursor-pointer group">
        <div className="flex items-center gap-3">
          {isSuccess ? (
            <CheckCircleIcon className="w-5 h-5 text-green-500" />
          ) : isFailed ? (
            <ExclamationCircleIcon className="w-5 h-5 text-red-500" />
          ) : isRunning ? (
            <ArrowPathIcon className="w-5 h-5 text-blue-500 animate-spin" />
          ) : (
            <ClockIcon className="w-5 h-5 text-[var(--muted-foreground)]" />
          )}
          <div>
            <div className="text-sm text-[var(--foreground)]">
              {formatDateTime(execution.started_at)}
            </div>
            {execution.duration_seconds && (
              <div className="text-xs text-[var(--muted-foreground)]">
                Completed in {formatDuration(execution.duration_seconds)}
              </div>
            )}
            {execution.error_message && (
              <div className="text-xs text-red-500 truncate max-w-[300px]">
                {execution.error_message}
              </div>
            )}
          </div>
        </div>
        <span className="text-sm text-[var(--muted-foreground)] group-hover:text-[var(--accent)] transition-colors">
          View
        </span>
      </div>
    </Link>
  );
}

/**
 * Automation Detail Page
 */
export default function AutomationDetailPage() {
  const params = useParams();
  const router = useRouter();
  const { isAuthenticated } = useAuthStore();
  const [automation, setAutomation] = useState<AutomationDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  const automationId = params.id as string;

  const loadAutomation = useCallback(async () => {
    if (!isAuthenticated || !automationId) return;

    setLoading(true);
    setError(null);
    try {
      const data = await getAutomation(automationId);
      setAutomation(data);
    } catch (err) {
      console.error('Failed to load automation:', err);
      setError('Failed to load automation');
    } finally {
      setLoading(false);
    }
  }, [isAuthenticated, automationId]);

  useEffect(() => {
    loadAutomation();
  }, [loadAutomation]);

  const handlePause = async () => {
    if (!automation) return;
    setActionLoading('pause');
    try {
      await pauseAutomation(automation.id);
      await loadAutomation();
    } catch (err) {
      console.error('Failed to pause automation:', err);
    } finally {
      setActionLoading(null);
    }
  };

  const handleResume = async () => {
    if (!automation) return;
    setActionLoading('resume');
    try {
      await resumeAutomation(automation.id);
      await loadAutomation();
    } catch (err) {
      console.error('Failed to resume automation:', err);
    } finally {
      setActionLoading(null);
    }
  };

  const handleRunNow = async () => {
    if (!automation) return;
    setActionLoading('run');
    try {
      await runAutomationNow(automation.id);
      // Reload after a short delay to show the new execution
      setTimeout(loadAutomation, 1000);
    } catch (err) {
      console.error('Failed to run automation:', err);
    } finally {
      setActionLoading(null);
    }
  };

  const handleDelete = async () => {
    if (!automation) return;
    setActionLoading('delete');
    try {
      await deleteAutomation(automation.id);
      router.push('/automations');
    } catch (err) {
      console.error('Failed to delete automation:', err);
      setActionLoading(null);
    }
  };

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-8">
        <div className="flex items-center justify-center py-12">
          <ArrowPathIcon className="w-6 h-6 text-[var(--muted-foreground)] animate-spin" />
        </div>
      </div>
    );
  }

  if (error || !automation) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-8">
        <Link
          href="/automations"
          className="inline-flex items-center gap-2 text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors mb-8"
        >
          <ArrowLeftIcon className="w-4 h-4" />
          Automations
        </Link>
        <div className="text-center py-12">
          <p className="text-red-500">{error || 'Automation not found'}</p>
        </div>
      </div>
    );
  }

  const isPaused = !automation.schedule_enabled;
  const lastExecution = automation.last_execution;
  const isHealthy = !lastExecution || lastExecution.status === 'completed';

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      {/* Back link */}
      <Link
        href="/automations"
        className="inline-flex items-center gap-2 text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors mb-8"
      >
        <ArrowLeftIcon className="w-4 h-4" />
        Automations
      </Link>

      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-8"
      >
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-2">
              <h1 className="text-2xl font-bold text-[var(--foreground)] tracking-tight">
                {automation.name}
              </h1>
              {isPaused ? (
                <span className="px-2 py-0.5 text-xs font-mono rounded bg-[var(--muted)]/20 text-[var(--muted-foreground)]">
                  PAUSED
                </span>
              ) : isHealthy ? (
                <span className="px-2 py-0.5 text-xs font-mono rounded bg-green-500/20 text-green-600 dark:text-green-400">
                  ACTIVE
                </span>
              ) : (
                <span className="px-2 py-0.5 text-xs font-mono rounded bg-amber-500/20 text-amber-600 dark:text-amber-400">
                  NEEDS ATTENTION
                </span>
              )}
            </div>
            <p className="text-sm text-[var(--muted-foreground)] font-mono">
              {formatSchedule(automation.schedule_cron)}
              {automation.next_scheduled_run && !isPaused && (
                <span className="ml-2">
                  • Next run {formatRelativeTime(automation.next_scheduled_run)}
                </span>
              )}
            </p>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 mt-6">
          <button
            onClick={handleRunNow}
            disabled={actionLoading !== null}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-mono rounded border border-[var(--accent)] text-[var(--accent)] hover:bg-[var(--accent)] hover:text-white transition-all disabled:opacity-50"
          >
            {actionLoading === 'run' ? (
              <ArrowPathIcon className="w-4 h-4 animate-spin" />
            ) : (
              <PlayCircleIcon className="w-4 h-4" />
            )}
            Run Now
          </button>

          {isPaused ? (
            <button
              onClick={handleResume}
              disabled={actionLoading !== null}
              className="inline-flex items-center gap-2 px-4 py-2 text-sm font-mono rounded border border-[var(--border)] text-[var(--foreground)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-all disabled:opacity-50"
            >
              {actionLoading === 'resume' ? (
                <ArrowPathIcon className="w-4 h-4 animate-spin" />
              ) : (
                <PlayCircleIcon className="w-4 h-4" />
              )}
              Resume
            </button>
          ) : (
            <button
              onClick={handlePause}
              disabled={actionLoading !== null}
              className="inline-flex items-center gap-2 px-4 py-2 text-sm font-mono rounded border border-[var(--border)] text-[var(--foreground)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-all disabled:opacity-50"
            >
              {actionLoading === 'pause' ? (
                <ArrowPathIcon className="w-4 h-4 animate-spin" />
              ) : (
                <PauseCircleIcon className="w-4 h-4" />
              )}
              Pause
            </button>
          )}

          <button
            onClick={() => setShowDeleteConfirm(true)}
            disabled={actionLoading !== null}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-mono rounded border border-[var(--border)] text-red-500 hover:border-red-500 hover:bg-red-500/10 transition-all disabled:opacity-50"
          >
            <TrashIcon className="w-4 h-4" />
            Delete
          </button>
        </div>
      </motion.div>

      {/* Delete confirmation modal */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="bg-[var(--card)] border border-[var(--border)] rounded-lg p-6 max-w-sm mx-4"
          >
            <h3 className="text-lg font-bold text-[var(--foreground)] mb-2">
              Delete Automation?
            </h3>
            <p className="text-sm text-[var(--muted-foreground)] mb-6">
              This will remove the schedule. Past executions will be preserved.
            </p>
            <div className="flex items-center gap-3 justify-end">
              <button
                onClick={() => setShowDeleteConfirm(false)}
                className="px-4 py-2 text-sm font-mono rounded border border-[var(--border)] text-[var(--foreground)] hover:border-[var(--accent)] transition-all"
              >
                Cancel
              </button>
              <button
                onClick={handleDelete}
                disabled={actionLoading === 'delete'}
                className="px-4 py-2 text-sm font-mono rounded bg-red-500 text-white hover:bg-red-600 transition-all disabled:opacity-50"
              >
                {actionLoading === 'delete' ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </motion.div>
        </div>
      )}

      {/* Stats */}
      {automation.stats.total_runs > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="grid grid-cols-3 gap-4 mb-8"
        >
          <div className="p-4 rounded-lg border border-[var(--border)] bg-[var(--card)]">
            <div className="text-2xl font-bold text-[var(--foreground)]">
              {automation.stats.total_runs}
            </div>
            <div className="text-xs text-[var(--muted-foreground)] font-mono">TOTAL RUNS</div>
          </div>
          <div className="p-4 rounded-lg border border-[var(--border)] bg-[var(--card)]">
            <div className="text-2xl font-bold text-green-500">
              {Math.round(automation.stats.success_rate * 100)}%
            </div>
            <div className="text-xs text-[var(--muted-foreground)] font-mono">SUCCESS RATE</div>
          </div>
          <div className="p-4 rounded-lg border border-[var(--border)] bg-[var(--card)]">
            <div className="text-2xl font-bold text-[var(--foreground)]">
              {automation.stats.avg_duration_seconds
                ? formatDuration(automation.stats.avg_duration_seconds)
                : 'N/A'}
            </div>
            <div className="text-xs text-[var(--muted-foreground)] font-mono">AVG DURATION</div>
          </div>
        </motion.div>
      )}

      {/* Recent runs */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
      >
        <h2 className="text-sm font-mono text-[var(--muted-foreground)] mb-4 tracking-wider">
          RECENT RUNS
        </h2>
        {automation.recent_executions.length === 0 ? (
          <div className="text-center py-8 text-[var(--muted-foreground)]">
            No executions yet
          </div>
        ) : (
          <div className="space-y-2">
            {automation.recent_executions.map((execution) => (
              <ExecutionRow key={execution.id} execution={execution} />
            ))}
          </div>
        )}
      </motion.div>
    </div>
  );
}
