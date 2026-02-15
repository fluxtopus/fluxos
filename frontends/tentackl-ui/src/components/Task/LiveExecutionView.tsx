'use client';

import {
  ArrowPathIcon,
  CheckCircleIcon,
  ExclamationCircleIcon,
  PauseIcon,
} from '@heroicons/react/24/outline';
import type { Task, TaskStep } from '../../types/task';

/** Convert snake_case step name to Title Case for display */
function formatStepName(name: string): string {
  return name
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase());
}

interface LiveExecutionViewProps {
  task: Task;
  activeStepId: string | null;
  onPause?: () => void;
  isPausing?: boolean;
}

/**
 * LiveExecutionView - Shows real-time execution progress.
 * Visual representation of what's happening right now.
 */
export function LiveExecutionView({
  task,
  activeStepId,
  onPause,
  isPausing = false,
}: LiveExecutionViewProps) {
  const completedSteps = task.steps.filter((s: TaskStep) => s.status === 'done').length;
  const totalSteps = task.steps.length;
  const activeStep = task.steps.find((s: TaskStep) => s.id === activeStepId);

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--card)] overflow-hidden">
      {/* Header with progress */}
      <div className="px-5 py-4 border-b border-[var(--border)]">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-[oklch(0.65_0.25_180/0.1)] flex items-center justify-center">
              <ArrowPathIcon className="w-5 h-5 text-[oklch(0.65_0.25_180)] animate-spin" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-[var(--foreground)]">
                Running
              </h3>
              <p className="text-sm text-[var(--muted-foreground)]">
                {completedSteps} of {totalSteps} steps completed
              </p>
            </div>
          </div>

          {onPause && (
            <button
              onClick={onPause}
              disabled={isPausing}
              className="flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-[var(--muted-foreground)] hover:text-[var(--foreground)] border border-[var(--border)] rounded-lg hover:bg-[var(--muted)] transition-colors disabled:opacity-50"
            >
              <PauseIcon className="w-4 h-4" />
              {isPausing ? 'Pausing...' : 'Pause'}
            </button>
          )}
        </div>

        {/* Progress bar */}
        <div className="h-2 bg-[var(--muted)] rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-[oklch(0.65_0.25_180)] to-[oklch(0.55_0.2_200)] transition-all duration-500"
            style={{ width: `${task.progress_percentage}%` }}
          />
        </div>
      </div>

      {/* Current step */}
      {activeStep && (
        <div className="px-5 py-4 bg-[oklch(0.65_0.25_180/0.05)]">
          <p className="text-xs text-[var(--muted-foreground)] uppercase tracking-wide mb-1">
            Currently working on
          </p>
          <p className="text-sm font-medium text-[var(--foreground)]">
            {activeStep.name}
          </p>
          <p className="text-sm text-[var(--muted-foreground)] mt-1">
            {activeStep.description}
          </p>
        </div>
      )}

      {/* Step list */}
      <div className="px-5 py-4">
        <div className="space-y-2">
          {task.steps.map((step: TaskStep, idx: number) => {
            const isActive = step.id === activeStepId;
            const isDone = step.status === 'done';
            const isFailed = step.status === 'failed';
            const isSkipped = step.status === 'skipped';

            return (
              <div
                key={step.id}
                className={`flex items-center gap-3 px-3 py-2 rounded-lg transition-colors ${
                  isActive ? 'bg-[oklch(0.65_0.25_180/0.1)]' : ''
                }`}
              >
                {/* Status indicator */}
                <div className="flex-shrink-0">
                  {isDone ? (
                    <CheckCircleIcon className="w-5 h-5 text-[oklch(0.78_0.22_150)]" />
                  ) : isFailed ? (
                    <ExclamationCircleIcon className="w-5 h-5 text-[oklch(0.65_0.25_27)]" />
                  ) : isActive ? (
                    <ArrowPathIcon className="w-5 h-5 text-[oklch(0.65_0.25_180)] animate-spin" />
                  ) : (
                    <div className="w-5 h-5 rounded-full border-2 border-[var(--border)] flex items-center justify-center text-xs text-[var(--muted-foreground)]">
                      {idx + 1}
                    </div>
                  )}
                </div>

                {/* Step name */}
                <span className={`text-sm ${
                  isDone
                    ? 'text-[var(--muted-foreground)] line-through'
                    : isActive
                      ? 'text-[var(--foreground)] font-medium'
                      : isSkipped
                        ? 'text-[var(--muted-foreground)] line-through'
                        : 'text-[var(--muted-foreground)]'
                }`}>
                  {formatStepName(step.name)}
                </span>

                {/* Checkpoint badge */}
                {step.checkpoint_required && !isDone && (
                  <span className="ml-auto text-xs text-[oklch(0.7_0.2_60)]">
                    Needs approval
                  </span>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
