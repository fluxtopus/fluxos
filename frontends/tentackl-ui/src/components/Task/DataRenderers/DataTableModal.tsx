'use client';

import { useEffect } from 'react';
import { XMarkIcon, TableCellsIcon } from '@heroicons/react/24/outline';
import { DataTable } from './DataTable';
import { MobileSheet } from '../../MobileSheet';

interface DataTableModalProps {
  data: Record<string, unknown>[];
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  itemCount?: number;
}

/**
 * DataTableModal - Full-screen modal for viewing tabular data.
 * Opens when users click to expand columnar data from inline preview.
 */
export function DataTableModal({
  data,
  isOpen,
  onClose,
  title,
  itemCount,
}: DataTableModalProps) {
  // Close on Escape key
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // Prevent body scroll when modal is open
  useEffect(() => {
    if (!isOpen) return;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = '';
    };
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <MobileSheet isOpen={isOpen} onClose={onClose} title={title || 'Table View'}>
      <div className="w-full h-full sm:h-auto sm:max-h-[85vh] sm:max-w-4xl mx-auto bg-[var(--card)] rounded-2xl shadow-xl border border-[var(--border)] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--border)] shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-[oklch(0.65_0.25_180/0.1)] flex items-center justify-center">
              <TableCellsIcon className="w-4 h-4 text-[oklch(0.65_0.25_180)]" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-[var(--foreground)]">
                {title || 'Table View'}
              </h2>
              {itemCount !== undefined && (
                <p className="text-xs text-[var(--muted-foreground)]">
                  {itemCount} {itemCount === 1 ? 'row' : 'rows'}
                </p>
              )}
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--muted)] rounded-lg transition-colors"
          >
            <XMarkIcon className="w-5 h-5" />
          </button>
        </div>

        {/* Table content - scrollable */}
        <div className="flex-1 overflow-auto p-3 sm:p-4">
          <DataTable data={data} />
        </div>
      </div>
    </MobileSheet>
  );
}
