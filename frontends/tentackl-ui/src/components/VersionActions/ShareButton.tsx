'use client';

import React, { useState } from 'react';
import { shareSpec, unshareSpec } from '../../services/versions';

interface ShareButtonProps {
  specId: string;
  isPublic: boolean;
  onShareChange?: (isPublic: boolean) => void;
}

export const ShareButton: React.FC<ShareButtonProps> = ({
  specId,
  isPublic,
  onShareChange,
}) => {
  const [loading, setLoading] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  const handleToggle = async () => {
    if (isPublic) {
      // Unshare immediately
      setLoading(true);
      try {
        await unshareSpec(specId);
        onShareChange?.(false);
      } finally {
        setLoading(false);
      }
    } else {
      // Show confirmation before sharing
      setShowConfirm(true);
    }
  };

  const handleConfirmShare = async () => {
    setLoading(true);
    try {
      await shareSpec(specId);
      onShareChange?.(true);
      setShowConfirm(false);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <button
        onClick={handleToggle}
        disabled={loading}
        className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded transition-colors ${
          isPublic
            ? 'bg-green-100 text-green-700 hover:bg-green-200 dark:bg-green-900/30 dark:text-green-400 dark:hover:bg-green-900/50'
            : 'bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-300 dark:hover:bg-gray-600'
        } disabled:opacity-50`}
        title={isPublic ? 'Make private' : 'Share publicly'}
      >
        {isPublic ? (
          <>
            <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            Public
          </>
        ) : (
          <>
            <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
            </svg>
            Private
          </>
        )}
      </button>

      {showConfirm && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg w-96 max-w-full p-4">
            <h4 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">
              Share Publicly?
            </h4>
            <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
              This will make your workflow template visible in the public gallery.
              Anyone can copy it to their account.
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setShowConfirm(false)}
                className="px-3 py-1.5 text-sm rounded border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmShare}
                disabled={loading}
                className="px-3 py-1.5 text-sm rounded bg-green-600 text-white hover:bg-green-700 disabled:opacity-50"
              >
                {loading ? 'Sharing...' : 'Share'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default ShareButton;
