'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import { InboxIcon, ArrowRightIcon } from '@heroicons/react/24/outline';
import { useTaskStore } from '../../store/taskStore';
import { DecisionCard } from './DecisionCard';

/**
 * DecisionsQueue - Shows all pending checkpoints needing decisions.
 * A quick inbox for approvals, not a workflow management page.
 */
export function DecisionsQueue() {
  const {
    pendingCheckpoints,
    loading,
    errorMessage,
    loadPendingCheckpoints,
    approveCheckpoint,
    rejectCheckpoint,
  } = useTaskStore();

  useEffect(() => {
    loadPendingCheckpoints();
  }, [loadPendingCheckpoints]);

  const handleApprove = async (
    taskId: string,
    stepId: string,
    feedback?: string,
    learnPreference?: boolean
  ) => {
    await approveCheckpoint(taskId, stepId, feedback, learnPreference);
    // Refresh the queue after approval
    await loadPendingCheckpoints();
  };

  const handleReject = async (
    taskId: string,
    stepId: string,
    reason: string,
    learnPreference?: boolean
  ) => {
    await rejectCheckpoint(taskId, stepId, reason, learnPreference);
    // Refresh the queue after rejection
    await loadPendingCheckpoints();
  };

  if (loading && pendingCheckpoints.length === 0) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="flex flex-col items-center gap-3 text-[var(--muted-foreground)]">
          <div className="w-8 h-8 border-2 border-current border-t-transparent rounded-full animate-spin" />
          <span className="text-sm">Loading decisions...</span>
        </div>
      </div>
    );
  }

  if (errorMessage) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="text-center max-w-md px-4">
          <h3 className="text-lg font-medium text-[var(--foreground)] mb-2">
            Something went wrong
          </h3>
          <p className="text-sm text-[var(--muted-foreground)] mb-4">
            {errorMessage}
          </p>
          <button
            onClick={() => loadPendingCheckpoints()}
            className="px-4 py-2 text-sm font-medium rounded-lg bg-[var(--muted)] hover:bg-[var(--border)] transition-colors"
          >
            Try again
          </button>
        </div>
      </div>
    );
  }

  if (pendingCheckpoints.length === 0) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="text-center max-w-md px-4">
          <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-[var(--muted)] flex items-center justify-center">
            <InboxIcon className="w-8 h-8 text-[var(--muted-foreground)]" />
          </div>
          <h3 className="text-lg font-medium text-[var(--foreground)] mb-2">
            No pending decisions
          </h3>
          <p className="text-sm text-[var(--muted-foreground)] mb-6">
            When tasks need your approval, they&apos;ll appear here.
          </p>
          <Link
            href="/tasks"
            className="inline-flex items-center gap-2 text-sm text-[oklch(0.65_0.25_180)] hover:underline"
          >
            View all tasks
            <ArrowRightIcon className="w-4 h-4" />
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {pendingCheckpoints.map((checkpoint) => (
        <div key={`${checkpoint.task_id}-${checkpoint.step_id}`}>
          {/* Link to the task */}
          <Link
            href={`/tasks/${checkpoint.task_id}`}
            className="text-xs text-[var(--muted-foreground)] hover:text-[oklch(0.65_0.25_180)] mb-2 inline-block"
          >
            View full task →
          </Link>
          <DecisionCard
            checkpoint={checkpoint}
            onApprove={(feedback, learn) =>
              handleApprove(checkpoint.task_id, checkpoint.step_id, feedback, learn)
            }
            onReject={(reason, learn) =>
              handleReject(checkpoint.task_id, checkpoint.step_id, reason, learn)
            }
            isProcessing={loading}
          />
        </div>
      ))}
    </div>
  );
}
