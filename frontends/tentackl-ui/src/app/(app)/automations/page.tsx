'use client';

import { useEffect, useState, useCallback } from 'react';
import Link from 'next/link';
import { ArrowPathIcon, CheckCircleIcon, ExclamationCircleIcon, PauseCircleIcon } from '@heroicons/react/24/outline';
import { motion } from 'framer-motion';
import { useAuthStore } from '../../../store/authStore';
import { listAutomations } from '../../../services/automationApi';
import type { AutomationSummary, AutomationListResponse } from '../../../types/automation';

/**
 * Format cron expression to human-readable schedule
 */
function formatSchedule(cron: string | null, timezone: string): string {
  if (!cron) return 'No schedule';
  // Simple cron parsing for common patterns
  const parts = cron.split(' ');
  if (parts.length !== 5) return cron;

  const [minute, hour, dayOfMonth, month, dayOfWeek] = parts;

  // Daily at specific time
  if (dayOfMonth === '*' && month === '*' && dayOfWeek === '*') {
    const hourNum = parseInt(hour);
    const minuteNum = parseInt(minute);
    const period = hourNum >= 12 ? 'PM' : 'AM';
    const displayHour = hourNum === 0 ? 12 : hourNum > 12 ? hourNum - 12 : hourNum;
    const displayMinute = minuteNum.toString().padStart(2, '0');
    return `Daily at ${displayHour}:${displayMinute} ${period}`;
  }

  // Weekly patterns
  if (dayOfMonth === '*' && month === '*' && dayOfWeek !== '*') {
    const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    const dayNum = parseInt(dayOfWeek);
    const hourNum = parseInt(hour);
    const period = hourNum >= 12 ? 'PM' : 'AM';
    const displayHour = hourNum === 0 ? 12 : hourNum > 12 ? hourNum - 12 : hourNum;
    return `Every ${days[dayNum]} at ${displayHour}:00 ${period}`;
  }

  return cron;
}

/**
 * Format relative time for last execution
 */
function formatRelativeTime(dateString: string | null): string {
  if (!dateString) return 'Never run';

  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / (1000 * 60));
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins} min ago`;
  if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays} days ago`;

  return date.toLocaleDateString();
}

/**
 * Automation Card Component
 */
function AutomationCard({ automation }: { automation: AutomationSummary }) {
  const lastExecution = automation.last_execution;
  const isHealthy = !lastExecution || lastExecution.status === 'completed';
  const isPaused = !automation.schedule_enabled;

  return (
    <Link href={`/automations/${automation.id}`}>
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className={`
          group relative p-4 rounded-lg border transition-all duration-200 cursor-pointer
          ${isPaused
            ? 'border-[var(--border)] bg-[var(--card)] opacity-60'
            : isHealthy
              ? 'border-[var(--border)] bg-[var(--card)] hover:border-[var(--accent)]'
              : 'border-amber-500/50 bg-amber-500/5 hover:border-amber-500'
          }
        `}
      >
        <div className="flex items-start justify-between gap-4">
          {/* Status indicator */}
          <div className="flex-shrink-0 mt-0.5">
            {isPaused ? (
              <PauseCircleIcon className="w-5 h-5 text-[var(--muted-foreground)]" />
            ) : isHealthy ? (
              <CheckCircleIcon className="w-5 h-5 text-green-500" />
            ) : (
              <ExclamationCircleIcon className="w-5 h-5 text-amber-500" />
            )}
          </div>

          {/* Content */}
          <div className="flex-1 min-w-0">
            <h3 className="font-medium text-[var(--foreground)] truncate group-hover:text-[var(--accent)] transition-colors">
              {automation.name}
            </h3>
            <p className="text-sm text-[var(--muted-foreground)] mt-1 font-mono">
              {formatSchedule(automation.schedule_cron, automation.schedule_timezone)}
            </p>
          </div>

          {/* Last run info */}
          <div className="flex-shrink-0 text-right">
            {lastExecution ? (
              <div className={`text-sm ${isHealthy ? 'text-[var(--muted-foreground)]' : 'text-amber-500'}`}>
                {isHealthy ? (
                  <>
                    <CheckCircleIcon className="w-3 h-3 inline mr-1" />
                    {formatRelativeTime(lastExecution.completed_at || lastExecution.started_at)}
                  </>
                ) : (
                  <>
                    <ExclamationCircleIcon className="w-3 h-3 inline mr-1" />
                    Failed {formatRelativeTime(lastExecution.started_at)}
                  </>
                )}
              </div>
            ) : (
              <span className="text-sm text-[var(--muted-foreground)]">Never run</span>
            )}
          </div>
        </div>

        {/* Stats row */}
        {automation.stats.total_runs > 0 && (
          <div className="mt-3 pt-3 border-t border-[var(--border)] flex items-center gap-4 text-xs text-[var(--muted-foreground)] font-mono">
            <span>{automation.stats.total_runs} runs</span>
            <span>{Math.round(automation.stats.success_rate * 100)}% success</span>
            {automation.stats.avg_duration_seconds && (
              <span>{Math.round(automation.stats.avg_duration_seconds)}s avg</span>
            )}
          </div>
        )}
      </motion.div>
    </Link>
  );
}

