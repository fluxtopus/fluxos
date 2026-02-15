'use client';

import {
  CheckIcon,
  XMarkIcon,
  PlayIcon,
  ChevronDownIcon,
  ChevronUpIcon,
} from '@heroicons/react/24/outline';
import { useState } from 'react';
import type { Task, TaskStep } from '../../types/task';

/** Convert snake_case step name to Title Case for display */
function formatStepName(name: string): string {
  return name
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase());
}

interface PlanPreviewProps {
  task: Task;
  onStart: () => void;
  onCancel: () => void;
  isStarting?: boolean;
}

/**
 * PlanPreview - Shows "What I'll do" before execution starts.
 * Human-readable, not a YAML dump. Shows the user what they're approving.
 */
export function PlanPreview({
  task,
  onStart,
  onCancel,
  isStarting = false,
}: PlanPreviewProps) {
  const [showSteps, setShowSteps] = useState(false);

  // Group steps by parallel_group for display
  const stepGroups: { steps: TaskStep[]; isParallel: boolean }[] = [];
  let currentGroup: TaskStep[] = [];
  let currentParallelGroup: string | null = null;

  task.steps.forEach((step: TaskStep) => {
    if (step.parallel_group !== currentParallelGroup) {
      if (currentGroup.length > 0) {
        stepGroups.push({
          steps: currentGroup,
          isParallel: currentGroup.length > 1,
        });
      }
      currentGroup = [step];
      currentParallelGroup = step.parallel_group || null;
    } else {
      currentGroup.push(step);
    }
  });
  if (currentGroup.length > 0) {
    stepGroups.push({
      steps: currentGroup,
      isParallel: currentGroup.length > 1,
    });
  }

  // Create human-readable summary
  const getSummary = () => {
    const uniqueAgentTypes = [...new Set(task.steps.map(s => s.agent_type))];
    const actions: string[] = [];

    if (uniqueAgentTypes.includes('http_fetch')) {
      actions.push('fetch content from the web');
    }
    if (uniqueAgentTypes.includes('summarize')) {
      actions.push('summarize information');
    }
    if (uniqueAgentTypes.includes('analyze')) {
      actions.push('analyze data');
    }
    if (uniqueAgentTypes.includes('compose')) {
      actions.push('compose content');
    }
    if (uniqueAgentTypes.includes('notify')) {
      actions.push('send notifications');
    }
    if (uniqueAgentTypes.includes('file_storage')) {
      actions.push('store files');
    }
    if (uniqueAgentTypes.includes('generate_image')) {
      actions.push('generate images');
    }
    if (uniqueAgentTypes.includes('transform')) {
      actions.push('transform data');
    }

    if (actions.length === 0) {
      return `I'll complete ${task.steps.length} step${task.steps.length > 1 ? 's' : ''} to accomplish your goal.`;
    }

    if (actions.length === 1) {
      return `I'll ${actions[0]} to accomplish your goal.`;
    }

    const lastAction = actions.pop();
    return `I'll ${actions.join(', ')} and ${lastAction}.`;
  };

  const checkpointCount = task.steps.filter(s => s.checkpoint_required).length;

  return (
    <div className="w-full max-w-2xl mx-auto">
      <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] overflow-hidden">
        {/* Header */}
        <div className="px-6 py-5 border-b border-[var(--border)]">
          <h2 className="text-lg font-semibold text-[var(--foreground)] mb-1">
            Here&apos;s what I&apos;ll do
          </h2>
          <p className="text-sm text-[var(--muted-foreground)]">
            {getSummary()}
          </p>
        </div>

        {/* Stats */}
        <div className="px-6 py-4 border-b border-[var(--border)] bg-[var(--muted)]/30">
          <div className="flex items-center gap-6 text-sm">
            <div>
              <span className="text-[var(--muted-foreground)]">Steps: </span>
              <span className="font-medium text-[var(--foreground)]">{task.steps.length}</span>
            </div>
            {checkpointCount > 0 && (
              <div>
                <span className="text-[var(--muted-foreground)]">Approvals needed: </span>
                <span className="font-medium text-[oklch(0.7_0.2_60)]">{checkpointCount}</span>
              </div>
            )}
          </div>
        </div>

        {/* Expandable steps */}
        <div className="px-6 py-4">
          <button
            onClick={() => setShowSteps(!showSteps)}
            className="flex items-center gap-2 text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors"
          >
            {showSteps ? (
              <>
                <ChevronUpIcon className="w-4 h-4" />
                Hide details
              </>
            ) : (
              <>
                <ChevronDownIcon className="w-4 h-4" />
                Show {task.steps.length} steps
              </>
            )}
          </button>

          {showSteps && (
            <div className="mt-4 space-y-3">
              {stepGroups.map((group, groupIdx) => (
                <div key={groupIdx} className="relative">
                  {group.isParallel && (
                    <div className="absolute left-[9px] top-8 bottom-2 w-px bg-[var(--border)]" />
                  )}
                  {group.steps.map((step, stepIdx) => (
                    <div
                      key={step.id}
                      className={`flex items-start gap-3 ${stepIdx > 0 ? 'mt-2' : ''}`}
                    >
                      <div className={`
                        flex-shrink-0 w-5 h-5 rounded-full border-2 flex items-center justify-center text-xs
                        ${step.checkpoint_required
                          ? 'border-[oklch(0.7_0.2_60)] text-[oklch(0.7_0.2_60)]'
                          : 'border-[var(--border)] text-[var(--muted-foreground)]'
                        }
                      `}>
                        {groupIdx + 1}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-[var(--foreground)]">
                          {formatStepName(step.name)}
                        </p>
                        <p className="text-xs text-[var(--muted-foreground)] line-clamp-1">
                          {step.description}
                        </p>
                        {step.checkpoint_required && (
                          <span className="inline-block mt-1 text-xs text-[oklch(0.7_0.2_60)]">
                            Needs approval
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="px-6 py-4 border-t border-[var(--border)] bg-[var(--muted)]/30 flex items-center justify-end gap-3">
          <button
            onClick={onCancel}
            disabled={isStarting}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors disabled:opacity-50"
          >
            <XMarkIcon className="w-4 h-4" />
            Cancel
          </button>
          <button
            onClick={onStart}
            disabled={isStarting}
            className="flex items-center gap-2 px-5 py-2 text-sm font-medium text-white rounded-lg delegation-cta disabled:opacity-50"
          >
            {isStarting ? (
              <>
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Starting...
              </>
            ) : (
              <>
                <PlayIcon className="w-4 h-4" />
                Start
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
