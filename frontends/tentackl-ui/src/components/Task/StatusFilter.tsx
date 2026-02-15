'use client';

import {
  CheckCircleIcon,
  ExclamationCircleIcon,
} from '@heroicons/react/24/outline';
import type { TaskStatus } from '../../types/task';

export type StatusFilterValue = 'all' | 'attention' | 'completed';

interface FilterOption {
  value: StatusFilterValue;
  label: string;
  icon?: typeof CheckCircleIcon;
}

const FILTER_OPTIONS: FilterOption[] = [
  { value: 'all', label: 'All' },
  { value: 'attention', label: 'Needs You', icon: ExclamationCircleIcon },
  { value: 'completed', label: 'Done', icon: CheckCircleIcon },
];

// Statuses that need user attention
export const ATTENTION_STATUSES: TaskStatus[] = ['executing', 'planning', 'checkpoint', 'ready'];

// Statuses considered "done" (completed, failed, cancelled, etc.)
export const COMPLETED_STATUSES: TaskStatus[] = ['completed', 'failed', 'cancelled', 'superseded', 'paused'];

interface StatusFilterProps {
  value: StatusFilterValue;
  onChange: (value: StatusFilterValue) => void;
  counts?: {
    all: number;
    attention: number;
    completed: number;
  };
}

/**
 * StatusFilter - Simplified filter for task list.
 * Only 3 options that map to user intent: All, Needs Attention, Completed.
 */
export function StatusFilter({ value, onChange, counts }: StatusFilterProps) {
  return (
    <div className="flex items-center gap-1.5">
      {FILTER_OPTIONS.map((option) => {
        const isActive = value === option.value;
        const Icon = option.icon;
        const count = counts?.[option.value];

        return (
          <button
            key={option.value}
            onClick={() => onChange(option.value)}
            className={`
              inline-flex items-center gap-1.5 px-3 py-2.5 text-xs font-mono tracking-wide
              rounded-full border transition-all duration-200 whitespace-nowrap min-h-[44px]
              ${
                isActive
                  ? 'bg-[var(--accent)]/10 border-[var(--accent)]/50 text-[var(--accent)]'
                  : 'bg-[var(--card)] border-[var(--border)] text-[var(--muted-foreground)] hover:border-[var(--accent)]/30 hover:text-[var(--foreground)]'
              }
            `}
          >
            {Icon && <Icon className="w-3.5 h-3.5" />}
            <span>{option.label}</span>
            {count !== undefined && count > 0 && (
              <span
                className={`
                  ml-0.5 px-1.5 py-0.5 text-[10px] rounded-full min-w-[1.25rem] text-center
                  ${isActive ? 'bg-[var(--accent)]/20' : 'bg-[var(--muted)]'}
                `}
              >
                {count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

/**
 * Convert filter value to API-compatible status or status array.
 * Returns undefined for 'all' (no filter).
 */
export function filterValueToStatuses(value: StatusFilterValue): TaskStatus[] | undefined {
  switch (value) {
    case 'attention':
      return ATTENTION_STATUSES;
    case 'completed':
      return COMPLETED_STATUSES;
    default:
      return undefined;
  }
}
