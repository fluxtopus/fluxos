'use client';

import React, { useState, useEffect } from 'react';
import { checkForUpdates } from '../../services/versions';
import type { UpdateCheckResponse } from '../../types/version';

interface UpdateBadgeProps {
  specId: string;
  copiedFromId?: string | null;
  onUpdateAvailable?: (updateInfo: UpdateCheckResponse) => void;
}

export const UpdateBadge: React.FC<UpdateBadgeProps> = ({
  specId,
  copiedFromId,
  onUpdateAvailable,
}) => {
  const [updateInfo, setUpdateInfo] = useState<UpdateCheckResponse | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!copiedFromId) return;

    const checkUpdates = async () => {
      setLoading(true);
      try {
        const info = await checkForUpdates(specId);
        setUpdateInfo(info);
        if (info.has_update && onUpdateAvailable) {
          onUpdateAvailable(info);
        }
      } catch {
        // Silently fail - update checking is not critical
      } finally {
        setLoading(false);
      }
    };

    checkUpdates();
  }, [specId, copiedFromId, onUpdateAvailable]);

  if (!copiedFromId || loading || !updateInfo?.has_update) {
    return null;
  }

  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300"
      title={`Update available from ${updateInfo.original_name || 'original'}: v${updateInfo.latest_version}`}
    >
      <svg
        className="h-3 w-3"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
        />
      </svg>
      Update: v{updateInfo.latest_version}
    </span>
  );
};

export default UpdateBadge;
