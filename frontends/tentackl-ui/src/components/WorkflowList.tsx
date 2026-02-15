import React, { useEffect } from 'react';
import { motion } from 'framer-motion';
import { format } from 'date-fns';
import toast from 'react-hot-toast';
import { ArrowPathIcon, TrashIcon } from '@heroicons/react/24/outline';
import { useWorkflowStore } from '../store/workflowStore';
import { WorkflowStatus } from '../types/workflow';
import api from '../services/api';

const statusColors = {
  [WorkflowStatus.PENDING]: 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 border border-gray-400 dark:border-gray-600',
  [WorkflowStatus.RUNNING]: 'bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400 border border-blue-500 dark:border-blue-500',
  [WorkflowStatus.COMPLETED]: 'bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-400 border border-green-500 dark:border-green-500',
  [WorkflowStatus.FAILED]: 'bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-400 border border-red-500 dark:border-red-500',
  [WorkflowStatus.PAUSED]: 'bg-yellow-50 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400 border border-yellow-500 dark:border-yellow-500',
  [WorkflowStatus.CANCELLED]: 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 border border-gray-400 dark:border-gray-600',
};

export const WorkflowList: React.FC = () => {
  const {
    workflows,
    loading,
    manualRefresh,
    error,
    fetchWorkflows,
    selectWorkflow,
    currentWorkflow,
    connectWorkflowsWebSocket
  } = useWorkflowStore();
  const [isLoadingFromUrl, setIsLoadingFromUrl] = React.useState(false);

  const handleDelete = async (workflowId: string, event: React.MouseEvent) => {
    event.stopPropagation(); // Prevent selecting the workflow

    if (window.confirm(`Are you sure you want to delete workflow ${workflowId}?`)) {
      try {
        await api.delete(`/api/workflows/${workflowId}`);
        toast.success('Workflow deleted');
        await fetchWorkflows(true); // Refresh the list (manual action)

        // If we deleted the current workflow, clear selection
        if (currentWorkflow?.id === workflowId) {
          // Clear the current workflow by disconnecting WebSocket
          // The store will handle clearing when workflows list updates
        }
      } catch (error) {
        console.error('Failed to delete workflow:', error);
        toast.error('Failed to delete workflow');
      }
    }
  };

  // Initialize workflows and WebSocket connection on mount
  useEffect(() => {
    fetchWorkflows();
    connectWorkflowsWebSocket();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Handle URL parameter selection on mount and when URL changes
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const workflowRunId = params.get('workflowRunId');

    if (workflowRunId && workflowRunId !== currentWorkflow?.id) {
      setIsLoadingFromUrl(true);
      // selectWorkflow will fetch the workflow from API even if not in the list
      selectWorkflow(workflowRunId).finally(() => {
        setIsLoadingFromUrl(false);
      });
    }
  }, [currentWorkflow, selectWorkflow]); // Run when currentWorkflow or selectWorkflow changes

  // Listen for browser navigation (back/forward buttons)
  useEffect(() => {
    const handlePopState = () => {
      const params = new URLSearchParams(window.location.search);
      const workflowRunId = params.get('workflowRunId');

      if (workflowRunId) {
        setIsLoadingFromUrl(true);
        selectWorkflow(workflowRunId).finally(() => {
          setIsLoadingFromUrl(false);
        });
      }
    };

    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, [selectWorkflow]);

  // Handle workflow selection with URL update
  const handleSelectWorkflow = (workflowId: string) => {
    selectWorkflow(workflowId);
    // Update URL parameter
    const url = new URL(window.location.href);
    url.searchParams.set('workflowRunId', workflowId);
    window.history.pushState({}, '', url.toString());
  };

  // Show loading state when initially loading or loading from URL
  if ((loading && workflows.length === 0) || isLoadingFromUrl) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="flex flex-col items-center gap-3">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 dark:border-blue-400"></div>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {isLoadingFromUrl ? 'Loading workflow run...' : 'Loading workflows...'}
          </p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 bg-red-50 dark:bg-red-900/20 border border-red-500 dark:border-red-500 rounded-md">
        <p className="text-red-700 dark:text-red-400">Error: {error}</p>
        <button
          onClick={() => fetchWorkflows(true)}
          className="mt-2 text-sm text-red-700 dark:text-red-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
        >
          Retry
        </button>
      </div>
    );
  }

  if (workflows.length === 0) {
    return (
      <div className="p-8 text-center">
        <p className="text-gray-500 dark:text-gray-400">No workflow runs found</p>
        <p className="text-sm text-gray-400 dark:text-gray-500 mt-2">
          Run an example or use Flux to create a workflow
        </p>
      </div>
    );
  }

  // Sort workflows by created_at (newest first)
  const sortedWorkflows = [...workflows].sort((a, b) => {
    const dateA = a.created_at ? new Date(a.created_at).getTime() : 0;
    const dateB = b.created_at ? new Date(b.created_at).getTime() : 0;
    return dateB - dateA;
  });

  return (
    <div className="space-y-2">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-xs font-medium text-gray-700 dark:text-gray-300">
          Workflow Run History ({workflows.length})
        </h3>
        <button
          onClick={() => fetchWorkflows(true)}
          className="p-1 border border-gray-300 dark:border-gray-600 rounded hover:border-blue-500 dark:hover:border-blue-400 transition-all"
          title="Refresh workflows"
          disabled={manualRefresh}
        >
          <ArrowPathIcon className={`w-4 h-4 text-gray-700 dark:text-gray-300 ${manualRefresh ? 'animate-spin' : ''}`} />
        </button>
      </div>
      {sortedWorkflows.map((workflow, index) => (
        <motion.div
          key={workflow.id}
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: index * 0.05 }}
          className={`p-3 cursor-pointer transition-all border rounded-md ${
            currentWorkflow?.id === workflow.id
              ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-500 dark:border-blue-500'
              : 'bg-white dark:bg-gray-700 border-gray-300 dark:border-gray-600 hover:border-blue-400 dark:hover:border-blue-500'
          }`}
          onClick={() => handleSelectWorkflow(workflow.id)}
        >
          <div className="flex items-start justify-between">
            <div className="flex-1 min-w-0">
              <h3 className="font-semibold text-gray-900 dark:text-white truncate">
                {workflow.name}
              </h3>
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1 truncate font-mono">
                {workflow.id}
              </p>
              {workflow.created_at && (
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  {format(new Date(workflow.created_at), 'MMM d, yyyy h:mm a')}
                </p>
              )}
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <span className={`px-2 py-0.5 text-xs font-medium rounded ${
                statusColors[workflow.status]
              }`}>
                {workflow.status}
              </span>
              <button
                onClick={(e) => handleDelete(workflow.id, e)}
                className="p-1 border border-red-300 dark:border-red-600 rounded hover:border-red-500 dark:hover:border-red-500 transition-all"
                title="Delete workflow"
              >
                <TrashIcon className="w-3 h-3 text-red-600 dark:text-red-400" />
              </button>
            </div>
          </div>
        </motion.div>
      ))}
    </div>
  );
};
