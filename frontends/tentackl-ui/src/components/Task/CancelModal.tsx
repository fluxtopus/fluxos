'use client';

import { XMarkIcon, ExclamationTriangleIcon } from '@heroicons/react/24/outline';
import { MobileSheet } from '../MobileSheet';

interface CancelModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  isProcessing?: boolean;
  planGoal?: string;
}

/**
 * CancelModal - Confirmation for stopping a task.
 * Simple, clear, not scary.
 */
export function CancelModal({
  isOpen,
  onClose,
  onConfirm,
  isProcessing = false,
  planGoal,
}: CancelModalProps) {
  return (
    <MobileSheet isOpen={isOpen} onClose={onClose} title="Stop this task?">
      <div className="bg-[var(--card)] rounded-2xl shadow-xl border border-[var(--border)] overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--border)]">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-[oklch(0.7_0.2_60/0.1)] flex items-center justify-center">
              <ExclamationTriangleIcon className="w-5 h-5 text-[oklch(0.7_0.2_60)]" />
            </div>
            <h2 className="text-lg font-semibold text-[var(--foreground)]">
              Stop this task?
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-1 text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors"
          >
            <XMarkIcon className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="px-5 py-4">
          {planGoal && (
            <p className="text-sm text-[var(--muted-foreground)] mb-4">
              <span className="font-medium text-[var(--foreground)]">&quot;{planGoal}&quot;</span>
            </p>
          )}
          <p className="text-sm text-[var(--muted-foreground)]">
            This will stop the task. Any completed steps will be preserved,
            but remaining work will not be done.
          </p>
        </div>

        {/* Actions */}
        <div className="px-5 py-4 border-t border-[var(--border)] bg-[var(--muted)]/30 flex items-center justify-end gap-3">
          <button
            onClick={onClose}
            disabled={isProcessing}
            className="px-4 py-2 text-sm font-medium text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors disabled:opacity-50"
          >
            Keep running
          </button>
          <button
            onClick={onConfirm}
            disabled={isProcessing}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-[oklch(0.65_0.25_27)] hover:bg-[oklch(0.6_0.25_27)] rounded-lg transition-colors disabled:opacity-50"
          >
            {isProcessing ? (
              <>
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Stopping...
              </>
            ) : (
              'Stop task'
            )}
          </button>
        </div>
      </div>
    </MobileSheet>
  );
}
