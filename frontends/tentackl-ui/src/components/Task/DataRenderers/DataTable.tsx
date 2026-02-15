'use client';

import { useState, useMemo } from 'react';
import {
  ChevronUpIcon,
  ChevronDownIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  MagnifyingGlassIcon,
} from '@heroicons/react/24/outline';
import { useIsMobile } from '../../../hooks/useMediaQuery';

interface DataTableProps {
  data: Record<string, unknown>[];
  maxColumns?: number;
  maxRows?: number;
}

type SortDirection = 'asc' | 'desc' | null;

/**
 * Infer columns from data, prioritizing common/important fields.
 */
export function inferColumns(
  data: Record<string, unknown>[],
  maxColumns: number
): string[] {
  if (data.length === 0) return [];

  // Priority fields (show first)
  const priority = [
    'title',
    'summary',
    'name',
    'email',
    'start',
    'end',
    'status',
    'type',
  ];

  // Collect all unique keys
  const allKeys = new Set<string>();
  data.slice(0, 10).forEach((item) => {
    Object.keys(item).forEach((key) => {
      // Skip internal fields
      if (key.startsWith('_')) return;
      // Skip complex objects (except small arrays)
      const val = item[key];
      if (typeof val === 'object' && val !== null) {
        if (Array.isArray(val) && val.length <= 3) {
          allKeys.add(key);
        }
        return;
      }
      allKeys.add(key);
    });
  });

  // Sort: priority fields first, then alphabetical
  const columns = Array.from(allKeys).sort((a, b) => {
    const aIdx = priority.indexOf(a);
    const bIdx = priority.indexOf(b);
    if (aIdx >= 0 && bIdx >= 0) return aIdx - bIdx;
    if (aIdx >= 0) return -1;
    if (bIdx >= 0) return 1;
    return a.localeCompare(b);
  });

  return columns.slice(0, maxColumns);
}

/**
 * Format a cell value for display.
 */
export function formatCellValue(value: unknown): string {
  if (value === null || value === undefined) return '-';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (Array.isArray(value))
    return (
      value.slice(0, 3).join(', ') + (value.length > 3 ? '...' : '')
    );
  if (typeof value === 'object') return JSON.stringify(value);
  if (
    typeof value === 'string' &&
    value.match(/^\d{4}-\d{2}-\d{2}T/)
  ) {
    // ISO date - format nicely
    try {
      return new Date(value).toLocaleString();
    } catch {
      return value;
    }
  }
  return String(value);
}

/**
 * Format column header from snake_case/camelCase.
 */
export function formatHeader(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/([A-Z])/g, ' $1')
    .replace(/^\w/, (c) => c.toUpperCase())
    .trim();
}

const ROWS_PER_PAGE_OPTIONS = [10, 25, 50];

