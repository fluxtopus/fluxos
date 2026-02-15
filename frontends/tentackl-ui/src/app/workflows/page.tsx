'use client';

import { Suspense, useEffect } from 'react';
import { useSearchParams } from 'next/navigation';
import { WorkflowList } from '../../components/WorkflowList';
import { WorkflowVisualization } from '../../components/WorkflowVisualization';
import { WorkflowSummaryPanel } from '../../components/WorkflowSummaryPanel';
import { CollapsibleOrchestratorChat } from '../../components/CollapsibleOrchestratorChat';
import { useWorkflowStore } from '../../store/workflowStore';

function WorkflowsContent() {
  const searchParams = useSearchParams();
  const { currentWorkflow, selectWorkflow } = useWorkflowStore();

  // Handle workflowRunId from URL
  useEffect(() => {
    const workflowRunId = searchParams?.get('workflowRunId');
    if (workflowRunId) {
      selectWorkflow(workflowRunId);
    }
  }, [searchParams, selectWorkflow]);

  return (
    <div className="h-full flex">
      {/* Left Sidebar - Workflow List */}
      <div className="w-64 border-r border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4 overflow-y-auto">
        <WorkflowList />
      </div>

      {/* Center - Workflow Visualization */}
      <div className="flex-1">
        <WorkflowVisualization />
      </div>

      {/* Right Sidebar - Workflow Summary and Chat */}
      {currentWorkflow && (
        <div className="w-96 border-l border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 flex flex-col">
          <div className="p-3 border-b border-gray-200 dark:border-gray-700">
            <WorkflowSummaryPanel />
          </div>
          <div className="flex-1 overflow-hidden">
            <CollapsibleOrchestratorChat />
          </div>
        </div>
      )}
    </div>
  );
}

export default function WorkflowsPage() {
  return (
    <Suspense fallback={<div className="h-full flex items-center justify-center">Loading...</div>}>
      <WorkflowsContent />
    </Suspense>
  );
}

