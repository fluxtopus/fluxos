import React from 'react';
import { motion } from 'framer-motion';
import {
  CheckCircleIcon,
  XCircleIcon,
  ClockIcon,
  ChartBarIcon,
} from '@heroicons/react/24/outline';
import { useWorkflowStore } from '../store/workflowStore';

interface MetricsPanelProps {
  compact?: boolean;
}

export const MetricsPanel: React.FC<MetricsPanelProps> = ({ compact = false }) => {
  const { currentMetrics } = useWorkflowStore();

  if (!currentMetrics) {
    return null;
  }

  const metrics = [
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
  ];

  return (
    <div className={compact ? "" : "p-4 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg"}>
      <h2 className={compact ? "text-xs font-medium mb-2 text-gray-700 dark:text-gray-300" : "text-lg font-semibold mb-4 text-gray-900 dark:text-white"}>
        {compact ? 'Metrics' : 'Workflow Metrics'}
      </h2>

      <div className={compact ? "grid grid-cols-2 gap-2" : "grid grid-cols-2 gap-4"}>
        {metrics.map((metric, index) => (
          <motion.div
            key={metric.label}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.1 }}
            className={`${compact ? 'p-2' : 'p-3'} bg-gray-50 dark:bg-gray-700 border ${metric.borderColor} rounded transition-all`}
          >
            <div className="flex items-center justify-between">
              <div>
                <p className={`${compact ? 'text-[9px]' : 'text-[10px]'} text-gray-500 dark:text-gray-400`}>
                  {metric.label}
                </p>
                <p className={`${compact ? 'text-sm' : 'text-2xl'} font-bold ${metric.color}`}>
                  {metric.value}
                </p>
              </div>
              {!compact && (
                <metric.icon className={`${compact ? 'w-5 h-5' : 'w-8 h-8'} ${metric.color}`} />
              )}
            </div>
          </motion.div>
        ))}
      </div>

      <div className={compact ? "mt-2 space-y-2" : "mt-4 space-y-3"}>
        <div>
          <div className={`${compact ? 'text-xs' : 'text-sm'} flex justify-between mb-1`}>
            <span className="text-gray-500 dark:text-gray-400">Success Rate</span>
            <span className="font-medium text-green-600 dark:text-green-400">
              {currentMetrics.success_rate.toFixed(1)}%
            </span>
          </div>
          <div className={`w-full bg-gray-200 dark:bg-gray-700 rounded ${compact ? 'h-2' : 'h-3'}`}>
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${currentMetrics.success_rate}%` }}
              transition={{ duration: 1, ease: 'easeOut' }}
              className={`bg-green-500 dark:bg-green-600 rounded ${compact ? 'h-2' : 'h-3'}`}
            />
          </div>
        </div>

        <div>
          <p className={`${compact ? 'text-[10px]' : 'text-xs'} text-gray-500 dark:text-gray-400`}>
            Total Execution Time
          </p>
          <p className={`${compact ? 'text-sm' : 'text-lg'} font-semibold text-blue-600 dark:text-blue-400`}>
            {(currentMetrics.total_execution_time / 1000).toFixed(2)}s
          </p>
        </div>

        <div>
          <p className={`${compact ? 'text-[10px]' : 'text-xs'} text-gray-500 dark:text-gray-400`}>
            Avg Node Time
          </p>
          <p className={`${compact ? 'text-sm' : 'text-lg'} font-semibold text-blue-600 dark:text-blue-400`}>
            {(currentMetrics.average_node_time / 1000).toFixed(2)}s
          </p>
        </div>
      </div>
    </div>
  );
};
