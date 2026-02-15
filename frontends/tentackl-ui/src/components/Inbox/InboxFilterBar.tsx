'use client';

import { useState, useEffect, useRef } from 'react';
import {
  MagnifyingGlassIcon,
  EllipsisHorizontalIcon,
  CheckIcon,
  ArchiveBoxIcon,
} from '@heroicons/react/24/outline';
import { Menu, MenuButton, MenuItem, MenuItems } from '@headlessui/react';
import { useIsMobile } from '@/hooks/useMediaQuery';
import type { InboxFilter } from '@/types/inbox';

interface InboxFilterBarProps {
  activeFilter: InboxFilter;
  onFilterChange: (filter: InboxFilter) => void;
  unreadCount: number;
  attentionCount: number;
  searchQuery?: string;
  onSearchChange?: (q: string) => void;
  onMarkAllRead?: () => void;
  selectionMode?: boolean;
  onToggleSelectionMode?: () => void;
  selectedCount?: number;
  onArchiveSelected?: () => void;
  onMarkSelectedRead?: () => void;
}

const filters: { key: InboxFilter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'unread', label: 'Unread' },
  { key: 'attention', label: 'Needs Attention' },
  { key: 'archived', label: 'Archived' },
];

export function InboxFilterBar({
  activeFilter,
  onFilterChange,
  unreadCount,
  attentionCount,
  searchQuery = '',
  onSearchChange,
  onMarkAllRead,
  selectionMode,
  onToggleSelectionMode,
  selectedCount = 0,
  onArchiveSelected,
  onMarkSelectedRead,
}: InboxFilterBarProps) {
  const [localSearch, setLocalSearch] = useState(searchQuery);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();

  // Sync external searchQuery → local state
  useEffect(() => {
    setLocalSearch(searchQuery);
  }, [searchQuery]);

  const handleSearchInput = (value: string) => {
    setLocalSearch(value);
    if (onSearchChange) {
      clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        onSearchChange(value);
      }, 300);
    }
  };

  const isMobile = useIsMobile();

  // Check if we have any overflow actions to show in the menu
  const hasOverflowActions =
    (onMarkAllRead && unreadCount > 0 && !selectionMode) ||
    onToggleSelectionMode;

  return (
    <div className="flex flex-col gap-2">
      {/* Search bar */}
      {onSearchChange && (
        <div className="relative">
          <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-[var(--muted-foreground)]" />
          <input
            type="text"
            value={localSearch}
            onChange={(e) => handleSearchInput(e.target.value)}
            placeholder="Search tasks..."
            inputMode="search"
            enterKeyHint="search"
            className="w-full pl-9 pr-3 py-2 text-sm rounded-lg border border-[var(--border)] bg-[var(--background)] text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)]"
          />
        </div>
      )}

      {/* Filter tabs + actions row */}
      <div className="flex items-center gap-1">
        {/* Scrollable filter tabs */}
        <div className="flex-1 min-w-0 overflow-x-auto scrollbar-hide">
          <div className="flex gap-1">
            {filters.map(({ key, label }) => {
              const isActive = activeFilter === key;
              // Shorter labels on mobile
              const mobileLabel =
                isMobile && key === 'attention' ? 'Attention' : label;
              return (
                <button
                  key={key}
                  onClick={() => onFilterChange(key)}
                  className={`text-xs font-medium uppercase tracking-wider pb-1 pt-2.5 border-b-2 transition-colors min-h-[44px] whitespace-nowrap flex-shrink-0 px-2 lg:px-3 ${
                    isActive
                      ? 'text-[var(--accent)] border-[var(--accent)]'
                      : 'text-[var(--muted-foreground)] border-transparent hover:text-[var(--foreground)]'
                  }`}
                >
                  {mobileLabel}
                  {key === 'unread' && unreadCount > 0 && (
                    <span className="ml-1 inline-block rounded-full bg-[var(--accent)] text-[var(--accent-foreground)] px-1.5 py-0.5 text-[10px] leading-none">
                      {unreadCount}
                    </span>
                  )}
                  {key === 'attention' && attentionCount > 0 && (
                    <span className="ml-1 inline-block rounded-full bg-amber-500 text-white px-1.5 py-0.5 text-[10px] leading-none">
                      {attentionCount}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {/* Actions — overflow menu on mobile, inline buttons on desktop */}
        {isMobile ? (
          hasOverflowActions && (
            <Menu as="div" className="relative flex-shrink-0">
              <MenuButton className="p-2.5 rounded-md hover:bg-[var(--muted)] transition-colors min-w-[44px] min-h-[44px] flex items-center justify-center">
                <EllipsisHorizontalIcon className="w-5 h-5 text-[var(--muted-foreground)]" />
              </MenuButton>
              <MenuItems className="absolute right-0 top-full mt-1 w-48 py-1 bg-[var(--card)] border border-[var(--border)] rounded-lg shadow-lg z-20">
                {onMarkAllRead && unreadCount > 0 && !selectionMode && (
                  <MenuItem>
                    {({ focus }) => (
                      <button
                        onClick={onMarkAllRead}
                        className={`flex items-center gap-2 w-full px-3 py-2.5 text-xs font-mono tracking-wider text-left text-[var(--foreground)] ${
                          focus ? 'bg-[var(--muted)]' : ''
                        }`}
                      >
                        <CheckIcon className="w-4 h-4" />
                        MARK ALL READ
                      </button>
                    )}
                  </MenuItem>
                )}
                {onToggleSelectionMode && (
                  <MenuItem>
                    {({ focus }) => (
                      <button
                        onClick={onToggleSelectionMode}
                        className={`flex items-center gap-2 w-full px-3 py-2.5 text-xs font-mono tracking-wider text-left ${
                          selectionMode ? 'text-[var(--accent)]' : 'text-[var(--foreground)]'
                        } ${focus ? 'bg-[var(--muted)]' : ''}`}
                      >
                        {selectionMode ? 'CANCEL' : 'SELECT'}
                      </button>
                    )}
                  </MenuItem>
                )}
              </MenuItems>
            </Menu>
          )
        ) : (
          <div className="flex items-center gap-1.5 flex-shrink-0">
            {onMarkAllRead && unreadCount > 0 && !selectionMode && (
              <button
                onClick={onMarkAllRead}
                className="text-[10px] font-medium uppercase tracking-wider text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors px-2 py-2.5 rounded hover:bg-[var(--muted)] min-h-[44px]"
              >
                Mark All Read
              </button>
            )}
            {onToggleSelectionMode && (
              <button
                onClick={onToggleSelectionMode}
                className={`text-[10px] font-medium uppercase tracking-wider transition-colors px-2 py-2.5 rounded min-h-[44px] ${
                  selectionMode
                    ? 'text-[var(--accent)] bg-[var(--accent)]/10'
                    : 'text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:bg-[var(--muted)]'
                }`}
              >
                {selectionMode ? 'Cancel' : 'Select'}
              </button>
            )}
          </div>
        )}
      </div>

      {/* Selection action bar */}
      {selectionMode && selectedCount > 0 && (
        <div className="flex items-center gap-2 py-1.5 px-2 rounded-md bg-[var(--muted)]/50 border border-[var(--border)]">
          <span className="text-xs text-[var(--muted-foreground)]">
            {selectedCount} selected
          </span>
          <div className="flex items-center gap-1.5 ml-auto">
            {onMarkSelectedRead && (
              <button
                onClick={onMarkSelectedRead}
                className="inline-flex items-center gap-1 text-xs font-medium text-[var(--foreground)] hover:text-[var(--accent)] transition-colors px-2 py-1.5 rounded hover:bg-[var(--muted)] min-h-[36px]"
              >
                <CheckIcon className="w-3.5 h-3.5" />
                {!isMobile && <span className="uppercase tracking-wider text-[10px]">Mark Read</span>}
              </button>
            )}
            {onArchiveSelected && (
              <button
                onClick={onArchiveSelected}
                className="inline-flex items-center gap-1 text-xs font-medium text-[var(--destructive)] hover:text-[var(--destructive)] transition-colors px-2 py-1.5 rounded hover:bg-[var(--destructive)]/10 min-h-[36px]"
              >
                <ArchiveBoxIcon className="w-3.5 h-3.5" />
                {!isMobile && <span className="uppercase tracking-wider text-[10px]">Archive</span>}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
