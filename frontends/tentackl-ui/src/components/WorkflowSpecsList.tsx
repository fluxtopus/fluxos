import React, { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { format } from 'date-fns';
import toast from 'react-hot-toast';
import { ArrowPathIcon, PlayIcon, EyeIcon, DocumentTextIcon } from '@heroicons/react/24/outline';
import { WorkflowSpecSummary, WorkflowRun } from '../types/workflow';
import api from '../services/api';

export const WorkflowSpecsList: React.FC = () => {
  const [specs, setSpecs] = useState<WorkflowSpecSummary[]>([]);
  const [selectedSpec, setSelectedSpec] = useState<string | null>(null);
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [runLoading, setRunLoading] = useState(false);

  const fetchSpecs = async () => {
    try {
      setLoading(true);
      const response = await api.get('/api/workflow-specs');
      setSpecs(response.data.specs || []);
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch workflow specs');
    } finally {
      setLoading(false);
    }
  };

  const fetchRunsForSpec = async (specId: string) => {
    try {
      const response = await api.get(`/api/workflow-runs/spec/${specId}`);
      setRuns(response.data.runs || []);
    } catch (err: any) {
      console.error('Failed to fetch runs:', err);
    }
  };

  const createRun = async (specId: string, specName: string) => {
    if (!window.confirm(`Create a new run for workflow "${specName}"?`)) {
      return;
    }

    try {
      setRunLoading(true);
      const response = await api.post(`/api/workflow-runs/spec/${specId}`, {
        parameters: {},
        triggered_by: 'manual'
      });

      toast.success(`Created run #${response.data.run_number} for ${specName}`);

      // Refresh runs if this spec is selected
      if (selectedSpec === specId) {
        await fetchRunsForSpec(specId);
      }
    } catch (err: any) {
      toast.error(`Failed to create run: ${err.message}`);
    } finally {
      setRunLoading(false);
    }
  };

  const handleSelectSpec = async (specId: string) => {
    setSelectedSpec(specId);
    await fetchRunsForSpec(specId);
  };

  useEffect(() => {
    fetchSpecs();
  }, []);

  if (loading && specs.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 dark:border-blue-400"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 bg-red-50 dark:bg-red-900/20 border border-red-500 rounded-md">
        <p className="text-red-700 dark:text-red-400">Error: {error}</p>
        <button
          onClick={fetchSpecs}
          className="mt-2 text-sm text-red-700 dark:text-red-400 hover:text-blue-600 transition-colors"
        >
          Retry
        </button>
      </div>
    );
  }

  if (specs.length === 0) {
    return (
      <div className="p-8 text-center">
        <DocumentTextIcon className="w-16 h-16 mx-auto text-gray-400 dark:text-gray-500 mb-4" />
        <p className="text-gray-500 dark:text-gray-400">No workflow specs found</p>
        <p className="text-sm text-gray-400 dark:text-gray-500 mt-2">
          Register a workflow spec to get started
        </p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* Specs List */}
      <div className="space-y-2">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
            Workflow Specifications ({specs.length})
          </h3>
          <button
            onClick={fetchSpecs}
            className="p-1 border border-gray-300 dark:border-gray-600 rounded hover:border-blue-500 transition-all"
            title="Refresh specs"
          >
            <ArrowPathIcon className={`w-4 h-4 text-gray-700 dark:text-gray-300 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>

        {specs.map((spec, index) => (
          <motion.div
            key={spec.id}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.05 }}
            className={`p-4 cursor-pointer transition-all border rounded-lg ${
              selectedSpec === spec.id
                ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-500 dark:border-blue-500'
                : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 hover:border-blue-400'
            }`}
            onClick={() => handleSelectSpec(spec.id)}
          >
            <div className="flex items-start justify-between">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <h4 className="font-semibold text-gray-900 dark:text-white">
                    {spec.name}
                  </h4>
                  {spec.is_active ? (
                    <span className="px-2 py-0.5 text-xs font-medium rounded bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 border border-green-500">
                      Active
                    </span>
                  ) : (
                    <span className="px-2 py-0.5 text-xs font-medium rounded bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 border border-gray-400">
                      Inactive
                    </span>
                  )}
                </div>

                {spec.description && (
                  <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                    {spec.description}
                  </p>
                )}

                <div className="flex items-center gap-4 mt-2 text-xs text-gray-500 dark:text-gray-400">
                  <span>v{spec.version}</span>
                  <span>{format(new Date(spec.created_at), 'MMM d, yyyy')}</span>
                  {spec.run_count !== undefined && (
                    <span className="font-medium">{spec.run_count} runs</span>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-2 flex-shrink-0 ml-4">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    createRun(spec.id, spec.name);
                  }}
                  disabled={!spec.is_active || runLoading}
                  className="p-2 border border-blue-300 dark:border-blue-600 rounded hover:bg-blue-50 dark:hover:bg-blue-900/30 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                  title="Create new run"
                >
                  <PlayIcon className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                </button>
              </div>
            </div>
          </motion.div>
        ))}
      </div>

      {/* Runs List for Selected Spec */}
      {selectedSpec && (
        <div className="space-y-2">
          <div className="mb-4">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-white">
              Run History ({runs.length})
            </h3>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              {specs.find(s => s.id === selectedSpec)?.name}
            </p>
          </div>

          {runs.length === 0 ? (
            <div className="p-8 text-center border border-gray-200 dark:border-gray-700 rounded-lg">
              <EyeIcon className="w-12 h-12 mx-auto text-gray-400 dark:text-gray-500 mb-2" />
              <p className="text-sm text-gray-500 dark:text-gray-400">
                No runs yet for this spec
              </p>
            </div>
          ) : (
            runs.map((run, index) => (
              <motion.div
                key={run.workflow_id}
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: index * 0.05 }}
                className="p-3 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg hover:border-blue-400 transition-all"
              >
                <div className="flex items-center justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-gray-900 dark:text-white">
                        Run #{run.run_number}
                      </span>
                      <span className={`px-2 py-0.5 text-xs font-medium rounded ${
                        run.status === 'completed' ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 border border-green-500' :
                        run.status === 'running' ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-400 border border-blue-500' :
                        run.status === 'failed' ? 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400 border border-red-500' :
                        'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 border border-gray-400'
                      }`}>
                        {run.status}
                      </span>
                    </div>
                    <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                      <div>Created: {format(new Date(run.created_at), 'MMM d, yyyy h:mm a')}</div>
                      {run.triggered_by && (
                        <div>Triggered by: {run.triggered_by}</div>
                      )}
                    </div>
                  </div>
                </div>
              </motion.div>
            ))
          )}
        </div>
      )}
    </div>
  );
};
