import React, { useEffect } from 'react';
import { DocumentTextIcon, ArrowPathIcon } from '@heroicons/react/24/outline';
import { useArrowStore } from '../store/arrowStore';
import SpecCard from './SpecCard';

interface SpecListProps {
  onRunClick: (runId: string) => void;
}

const SpecList: React.FC<SpecListProps> = ({ onRunClick }) => {
  const {
    selectedConversationId,
    specs,
    runs,
    loadingSpecs,
    loadingRuns,
    loadSpecs
  } = useArrowStore();

  // Load specs when conversation changes
  useEffect(() => {
    if (selectedConversationId) {
      loadSpecs(selectedConversationId);
    }
  }, [selectedConversationId, loadSpecs]);

  // Show empty state if no conversation is selected
  if (!selectedConversationId) {
    return (
      <div className="h-full flex flex-col items-center justify-center text-gray-500 dark:text-gray-400 px-4">
        <DocumentTextIcon className="w-16 h-16 mb-4 opacity-50" />
        <p className="text-center text-sm">
          Select a conversation to view its workflow specs
        </p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-white dark:bg-gray-900">
      {/* Header */}
      <div className="p-4 border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              Workflow Specs
            </h3>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              {specs.length} spec{specs.length !== 1 ? 's' : ''} generated
            </p>
          </div>
          {loadingSpecs && (
            <ArrowPathIcon className="w-5 h-5 text-blue-600 dark:text-blue-400 animate-spin" />
          )}
        </div>
      </div>

      {/* Specs List */}
      <div className="flex-1 overflow-y-auto p-4">
        {loadingSpecs && specs.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-gray-500 dark:text-gray-400">
            <ArrowPathIcon className="w-8 h-8 animate-spin mb-2" />
            <span className="text-sm">Loading specs...</span>
          </div>
        ) : specs.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-gray-500 dark:text-gray-400">
            <DocumentTextIcon className="w-12 h-12 mb-3 opacity-50" />
            <p className="text-sm text-center">
              No workflow specs yet.<br />
              Create one in the chat!
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {specs.map((spec) => (
              <SpecCard
                key={spec.id}
                spec={spec}
                runs={runs[spec.id] || []}
                isLoadingRuns={loadingRuns[spec.id] || false}
                onRunClick={onRunClick}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default SpecList;
