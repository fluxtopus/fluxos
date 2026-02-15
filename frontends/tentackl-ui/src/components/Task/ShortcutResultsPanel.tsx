'use client';

import { XMarkIcon, ExclamationTriangleIcon } from '@heroicons/react/24/outline';
import type { StructuredDataContent } from '../../types/structured-data';
import { StructuredDataRenderer } from './DataRenderers/StructuredDataRenderer';

interface ShortcutResultsPanelProps {
  results: StructuredDataContent | null;
  error: string | null;
  isLoading: boolean;
  onDismiss: () => void;
  onDataChange?: () => void;
  hasMore?: boolean;
  isLoadingMore?: boolean;
  onLoadMore?: () => void;
}

/**
 * ShortcutResultsPanel - Displays results from workspace shortcut queries.
 *
 * Shows inline below the input when a shortcut is executed.
 * Uses StructuredDataRenderer for proper display of events/contacts.
 */
export function ShortcutResultsPanel({
  results,
  error,
  isLoading,
  onDismiss,
  onDataChange,
  hasMore = false,
  isLoadingMore = false,
  onLoadMore,
}: ShortcutResultsPanelProps) {
  // Loading state
  if (isLoading) {
    return (
      <div className="mt-4 p-4 rounded-xl border border-[var(--border)] bg-[var(--card)]">
        <div className="flex items-center gap-3 text-[var(--muted-foreground)]">
          <div className="w-5 h-5 border-2 border-current border-t-transparent rounded-full animate-spin" />
          <span className="text-sm">Fetching data...</span>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="mt-4 p-4 rounded-xl border border-[oklch(0.65_0.25_27/0.3)] bg-[oklch(0.65_0.25_27/0.05)]">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <ExclamationTriangleIcon className="w-5 h-5 text-[oklch(0.65_0.25_27)] flex-shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-medium text-[var(--foreground)]">
                Failed to fetch data
              </p>
              <p className="text-xs text-[var(--muted-foreground)] mt-1">{error}</p>
            </div>
          </div>
          <button
            onClick={onDismiss}
            className="p-1 rounded hover:bg-[var(--muted)] transition-colors"
            aria-label="Dismiss"
          >
            <XMarkIcon className="w-4 h-4 text-[var(--muted-foreground)]" />
          </button>
        </div>
      </div>
    );
  }

  // No results
  if (!results) {
    return null;
  }

  // Empty results
  if (!results.data || results.data.length === 0) {
    return (
      <div className="mt-4 p-4 rounded-xl border border-[var(--border)] bg-[var(--card)]">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-sm font-medium text-[var(--foreground)]">
              No {results.object_type || 'data'} found
            </p>
            <p className="text-xs text-[var(--muted-foreground)] mt-1">
              Try a different query or check your workspace data.
            </p>
          </div>
          <button
            onClick={onDismiss}
            className="p-1 rounded hover:bg-[var(--muted)] transition-colors"
            aria-label="Dismiss"
          >
            <XMarkIcon className="w-4 h-4 text-[var(--muted-foreground)]" />
          </button>
        </div>
      </div>
    );
  }

  // Results with data
  return (
    <div className="mt-4 rounded-xl border border-[var(--border)] bg-[var(--card)] overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-[var(--border)] bg-[var(--muted)]/30 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-[var(--foreground)]">
            Workspace Results
          </span>
          {results.data && results.data.length > 0 && (
            <span className="text-xs text-[var(--muted-foreground)] bg-[var(--muted)] px-2 py-0.5 rounded-full">
              {results.data.length} loaded{hasMore ? '+' : ''}
            </span>
          )}
        </div>
        <button
          onClick={onDismiss}
          className="p-1 rounded hover:bg-[var(--muted)] transition-colors"
          aria-label="Dismiss results"
        >
          <XMarkIcon className="w-4 h-4 text-[var(--muted-foreground)]" />
        </button>
      </div>

      {/* Content */}
      <div className="p-4 max-h-[400px] overflow-y-auto">
        <StructuredDataRenderer content={results} defaultView="card" onDataChange={onDataChange} />

        {/* Load More */}
        {hasMore && onLoadMore && (
          <div className="mt-4 flex justify-center">
            <button
              onClick={onLoadMore}
              disabled={isLoadingMore}
              className="px-4 py-2 text-sm font-medium text-[var(--foreground)] bg-[var(--muted)] hover:bg-[var(--border)] rounded-lg transition-colors disabled:opacity-50"
            >
              {isLoadingMore ? (
                <span className="inline-flex items-center gap-2">
                  <span className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
                  Loading...
                </span>
              ) : (
                'Load More'
              )}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
