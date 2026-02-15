'use client';

import { useEffect, useState, useRef, useCallback } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { formatDistanceToNow } from 'date-fns';
import {
  ArrowLeftIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  PauseIcon,
  PlayIcon,
  ArrowPathIcon,
  CheckIcon,
  XMarkIcon,
  ClockIcon,
  SparklesIcon,
  ChevronDownIcon,
  PencilSquareIcon,
  CalendarDaysIcon,
} from '@heroicons/react/24/outline';
import { useTask, getTaskPhase, type TaskPhase } from '../../hooks/useTask';
import { useTaskSSE } from '../../hooks/useTaskSSE';
import { usePlanningProgress } from '../../hooks/usePlanningProgress';
import { startTask, pauseTask, cancelTask, approveCheckpoint, rejectCheckpoint, getTaskCheckpoints, createTask } from '../../services/taskApi';
import { hapticSuccess, hapticError } from '../../utils/haptics';
import { createAutomationFromTask } from '../../services/automationApi';
import { LiveExecutionView } from './LiveExecutionView';
import { PlanningInterstitial } from './PlanningInterstitial';
import { ActivityFeed } from './ActivityFeed';
import { DeliveryCard } from './DeliveryCard';
import type { Task, TaskStep, Checkpoint, ActivityItem, Delivery } from '../../types/task';

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

/**
 * Format a step name for display.
 * Converts snake_case to Title Case (e.g., "research_cursor" → "Research Cursor")
 */
function formatStepName(name: string): string {
  return name
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(' ');
}

/**
 * Detect the delivery type based on output content.
 * Checks for file types (PDF, images) vs text content.
 */
function detectDeliveryType(outputs: Record<string, unknown>): Delivery['type'] {
  // Check for base64 encoded files
  if ('pdf_base64' in outputs || 'file_base64' in outputs) {
    return 'file';
  }

  // Check for image base64 or URLs
  if ('image_base64' in outputs) {
    return 'image';
  }

  // Check for file objects with URLs
  if (outputs.file && typeof outputs.file === 'object') {
    return 'file';
  }

  // Check for image URLs
  const urlFields = ['url', 'image_url', 'src', 'image'];
  for (const field of urlFields) {
    const val = outputs[field];
    if (typeof val === 'string') {
      if (val.match(/\.(png|jpg|jpeg|gif|webp|svg)$/i)) {
        return 'image';
      }
      if (val.match(/\.(pdf|doc|docx|xls|xlsx|csv|zip)$/i)) {
        return 'file';
      }
    }
  }

  // Check for notification-related outputs
  if ('notification_sent' in outputs || 'email_sent' in outputs) {
    return 'notification';
  }

  // Default to text/data
  return 'text';
}

interface TaskDetailProps {
  taskId: string;
}

/**
 * TaskDetail - Main detail view for a task.
 *
 * Architecture:
 * - Server state is the source of truth (via useTask hook)
 * - SSE subscription pushes updates (via useTaskSSE hook)
 * - UI derives display state from task.status
 * - No polling, no local state machine
 */
