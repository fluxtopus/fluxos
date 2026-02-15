'use client';

import { useEffect, useState, useRef } from 'react';
import { PlusIcon, ChevronDownIcon, ChevronUpIcon } from '@heroicons/react/24/outline';
import Link from 'next/link';
import { motion } from 'framer-motion';
import { useTaskStore } from '../../store/taskStore';
import { useAuthStore } from '../../store/authStore';
import { TaskCard } from './TaskCard';
import { ATTENTION_STATUSES, COMPLETED_STATUSES } from './StatusFilter';
import type { StatusFilterValue } from './StatusFilter';
import type { Task, TaskStatus } from '../../types/task';

const RECENT_TASKS_LIMIT = 5;
const LIST_POLLING_INTERVAL = 10000; // 10 seconds for list view

// Statuses that indicate active tasks that should trigger polling
const ACTIVE_TASK_STATUSES = ['planning', 'executing', 'checkpoint', 'ready'];

interface TaskListProps {
  /**
   * @deprecated Use statusFilter instead.
   */
  filterStatus?: TaskStatus;
  /**
   * Filter to apply: 'all', 'attention', or 'completed'
   */
  statusFilter?: StatusFilterValue;
}

/**
 * TaskList - Shows user's tasks with futuristic Tentackl design.
 * Shows login prompt for unauthenticated users.
 * Polls for updates when there are active tasks.
 */
