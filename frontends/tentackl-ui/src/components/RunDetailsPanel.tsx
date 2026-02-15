import React from 'react';
import api from '../services/api';
import { useWorkflowStore } from '../store/workflowStore';

interface RunDetails {
  run_id: string;
  keep_alive: boolean;
  waiting: boolean;
  waiting_for?: any;
  root_status?: string | null;
  counts: Record<string, number>;
}

const RunDetailsPanel: React.FC = () => {
  const { currentWorkflow } = useWorkflowStore();
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

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-gray-800 dark:text-gray-200">Run Details</h3>
        <button
          onClick={() => load(true)}
          disabled={manualRefresh}
          className="text-xs px-2 py-1 rounded bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-100 disabled:opacity-50"
        >
          {manualRefresh ? '…' : 'Refresh'}
        </button>
      </div>
      {details ? (
        <div className="text-xs text-gray-700 dark:text-gray-300 space-y-1">
          <div>Root: <span className="font-semibold">{details.root_status || 'unknown'}</span></div>
          <div>Keep Alive: {String(details.keep_alive)}</div>
          <div>Waiting: {String(details.waiting)}</div>
          {details.waiting_for && (
            <pre className="bg-gray-50 dark:bg-gray-900 rounded p-2 overflow-auto border border-gray-200 dark:border-gray-700">{JSON.stringify(details.waiting_for, null, 2)}</pre>
          )}
          {details.counts && (
            <div className="flex gap-2 flex-wrap">
              {Object.entries(details.counts).map(([k,v]) => (
                <span key={k} className="px-2 py-0.5 rounded bg-gray-100 dark:bg-gray-800 border border-gray-200 dark:border-gray-700">{k}: {v}</span>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="text-xs text-gray-500">No details</div>
      )}
    </div>
  );
};

export default RunDetailsPanel;

