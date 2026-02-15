'use client';

import { useEffect, useCallback, useMemo } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { PlusIcon, ArrowPathIcon } from '@heroicons/react/24/outline';
import { motion } from 'framer-motion';
import { TaskList, StatusFilter, DecisionStack, ATTENTION_STATUSES, COMPLETED_STATUSES } from '../../../components/Task';
import type { StatusFilterValue } from '../../../components/Task';
import { useAuthStore } from '../../../store/authStore';
import { useTaskStore } from '../../../store/taskStore';
import { PullToRefresh } from '../../../components/PullToRefresh';
import type { Task } from '../../../types/task';

// Only show filter when there are enough tasks to make filtering useful
const MIN_TASKS_FOR_FILTER = 6;

/**
 * My Tasks - The home page.
 * Futuristic Tentackl design with OKLCH colors.
 * Filter state is URL-based for bookmarkability and refresh persistence.
 */
export default function TasksPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { isAuthenticated } = useAuthStore();
  const { tasks, loading, loadTasks } = useTaskStore();

  // Compute counts for filter chips
  const filterCounts = useMemo(() => ({
    all: tasks.length,
    attention: tasks.filter((t: Task) => ATTENTION_STATUSES.includes(t.status)).length,
    completed: tasks.filter((t: Task) => COMPLETED_STATUSES.includes(t.status)).length,
  }), [tasks]);

  // Get status filter from URL; default to 'attention' when there are items needing the user
  const statusParam = searchParams.get('status');
  const statusFilter: StatusFilterValue = useMemo(() => {
    if (statusParam === 'attention' || statusParam === 'completed') return statusParam;
    if (statusParam === 'all') return 'all';
    // No explicit param — smart default
    return filterCounts.attention > 0 ? 'attention' : 'all';
  }, [statusParam, filterCounts.attention]);

  // Dynamic subtitle based on task state
  const subtitle = useMemo(() => {
    if (filterCounts.attention > 0) {
      return `${filterCounts.attention} THING${filterCounts.attention === 1 ? '' : 'S'} NEED${filterCounts.attention === 1 ? 'S' : ''} YOU`;
    }
    if (tasks.length > 0) return 'ALL RUNNING SMOOTHLY';
    return 'READY WHEN YOU ARE';
  }, [filterCounts.attention, tasks.length]);

  // Should we show the filter?
  const showFilter = tasks.length >= MIN_TASKS_FOR_FILTER;

  // Load tasks on mount and when auth changes
  useEffect(() => {
    if (isAuthenticated) {
      loadTasks(); // Always load all tasks, filter client-side for counts
    }
  }, [isAuthenticated, loadTasks]);

  // Update URL when filter changes
  const handleFilterChange = useCallback((value: StatusFilterValue) => {
    const params = new URLSearchParams(searchParams.toString());
    if (value === 'all') {
      params.delete('status');
    } else {
      params.set('status', value);
    }
    const queryString = params.toString();
    router.push(queryString ? `?${queryString}` : '/tasks', { scroll: false });
  }, [router, searchParams]);

  const handleRefresh = useCallback(async () => {
    if (isAuthenticated) {
      await loadTasks();
    }
  }, [isAuthenticated, loadTasks]);

  return (
    <PullToRefresh onRefresh={handleRefresh}>
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
            My Tasks
          </h1>
          <p className="text-sm text-[var(--muted-foreground)] mt-1 font-mono tracking-wide">
            {subtitle}
          </p>
        </div>
        {isAuthenticated && (
          <div className="flex items-center gap-2">
            <button
              onClick={handleRefresh}
              disabled={loading}
              className="inline-flex items-center justify-center w-10 h-10 text-[var(--muted-foreground)] rounded border border-[var(--border)] bg-[var(--card)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-all duration-200 disabled:opacity-50"
              title="Refresh"
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
        )}
      </motion.div>

      {/* Inline decision stack for checkpoint tasks */}
      <DecisionStack tasks={tasks} />

      {/* Status filter - only show when there are enough tasks */}
      {isAuthenticated && showFilter && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.1 }}
          className="sticky top-0 z-10 bg-[var(--background)] mb-6 -mx-4 px-4 py-2"
        >
          <StatusFilter
            value={statusFilter}
            onChange={handleFilterChange}
            counts={filterCounts}
          />
        </motion.div>
      )}

      {/* Task list */}
      <TaskList statusFilter={statusFilter} />
    </div>
    </PullToRefresh>
  );
}
