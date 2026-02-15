'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import { ArrowLeftIcon, ArrowPathIcon } from '@heroicons/react/24/outline';
import Link from 'next/link';
import { useTaskStore } from '../../../../store/taskStore';
import { NewTaskInput } from '../../../../components/Task/NewTaskInput';
import type { FileReference } from '../../../../services/fileService';

/**
 * New Task page.
 * User describes what they want -> Task is created immediately -> Redirect to detail page.
 *
 * The API returns a PLANNING-status stub instantly (202).
 * The detail page shows real-time planning progress via SSE.
 */
export default function NewTaskPage() {
  const router = useRouter();
  const hasRedirectedRef = useRef(false);
  const [submittedGoal, setSubmittedGoal] = useState<string | null>(null);
  const {
    phase,
    currentTask,
    loading,
    createTask,
  } = useTaskStore();

  const handleSubmit = async (goal: string, fileReferences?: FileReference[], agentId?: string) => {
    hasRedirectedRef.current = false;
    setSubmittedGoal(goal);
    const constraints = fileReferences?.length
      ? { file_references: fileReferences }
      : undefined;
    const metadata = agentId ? { agent_id: agentId } : undefined;
    await createTask(goal, constraints, metadata);
  };

  // Redirect as soon as we have a task ID (don't wait for planning to finish)
  useEffect(() => {
    if (submittedGoal && currentTask && !hasRedirectedRef.current) {
      hasRedirectedRef.current = true;
      router.push(`/tasks/${currentTask.id}`);
    }
  }, [submittedGoal, currentTask, router]);

  // Brief submitting state while API roundtrip is in progress
  if (phase === 'creating' && submittedGoal && !currentTask) {
    return (
      <div className="min-h-full flex flex-col items-center justify-center px-4 py-12">
        <div className="text-center max-w-md">
          <div className="w-16 h-16 mx-auto mb-6 rounded-full bg-[oklch(0.65_0.25_180/0.1)] flex items-center justify-center">
            <ArrowPathIcon className="w-8 h-8 text-[oklch(0.65_0.25_180)] animate-spin" />
          </div>
          <h2 className="text-xl font-semibold text-[var(--foreground)] mb-2">
            Submitting...
          </h2>
        </div>
      </div>
    );
  }

  // Show input form
  return (
    <div className="min-h-full flex flex-col">
      {/* Header */}
      <div className="px-4 py-4 border-b border-[var(--border)]">
        <div className="max-w-2xl mx-auto">
          <Link
            href="/tasks"
            className="flex items-center gap-2 text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors"
          >
            <ArrowLeftIcon className="w-4 h-4" />
            Back to tasks
          </Link>
        </div>
      </div>

      {/* Main content - centered */}
      <div className="flex-1 flex items-center justify-center px-4 py-12">
        <div className="w-full">
          <div className="max-w-2xl mx-auto text-center mb-8">
            <h1 className="text-2xl font-bold text-[var(--foreground)] mb-2">
              What needs to get done?
            </h1>
            <p className="text-[var(--muted-foreground)]">
              Tell me the goal. I'll handle the rest.
            </p>
          </div>

          <NewTaskInput
            onSubmit={handleSubmit}
            isLoading={loading || phase === 'creating'}
            placeholder="Describe your goal..."
          />
        </div>
      </div>
    </div>
  );
}