export function TaskDetail({ taskId }: TaskDetailProps) {
  // Server state is the source of truth
  const { task, isLoading, error, refetch } = useTask(taskId);
  const router = useRouter();

  // Local UI state (not task state)
  const [activities, setActivities] = useState<ActivityItem[]>([]);
  const [deliveries, setDeliveries] = useState<Delivery[]>([]);
  const [activeStepId, setActiveStepId] = useState<string | null>(null);
  const [activeCheckpoint, setActiveCheckpoint] = useState<Partial<Checkpoint> | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  // Checkpoint interaction state
  const [rejectReason, setRejectReason] = useState('');
  const [showRejectInput, setShowRejectInput] = useState(false);
  const [learnPreference, setLearnPreference] = useState(true);

  // Celebration animation state
  const [showCelebration, setShowCelebration] = useState(false);
  const prevStatusRef = useRef<string | null>(null);

  // Collapsible details for completed state
  const [showDetails, setShowDetails] = useState(false);

  // Planning progress state
  const { progress: planningProgress, handlePlanningEvent, reset: resetPlanningProgress } = usePlanningProgress();
  const [planningExpanded, setPlanningExpanded] = useState(true);

  // Derive phase from task status
  const phase = getTaskPhase(task);

  // Add activity helper
  const addActivity = useCallback((activity: Omit<ActivityItem, 'id' | 'timestamp'>) => {
    setActivities(prev => [
      {
        ...activity,
        id: `activity-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
        timestamp: new Date().toISOString(),
      },
      ...prev,
    ]);
  }, []);

  // SSE subscription - connect for planning, executing, and checkpoint phases
  const shouldConnectSSE = phase === 'planning' || phase === 'executing' || phase === 'checkpoint';

  useTaskSSE(taskId, {
    onStatusChange: () => {
      // Refetch task when status changes
      refetch();
    },
    onPlanningProgress: (event) => {
      handlePlanningEvent(event);
      // On planning completed, refetch task to get steps and new status
      if (event.type === 'task.planning.completed' || event.type === 'task.planning.failed') {
        refetch();
      }
    },
    onStepStarted: (stepId, stepName) => {
      setActiveStepId(stepId);
      addActivity({
        type: 'progress',
        message: `Working on: ${formatStepName(stepName)}`,
        stepId,
      });
    },
    onStepCompleted: (stepId, stepName, outputs) => {
      addActivity({
        type: 'completed',
        message: `Completed: ${formatStepName(stepName)}`,
        stepId,
        details: outputs,
      });
      // Extract deliveries from outputs if present
      // Pass the entire outputs object for rich rendering by DeliveryCard
      if (outputs && typeof outputs === 'object') {
        setDeliveries(prev => [
          ...prev,
          {
            id: `delivery-${stepId}`,
            stepId,
            stepName,
            type: 'text' as const,
            title: formatStepName(stepName),
            content: outputs, // Pass whole object for rich rendering
            createdAt: new Date().toISOString(),
          },
        ]);
      }
    },
    onStepFailed: (stepId, error) => {
      addActivity({
        type: 'error',
        message: `Step failed: ${error}`,
        stepId,
      });
    },
    onCheckpoint: (checkpoint) => {
      setActiveCheckpoint({
        step_id: checkpoint.step_id,
        checkpoint_name: checkpoint.checkpoint_name,
        description: checkpoint.checkpoint_name,
        preview_data: checkpoint.preview_data,
      });
      addActivity({
        type: 'decision',
        message: checkpoint.checkpoint_name || 'Approval needed',
        stepId: checkpoint.step_id,
      });
    },
    onComplete: (result) => {
      setActiveStepId(null);
      addActivity({
        type: 'completed',
        message: 'Task completed successfully',
        details: result,
      });
    },
    onError: (error) => {
      setActiveStepId(null);
      setActionError(error);
      addActivity({
        type: 'error',
        message: error,
      });
    },
  }, shouldConnectSSE);

  // Detect completion transition for celebration animation
  useEffect(() => {
    if (prevStatusRef.current === 'executing' && task?.status === 'completed') {
      setShowCelebration(true);
      const timer = setTimeout(() => setShowCelebration(false), 3000);
      return () => clearTimeout(timer);
    }
    prevStatusRef.current = task?.status || null;
  }, [task?.status]);

  // Clear checkpoint when task is no longer at checkpoint
  useEffect(() => {
    if (task?.status !== 'checkpoint') {
      setActiveCheckpoint(null);
    }
  }, [task?.status]);

  // Load existing checkpoint when task is in checkpoint status but no activeCheckpoint
  useEffect(() => {
    if (task?.status === 'checkpoint' && !activeCheckpoint) {
      getTaskCheckpoints(taskId).then((checkpoints) => {
        if (checkpoints.length > 0) {
          const cp = checkpoints[0];
          setActiveCheckpoint({
            step_id: cp.step_id,
            checkpoint_name: cp.checkpoint_name,
            description: cp.description || cp.checkpoint_name,
            preview_data: cp.preview_data,
          });
        }
      }).catch((err) => {
        console.error('Failed to load checkpoints:', err);
      });
    }
  }, [task?.status, taskId, activeCheckpoint]);

  // Load deliveries from completed steps when viewing a completed task
  // This handles page refresh or direct navigation to a completed task
  useEffect(() => {
    if (task?.status === 'completed' && task.steps) {
      setDeliveries(prev => {
        // Don't overwrite if SSE already populated deliveries during live execution
        if (prev.length > 0) return prev;

        const completedDeliveries = task.steps!
          .filter(step => step.status === 'done' && step.outputs)
          .map(step => {
            const outputs = step.outputs as Record<string, unknown>;
            // Detect the appropriate delivery type from output content
            const deliveryType = detectDeliveryType(outputs);
            // Pass the entire outputs object to DeliveryCard for proper parsing
            // DeliveryCard will extract structured data (items, insights) and handle
            // legacy data with embedded JSON in markdown code blocks
            return {
              id: `delivery-${step.id}`,
              stepId: step.id,
              stepName: step.name,
              type: deliveryType,
              title: formatStepName(step.name), // Format for display
              content: outputs, // Pass whole object for rich rendering
              createdAt: task.updated_at || new Date().toISOString(),
            };
          })
          .filter(d => d.content && Object.keys(d.content as Record<string, unknown>).length > 0);

        return completedDeliveries.length > 0 ? completedDeliveries : prev;
      });
    }
  }, [task?.status, task?.steps]);

  // Action handlers
  const handleStart = async () => {
    setActionLoading(true);
    setActionError(null);
    try {
      const result = await startTask(taskId);
      if (result.status === 'already_executing') {
        addActivity({
          type: 'progress',
          message: 'Reconnecting to execution...',
        });
      } else if (result.status === 'started') {
        addActivity({
          type: 'started',
          message: 'Execution started',
        });
      }
      // Refetch to get updated status
      await refetch();
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Failed to start task';
      setActionError(message);
      addActivity({
        type: 'error',
        message,
      });
    } finally {
      setActionLoading(false);
    }
  };

  // Re-run with additional instructions - creates a new task
  const handleRerunWithInstructions = async (instructions: string) => {
    if (!task) return;
    setActionLoading(true);
    setActionError(null);
    try {
      // Create new task with combined goal
      const newGoal = instructions.trim()
        ? `${task.goal}\n\nAdditional instructions:\n${instructions.trim()}`
        : task.goal;

      const newTask = await createTask({
        goal: newGoal,
        metadata: {
          rerun_from: taskId,
        },
      });

      // Navigate to new task
      router.push(`/tasks/${newTask.id}`);
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Failed to create task';
      setActionError(message);
      addActivity({
        type: 'error',
        message,
      });
      setActionLoading(false);
    }
    // Don't setActionLoading(false) on success - we're navigating away
  };

  const handlePause = async () => {
    setActionLoading(true);
    setActionError(null);
    try {
      await pauseTask(taskId);
      addActivity({
        type: 'progress',
        message: 'Execution paused',
      });
      await refetch();
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Failed to pause task';
      setActionError(message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleApprove = async () => {
    if (!activeCheckpoint?.step_id) return;
    setActionLoading(true);
    setActionError(null);
    try {
      await approveCheckpoint(taskId, activeCheckpoint.step_id, { learn_preference: learnPreference });
      hapticSuccess();
      setActiveCheckpoint(null);
      addActivity({
        type: 'completed',
        message: 'Checkpoint approved',
      });
      await refetch();
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Failed to approve checkpoint';
      setActionError(message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleReject = async () => {
    if (!activeCheckpoint?.step_id || !rejectReason.trim()) return;
    setActionLoading(true);
    setActionError(null);
    try {
      await rejectCheckpoint(taskId, activeCheckpoint.step_id, { reason: rejectReason, learn_preference: learnPreference });
      hapticError();
      setActiveCheckpoint(null);
      setRejectReason('');
      setShowRejectInput(false);
      addActivity({
        type: 'error',
        message: 'Checkpoint rejected',
      });
      await refetch();
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Failed to reject checkpoint';
      setActionError(message);
    } finally {
      setActionLoading(false);
    }
  };

  // Loading state
  if (isLoading && !task) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="flex flex-col items-center gap-3 text-[var(--muted-foreground)]">
          <div className="w-8 h-8 border-2 border-current border-t-transparent rounded-full animate-spin" />
          <span className="text-sm">Loading...</span>
        </div>
      </div>
    );
  }

  // Not found state
  if (!task) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="text-center">
          <p className="text-[var(--muted-foreground)]">Task not found</p>
          <Link
            href="/tasks"
            className="inline-flex items-center gap-2 mt-4 text-sm text-[oklch(0.65_0.25_180)] hover:underline"
          >
            <ArrowLeftIcon className="w-4 h-4" />
            Back to tasks
          </Link>
        </div>
      </div>
    );
  }

  // Cancel planning handler
  const handleCancelPlanning = async () => {
    setActionLoading(true);
    setActionError(null);
    try {
      await cancelTask(taskId);
      await refetch();
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Failed to cancel';
      setActionError(message);
    } finally {
      setActionLoading(false);
    }
  };

  // Display state helpers
  const isPlanning = phase === 'planning';
  const isReady = phase === 'ready';
  const isExecuting = phase === 'executing';
  const isCompleted = phase === 'completed';
  const isFailed = phase === 'failed';
  const isPaused = phase === 'paused';
  const isCheckpoint = phase === 'checkpoint';
  const isCancelled = phase === 'cancelled';

  // Find error from failed steps or planning error
  const displayError = actionError ||
    task.planning_error ||
    task.steps?.find(s => s.status === 'failed')?.error_message;

  // Check for failed steps
  const hasFailedSteps = task.steps?.some(s => s.status === 'failed') || false;

  return (
    <div className="max-w-4xl mx-auto px-4 py-6">
      {/* Header */}
      <div className="mb-6">
        <Link
          href="/tasks"
          className="inline-flex items-center gap-2 text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors mb-4"
        >
          <ArrowLeftIcon className="w-4 h-4" />
          Back to tasks
        </Link>

        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-[var(--foreground)] mb-2">
              {task.goal}
            </h1>
            <p className="text-sm text-[var(--muted-foreground)]">
              Created {formatDistanceToNow(parseAsUTC(task.created_at), { addSuffix: true })}
            </p>
          </div>

          {/* Status badge - derived from task.status */}
          <div className="flex-shrink-0">
            <StatusBadge status={task.status} />
          </div>
        </div>
      </div>

      {/* COMPLETED STATE */}
      {isCompleted && (
        <CompletedView
          task={task}
          deliveries={deliveries}
          activities={activities}
          hasFailedSteps={hasFailedSteps}
          displayError={displayError}
          showCelebration={showCelebration}
          showDetails={showDetails}
          setShowDetails={setShowDetails}
          onRerun={handleStart}
          onRerunWithInstructions={handleRerunWithInstructions}
          loading={actionLoading}
        />
      )}

      {/* CANCELLED STATE */}
      {isCancelled && (
        <CancelledView task={task} onRetry={handleStart} loading={actionLoading} />
      )}

      {/* Planning interstitial - full width, outside grid for proper centering */}
      {!isCompleted && !isCancelled && isPlanning && (
        <PlanningInterstitial
          progress={planningProgress}
          onCancel={handleCancelPlanning}
          isExpanded={planningExpanded}
          onToggleExpand={() => setPlanningExpanded(!planningExpanded)}
        />
      )}

      {/* Main content grid - for non-completed states */}
      {!isCompleted && !isCancelled && !isPlanning && (
        <div className="grid gap-6 lg:grid-cols-[1fr,320px]">
          {/* Left column - Primary content */}
          <div className="space-y-6">
            {isReady && <ReadyView task={task} onStart={handleStart} loading={actionLoading} />}
            {isExecuting && (
              <LiveExecutionView
                task={task}
                activeStepId={activeStepId}
                onPause={handlePause}
                isPausing={actionLoading}
              />
            )}
            {isCheckpoint && (
              <CheckpointView
                checkpoint={activeCheckpoint}
                learnPreference={learnPreference}
                setLearnPreference={setLearnPreference}
                showRejectInput={showRejectInput}
                setShowRejectInput={setShowRejectInput}
                rejectReason={rejectReason}
                setRejectReason={setRejectReason}
                onApprove={handleApprove}
                onReject={handleReject}
                onResume={handleStart}
                loading={actionLoading}
              />
            )}
            {isPaused && <PausedView onResume={handleStart} loading={actionLoading} />}
            {isFailed && (
              <FailedView
                task={task}
                displayError={displayError}
                onRetry={handleStart}
                loading={actionLoading}
              />
            )}

            {/* Partial results during execution */}
            {deliveries.length > 0 && !isCompleted && (
              <section>
                <div className="flex items-center gap-2 mb-4">
                  <SparklesIcon className="w-5 h-5 text-[oklch(0.65_0.25_180)]" />
                  <h2 className="text-sm font-medium text-[var(--foreground)] uppercase tracking-wide">
                    Results so far
                  </h2>
                </div>
                <div className="space-y-4">
                  {deliveries.map((delivery) => (
                    <DeliveryCard key={delivery.id} delivery={delivery} />
                  ))}
                </div>
              </section>
            )}
          </div>

          {/* Right column - Activity (only show when there are activities) */}
          {activities.length > 0 && (
            <div className="space-y-6">
              <div className="rounded-xl border border-[var(--border)] bg-[var(--card)] overflow-hidden sticky top-6">
                <div className="px-4 py-3 border-b border-[var(--border)]">
                  <h2 className="text-sm font-medium text-[var(--foreground)]">Activity</h2>
                </div>
                <div className="p-4 max-h-[500px] overflow-y-auto">
                  <ActivityFeed activities={activities} />
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// === Sub-components ===

function StatusBadge({ status }: { status: string }) {
  switch (status) {
    case 'planning':
      return (
        <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium delegation-running border">
          <ArrowPathIcon className="w-4 h-4 animate-spin" />
          Planning
        </span>
      );
    case 'ready':
      return (
        <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium text-[var(--muted-foreground)] bg-[var(--muted)] border border-[var(--border)]">
          <ClockIcon className="w-4 h-4" />
          Ready
        </span>
      );
    case 'executing':
      return (
        <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium delegation-running border">
          <div className="w-2 h-2 rounded-full bg-current delegation-pulse" />
          Running
        </span>
      );
    case 'completed':
      return (
        <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium delegation-done border">
          <CheckCircleIcon className="w-4 h-4" />
          Done
        </span>
      );
    case 'failed':
      return (
        <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium delegation-error border">
          <ExclamationTriangleIcon className="w-4 h-4" />
          Failed
        </span>
      );
    case 'paused':
      return (
        <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium text-[var(--muted-foreground)] bg-[var(--muted)] border border-[var(--border)]">
          <PauseIcon className="w-4 h-4" />
          Paused
        </span>
      );
    case 'checkpoint':
      return (
        <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium delegation-waiting border">
          Needs decision
        </span>
      );
    case 'cancelled':
      return (
        <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium text-[var(--muted-foreground)] bg-[var(--muted)] border border-[var(--border)]">
          <XMarkIcon className="w-4 h-4" />
          Cancelled
        </span>
      );
    default:
      return null;
  }
}

// PlanningView removed — replaced by PlanningInterstitial component with real SSE progress

function ReadyView({ task, onStart, loading }: { task: Task; onStart: () => void; loading: boolean }) {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--card)] overflow-hidden">
      <div className="px-5 py-4 border-b border-[var(--border)]">
        <h3 className="text-sm font-medium text-[var(--muted-foreground)] uppercase tracking-wider">
          What I&apos;ll do
        </h3>
      </div>
      <div className="p-5">
        <div className="space-y-3 mb-6">
          {task.steps?.map((step, i) => (
            <div key={step.id} className="flex items-start gap-3">
              <span className="w-6 h-6 rounded-full bg-[oklch(0.65_0.25_180/0.1)] text-[oklch(0.65_0.25_180)] text-xs flex items-center justify-center flex-shrink-0 mt-0.5">
                {i + 1}
              </span>
              <div>
                <p className="text-sm font-medium text-[var(--foreground)]">{formatStepName(step.name)}</p>
                {step.description && (
                  <p className="text-xs text-[var(--muted-foreground)] mt-0.5 text-body">{step.description}</p>
                )}
                {step.checkpoint_required && (
                  <span className="inline-flex items-center gap-1 text-xs text-amber-600 mt-1">
                    <ClockIcon className="w-3 h-3" />
                    Needs approval
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
        <button
          onClick={onStart}
          disabled={loading}
          className="w-full inline-flex items-center justify-center gap-2 px-5 py-3 text-sm font-medium text-white rounded-lg delegation-cta disabled:opacity-50"
        >
          {loading ? (
            <ArrowPathIcon className="w-4 h-4 animate-spin" />
          ) : (
            <PlayIcon className="w-4 h-4" />
          )}
          Start
        </button>
      </div>
    </div>
  );
}

function PausedView({ onResume, loading }: { onResume: () => void; loading: boolean }) {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-6 text-center">
      <PauseIcon className="w-10 h-10 mx-auto text-[var(--muted-foreground)] mb-3" />
      <h3 className="text-lg font-medium text-[var(--foreground)] mb-2">Execution Paused</h3>
      <p className="text-sm text-[var(--muted-foreground)] mb-4 text-body">
        Resume when you&apos;re ready to continue.
      </p>
      <button
        onClick={onResume}
        disabled={loading}
        className="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-medium text-white rounded-lg delegation-cta disabled:opacity-50"
      >
        {loading ? <ArrowPathIcon className="w-4 h-4 animate-spin" /> : <PlayIcon className="w-4 h-4" />}
        Resume
      </button>
    </div>
  );
}

function CancelledView({ task, onRetry, loading }: { task: Task; onRetry: () => void; loading: boolean }) {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-6 text-center">
      <XMarkIcon className="w-10 h-10 mx-auto text-[var(--muted-foreground)] mb-3" />
      <h3 className="text-lg font-medium text-[var(--foreground)] mb-2">Task Cancelled</h3>
      <p className="text-sm text-[var(--muted-foreground)] mb-4 text-body">This task was cancelled.</p>
      <div className="flex gap-3 justify-center">
        <button
          onClick={onRetry}
          disabled={loading}
          className="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-medium text-white rounded-lg delegation-cta disabled:opacity-50"
        >
          {loading ? <ArrowPathIcon className="w-4 h-4 animate-spin" /> : <ArrowPathIcon className="w-4 h-4" />}
          Try Again
        </button>
        <Link
          href="/tasks/new"
          className="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-medium text-[var(--foreground)] bg-[var(--muted)] rounded-lg hover:bg-[var(--muted)]/80"
        >
          Start Fresh
        </Link>
      </div>
    </div>
  );
}

function FailedView({
  task,
  displayError,
  onRetry,
  loading,
}: {
  task: Task;
  displayError?: string | null;
  onRetry: () => void;
  loading: boolean;
}) {
  return (
    <div className="rounded-xl border border-[oklch(0.65_0.25_27/0.3)] bg-[oklch(0.65_0.25_27/0.05)] p-6">
      <div className="flex items-start gap-4">
        <ExclamationTriangleIcon className="w-8 h-8 text-[oklch(0.65_0.25_27)] flex-shrink-0" />
        <div className="flex-1">
          <h3 className="text-lg font-medium text-[var(--foreground)] mb-2">Something went wrong</h3>
          {displayError && <p className="text-sm text-[var(--muted-foreground)] mb-4 text-body">{displayError}</p>}

          {task.steps?.some(s => s.status === 'failed') && (
            <div className="mb-4 p-3 bg-[var(--muted)] rounded-lg">
              <p className="text-xs font-medium text-[var(--muted-foreground)] uppercase mb-2">Failed Step</p>
              {task.steps.filter(s => s.status === 'failed').map(step => (
                <div key={step.id} className="text-sm">
                  <p className="font-medium text-[var(--foreground)]">{formatStepName(step.name)}</p>
                  {step.error_message && (
                    <p className="text-[var(--muted-foreground)] mt-1">{step.error_message}</p>
                  )}
                </div>
              ))}
            </div>
          )}

          <div className="flex gap-3">
            <button
              onClick={onRetry}
              disabled={loading}
              className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white rounded-lg delegation-cta disabled:opacity-50"
            >
              {loading ? <ArrowPathIcon className="w-4 h-4 animate-spin" /> : <ArrowPathIcon className="w-4 h-4" />}
              Try Again
            </button>
            <Link
              href="/tasks/new"
              className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-[var(--foreground)] bg-[var(--muted)] rounded-lg hover:bg-[var(--muted)]/80"
            >
              Start Fresh
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}

function CheckpointView({
  checkpoint,
  learnPreference,
  setLearnPreference,
  showRejectInput,
  setShowRejectInput,
  rejectReason,
  setRejectReason,
  onApprove,
  onReject,
  onResume,
  loading,
}: {
  checkpoint: Partial<Checkpoint> | null;
  learnPreference: boolean;
  setLearnPreference: (v: boolean) => void;
  showRejectInput: boolean;
  setShowRejectInput: (v: boolean) => void;
  rejectReason: string;
  setRejectReason: (v: string) => void;
  onApprove: () => void;
  onReject: () => void;
  onResume: () => void;
  loading: boolean;
}) {
  if (!checkpoint) {
    return (
      <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-6 text-center">
        <ClockIcon className="w-10 h-10 mx-auto text-amber-500 mb-3" />
        <h3 className="text-lg font-medium text-[var(--foreground)] mb-2">Waiting for Decision</h3>
        <p className="text-sm text-[var(--muted-foreground)] mb-4 text-body">
          This task is paused waiting for a decision. Resume to see the checkpoint.
        </p>
        <button
          onClick={onResume}
          disabled={loading}
          className="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-medium text-white rounded-lg delegation-cta disabled:opacity-50"
        >
          {loading ? <ArrowPathIcon className="w-4 h-4 animate-spin" /> : <PlayIcon className="w-4 h-4" />}
          Resume
        </button>
      </div>
    );
  }

  return (
    <div className="rounded-xl border-2 border-amber-500/30 bg-amber-500/5 overflow-hidden">
      <div className="px-5 py-4 border-b border-amber-500/20 bg-amber-500/10">
        <div className="flex items-center gap-2">
          <ClockIcon className="w-5 h-5 text-amber-500" />
          <h3 className="text-sm font-medium text-amber-500 uppercase tracking-wider">Your Decision Needed</h3>
        </div>
      </div>
      <div className="p-5">
        <h4 className="text-lg font-semibold text-[var(--foreground)] mb-2">{checkpoint.checkpoint_name}</h4>
        <p className="text-sm text-[var(--muted-foreground)] mb-4 text-body">{checkpoint.description}</p>

        {checkpoint.preview_data && Object.keys(checkpoint.preview_data).length > 0 && (
          <div className="mb-4 p-3 bg-[var(--muted)] rounded-lg overflow-hidden">
            <p className="text-xs font-medium text-[var(--muted-foreground)] uppercase mb-2">Preview</p>
            <pre className="text-xs text-[var(--foreground)] whitespace-pre-wrap break-all max-w-full">
              {JSON.stringify(checkpoint.preview_data, null, 2)}
            </pre>
          </div>
        )}

        <label className="flex items-center gap-2 text-sm text-[var(--muted-foreground)] mb-4 cursor-pointer">
          <input
            type="checkbox"
            checked={learnPreference}
            onChange={(e) => setLearnPreference(e.target.checked)}
            className="rounded border-[var(--border)]"
          />
          Remember my choice for similar situations
        </label>

        {showRejectInput && (
          <div className="mb-4">
            <input
              type="text"
              value={rejectReason}
              onChange={(e) => setRejectReason(e.target.value)}
              placeholder="Why are you rejecting this?"
              className="w-full px-3 py-2 text-sm bg-[var(--background)] border border-[var(--border)] rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-500/50"
              autoFocus
            />
          </div>
        )}

        <div className="flex gap-3">
          {showRejectInput ? (
            <>
              <button
                onClick={() => setShowRejectInput(false)}
                className="flex-1 inline-flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium text-[var(--foreground)] bg-[var(--muted)] rounded-lg hover:bg-[var(--muted)]/80"
              >
                Cancel
              </button>
              <button
                onClick={onReject}
                disabled={loading || !rejectReason.trim()}
                className="flex-1 inline-flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium text-white bg-red-500 rounded-lg hover:bg-red-600 disabled:opacity-50"
              >
                <XMarkIcon className="w-4 h-4" />
                Confirm Reject
              </button>
            </>
          ) : (
            <>
              <button
                onClick={() => setShowRejectInput(true)}
                className="flex-1 inline-flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium text-red-500 bg-red-500/10 border border-red-500/30 rounded-lg hover:bg-red-500/20"
              >
                <XMarkIcon className="w-4 h-4" />
                Reject
              </button>
              <button
                onClick={onApprove}
                disabled={loading}
                className="flex-1 inline-flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium text-white bg-emerald-500 rounded-lg hover:bg-emerald-600 disabled:opacity-50"
              >
                {loading ? <ArrowPathIcon className="w-4 h-4 animate-spin" /> : <CheckIcon className="w-4 h-4" />}
                Approve
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function CompletedView({
  task,
  deliveries,
  activities,
  hasFailedSteps,
  displayError,
  showCelebration,
  showDetails,
  setShowDetails,
  onRerun,
  onRerunWithInstructions,
  loading,
}: {
  task: Task;
  deliveries: Delivery[];
  activities: ActivityItem[];
  hasFailedSteps: boolean;
  displayError?: string | null;
  showCelebration: boolean;
  showDetails: boolean;
  setShowDetails: (v: boolean) => void;
  onRerun: () => void;
  onRerunWithInstructions: (instructions: string) => void;
  loading: boolean;
}) {
  const router = useRouter();
  // State for re-run with instructions
  const [showInstructionsInput, setShowInstructionsInput] = useState(false);
  const [instructions, setInstructions] = useState('');
  // State for Make Recurring modal
  const [showRecurringModal, setShowRecurringModal] = useState(false);
  const [recurringSchedule, setRecurringSchedule] = useState<'daily_8am' | 'daily_9am' | 'weekly_monday' | 'custom'>('daily_8am');
  const [customCron, setCustomCron] = useState('0 8 * * *');
  const [creatingAutomation, setCreatingAutomation] = useState(false);
  const [automationSuccess, setAutomationSuccess] = useState<{ name: string; schedule: string } | null>(null);
  const [automationError, setAutomationError] = useState<string | null>(null);
  // Separate primary outputs (files, final output) from intermediate research
  // Primary: file types OR the last delivery if it's not research
  // Intermediate: research steps, aggregation, anything feeding into the final output
  const primaryOutputs = deliveries.filter((d, index) => {
    // Files are always primary
    if (d.type === 'file' || d.type === 'image') return true;
    // Last delivery is primary if it's not a research step
    if (index === deliveries.length - 1 && !d.stepName.toLowerCase().includes('research')) return true;
    return false;
  });

  const intermediateOutputs = deliveries.filter(d => !primaryOutputs.includes(d));

  // Handle creating recurring automation
  const handleCreateRecurring = async () => {
    const cronExpression = recurringSchedule === 'custom'
      ? customCron
      : recurringSchedule === 'daily_8am'
        ? '0 8 * * *'
        : recurringSchedule === 'daily_9am'
          ? '0 9 * * *'
          : '0 8 * * 1'; // weekly monday

    // Human-readable schedule for success message
    const scheduleLabel = recurringSchedule === 'custom'
      ? customCron
      : recurringSchedule === 'daily_8am'
        ? 'Daily at 8:00 AM'
        : recurringSchedule === 'daily_9am'
          ? 'Daily at 9:00 AM'
          : 'Weekly on Monday at 8:00 AM';

    setCreatingAutomation(true);
    setAutomationError(null);
    try {
      const automation = await createAutomationFromTask(task.id, {
        schedule_cron: cronExpression,
        schedule_timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      });

      // Show success celebration before redirect
      setAutomationSuccess({ name: automation.name || task.goal.slice(0, 50), schedule: scheduleLabel });

      // Wait for the magic moment, then redirect
      setTimeout(() => {
        setShowRecurringModal(false);
        router.push(`/automations/${automation.id}`);
      }, 1500);
    } catch (err) {
      console.error('Failed to create automation:', err);
      setAutomationError('Failed to create automation. Please try again.');
      setCreatingAutomation(false);
    }
  };

  return (
    <div className="space-y-6">
      {showCelebration && (
        <div className="p-6 rounded-xl bg-gradient-to-br from-[oklch(0.7_0.2_150/0.15)] to-[oklch(0.65_0.25_180/0.1)] border border-[oklch(0.7_0.2_150/0.3)] animate-in fade-in slide-in-from-bottom-4 duration-500">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-full bg-[oklch(0.7_0.2_150/0.2)] flex items-center justify-center animate-bounce">
              <SparklesIcon className="w-6 h-6 text-[oklch(0.78_0.22_150)]" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-[var(--foreground)]">Done!</h3>
              <p className="text-sm text-[var(--muted-foreground)] text-body">Here&apos;s what I made for you</p>
            </div>
          </div>
        </div>
      )}

      {primaryOutputs.length > 0 ? (
        <section>
          <div className="flex items-center gap-2 mb-4">
            <SparklesIcon className="w-5 h-5 text-[oklch(0.65_0.25_180)]" />
            <h2 className="text-sm font-medium text-[var(--foreground)] uppercase tracking-wide">
              Your result
            </h2>
          </div>
          <div className="space-y-4">
            {primaryOutputs.map((delivery, index) => (
              <div
                key={delivery.id}
                className={showCelebration ? 'animate-in fade-in slide-in-from-bottom-2' : ''}
                style={showCelebration ? { animationDelay: `${index * 100}ms` } : undefined}
              >
                <DeliveryCard delivery={delivery} />
              </div>
            ))}
          </div>
        </section>
      ) : hasFailedSteps ? (
        <div className="rounded-xl border border-[oklch(0.6_0.15_30/0.3)] bg-gradient-to-br from-[oklch(0.6_0.15_30/0.08)] to-transparent p-6 text-center">
          <div className="w-14 h-14 mx-auto mb-4 rounded-full bg-[oklch(0.6_0.15_30/0.15)] flex items-center justify-center">
            <ExclamationTriangleIcon className="w-7 h-7 text-[oklch(0.6_0.15_30)]" />
          </div>
          <h3 className="text-lg font-semibold text-[var(--foreground)] mb-2">Ran into an issue</h3>
          <p className="text-sm text-[var(--muted-foreground)] mb-4 text-body">
            {displayError || "Couldn't complete this request."}
          </p>
          <button onClick={() => setShowDetails(true)} className="text-sm text-[oklch(0.65_0.25_180)] hover:underline">
            See what happened
          </button>
        </div>
      ) : (
        <div className="rounded-xl border border-[oklch(0.7_0.2_150/0.3)] bg-gradient-to-br from-[oklch(0.7_0.2_150/0.08)] to-transparent p-6 text-center">
          <div className="w-14 h-14 mx-auto mb-4 rounded-full bg-[oklch(0.7_0.2_150/0.15)] flex items-center justify-center">
            <CheckCircleIcon className="w-7 h-7 text-[oklch(0.78_0.22_150)]" />
          </div>
          <h3 className="text-lg font-semibold text-[var(--foreground)] mb-2">All done!</h3>
          <p className="text-sm text-[var(--muted-foreground)] text-body">Your request was completed successfully.</p>
        </div>
      )}

      <div className="border border-[var(--border)] rounded-xl overflow-hidden">
        <button
          onClick={() => setShowDetails(!showDetails)}
          className="w-full px-5 py-4 flex items-center justify-between text-left hover:bg-[var(--muted)]/50 transition-colors"
        >
          <span className="text-sm font-medium text-[var(--muted-foreground)]">How I did it</span>
          <ChevronDownIcon
            className={`w-4 h-4 text-[var(--muted-foreground)] transition-transform ${showDetails ? 'rotate-180' : ''}`}
          />
        </button>

        {showDetails && (
          <div className="border-t border-[var(--border)]">
            {/* Research & Analysis - intermediate outputs */}
            {intermediateOutputs.length > 0 && (
              <div className="px-5 py-4 border-b border-[var(--border)]">
                <p className="text-xs font-medium text-[var(--muted-foreground)] uppercase tracking-wide mb-3">
                  Research & Analysis
                </p>
                <div className="space-y-3">
                  {intermediateOutputs.map((delivery) => (
                    <DeliveryCard key={delivery.id} delivery={delivery} />
                  ))}
                </div>
              </div>
            )}

            {/* Steps completed */}
            <div className="px-5 py-4 border-b border-[var(--border)]">
              <p className="text-xs font-medium text-[var(--muted-foreground)] uppercase tracking-wide mb-3">
                Steps completed
              </p>
              <div className="space-y-2">
                {task.steps?.map((step) => (
                  <div key={step.id} className="flex items-center gap-3 text-sm">
                    <CheckCircleIcon className="w-4 h-4 text-[oklch(0.78_0.22_150)] flex-shrink-0" />
                    <span className="text-[var(--foreground)]">{formatStepName(step.name)}</span>
                  </div>
                ))}
              </div>
            </div>

            {activities.length > 0 && (
              <div className="px-5 py-4">
                <p className="text-xs font-medium text-[var(--muted-foreground)] uppercase tracking-wide mb-3">
                  Activity log
                </p>
                <ActivityFeed activities={activities} />
              </div>
            )}
          </div>
        )}
      </div>

      {/* Re-run and New Task actions */}
      <div className="space-y-4 mt-6">
        <div className="flex flex-wrap gap-3">
          <button
            onClick={onRerun}
            disabled={loading}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-[var(--foreground)] bg-[var(--muted)] rounded-lg hover:bg-[var(--muted)]/80 disabled:opacity-50 transition-colors"
          >
            {loading && !showInstructionsInput ? (
              <ArrowPathIcon className="w-4 h-4 animate-spin" />
            ) : (
              <ArrowPathIcon className="w-4 h-4" />
            )}
            Re-run
          </button>
          <button
            onClick={() => setShowInstructionsInput(!showInstructionsInput)}
            disabled={loading}
            className={`inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition-colors disabled:opacity-50 ${
              showInstructionsInput
                ? 'bg-[oklch(0.65_0.25_180/0.15)] text-[oklch(0.65_0.25_180)] border border-[oklch(0.65_0.25_180/0.3)]'
                : 'text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--muted)]'
            }`}
          >
            <PencilSquareIcon className="w-4 h-4" />
            Re-run with instructions
          </button>
          <Link
            href="/tasks/new"
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors"
          >
            New Task
          </Link>
          <button
            onClick={() => setShowRecurringModal(true)}
            disabled={loading}
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-[oklch(0.65_0.25_180)] border border-[oklch(0.65_0.25_180/0.3)] rounded-lg hover:bg-[oklch(0.65_0.25_180/0.1)] transition-colors disabled:opacity-50"
          >
            <CalendarDaysIcon className="w-4 h-4" />
            Make recurring
          </button>
        </div>

        {/* Instructions input panel */}
        {showInstructionsInput && (
          <div className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-4 space-y-3 animate-in fade-in slide-in-from-top-2 duration-200">
            <div>
              <label className="block text-sm font-medium text-[var(--foreground)] mb-1.5">
                Additional instructions
              </label>
              <p className="text-xs text-[var(--muted-foreground)] mb-2">
                These will be appended to the original goal: &ldquo;{task.goal.slice(0, 100)}{task.goal.length > 100 ? '...' : ''}&rdquo;
              </p>
              <textarea
                value={instructions}
                onChange={(e) => setInstructions(e.target.value)}
                placeholder="e.g., Also include competitor analysis, Format output as markdown..."
                rows={3}
                className="w-full px-3 py-2 text-sm bg-[var(--background)] border border-[var(--border)] rounded-lg focus:outline-none focus:ring-2 focus:ring-[oklch(0.65_0.25_180/0.3)] focus:border-[oklch(0.65_0.25_180)] text-[var(--foreground)] placeholder-[var(--muted-foreground)] resize-none"
              />
            </div>
            <div className="flex items-center justify-end gap-2">
              <button
                onClick={() => {
                  setShowInstructionsInput(false);
                  setInstructions('');
                }}
                className="px-3 py-1.5 text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => onRerunWithInstructions(instructions)}
                disabled={loading}
                className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-[oklch(0.65_0.25_180)] rounded-lg hover:bg-[oklch(0.6_0.25_180)] disabled:opacity-50 transition-colors"
              >
                {loading ? (
                  <ArrowPathIcon className="w-4 h-4 animate-spin" />
                ) : (
                  <PlayIcon className="w-4 h-4" />
                )}
                Run with instructions
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Make Recurring Modal */}
      {showRecurringModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/50 backdrop-blur-sm"
            onClick={() => !automationSuccess && setShowRecurringModal(false)}
          />

          {/* Modal */}
          <div className="relative w-full max-w-md mx-4 rounded-xl border border-[var(--border)] bg-[var(--card)] shadow-2xl animate-in fade-in zoom-in-95 duration-200 overflow-hidden">
            {/* Success State - The Magic Moment */}
            {automationSuccess ? (
              <div className="p-8 text-center animate-in fade-in zoom-in-95 duration-300">
                <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-[oklch(0.7_0.2_150/0.15)] flex items-center justify-center">
                  <CheckCircleIcon className="w-10 h-10 text-[oklch(0.78_0.22_150)] animate-in zoom-in-50 duration-300" />
                </div>
                <h3 className="text-xl font-semibold text-[var(--foreground)] mb-2">
                  You&apos;re all set!
                </h3>
                <p className="text-sm text-[var(--muted-foreground)]">
                  {automationSuccess.schedule}
                </p>
                <div className="mt-4 flex items-center justify-center gap-2 text-xs text-[var(--muted-foreground)]">
                  <ArrowPathIcon className="w-3 h-3 animate-spin" />
                  <span>Taking you to your automation...</span>
                </div>
              </div>
            ) : (
              <>
                {/* Error Toast */}
                {automationError && (
                  <div className="px-6 py-3 bg-red-500/10 border-b border-red-500/20 flex items-center gap-2 animate-in slide-in-from-top duration-200">
                    <ExclamationTriangleIcon className="w-4 h-4 text-red-500 flex-shrink-0" />
                    <p className="text-sm text-red-600 dark:text-red-400 flex-1">{automationError}</p>
                    <button
                      onClick={() => setAutomationError(null)}
                      className="text-red-500 hover:text-red-600"
                    >
                      <XMarkIcon className="w-4 h-4" />
                    </button>
                  </div>
                )}

                <div className="px-6 py-4 border-b border-[var(--border)]">
                  <h3 className="text-lg font-semibold text-[var(--foreground)]">Make this recurring</h3>
                  <p className="text-sm text-[var(--muted-foreground)] mt-1">
                    How often should this task run?
                  </p>
                </div>

                <div className="p-6 space-y-3">
                  {/* Schedule options */}
                  <label className="flex items-center gap-3 p-3 rounded-lg border border-[var(--border)] cursor-pointer hover:border-[oklch(0.65_0.25_180/0.5)] transition-colors has-[:checked]:border-[oklch(0.65_0.25_180)] has-[:checked]:bg-[oklch(0.65_0.25_180/0.05)]">
                    <input
                      type="radio"
                      name="schedule"
                      value="daily_8am"
                      checked={recurringSchedule === 'daily_8am'}
                      onChange={() => setRecurringSchedule('daily_8am')}
                      className="w-4 h-4 text-[oklch(0.65_0.25_180)] border-[var(--border)] focus:ring-[oklch(0.65_0.25_180)]"
                    />
                    <div>
                      <p className="text-sm font-medium text-[var(--foreground)]">Daily at 8:00 AM</p>
                      <p className="text-xs text-[var(--muted-foreground)]">Run every morning</p>
                    </div>
                  </label>

                  <label className="flex items-center gap-3 p-3 rounded-lg border border-[var(--border)] cursor-pointer hover:border-[oklch(0.65_0.25_180/0.5)] transition-colors has-[:checked]:border-[oklch(0.65_0.25_180)] has-[:checked]:bg-[oklch(0.65_0.25_180/0.05)]">
                    <input
                      type="radio"
                      name="schedule"
                      value="daily_9am"
                      checked={recurringSchedule === 'daily_9am'}
                      onChange={() => setRecurringSchedule('daily_9am')}
                      className="w-4 h-4 text-[oklch(0.65_0.25_180)] border-[var(--border)] focus:ring-[oklch(0.65_0.25_180)]"
                    />
                    <div>
                      <p className="text-sm font-medium text-[var(--foreground)]">Daily at 9:00 AM</p>
                      <p className="text-xs text-[var(--muted-foreground)]">Run every morning</p>
                    </div>
                  </label>

                  <label className="flex items-center gap-3 p-3 rounded-lg border border-[var(--border)] cursor-pointer hover:border-[oklch(0.65_0.25_180/0.5)] transition-colors has-[:checked]:border-[oklch(0.65_0.25_180)] has-[:checked]:bg-[oklch(0.65_0.25_180/0.05)]">
                    <input
                      type="radio"
                      name="schedule"
                      value="weekly_monday"
                      checked={recurringSchedule === 'weekly_monday'}
                      onChange={() => setRecurringSchedule('weekly_monday')}
                      className="w-4 h-4 text-[oklch(0.65_0.25_180)] border-[var(--border)] focus:ring-[oklch(0.65_0.25_180)]"
                    />
                    <div>
                      <p className="text-sm font-medium text-[var(--foreground)]">Weekly on Monday</p>
                      <p className="text-xs text-[var(--muted-foreground)]">Run every Monday at 8:00 AM</p>
                    </div>
                  </label>

                  <label className="flex items-center gap-3 p-3 rounded-lg border border-[var(--border)] cursor-pointer hover:border-[oklch(0.65_0.25_180/0.5)] transition-colors has-[:checked]:border-[oklch(0.65_0.25_180)] has-[:checked]:bg-[oklch(0.65_0.25_180/0.05)]">
                    <input
                      type="radio"
                      name="schedule"
                      value="custom"
                      checked={recurringSchedule === 'custom'}
                      onChange={() => setRecurringSchedule('custom')}
                      className="w-4 h-4 text-[oklch(0.65_0.25_180)] border-[var(--border)] focus:ring-[oklch(0.65_0.25_180)]"
                    />
                    <div className="flex-1">
                      <p className="text-sm font-medium text-[var(--foreground)]">Custom schedule</p>
                      <p className="text-xs text-[var(--muted-foreground)]">Use cron expression</p>
                    </div>
                  </label>

                  {/* Custom cron input */}
                  {recurringSchedule === 'custom' && (
                    <div className="mt-3 pl-7">
                      <input
                        type="text"
                        value={customCron}
                        onChange={(e) => setCustomCron(e.target.value)}
                        placeholder="0 8 * * *"
                        className="w-full px-3 py-2 text-sm font-mono bg-[var(--background)] border border-[var(--border)] rounded-lg focus:outline-none focus:ring-2 focus:ring-[oklch(0.65_0.25_180/0.3)] focus:border-[oklch(0.65_0.25_180)] text-[var(--foreground)]"
                      />
                      <p className="text-xs text-[var(--muted-foreground)] mt-1.5">
                        Format: minute hour day month weekday
                      </p>
                    </div>
                  )}
                </div>

                <div className="px-6 py-4 border-t border-[var(--border)] flex items-center justify-end gap-3">
                  <button
                    onClick={() => {
                      setShowRecurringModal(false);
                      setAutomationError(null);
                    }}
                    className="px-4 py-2 text-sm font-medium text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleCreateRecurring}
                    disabled={creatingAutomation}
                    className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-[oklch(0.65_0.25_180)] rounded-lg hover:bg-[oklch(0.6_0.25_180)] disabled:opacity-50 transition-colors"
                  >
                    {creatingAutomation ? (
                      <ArrowPathIcon className="w-4 h-4 animate-spin" />
                    ) : (
                      <CalendarDaysIcon className="w-4 h-4" />
                    )}
                    Create automation
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