/**
 * Automations Page - Fleet overview
 * Magic moment: All green, close in 3 seconds.
 */
export default function AutomationsPage() {
  const { isAuthenticated } = useAuthStore();
  const [data, setData] = useState<AutomationListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadAutomations = useCallback(async () => {
    if (!isAuthenticated) return;

    setLoading(true);
    setError(null);
    try {
      const response = await listAutomations();
      setData(response);
    } catch (err) {
      console.error('Failed to load automations:', err);
      setError('Failed to load automations');
    } finally {
      setLoading(false);
    }
  }, [isAuthenticated]);

  useEffect(() => {
    loadAutomations();
  }, [loadAutomations]);

  const handleRefresh = () => {
    loadAutomations();
  };

  const automations = data?.automations || [];
  const needsAttention = data?.needs_attention || 0;
  const allHealthy = needsAttention === 0 && automations.length > 0;

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="flex items-center justify-between mb-8"
      >
        <div>
          <h1 className="text-2xl font-bold text-[var(--foreground)] tracking-tight">
            Automations
          </h1>
          <p className="text-sm text-[var(--muted-foreground)] mt-1 font-mono tracking-wide">
            YOUR SCHEDULED WORKFLOWS
          </p>
        </div>
        {isAuthenticated && (
          <button
            onClick={handleRefresh}
            disabled={loading}
            className="inline-flex items-center justify-center w-10 h-10 text-[var(--muted-foreground)] rounded border border-[var(--border)] bg-[var(--card)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-all duration-200 disabled:opacity-50"
            title="Refresh"
          >
            <ArrowPathIcon className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        )}
      </motion.div>

      {/* Status banner */}
      {!loading && automations.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.1 }}
          className={`
            mb-6 p-4 rounded-lg border flex items-center justify-between
            ${allHealthy
              ? 'border-green-500/30 bg-green-500/5'
              : 'border-amber-500/30 bg-amber-500/5'
            }
          `}
        >
          <div className="flex items-center gap-3">
            {allHealthy ? (
              <>
                <CheckCircleIcon className="w-5 h-5 text-green-500" />
                <span className="text-green-600 dark:text-green-400 font-medium">
                  All systems running
                </span>
              </>
            ) : (
              <>
                <ExclamationCircleIcon className="w-5 h-5 text-amber-500" />
                <span className="text-amber-600 dark:text-amber-400 font-medium">
                  {needsAttention} need{needsAttention !== 1 ? 's' : ''} attention
                </span>
              </>
            )}
          </div>
          <span className="text-sm text-[var(--muted-foreground)] font-mono">
            {automations.length} automation{automations.length !== 1 ? 's' : ''}
          </span>
        </motion.div>
      )}

      {/* Content */}
      {loading ? (
        <div className="space-y-3">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="p-4 rounded-lg border border-[var(--border)] bg-[var(--card)] animate-pulse">
              <div className="flex items-start gap-4">
                <div className="w-5 h-5 bg-[var(--muted)] rounded-full flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="h-5 w-2/3 bg-[var(--muted)] rounded mb-2" />
                  <div className="h-4 w-1/3 bg-[var(--muted)] rounded" />
                </div>
                <div className="h-4 w-20 bg-[var(--muted)] rounded flex-shrink-0" />
              </div>
            </div>
          ))}
        </div>
      ) : error ? (
        <div className="text-center py-12">
          <p className="text-red-500">{error}</p>
          <button
            onClick={handleRefresh}
            className="mt-4 text-sm text-[var(--accent)] hover:underline"
          >
            Try again
          </button>
        </div>
      ) : automations.length === 0 ? (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="text-center py-12"
        >
          <ArrowPathIcon className="w-12 h-12 text-[var(--muted-foreground)] mx-auto mb-4 opacity-50" />
          <h3 className="text-lg font-medium text-[var(--foreground)] mb-2">
            No automations yet
          </h3>
          <p className="text-sm text-[var(--muted-foreground)] max-w-sm mx-auto">
            When you complete a task and choose &quot;Make this recurring&quot;, it will appear here.
          </p>
        </motion.div>
      ) : (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.3, delay: 0.2 }}
          className="space-y-3"
        >
          {automations.map((automation, index) => (
            <motion.div
              key={automation.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.1 + index * 0.05 }}
            >
              <AutomationCard automation={automation} />
            </motion.div>
          ))}
        </motion.div>
      )}
    </div>
  );
}
