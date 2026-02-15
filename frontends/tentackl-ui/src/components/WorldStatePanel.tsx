'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ChevronDownIcon,
  ChevronUpIcon,
  PlayIcon,
  ExclamationTriangleIcon,
  CheckIcon,
  ClockIcon,
  ArrowPathIcon,
} from '@heroicons/react/24/outline';
import { formatDistanceToNow } from 'date-fns';
import Link from 'next/link';
import { tasksApi, Task, Checkpoint } from '../services/tasks';

interface WorldStatePanelProps {
  className?: string;
  onTaskClick?: (taskId: string) => void;
  onCheckpointApprove?: (taskId: string, stepId: string) => void;
}

function TaskMiniCard({ task, onClick }: { task: Task; onClick?: () => void }) {
  const completedSteps = task.steps.filter(s => s.status === 'completed').length;
  const totalSteps = task.steps.length;
  const progress = totalSteps > 0 ? (completedSteps / totalSteps) * 100 : 0;

  const statusColors: Record<string, string> = {
    executing: 'bg-yellow-500',
    checkpoint: 'bg-purple-500',
    ready: 'bg-cyan-500',
    paused: 'bg-orange-500',
  };

  return (
    <button
      onClick={onClick}
      className="w-full text-left p-2 rounded-md bg-gray-800/50 hover:bg-gray-800 border border-gray-700 hover:border-purple-500/50 transition-all group"
    >
      <div className="flex items-center gap-2">
        <div className={`w-2 h-2 rounded-full ${statusColors[task.status] || 'bg-gray-500'} ${task.status === 'executing' ? 'animate-pulse' : ''}`} />
        <span className="text-xs font-medium text-gray-200 truncate flex-1">
          {task.goal.length > 40 ? task.goal.substring(0, 40) + '...' : task.goal}
        </span>
      </div>
      <div className="flex items-center gap-2 mt-1.5">
        <div className="flex-1 h-1 bg-gray-700 rounded-full overflow-hidden">
          <div
            className="h-full bg-purple-500 rounded-full transition-all"
            style={{ width: `${progress}%` }}
          />
        </div>
        <span className="text-[10px] text-gray-500">
          {completedSteps}/{totalSteps}
        </span>
      </div>
    </button>
  );
}

function CheckpointMiniCard({
  checkpoint,
  onApprove,
}: {
  checkpoint: Checkpoint;
  onApprove?: () => void;
}) {
  return (
    <div className="p-2 rounded-md bg-purple-500/10 border border-purple-500/30">
      <div className="flex items-start gap-2">
        <ExclamationTriangleIcon className="w-4 h-4 text-purple-400 mt-0.5 flex-shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium text-purple-300 truncate">
            {checkpoint.checkpoint_name}
          </p>
          <p className="text-[10px] text-gray-400 mt-0.5 truncate">
            {checkpoint.description}
          </p>
        </div>
      </div>
      {onApprove && (
        <button
          onClick={onApprove}
          className="mt-2 w-full flex items-center justify-center gap-1 px-2 py-1 text-[10px] font-medium text-green-400 bg-green-500/20 rounded hover:bg-green-500/30 transition-colors"
        >
          <CheckIcon className="w-3 h-3" />
          Approve
        </button>
      )}
    </div>
  );
}

