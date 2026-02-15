import React, { useEffect, useState } from 'react';
import { ChevronDownIcon, ChevronUpIcon, ArrowPathIcon, PlayIcon } from '@heroicons/react/24/outline';
import { motion, AnimatePresence } from 'framer-motion';
import { format } from 'date-fns';
import { getConversationSpecs, getSpecRuns, type WorkflowSpec, type WorkflowRun } from '../services/arrow';

interface WorkflowSummaryProps {
  conversationId: string;
  onRunClick: (runId: string) => void;
}

interface WorkflowWithRuns extends WorkflowSpec {
  runs: WorkflowRun[];
  isLoadingRuns: boolean;
}

const WorkflowSummary: React.FC<WorkflowSummaryProps> = ({ conversationId, onRunClick }) => {
  const [isExpanded, setIsExpanded] = useState(true);
  const [workflows, setWorkflows] = useState<WorkflowWithRuns[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadWorkflows = async () => {
      setIsLoading(true);
      setError(null);
      try {
        // Get all specs for this conversation
        const specs = await getConversationSpecs(conversationId);
        
        // Get runs for each spec
        const workflowsWithRuns: WorkflowWithRuns[] = await Promise.all(
          specs.map(async (spec) => {
            try {
              const runs = await getSpecRuns(spec.id, 10); // Get latest 10 runs
              return {
                ...spec,
                runs,
                isLoadingRuns: false,
              };
            } catch (err) {
              console.error(`Failed to load runs for spec ${spec.id}:`, err);
              return {
                ...spec,
                runs: [],
                isLoadingRuns: false,
              };
            }
          })
        );

        setWorkflows(workflowsWithRuns);
      } catch (err: any) {
        console.error('Failed to load workflows:', err);
        setError(err?.message || 'Failed to load workflows');
      } finally {
        setIsLoading(false);
      }
    };

    if (conversationId) {
      loadWorkflows();
    }
  }, [conversationId]);

  const getStatusColor = (status: string) => {
    switch (status.toLowerCase()) {
      case 'completed':
        return 'text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800';
      case 'failed':
        return 'text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800';
      case 'running':
        return 'text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800';
      case 'pending':
        return 'text-yellow-600 dark:text-yellow-400 bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800';
      default:
        return 'text-gray-600 dark:text-gray-400 bg-gray-50 dark:bg-gray-900/20 border-gray-200 dark:border-gray-800';
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

  if (isLoading) {
    return (
      <div className="border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 p-4">
        <div className="flex items-center justify-center gap-2 text-sm text-gray-500 dark:text-gray-400">
          <ArrowPathIcon className="w-4 h-4 animate-spin" />
          <span>Loading workflows...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="border-b border-gray-200 dark:border-gray-700 bg-red-50 dark:bg-red-900/20 p-4">
        <div className="text-sm text-red-700 dark:text-red-400">
          Error: {error}
        </div>
      </div>
    );
  }

  if (workflows.length === 0) {
    return null; // Don't show summary if no workflows
  }

  const totalRuns = workflows.reduce((sum, wf) => sum + wf.runs.length, 0);

  return (
    <div className="border-b border-gray-200 dark:border-gray-700 bg-gradient-to-r from-purple-50 to-blue-50 dark:from-purple-900/20 dark:to-blue-900/20">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-4 py-3 flex items-center justify-between hover:bg-purple-100/50 dark:hover:bg-purple-900/30 transition-colors"
      >
        <div className="flex items-center gap-3">
          <div className="text-lg font-semibold text-gray-900 dark:text-white">
            Workflows Created
          </div>
          <div className="text-sm text-gray-600 dark:text-gray-400">
            {workflows.length} workflow{workflows.length !== 1 ? 's' : ''} • {totalRuns} run{totalRuns !== 1 ? 's' : ''}
          </div>
        </div>
        {isExpanded ? (
          <ChevronUpIcon className="w-5 h-5 text-gray-500" />
        ) : (
          <ChevronDownIcon className="w-5 h-5 text-gray-500" />
        )}
      </button>

      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="px-4 pb-4 space-y-3">
              {workflows.map((workflow) => (
                <div
                  key={workflow.id}
                  className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-3 shadow-sm"
                >
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <h4 className="font-semibold text-gray-900 dark:text-white truncate">
                          {workflow.name}
                        </h4>
                        <span className="text-xs px-2 py-0.5 rounded bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300">
                          v{workflow.version}
                        </span>
                      </div>
                      {workflow.description && (
                        <p className="text-sm text-gray-600 dark:text-gray-400 line-clamp-2">
                          {workflow.description}
                        </p>
                      )}
                      <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                        Created {format(new Date(workflow.created_at), 'MMM d, yyyy HH:mm')}
                      </div>
                    </div>
                  </div>

                  {workflow.runs.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
                      <div className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2">
                        Recent Runs
                      </div>
                      <div className="space-y-2">
                        {workflow.runs.map((run) => (
                          <div
                            key={run.run_id}
                            onClick={() => onRunClick(run.run_id)}
                            className="flex items-center justify-between p-2 bg-gray-50 dark:bg-gray-900/50 rounded-md border border-gray-200 dark:border-gray-700 hover:border-blue-400 dark:hover:border-blue-600 cursor-pointer transition-colors group"
                          >
                            <div className="flex items-center gap-2 flex-1 min-w-0">
                              <span className={`inline-flex items-center gap-1 text-xs px-2 py-1 rounded border ${getStatusColor(run.status)}`}>
                                <span>{getStatusIcon(run.status)}</span>
                                <span className="font-medium">{run.status}</span>
                              </span>
                              <span className="text-xs text-gray-600 dark:text-gray-400">
                                Run #{run.run_number}
                              </span>
                            </div>
                            <div className="flex items-center gap-2">
                              <div className="text-xs text-gray-500 dark:text-gray-400">
                                {run.completed_at
                                  ? format(new Date(run.completed_at), 'MMM d, HH:mm')
                                  : run.started_at
                                  ? format(new Date(run.started_at), 'MMM d, HH:mm')
                                  : format(new Date(run.created_at), 'MMM d, HH:mm')
                                }
                              </div>
                              <PlayIcon className="w-4 h-4 text-gray-400 group-hover:text-blue-500 dark:group-hover:text-blue-400 transition-colors" />
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {workflow.runs.length === 0 && (
                    <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700 text-xs text-gray-500 dark:text-gray-400 text-center">
                      No runs yet
                    </div>
                  )}
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default WorkflowSummary;