export function TaskList({ filterStatus, statusFilter = 'all' }: TaskListProps) {
  const { tasks, loading, errorMessage, loadTasks } = useTaskStore();
  const { isAuthenticated, openAuthModal } = useAuthStore();
  const [showAllRecent, setShowAllRecent] = useState(false);
  const pollingRef = useRef<NodeJS.Timeout | null>(null);

  // Check if there are any active tasks that need polling
  const hasActiveTasks = tasks.some((t: Task) =>
    ACTIVE_TASK_STATUSES.includes(t.status)
  );

  // Initial load (only if filterStatus prop is used - legacy support)
  useEffect(() => {
    if (isAuthenticated && filterStatus) {
      loadTasks(filterStatus);
    }
  }, [loadTasks, filterStatus, isAuthenticated]);

  // Polling for active tasks
  useEffect(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }

    if (isAuthenticated && hasActiveTasks) {
      pollingRef.current = setInterval(() => {
        loadTasks(filterStatus, { silent: true });
      }, LIST_POLLING_INTERVAL);
    }

    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [isAuthenticated, hasActiveTasks, filterStatus, loadTasks]);

  // Apply client-side filter based on statusFilter
  const getFilteredTasks = (): Task[] => {
    if (statusFilter === 'attention') {
      return tasks.filter((t: Task) => ATTENTION_STATUSES.includes(t.status));
    }
    if (statusFilter === 'completed') {
      return tasks.filter((t: Task) => COMPLETED_STATUSES.includes(t.status));
    }
    return tasks; // 'all'
  };

  const filteredTasks = getFilteredTasks();

  // Group tasks: active first, then recent
  const activeTasks = filteredTasks.filter((t: Task) =>
    ATTENTION_STATUSES.includes(t.status)
  );
  const allCompletedTasks = filteredTasks.filter((t: Task) =>
    COMPLETED_STATUSES.includes(t.status)
  );

  // Limit recent tasks unless "Show all" is clicked
  const completedTasks = showAllRecent
    ? allCompletedTasks
    : allCompletedTasks.slice(0, RECENT_TASKS_LIMIT);
  const hasMoreTasks = allCompletedTasks.length > RECENT_TASKS_LIMIT;

  // Contextual empty state message based on filter
  const getEmptyStateMessage = () => {
    switch (statusFilter) {
      case 'attention':
        return {
          title: 'Nothing needs your attention',
          subtitle: 'All caught up! Your tasks are running smoothly.',
        };
      case 'completed':
        return {
          title: 'No completed tasks yet',
          subtitle: 'Tasks will appear here once they finish.',
        };
      default:
        return {
          title: 'No tasks yet',
          subtitle: "Tell me what you need done and I'll handle it for you",
        };
    }
  };

  // Login prompt for unauthenticated users
  if (!isAuthenticated) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="text-center">
          <div className="relative inline-block mb-6">
            <svg className="w-24 h-24 text-[var(--border)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={0.5} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="w-3 h-3 rounded-full bg-[var(--muted)]" />
            </div>
          </div>
          <p className="font-mono text-sm text-[var(--muted-foreground)] mb-1">
            Sign in to start delegating
          </p>
          <p className="font-mono text-[10px] text-[var(--muted-foreground)]/60 mb-6">
            Tell me what you need done and I&apos;ll handle it for you
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
            <button
              onClick={() => openAuthModal('login')}
              className="flex items-center justify-center gap-2 px-6 py-3 font-mono text-sm tracking-wider uppercase rounded border bg-[var(--accent)] border-[var(--accent)] text-white hover:opacity-90 transition-all"
            >
              SIGN IN
            </button>
            <Link
              href="/playground"
              className="flex items-center justify-center gap-2 px-6 py-3 font-mono text-sm tracking-wider uppercase rounded border border-[var(--border)] bg-[var(--card)] text-[var(--muted-foreground)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-all"
            >
              TRY PLAYGROUND
            </Link>
          </div>
        </div>
      </div>
    );
  }

  if (loading && tasks.length === 0) {
    return (
      <div className="space-y-3">
        {[...Array(3)].map((_, i) => (
          <div key={i} className="p-5 rounded-lg border border-[var(--border)] bg-[var(--card)] animate-pulse">
            <div className="flex items-center justify-between mb-4">
              <div className="h-5 w-24 bg-[var(--muted)] rounded" />
              <div className="h-4 w-16 bg-[var(--muted)] rounded" />
            </div>
            <div className="h-5 w-3/4 bg-[var(--muted)] rounded mb-2" />
            <div className="h-4 w-1/2 bg-[var(--muted)] rounded" />
          </div>
        ))}
      </div>
    );
  }

  if (errorMessage) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="text-center max-w-md px-4">
          <div className="w-14 h-14 mx-auto mb-4 rounded-xl bg-[var(--destructive)]/10 border border-[var(--destructive)]/30 flex items-center justify-center">
            <span className="text-2xl text-[var(--destructive)]">!</span>
          </div>
          <h3 className="text-lg font-bold text-[var(--foreground)] mb-2">
            Something went wrong
          </h3>
          <p className="text-sm text-[var(--muted-foreground)] mb-4">
            {errorMessage}
          </p>
          <button
            onClick={() => loadTasks(filterStatus)}
            className="px-4 py-2 text-xs font-mono tracking-wider rounded-lg bg-[var(--muted)] border border-[var(--border)] hover:border-[var(--accent)] transition-colors text-[var(--foreground)]"
          >
            TRY AGAIN
          </button>
        </div>
      </div>
    );
  }

  if (filteredTasks.length === 0) {
    const emptyState = getEmptyStateMessage();
    const showNewTaskButton = statusFilter === 'all';

    return (
      <div className="flex items-center justify-center py-16">
        <div className="text-center">
          <div className="relative inline-block mb-6">
            <svg className="w-24 h-24 text-[var(--border)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              {statusFilter === 'attention' ? (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={0.5} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              ) : (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={0.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
              )}
            </svg>
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="w-3 h-3 rounded-full bg-[var(--muted)]" />
            </div>
          </div>
          <p className="font-mono text-sm text-[var(--muted-foreground)] mb-1">
            {emptyState.title}
          </p>
          <p className="font-mono text-[10px] text-[var(--muted-foreground)]/60 mb-6">
            {emptyState.subtitle}
          </p>
          {showNewTaskButton && (
            <Link
              href="/tasks/new"
              className="inline-flex items-center justify-center gap-2 px-6 py-3 font-mono text-sm tracking-wider uppercase rounded border bg-[var(--accent)] border-[var(--accent)] text-white hover:opacity-90 transition-all"
            >
              <PlusIcon className="w-4 h-4" />
              NEW TASK
            </Link>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Active tasks */}
      {activeTasks.length > 0 && (
        <motion.section
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
        >
          <h2 className="text-xs font-mono tracking-wider text-[var(--accent)] mb-4 flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-[var(--accent)] animate-pulse" />
            ACTIVE
          </h2>
          <div className="grid gap-3">
            {activeTasks.map((task: Task, index: number) => (
              <motion.div
                key={task.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, delay: index * 0.05 }}
              >
                <TaskCard task={task} />
              </motion.div>
            ))}
          </div>
        </motion.section>
      )}

      {/* Completed tasks */}
      {completedTasks.length > 0 && (
        <motion.section
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.1 }}
        >
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xs font-mono tracking-wider text-[var(--muted-foreground)]">
              RECENT
            </h2>
            {hasMoreTasks && (
              <span className="text-xs font-mono text-[var(--muted-foreground)]">
                {showAllRecent
                  ? `${allCompletedTasks.length} tasks`
                  : `${RECENT_TASKS_LIMIT} of ${allCompletedTasks.length}`}
              </span>
            )}
          </div>
          <div className="grid gap-3">
            {completedTasks.map((task: Task, index: number) => (
              <motion.div
                key={task.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, delay: index * 0.05 }}
              >
                <TaskCard task={task} />
              </motion.div>
            ))}
          </div>

          {/* Show more/less toggle */}
          {hasMoreTasks && (
            <button
              onClick={() => setShowAllRecent(!showAllRecent)}
              className="w-full mt-4 py-3 flex items-center justify-center gap-2 text-xs font-mono tracking-wider text-[var(--muted-foreground)] hover:text-[var(--accent)] border border-[var(--border)] rounded-lg hover:border-[var(--accent)]/50 transition-colors"
            >
              {showAllRecent ? (
                <>
                  <ChevronUpIcon className="w-4 h-4" />
                  SHOW LESS
                </>
              ) : (
                <>
                  <ChevronDownIcon className="w-4 h-4" />
                  SHOW {allCompletedTasks.length - RECENT_TASKS_LIMIT} MORE
                </>
              )}
            </button>
          )}
        </motion.section>
      )}
    </div>
  );
}
