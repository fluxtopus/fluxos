'use client';

import { UserIcon, CpuChipIcon } from '@heroicons/react/24/outline';
import type { MentionItem, MentionSection } from '../../hooks/useMentions';

interface MentionDropdownProps {
  sections: MentionSection[];
  selectedIndex: number;
  isLoading: boolean;
  onSelect: (item: MentionItem) => void;
}

/**
 * MentionDropdown - Two-section dropdown for @ mentions (People + Agents).
 */
export function MentionDropdown({
  sections,
  selectedIndex,
  isLoading,
  onSelect,
}: MentionDropdownProps) {
  const flatItems = sections.flatMap((s) => s.items);

  if (isLoading) {
    return (
      <div className="absolute left-0 right-0 bottom-full mb-1 z-50 rounded-xl border border-[var(--border)] bg-[var(--card)] shadow-lg overflow-hidden">
        <div className="px-4 py-3 text-sm text-[var(--muted-foreground)]">
          Searching...
        </div>
      </div>
    );
  }

  if (flatItems.length === 0) {
    return (
      <div className="absolute left-0 right-0 bottom-full mb-1 z-50 rounded-xl border border-[var(--border)] bg-[var(--card)] shadow-lg overflow-hidden">
        <div className="px-4 py-3 text-sm text-[var(--muted-foreground)]">
          No results found
        </div>
      </div>
    );
  }

  let runningIndex = 0;

  return (
    <div className="absolute left-0 right-0 bottom-full mb-1 z-50 rounded-xl border border-[var(--border)] bg-[var(--card)] shadow-lg overflow-hidden">
      <ul className="max-h-64 overflow-y-auto">
        {sections.map((section) => (
          <li key={section.title}>
            <div className="px-4 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-[var(--muted-foreground)] bg-[var(--muted)]">
              {section.title}
            </div>
            <ul>
              {section.items.map((item) => {
                const itemIndex = runningIndex++;
                return (
                  <li key={item.id}>
                    <button
                      type="button"
                      onClick={() => onSelect(item)}
                      className={`
                        w-full px-4 py-2.5 flex items-center gap-3 text-left transition-colors
                        ${itemIndex === selectedIndex
                          ? item.type === 'agent'
                            ? 'bg-[oklch(0.7_0.15_280/0.1)]'
                            : 'bg-[oklch(0.65_0.25_180/0.1)]'
                          : 'hover:bg-[var(--muted)]'
                        }
                      `}
                    >
                      {item.type === 'contact' ? (
                        <UserIcon className="w-4 h-4 text-[var(--muted-foreground)] flex-shrink-0" />
                      ) : (
                        <CpuChipIcon className="w-4 h-4 text-[oklch(0.5_0.15_280)] flex-shrink-0" />
                      )}
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-[var(--foreground)] truncate">
                          {item.name}
                        </div>
                        {item.description && (
                          <div className="text-xs text-[var(--muted-foreground)] truncate">
                            {item.description}
                          </div>
                        )}
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          </li>
        ))}
      </ul>
      <div className="px-4 py-2 border-t border-[var(--border)] bg-[var(--muted)]">
        <p className="text-xs text-[var(--muted-foreground)]">
          <kbd className="px-1 py-0.5 bg-[var(--card)] rounded text-[10px] font-mono">
            ↑↓
          </kbd>{' '}
          navigate
          {' \u00b7 '}
          <kbd className="px-1 py-0.5 bg-[var(--card)] rounded text-[10px] font-mono">
            Enter
          </kbd>{' '}
          select
          {' \u00b7 '}
          <kbd className="px-1 py-0.5 bg-[var(--card)] rounded text-[10px] font-mono">
            Esc
          </kbd>{' '}
          close
        </p>
      </div>
    </div>
  );
}
