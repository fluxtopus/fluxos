'use client';

import {
  CalendarIcon,
  UserGroupIcon,
  CpuChipIcon,
} from '@heroicons/react/24/outline';
import type { ShortcutSuggestion } from '../../hooks/useWorkspaceShortcuts';

interface WorkspaceShortcutDropdownProps {
  suggestions: ShortcutSuggestion[];
  selectedIndex: number;
  isLoading: boolean;
  onSelect: (suggestion: ShortcutSuggestion) => void;
}

/**
 * Get icon for shortcut type.
 */
function getShortcutIcon(type: string): React.ReactNode {
  switch (type) {
    case 'calendar':
      return <CalendarIcon className="w-4 h-4" />;
    case 'contacts':
      return <UserGroupIcon className="w-4 h-4" />;
    case 'agent':
      return <CpuChipIcon className="w-4 h-4" />;
    default:
      return null;
  }
}

/**
 * WorkspaceShortcutDropdown - Dropdown showing available / shortcuts.
 */
export function WorkspaceShortcutDropdown({
  suggestions,
  selectedIndex,
  isLoading,
  onSelect,
}: WorkspaceShortcutDropdownProps) {
  if (suggestions.length === 0) {
    return (
      <div className="absolute left-0 right-0 bottom-full mb-1 z-50 rounded-xl border border-[var(--border)] bg-[var(--card)] shadow-lg overflow-hidden">
        <div className="px-4 py-3 text-sm text-[var(--muted-foreground)]">
          No shortcuts found
        </div>
      </div>
    );
  }

  return (
    <div className="absolute left-0 right-0 bottom-full mb-1 z-50 rounded-xl border border-[var(--border)] bg-[var(--card)] shadow-lg overflow-hidden">
      {isLoading ? (
        <div className="px-4 py-3 text-sm text-[var(--muted-foreground)]">
          Loading...
        </div>
      ) : (
        <>
          <ul className="max-h-64 overflow-y-auto">
            {suggestions.map((suggestion, index) => (
              <li key={suggestion.type}>
                <button
                  type="button"
                  onClick={() => onSelect(suggestion)}
                  className={`
                    w-full px-4 py-2.5 flex items-start gap-3 text-left transition-colors
                    ${
                      index === selectedIndex
                        ? 'bg-[oklch(0.65_0.25_180/0.1)]'
                        : 'hover:bg-[var(--muted)]'
                    }
                  `}
                >
                  <span
                    className={`
                      flex-shrink-0 mt-0.5
                      ${index === selectedIndex ? 'text-[oklch(0.65_0.25_180)]' : 'text-[var(--muted-foreground)]'}
                    `}
                  >
                    {getShortcutIcon(suggestion.type)}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-[var(--foreground)]">
                        {suggestion.label}
                      </span>
                      <code className="text-xs text-[var(--muted-foreground)] bg-[var(--muted)] px-1.5 py-0.5 rounded">
                        {suggestion.example}
                      </code>
                    </div>
                    <p className="text-xs text-[var(--muted-foreground)] mt-0.5">
                      {suggestion.description}
                    </p>
                  </div>
                </button>
              </li>
            ))}
          </ul>
          <div className="px-4 py-2 border-t border-[var(--border)] bg-[var(--muted)]">
            <p className="text-xs text-[var(--muted-foreground)]">
              <kbd className="px-1 py-0.5 bg-[var(--card)] rounded text-[10px] font-mono">
                ↑↓
              </kbd>{' '}
              navigate
              {' · '}
              <kbd className="px-1 py-0.5 bg-[var(--card)] rounded text-[10px] font-mono">
                Enter
              </kbd>{' '}
              select
              {' · '}
              <kbd className="px-1 py-0.5 bg-[var(--card)] rounded text-[10px] font-mono">
                Esc
              </kbd>{' '}
              close
            </p>
          </div>
        </>
      )}
    </div>
  );
}
