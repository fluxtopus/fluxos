'use client';

import {
  ExclamationTriangleIcon,
  ArrowPathIcon,
  XMarkIcon,
  LightBulbIcon,
} from '@heroicons/react/24/outline';
import { mapErrorToFriendly } from '../../services/taskApi';
import type { TaskError } from '../../types/task';

interface ErrorCardProps {
  error: string | TaskError;
  onRetry?: () => void;
  onDismiss?: () => void;
  onTryDifferent?: () => void;
  isRetrying?: boolean;
}

/**
 * ErrorCard - Conversational error display.
 * Not a stack trace. Friendly explanation of what went wrong.
 */
export function ErrorCard({
  error,
  onRetry,
  onDismiss,
  onTryDifferent,
  isRetrying = false,
}: ErrorCardProps) {
  // Convert string error to friendly format
  const errorInfo = typeof error === 'string'
    ? {
        ...mapErrorToFriendly(error),
        canRetry: true,
        canSkip: false,
        hasAlternative: false,
        technicalDetails: error,
      }
    : {
        friendlyMessage: error.friendlyMessage,
        whatToDoNext: error.whatToDoNext,
        canRetry: error.canRetry,
        canSkip: error.canSkip,
        hasAlternative: error.hasAlternative,
        technicalDetails: error.technicalDetails,
      };

  return (
    <div className="rounded-xl border border-[oklch(0.65_0.25_27/0.3)] bg-[var(--card)] overflow-hidden">
      {/* Header */}
      <div className="px-5 py-4 bg-[oklch(0.65_0.25_27/0.05)] border-b border-[oklch(0.65_0.25_27/0.2)]">
        <div className="flex items-start gap-3">
          <div className="w-10 h-10 rounded-xl bg-[oklch(0.65_0.25_27/0.15)] flex items-center justify-center flex-shrink-0">
            <ExclamationTriangleIcon className="w-5 h-5 text-[oklch(0.65_0.25_27)]" />
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-base font-semibold text-[var(--foreground)]">
              Something went wrong
            </h3>
            <p className="text-sm text-[var(--muted-foreground)] mt-0.5">
              {errorInfo.friendlyMessage}
            </p>
          </div>
          {onDismiss && (
            <button
              onClick={onDismiss}
              className="flex-shrink-0 p-1 text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors"
            >
              <XMarkIcon className="w-5 h-5" />
            </button>
          )}
        </div>
      </div>

      {/* Suggestions */}
      {errorInfo.whatToDoNext.length > 0 && (
        <div className="px-5 py-4 border-b border-[var(--border)]">
          <div className="flex items-start gap-2 text-sm">
            <LightBulbIcon className="w-4 h-4 text-[oklch(0.7_0.2_60)] flex-shrink-0 mt-0.5" />
            <div>
              <p className="font-medium text-[var(--foreground)] mb-1">
                What you can do:
              </p>
              <ul className="text-[var(--muted-foreground)] space-y-0.5">
                {errorInfo.whatToDoNext.map((suggestion, idx) => (
                  <li key={idx}>• {suggestion}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="px-5 py-4 flex items-center gap-3">
        {errorInfo.canRetry && onRetry && (
          <button
            onClick={onRetry}
            disabled={isRetrying}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-white rounded-lg delegation-cta disabled:opacity-50"
          >
            {isRetrying ? (
              <>
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Retrying...
              </>
            ) : (
              <>
                <ArrowPathIcon className="w-4 h-4" />
                Try again
              </>
            )}
          </button>
        )}

        {errorInfo.hasAlternative && onTryDifferent && (
          <button
            onClick={onTryDifferent}
            disabled={isRetrying}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-[var(--foreground)] border border-[var(--border)] rounded-lg hover:bg-[var(--muted)] transition-colors disabled:opacity-50"
          >
            Try a different approach
          </button>
        )}
      </div>

      {/* Technical details (collapsed) */}
      {errorInfo.technicalDetails && (
        <details className="px-5 py-3 border-t border-[var(--border)] bg-[var(--muted)]/30">
          <summary className="text-xs text-[var(--muted-foreground)] cursor-pointer hover:text-[var(--foreground)]">
            Technical details
          </summary>
          <pre className="mt-2 text-xs text-[var(--muted-foreground)] overflow-x-auto">
            {errorInfo.technicalDetails}
          </pre>
        </details>
      )}
    </div>
  );
}