export function DataTable({
  data,
  maxColumns = 6,
  maxRows = 500,
}: DataTableProps) {
  const isMobile = useIsMobile();
  const [sortColumn, setSortColumn] = useState<string | null>(null);
  const [sortDirection, setSortDirection] = useState<SortDirection>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [rowsPerPage, setRowsPerPage] = useState(10);

  const columns = useMemo(
    () => inferColumns(data, maxColumns),
    [data, maxColumns]
  );

  // Cap data at maxRows as a safety limit
  const cappedData = useMemo(() => data.slice(0, maxRows), [data, maxRows]);

  // Filter by search query across all visible columns
  const filteredData = useMemo(() => {
    if (!searchQuery.trim()) return cappedData;
    const query = searchQuery.toLowerCase();
    return cappedData.filter((row) =>
      columns.some((col) =>
        formatCellValue(row[col]).toLowerCase().includes(query)
      )
    );
  }, [cappedData, searchQuery, columns]);

  // Sort filtered data
  const sortedData = useMemo(() => {
    if (!sortColumn || !sortDirection) return filteredData;

    return [...filteredData].sort((a, b) => {
      const aVal = a[sortColumn];
      const bVal = b[sortColumn];

      if (aVal === bVal) return 0;
      if (aVal === null || aVal === undefined) return 1;
      if (bVal === null || bVal === undefined) return -1;

      const comparison = String(aVal).localeCompare(String(bVal), undefined, {
        numeric: true,
      });
      return sortDirection === 'asc' ? comparison : -comparison;
    });
  }, [filteredData, sortColumn, sortDirection]);

  // Pagination
  const totalRows = sortedData.length;
  const totalPages = Math.max(1, Math.ceil(totalRows / rowsPerPage));
  const safePage = Math.min(currentPage, totalPages);
  const startIdx = (safePage - 1) * rowsPerPage;
  const endIdx = Math.min(startIdx + rowsPerPage, totalRows);
  const pageData = sortedData.slice(startIdx, endIdx);
  const showPagination = totalRows > rowsPerPage;

  const handleSort = (column: string) => {
    if (sortColumn === column) {
      // Cycle: asc -> desc -> null
      setSortDirection((prev) =>
        prev === 'asc' ? 'desc' : prev === 'desc' ? null : 'asc'
      );
      if (sortDirection === 'desc') setSortColumn(null);
    } else {
      setSortColumn(column);
      setSortDirection('asc');
    }
    setCurrentPage(1);
  };

  const handleSearchChange = (value: string) => {
    setSearchQuery(value);
    setCurrentPage(1);
  };

  const handleRowsPerPageChange = (value: number) => {
    setRowsPerPage(value);
    setCurrentPage(1);
  };

  if (data.length === 0) {
    return (
      <div className="p-4 text-center text-sm text-[var(--muted-foreground)]">
        No data to display
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-[var(--border)]">
      {/* Search bar */}
      <div className="px-3 py-2 border-b border-[var(--border)]">
        <div className="relative">
          <MagnifyingGlassIcon className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--muted-foreground)]" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => handleSearchChange(e.target.value)}
            placeholder="Search all columns..."
            inputMode="search"
            enterKeyHint="search"
            className="w-full pl-8 pr-3 py-1.5 text-sm rounded-md border border-[var(--border)] bg-transparent text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-1 focus:ring-[var(--ring)]"
          />
        </div>
      </div>

      {/* Data view — stacked cards on mobile, table on desktop */}
      {isMobile ? (
        <div className="divide-y divide-[var(--border)]">
          {pageData.length === 0 ? (
            <div className="px-3 py-8 text-center text-sm text-[var(--muted-foreground)]">
              No matching rows
            </div>
          ) : (
            pageData.map((row, idx) => (
              <div
                key={(row.id as string) || startIdx + idx}
                className="px-3 py-3 space-y-1.5"
              >
                {columns.map((column) => (
                  <div key={column} className="flex items-baseline justify-between gap-2">
                    <span className="text-xs font-medium text-[var(--muted-foreground)] shrink-0">
                      {formatHeader(column)}
                    </span>
                    <span className="text-sm text-[var(--foreground)] text-right truncate">
                      {formatCellValue(row[column])}
                    </span>
                  </div>
                ))}
              </div>
            ))
          )}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-[var(--muted)]/50 border-b border-[var(--border)]">
                {columns.map((column) => (
                  <th
                    key={column}
                    onClick={() => handleSort(column)}
                    className="px-3 py-2 text-left font-medium text-[var(--muted-foreground)] cursor-pointer hover:text-[var(--foreground)] transition-colors select-none"
                  >
                    <span className="inline-flex items-center gap-1">
                      {formatHeader(column)}
                      {sortColumn === column &&
                        (sortDirection === 'asc' ? (
                          <ChevronUpIcon className="w-3 h-3" />
                        ) : sortDirection === 'desc' ? (
                          <ChevronDownIcon className="w-3 h-3" />
                        ) : null)}
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {pageData.length === 0 ? (
                <tr>
                  <td
                    colSpan={columns.length}
                    className="px-3 py-8 text-center text-sm text-[var(--muted-foreground)]"
                  >
                    No matching rows
                  </td>
                </tr>
              ) : (
                pageData.map((row, idx) => (
                  <tr
                    key={(row.id as string) || startIdx + idx}
                    className="border-b border-[var(--border)] last:border-0 hover:bg-[var(--muted)]/30 transition-colors"
                  >
                    {columns.map((column) => (
                      <td
                        key={column}
                        className="px-3 py-2 text-[var(--foreground)] max-w-[200px] truncate"
                        title={formatCellValue(row[column])}
                      >
                        {formatCellValue(row[column])}
                      </td>
                    ))}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination controls */}
      {showPagination && (
        <div className="px-3 py-2 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 text-xs text-[var(--muted-foreground)] bg-[var(--muted)]/30 border-t border-[var(--border)]">
          <div className="flex items-center gap-2">
            <span>Rows/page:</span>
            <select
              value={rowsPerPage}
              onChange={(e) => handleRowsPerPageChange(Number(e.target.value))}
              className="bg-transparent border border-[var(--border)] rounded px-1.5 py-0.5 text-xs text-[var(--foreground)] focus:outline-none focus:ring-1 focus:ring-[var(--ring)]"
            >
              {ROWS_PER_PAGE_OPTIONS.map((opt) => (
                <option key={opt} value={opt}>
                  {opt}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-3">
            <span>
              {startIdx + 1}-{endIdx} of {totalRows}
            </span>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                disabled={safePage <= 1}
                className="p-2 rounded hover:bg-[var(--muted)] disabled:opacity-30 disabled:cursor-not-allowed transition-colors min-w-[44px] min-h-[44px] flex items-center justify-center"
              >
                <ChevronLeftIcon className="w-4 h-4" />
              </button>
              <button
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                disabled={safePage >= totalPages}
                className="p-2 rounded hover:bg-[var(--muted)] disabled:opacity-30 disabled:cursor-not-allowed transition-colors min-w-[44px] min-h-[44px] flex items-center justify-center"
              >
                <ChevronRightIcon className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
