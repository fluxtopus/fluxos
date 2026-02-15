'use client';

import {
  CursorArrowRaysIcon,
  BoltIcon,
  CalendarIcon,
  LinkIcon,
} from '@heroicons/react/24/outline';
import type { TaskSource } from '../../types/task';

export type SourceFilterValue = 'all' | TaskSource;

interface FilterOption {
  value: SourceFilterValue;
  label: string;
  icon?: typeof CursorArrowRaysIcon;
}

const FILTER_OPTIONS: FilterOption[] = [
  { value: 'all', label: 'All' },
  { value: 'ui', label: 'Manual', icon: CursorArrowRaysIcon },
  { value: 'api', label: 'API', icon: BoltIcon },
  { value: 'schedule', label: 'Scheduled', icon: CalendarIcon },
  { value: 'webhook', label: 'Webhook', icon: LinkIcon },
];

interface SourceFilterProps {
  value: SourceFilterValue;
  onChange: (value: SourceFilterValue) => void;
  counts?: Record<SourceFilterValue, number>;
}

/**
 * SourceFilter - Filter tasks by trigger source/type.
 */
export function SourceFilter({ value, onChange, counts }: SourceFilterProps) {
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
              inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-mono tracking-wide
              rounded-full border transition-all duration-200 whitespace-nowrap
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
