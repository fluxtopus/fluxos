'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { CheckIcon, XMarkIcon, ClockIcon } from '@heroicons/react/24/outline';
import { useTaskStore } from '../../store/taskStore';
import type { Task } from '../../types/task';

interface DecisionStackProps {
  tasks: Task[];
}

/**
 * DecisionStack - Inline checkpoint decisions shown above filters.
 * Creates an "inbox zero" clearable experience for pending decisions.
 */
export function DecisionStack({ tasks }: DecisionStackProps) {
  const { approveCheckpoint, rejectCheckpoint } = useTaskStore();
  const [actingOn, setActingOn] = useState<string | null>(null);

  const checkpointTasks = tasks.filter(t => t.status === 'checkpoint');

  if (checkpointTasks.length === 0) return null;

  const handleApprove = async (task: Task) => {
    const step = task.steps.find(s => s.status === 'checkpoint');
    if (!step) return;
    setActingOn(task.id);
    try {
      await approveCheckpoint(task.id, step.id);
    } finally {
      setActingOn(null);
    }
  };

  const handleReject = async (task: Task) => {
    const step = task.steps.find(s => s.status === 'checkpoint');
    if (!step) return;
    setActingOn(task.id);
    try {
      await rejectCheckpoint(task.id, step.id, 'Rejected from task list');
    } finally {
      setActingOn(null);
    }
  };

  return (
    <div className="mb-6">
      <div className="flex items-center gap-2 mb-3">
        <ClockIcon className="w-4 h-4 text-amber-500" />
        <span className="text-xs font-mono tracking-wider text-amber-500">
          {checkpointTasks.length} DECISION{checkpointTasks.length !== 1 ? 'S' : ''} PENDING
        </span>
      </div>
      <div className="space-y-2">
        <AnimatePresence mode="popLayout">
          {checkpointTasks.map((task) => {
            const isActing = actingOn === task.id;
            return (
              <motion.div
                key={task.id}
                layout
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, x: -20, transition: { duration: 0.2 } }}
                className="flex items-center gap-3 px-4 py-3 rounded-lg border border-amber-500/30 bg-amber-500/5"
              >
                <span className="flex-1 text-sm text-[var(--foreground)] truncate">
                  {task.goal}
                </span>
                <div className="flex items-center gap-1.5 flex-shrink-0">
                  <button
                    onClick={() => handleApprove(task)}
                    disabled={isActing}
                    className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-mono tracking-wider rounded border border-emerald-500/50 text-emerald-500 hover:bg-emerald-500/10 transition-colors disabled:opacity-50"
                  >
                    <CheckIcon className="w-3 h-3" />
                    APPROVE
                  </button>
                  <button
                    onClick={() => handleReject(task)}
                    disabled={isActing}
                    className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-mono tracking-wider rounded border border-[var(--destructive)]/50 text-[var(--destructive)] hover:bg-[var(--destructive)]/10 transition-colors disabled:opacity-50"
                  >
                    <XMarkIcon className="w-3 h-3" />
                    REJECT
                  </button>
                </div>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
    </div>
  );
}