export function WorldStatePanel({
  className = '',
  onTaskClick,
  onCheckpointApprove,
}: WorldStatePanelProps) {
  const [isExpanded, setIsExpanded] = useState(true);
  const [activeTasks, setActiveTasks] = useState<Task[]>([]);
  const [pendingCheckpoints, setPendingCheckpoints] = useState<Checkpoint[]>([]);
  const [recentTasks, setRecentTasks] = useState<Task[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const fetchWorldState = useCallback(async () => {
    try {
      // Fetch active tasks (executing, checkpoint, ready)
      const [executing, checkpoint, ready, completed] = await Promise.all([
        tasksApi.listPlans('executing', 5).catch(() => []),
        tasksApi.listPlans('checkpoint', 5).catch(() => []),
        tasksApi.listPlans('ready', 5).catch(() => []),
        tasksApi.listPlans('completed', 3).catch(() => []),
      ]);

      setActiveTasks([...executing, ...checkpoint, ...ready]);
      setRecentTasks(completed);

      // Fetch pending checkpoints
      const checkpoints = await tasksApi.getPendingCheckpoints().catch(() => []);
      setPendingCheckpoints(checkpoints);
    } catch (err) {
      console.error('Failed to fetch world state:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchWorldState();

    // Poll every 10 seconds
    const interval = setInterval(fetchWorldState, 10000);
    return () => clearInterval(interval);
  }, [fetchWorldState]);

  const handleApproveCheckpoint = async (checkpoint: Checkpoint) => {
    try {
      await tasksApi.approveCheckpoint(checkpoint.plan_id, checkpoint.step_id);
      if (onCheckpointApprove) {
        onCheckpointApprove(checkpoint.plan_id, checkpoint.step_id);
      }
      // Refresh state
      fetchWorldState();
    } catch (err) {
      console.error('Failed to approve checkpoint:', err);
    }
  };

  const hasContent = activeTasks.length > 0 || pendingCheckpoints.length > 0 || recentTasks.length > 0;

  if (isLoading) {
    return (
      <div className={`p-3 border-b border-gray-700 bg-gray-900/50 ${className}`}>
        <div className="flex items-center gap-2 text-gray-500">
          <ArrowPathIcon className="w-4 h-4 animate-spin" />
          <span className="text-xs">Loading world state...</span>
        </div>
      </div>
    );
  }

  if (!hasContent) {
    return null;
  }

  return (
    <div className={`border-b border-gray-700 bg-gray-900/50 ${className}`}>
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-3 py-2 flex items-center justify-between hover:bg-gray-800/50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-purple-500 animate-pulse" />
          <span className="text-xs font-medium text-gray-300 uppercase tracking-wider">
            World State
          </span>
          {pendingCheckpoints.length > 0 && (
            <span className="px-1.5 py-0.5 text-[10px] font-medium text-purple-400 bg-purple-500/20 rounded-full">
              {pendingCheckpoints.length} pending
            </span>
          )}
        </div>
        {isExpanded ? (
          <ChevronUpIcon className="w-4 h-4 text-gray-500" />
        ) : (
          <ChevronDownIcon className="w-4 h-4 text-gray-500" />
        )}
      </button>

      {/* Content */}
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="px-3 pb-3 space-y-3">
              {/* Pending Checkpoints */}
              {pendingCheckpoints.length > 0 && (
                <div>
                  <h4 className="text-[10px] font-medium text-gray-500 uppercase tracking-wider mb-2 flex items-center gap-1">
                    <ExclamationTriangleIcon className="w-3 h-3" />
                    Awaiting Approval
                  </h4>
                  <div className="space-y-2">
                    {pendingCheckpoints.slice(0, 3).map((checkpoint) => (
                      <CheckpointMiniCard
                        key={`${checkpoint.plan_id}-${checkpoint.step_id}`}
                        checkpoint={checkpoint}
                        onApprove={() => handleApproveCheckpoint(checkpoint)}
                      />
                    ))}
                    {pendingCheckpoints.length > 3 && (
                      <Link
                        href="/tasks"
                        className="block text-center text-[10px] text-purple-400 hover:text-purple-300"
                      >
                        +{pendingCheckpoints.length - 3} more
                      </Link>
                    )}
                  </div>
                </div>
              )}

              {/* Active Tasks */}
              {activeTasks.length > 0 && (
                <div>
                  <h4 className="text-[10px] font-medium text-gray-500 uppercase tracking-wider mb-2 flex items-center gap-1">
                    <PlayIcon className="w-3 h-3" />
                    Active Tasks
                  </h4>
                  <div className="space-y-2">
                    {activeTasks.slice(0, 3).map((task) => (
                      <TaskMiniCard
                        key={task.id}
                        task={task}
                        onClick={() => onTaskClick?.(task.id)}
                      />
                    ))}
                    {activeTasks.length > 3 && (
                      <Link
                        href="/tasks"
                        className="block text-center text-[10px] text-purple-400 hover:text-purple-300"
                      >
                        +{activeTasks.length - 3} more
                      </Link>
                    )}
                  </div>
                </div>
              )}

              {/* Recent Completed */}
              {recentTasks.length > 0 && (
                <div>
                  <h4 className="text-[10px] font-medium text-gray-500 uppercase tracking-wider mb-2 flex items-center gap-1">
                    <ClockIcon className="w-3 h-3" />
                    Recently Completed
                  </h4>
                  <div className="space-y-1">
                    {recentTasks.map((task) => (
                      <button
                        key={task.id}
                        onClick={() => onTaskClick?.(task.id)}
                        className="w-full flex items-center gap-2 px-2 py-1 rounded text-left hover:bg-gray-800/50 transition-colors group"
                      >
                        <CheckIcon className="w-3 h-3 text-green-500 flex-shrink-0" />
                        <span className="text-[11px] text-gray-400 group-hover:text-gray-300 truncate flex-1">
                          {task.goal.length > 35 ? task.goal.substring(0, 35) + '...' : task.goal}
                        </span>
                        <span className="text-[10px] text-gray-600">
                          {formatDistanceToNow(new Date(task.completed_at || task.updated_at), { addSuffix: true })}
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* View All Link */}
              <Link
                href="/tasks"
                className="block w-full text-center py-1.5 text-xs text-purple-400 hover:text-purple-300 border border-purple-500/30 rounded-md hover:bg-purple-500/10 transition-colors"
              >
                View All Tasks
              </Link>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export default WorldStatePanel;
