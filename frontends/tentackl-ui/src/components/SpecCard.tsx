import React, { useState } from 'react';
import { ChevronDownIcon, ChevronUpIcon, PlayIcon, ArrowPathIcon } from '@heroicons/react/24/outline';
import { motion, AnimatePresence } from 'framer-motion';
import { format } from 'date-fns';
import type { WorkflowSpec, WorkflowRun } from '../services/arrow';
import { executeSpec } from '../services/arrow';
import { useArrowStore } from '../store/arrowStore';

interface SpecCardProps {
  spec: WorkflowSpec;
  runs: WorkflowRun[];
  isLoadingRuns: boolean;
  onRunClick: (runId: string) => void;
}

const SpecCard: React.FC<SpecCardProps> = ({ spec, runs, isLoadingRuns, onRunClick }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [isExecuting, setIsExecuting] = useState(false);
  const loadRuns = useArrowStore(state => state.loadRuns);

  const handleExpand = () => {
    setIsExpanded(!isExpanded);
    // Load runs when expanding if not already loaded
    if (!isExpanded && runs.length === 0 && !isLoadingRuns) {
      loadRuns(spec.id);
    }
  };

  const handleRerun = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsExecuting(true);
    try {
      const result = await executeSpec(spec.id);
      if (result.ok && result.run_id) {
        // Refresh runs list
        await loadRuns(spec.id);
        // Optionally navigate to the run
        onRunClick(result.run_id);
      }
    } catch (error) {
      console.error('Failed to execute spec:', error);
    } finally {
      setIsExecuting(false);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'completed':
        return 'text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-900/20';
      case 'failed':
        return 'text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20';
      case 'running':
        return 'text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/20';
      case 'pending':
        return 'text-yellow-600 dark:text-yellow-400 bg-yellow-50 dark:bg-yellow-900/20';
      default:
        return 'text-gray-600 dark:text-gray-400 bg-gray-50 dark:bg-gray-900/20';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status.toLowerCase()) {
      case 'completed':
        return '✅';
      case 'failed':
        return '❌';
      case 'running':
        return '🔄';
      case 'pending':
        return '⏳';
      default:
        return '⏸️';
    }
  };

  return (
    <div className="border border-gray-300 dark:border-gray-700 rounded-lg overflow-hidden bg-white dark:bg-gray-800 shadow-sm hover:shadow-md transition-shadow">
      {/* Header - always visible */}
      <div
        onClick={handleExpand}
        className="p-4 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <h3 className="font-semibold text-gray-900 dark:text-white truncate">
                {spec.name}
              </h3>
              <span className="text-xs px-2 py-0.5 rounded bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300">
                v{spec.version}
              </span>
            </div>
            {spec.description && (
              <p className="text-sm text-gray-600 dark:text-gray-400 mt-1 line-clamp-2">
                {spec.description}
              </p>
            )}
            <div className="flex items-center gap-3 mt-2 text-xs text-gray-500 dark:text-gray-400">
              <span>{spec.run_count} run{spec.run_count !== 1 ? 's' : ''}</span>
              <span>•</span>
              <span>{format(new Date(spec.created_at), 'MMM d, yyyy')}</span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleRerun}
              disabled={isExecuting}
              className={`p-2 rounded-md transition-colors ${
                isExecuting
                  ? 'bg-gray-100 dark:bg-gray-700 text-gray-400 cursor-not-allowed'
                  : 'bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-400 hover:bg-green-100 dark:hover:bg-green-900/40'
              }`}
              title="Rerun this workflow"
            >
              {isExecuting ? (
                <ArrowPathIcon className="w-4 h-4 animate-spin" />
              ) : (
                <PlayIcon className="w-4 h-4" />
              )}
            </button>
            {isExpanded ? (
              <ChevronUpIcon className="w-5 h-5 text-gray-500" />
            ) : (
              <ChevronDownIcon className="w-5 h-5 text-gray-500" />
            )}
          </div>
        </div>
      </div>

      {/* Collapsible runs list */}
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="border-t border-gray-200 dark:border-gray-700 overflow-hidden"
          >
            <div className="p-4 bg-gray-50 dark:bg-gray-900/50">
              <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
                Recent Runs
              </h4>

              {isLoadingRuns && (
                <div className="flex items-center justify-center py-6 text-gray-500 dark:text-gray-400">
                  <ArrowPathIcon className="w-5 h-5 animate-spin mr-2" />
                  <span className="text-sm">Loading runs...</span>
                </div>
              )}

              {!isLoadingRuns && runs.length === 0 && (
                <div className="text-center py-6 text-gray-500 dark:text-gray-400 text-sm">
                  No runs yet
                </div>
              )}

              {!isLoadingRuns && runs.length > 0 && (
                <div className="space-y-2">
                  {runs.map((run) => (
                    <div
                      key={run.run_id}
                      onClick={() => onRunClick(run.run_id)}
                      className="flex items-center justify-between p-3 bg-white dark:bg-gray-800 rounded-md border border-gray-200 dark:border-gray-700 hover:border-blue-400 dark:hover:border-blue-600 cursor-pointer transition-colors"
                    >
                      <div className="flex items-center gap-3 flex-1 min-w-0">
                        <span className={`inline-flex items-center gap-1 text-xs px-2 py-1 rounded ${getStatusColor(run.status)}`}>
                          <span>{getStatusIcon(run.status)}</span>
                          <span className="font-medium">{run.status}</span>
                        </span>
                        <span className="text-sm text-gray-600 dark:text-gray-400">
                          Run #{run.run_number}
                        </span>
                      </div>

                      <div className="text-xs text-gray-500 dark:text-gray-400">
                        {run.completed_at
                          ? format(new Date(run.completed_at), 'MMM d, HH:mm')
                          : run.started_at
                          ? format(new Date(run.started_at), 'MMM d, HH:mm')
                          : format(new Date(run.created_at), 'MMM d, HH:mm')
                        }
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default SpecCard;
