'use client';

import React, { useState } from 'react';
import { checkForUpdates, pullUpdate } from '../../services/versions';
import type { UpdateCheckResponse } from '../../types/version';
import { YamlDiffViewer } from '../DiffViewer';

interface PullUpdateButtonProps {
  specId: string;
  copiedFromId?: string | null;
  onPullSuccess?: () => void;
}

export const PullUpdateButton: React.FC<PullUpdateButtonProps> = ({
  specId,
  copiedFromId,
  onPullSuccess,
}) => {
  const [loading, setLoading] = useState(false);
  const [updateInfo, setUpdateInfo] = useState<UpdateCheckResponse | null>(null);
  const [showDiff, setShowDiff] = useState(false);
  const [pulling, setPulling] = useState(false);

  const handleCheckUpdates = async () => {
    setLoading(true);
    try {
      const info = await checkForUpdates(specId);
      setUpdateInfo(info);
      if (info.has_update) {
        setShowDiff(true);
      }
    } finally {
      setLoading(false);
    }
  };

  const handlePullUpdate = async () => {
    setPulling(true);
    try {
      await pullUpdate(specId);
      setShowDiff(false);
      setUpdateInfo(null);
      onPullSuccess?.();
    } finally {
      setPulling(false);
    }
  };

  if (!copiedFromId) {
    return null;
  }

  return (
    <>
      <button
        onClick={handleCheckUpdates}
        disabled={loading}
        className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded bg-blue-100 text-blue-700 hover:bg-blue-200 dark:bg-blue-900/30 dark:text-blue-400 dark:hover:bg-blue-900/50 disabled:opacity-50 transition-colors"
        title="Check for updates from original"
      >
        <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
        {loading ? 'Checking...' : 'Check Updates'}
      </button>

      {showDiff && updateInfo && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg w-full max-w-4xl max-h-[90vh] overflow-hidden flex flex-col">
            <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
              <div>
                <h4 className="text-lg font-semibold text-gray-900 dark:text-white">
                  {updateInfo.has_update ? 'Update Available' : 'No Updates'}
                </h4>
                {updateInfo.has_update && (
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    {updateInfo.original_name}: v{updateInfo.current_version} → v{updateInfo.latest_version}
                  </p>
                )}
              </div>
              <button
                onClick={() => setShowDiff(false)}
                className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
              >
                <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="flex-1 overflow-auto p-4">
              {updateInfo.has_update && updateInfo.local_yaml && updateInfo.original_yaml ? (
                <YamlDiffViewer
                  oldYaml={updateInfo.local_yaml}
                  newYaml={updateInfo.original_yaml}
                  oldTitle={`Your version (v${updateInfo.current_version})`}
                  newTitle={`Original (v${updateInfo.latest_version})`}
                />
              ) : !updateInfo.has_update ? (
                <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                  {updateInfo.reason || 'Your copy is up to date with the original.'}
                </div>
              ) : (
                <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                  Unable to show diff. Pull the update to get the latest version.
                </div>
              )}
            </div>

            {updateInfo.has_update && (
              <div className="flex items-center justify-between p-4 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900">
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  Pulling will overwrite your current YAML with the original version.
                </p>
                <div className="flex gap-2">
                  <button
                    onClick={() => setShowDiff(false)}
                    className="px-3 py-1.5 text-sm rounded border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handlePullUpdate}
                    disabled={pulling}
                    className="px-3 py-1.5 text-sm rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
                  >
                    {pulling ? 'Pulling...' : 'Pull Update'}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
};

export default PullUpdateButton;
