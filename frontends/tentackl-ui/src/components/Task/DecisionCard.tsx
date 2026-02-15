'use client';

import { useState } from 'react';
import { formatDistanceToNow } from 'date-fns';
import {
  CheckIcon,
  XMarkIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  ClockIcon,
} from '@heroicons/react/24/outline';
import type { Checkpoint } from '../../types/task';

interface DecisionCardProps {
  checkpoint: Checkpoint;
  onApprove: (feedback?: string, learnPreference?: boolean) => Promise<void>;
  onReject: (reason: string, learnPreference?: boolean) => Promise<void>;
  isProcessing?: boolean;
}

/**
 * DecisionCard - For approving or rejecting a checkpoint.
 * Quick, conversational, not a bureaucratic form.
 */
export function DecisionCard({
  checkpoint,
  onApprove,
  onReject,
  isProcessing = false,
}: DecisionCardProps) {
  const [showDetails, setShowDetails] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [showRejectInput, setShowRejectInput] = useState(false);
  const [learnPreference, setLearnPreference] = useState(false);

  const handleApprove = async () => {
    await onApprove(undefined, learnPreference);
  };

  const handleReject = async () => {
    if (!rejectReason.trim()) {
      setShowRejectInput(true);
      return;
    }
    await onReject(rejectReason.trim(), learnPreference);
  };

  const handleCancelReject = () => {
    setShowRejectInput(false);
    setRejectReason('');
  };

  return (
    <div className="rounded-xl border-2 border-[oklch(0.7_0.2_60/0.5)] bg-[var(--card)] overflow-hidden">
      {/* Header */}
      <div className="px-5 py-4 border-b border-[var(--border)] bg-[oklch(0.7_0.2_60/0.05)]">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-xl bg-[oklch(0.7_0.2_60/0.15)] flex items-center justify-center flex-shrink-0">
            <ClockIcon className="w-5 h-5 text-[oklch(0.7_0.2_60)]" />
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-base font-semibold text-[var(--foreground)]">
              {checkpoint.checkpoint_name}
            </h3>
            <p className="text-sm text-[var(--muted-foreground)] mt-0.5">
              {checkpoint.description}
            </p>
          </div>
        </div>
      </div>

      {/* Preview data toggle */}
      {Object.keys(checkpoint.preview_data).length > 0 && (
        <div className="px-5 py-3 border-b border-[var(--border)]">
          <button
            onClick={() => setShowDetails(!showDetails)}
            className="flex items-center gap-2 text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors"
          >
            {showDetails ? (
              <>
                <ChevronUpIcon className="w-4 h-4" />
                Hide preview
              </>
            ) : (
              <>
                <ChevronDownIcon className="w-4 h-4" />
                Show preview
              </>
            )}
          </button>

          {showDetails && (
            <div className="mt-3 p-3 bg-[var(--muted)] rounded-lg">
              <pre className="text-xs text-[var(--foreground)] overflow-x-auto">
                {JSON.stringify(checkpoint.preview_data, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}

      {/* Reject reason input */}
      {showRejectInput && (
        <div className="px-5 py-4 border-b border-[var(--border)]">
          <label className="block text-sm font-medium text-[var(--foreground)] mb-2">
            Why are you rejecting this?
          </label>
          <textarea
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            placeholder="Briefly explain your reason..."
            rows={2}
            className="w-full px-3 py-2 text-sm bg-[var(--background)] border border-[var(--border)] rounded-lg focus:outline-none focus:border-[oklch(0.65_0.25_180/0.5)] text-[var(--foreground)] placeholder-[var(--muted-foreground)]"
          />
          <div className="flex justify-end gap-2 mt-3">
            <button
              onClick={handleCancelReject}
              className="px-3 py-1.5 text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleReject}
              disabled={!rejectReason.trim() || isProcessing}
              className="px-4 py-1.5 text-sm font-medium text-white bg-[oklch(0.65_0.25_27)] hover:bg-[oklch(0.6_0.25_27)] rounded-lg transition-colors disabled:opacity-50"
            >
              Reject
            </button>
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="px-5 py-4">
        {/* Learn preference toggle */}
        <label className="flex items-center gap-2 mb-4 cursor-pointer">
          <input
            type="checkbox"
            checked={learnPreference}
            onChange={(e) => setLearnPreference(e.target.checked)}
            className="w-4 h-4 rounded border-[var(--border)] text-[oklch(0.65_0.25_180)] focus:ring-[oklch(0.65_0.25_180)] bg-[var(--background)]"
          />
          <span className="text-sm text-[var(--muted-foreground)]">
            Remember this choice for similar situations
          </span>
        </label>

        {/* Approve/Reject buttons */}
        {!showRejectInput && (
          <div className="flex items-center gap-3">
            <button
              onClick={handleApprove}
              disabled={isProcessing}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium text-white rounded-lg delegation-cta disabled:opacity-50"
            >
              {isProcessing ? (
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <CheckIcon className="w-4 h-4" />
              )}
              Approve
            </button>
            <button
              onClick={() => setShowRejectInput(true)}
              disabled={isProcessing}
              className="flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium text-[var(--muted-foreground)] hover:text-[oklch(0.65_0.25_27)] border border-[var(--border)] hover:border-[oklch(0.65_0.25_27/0.5)] rounded-lg transition-colors disabled:opacity-50"
            >
              <XMarkIcon className="w-4 h-4" />
              Reject
            </button>
          </div>
        )}
      </div>

      {/* Expiry warning */}
      {checkpoint.expires_at && (
        <div className="px-5 py-2 border-t border-[var(--border)] bg-[var(--muted)]/30">
          <p className="text-xs text-[var(--muted-foreground)]">
            Expires {formatDistanceToNow(new Date(checkpoint.expires_at), { addSuffix: true })}
          </p>
        </div>
      )}
    </div>
  );
}
