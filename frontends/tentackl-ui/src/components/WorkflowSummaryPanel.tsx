import React from 'react';
import { motion } from 'framer-motion';
import {
  CheckCircleIcon,
  XCircleIcon,
  ClockIcon,
  ChartBarIcon,
  ClipboardDocumentIcon,
} from '@heroicons/react/24/outline';
import toast from 'react-hot-toast';
import { useWorkflowStore } from '../store/workflowStore';
import api from '../services/api';

interface RunDetails {
  run_id: string;
  keep_alive: boolean;
  waiting: boolean;
  waiting_for?: any;
  root_status?: string | null;
  counts: Record<string, number>;
}

export const WorkflowSummaryPanel: React.FC = () => {
  const { currentWorkflow, currentMetrics } = useWorkflowStore();
  const [details, setDetails] = React.useState<RunDetails | null>(null);
  const [manualRefresh, setManualRefresh] = React.useState(false);

  const load = async (isManual = false) => {
    if (!currentWorkflow) return;
    if (isManual) setManualRefresh(true);
    try {
      const { data } = await api.get(`/api/workflows/${currentWorkflow.id}/run_details`);
      setDetails(data);
    } catch (e) {
      setDetails(null);
    } finally {
      if (isManual) setManualRefresh(false);
    }
  };

  React.useEffect(() => {
    load();
    // Poll lightly while a run is active
    const t = setInterval(() => {
      if (currentWorkflow) load(false);
    }, 4000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentWorkflow?.id]);

  if (!currentWorkflow) return null;

  // Copy workflow ID to clipboard
  const handleCopyWorkflowId = async () => {
    const id = currentWorkflow?.id;
    if (!id) return;
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(id);
      } else {
        const ta = document.createElement('textarea');
        ta.value = id;
        ta.style.position = 'fixed';
        ta.style.left = '-9999px';
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
      }
      toast.success('Workflow ID copied');
    } catch (e) {
      toast.error('Failed to copy ID');
    }
  };

  const metrics = currentMetrics ? [
    {
      label: 'Total Nodes',
      value: currentMetrics.total_nodes,
      icon: ChartBarIcon,
      color: 'text-gray-600 dark:text-gray-400',
      borderColor: 'border-gray-400 dark:border-gray-600',
    },
    {
      label: 'Completed',
      value: currentMetrics.completed_nodes,
      icon: CheckCircleIcon,
      color: 'text-green-600 dark:text-green-400',
      borderColor: 'border-green-500 dark:border-green-500',
    },
    {
      label: 'Failed',
      value: currentMetrics.failed_nodes,
      icon: XCircleIcon,
      color: 'text-red-600 dark:text-red-400',
      borderColor: 'border-red-500 dark:border-red-500',
    },
    {
      label: 'Pending',
      value: currentMetrics.pending_nodes,
      icon: ClockIcon,
      color: 'text-yellow-600 dark:text-yellow-400',
      borderColor: 'border-yellow-500 dark:border-yellow-500',
    },
  ] : [];

  return (
    <div className="space-y-3">
      {/* Workflow Name and ID */}
      <div className="border-b border-gray-200 dark:border-gray-700 pb-3">
        <h2 className="text-sm font-semibold text-gray-900 dark:text-white mb-1">
          {currentWorkflow.name}
        </h2>
        <div className="flex items-center gap-2">
          <p className="text-xs text-gray-500 dark:text-gray-400 font-mono truncate">
            {currentWorkflow.id}
          </p>
          <button
            onClick={handleCopyWorkflowId}
            className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded transition-colors"
            title="Copy Workflow ID"
          >
            <ClipboardDocumentIcon className="w-3.5 h-3.5 text-gray-500 dark:text-gray-400" />
          </button>
        </div>
      </div>

      {/* Run Details Section */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-xs font-medium text-gray-800 dark:text-gray-200">Run Status</h3>
          <button
            onClick={() => load(true)}
            disabled={manualRefresh}
            className="text-[10px] px-2 py-0.5 rounded bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-100 hover:bg-gray-300 dark:hover:bg-gray-600 disabled:opacity-50"
          >
            {manualRefresh ? '…' : 'Refresh'}
          </button>
        </div>
        {details ? (
          <div className="text-xs text-gray-700 dark:text-gray-300 space-y-1 bg-gray-50 dark:bg-gray-700 rounded-lg p-2">
            <div className="flex justify-between">
              <span className="text-gray-500 dark:text-gray-400">Root:</span>
              <span className="font-semibold">{details.root_status || 'unknown'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500 dark:text-gray-400">Keep Alive:</span>
              <span>{String(details.keep_alive)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500 dark:text-gray-400">Waiting:</span>
              <span>{String(details.waiting)}</span>
            </div>
            {details.waiting_for && (
              <div className="pt-1 border-t border-gray-200 dark:border-gray-600">
                <pre className="text-[10px] bg-gray-100 dark:bg-gray-800 rounded p-1 overflow-auto max-h-20">
                  {JSON.stringify(details.waiting_for, null, 2)}
                </pre>
              </div>
            )}
          </div>
        ) : (
          <div className="text-xs text-gray-500">No details</div>
        )}
      </div>

      {/* Metrics Section */}
      {currentMetrics && (
        <div>
          <h2 className="text-xs font-medium mb-2 text-gray-700 dark:text-gray-300">
            Workflow Metrics
          </h2>

          <div className="grid grid-cols-2 gap-2">
            {metrics.map((metric, index) => (
              <motion.div
                key={metric.label}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.1 }}
                className={`p-2 bg-gray-50 dark:bg-gray-700 border ${metric.borderColor} rounded transition-all`}
              >
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-[9px] text-gray-500 dark:text-gray-400">
                      {metric.label}
                    </p>
                    <p className={`text-sm font-bold ${metric.color}`}>
                      {metric.value}
                    </p>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>

          <div className="mt-2 space-y-2">
            <div>
              <div className="text-xs flex justify-between mb-1">
                <span className="text-gray-500 dark:text-gray-400">Success Rate</span>
                <span className="font-medium text-green-600 dark:text-green-400">
                  {currentMetrics.success_rate.toFixed(1)}%
                </span>
              </div>
              <div className="w-full bg-gray-200 dark:bg-gray-700 rounded h-2">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${currentMetrics.success_rate}%` }}
                  transition={{ duration: 1, ease: 'easeOut' }}
                  className="bg-green-500 dark:bg-green-600 rounded h-2"
                />
              </div>
            </div>

            <div>
              <p className="text-[10px] text-gray-500 dark:text-gray-400">
                Total Execution Time
              </p>
              <p className="text-sm font-semibold text-blue-600 dark:text-blue-400">
                {(currentMetrics.total_execution_time / 1000).toFixed(2)}s
              </p>
            </div>

            <div>
              <p className="text-[10px] text-gray-500 dark:text-gray-400">
                Avg Node Time
              </p>
              <p className="text-sm font-semibold text-blue-600 dark:text-blue-400">
                {(currentMetrics.average_node_time / 1000).toFixed(2)}s
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
