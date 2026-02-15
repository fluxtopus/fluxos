'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ArrowPathIcon,
  TrashIcon,
  BoltIcon,
  UserIcon,
  BuildingOfficeIcon,
} from '@heroicons/react/24/outline';
import * as triggersApi from '../../../../services/triggersApi';
import type { Trigger } from '../../../../types/trigger';

type ScopeFilter = 'all' | 'org' | 'user';

export default function TriggersPage() {
  const router = useRouter();
  const [triggers, setTriggers] = useState<Trigger[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [scopeFilter, setScopeFilter] = useState<ScopeFilter>('all');
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const loadTriggers = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await triggersApi.listTriggers(scopeFilter);
      setTriggers(result.triggers);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load triggers');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadTriggers();
  }, [scopeFilter]);

  const handleToggle = async (trigger: Trigger) => {
    setUpdatingId(trigger.task_id);
    try {
      await triggersApi.updateTrigger(trigger.task_id, { enabled: !trigger.enabled });
      setTriggers((prev) =>
        prev.map((t) =>
          t.task_id === trigger.task_id ? { ...t, enabled: !t.enabled } : t
        )
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update trigger');
    } finally {
      setUpdatingId(null);
    }
  };

  const handleDelete = async (trigger: Trigger) => {
    if (!confirm(`Delete trigger for pattern "${trigger.event_pattern}"?`)) {
      return;
    }
    setDeletingId(trigger.task_id);
    try {
      await triggersApi.deleteTrigger(trigger.task_id);
      setTriggers((prev) => prev.filter((t) => t.task_id !== trigger.task_id));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete trigger');
    } finally {
      setDeletingId(null);
    }
  };

  if (isLoading && triggers.length === 0) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="text-center">
          <div className="w-8 h-8 border-2 border-[var(--accent)] border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-xs font-mono text-[var(--muted-foreground)] tracking-wider">
            LOADING...
          </p>
        </div>
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-sm font-mono tracking-wider text-[var(--foreground)]">
            EVENT TRIGGERS
          </h2>
          <p className="text-xs font-mono text-[var(--muted-foreground)] mt-1">
            Tasks that execute automatically when events occur
          </p>
        </div>
        <button
          onClick={loadTriggers}
          disabled={isLoading}
          className="p-2 rounded border border-[var(--border)] bg-[var(--background)] text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:border-[var(--accent)] transition-colors disabled:opacity-50"
        >
          <ArrowPathIcon className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Scope Filter */}
      <div className="flex gap-2 mb-6">
        {(['all', 'org', 'user'] as const).map((scope) => (
          <button
            key={scope}
            onClick={() => setScopeFilter(scope)}
            className={`px-3 py-1.5 text-[10px] font-mono tracking-wider rounded border transition-colors ${
              scopeFilter === scope
                ? 'border-[var(--accent)] bg-[var(--accent)]/10 text-[var(--accent)]'
                : 'border-[var(--border)] text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:border-[var(--foreground)]'
            }`}
          >
            {scope.toUpperCase()}
          </button>
        ))}
      </div>

      {/* Error */}
      {error && (
        <div className="mb-4 p-3 rounded border border-[var(--destructive)]/30 bg-[var(--card)] text-xs font-mono text-[var(--destructive)]">
          {error}
        </div>
      )}

      {/* Empty State */}
      {triggers.length === 0 && !error && (
        <div className="py-12 text-center">
          <BoltIcon className="w-12 h-12 mx-auto text-[var(--muted-foreground)] mb-4" />
          <p className="text-sm font-mono text-[var(--muted-foreground)]">
            No triggers configured
          </p>
          <p className="text-xs font-mono text-[var(--muted-foreground)] mt-1">
            Triggers are created when tasks are configured with event patterns
          </p>
        </div>
      )}

      {/* Triggers Table */}
      {triggers.length > 0 && (
        <div className="rounded border border-[var(--border)] bg-[var(--card)] overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-[var(--border)] bg-[var(--muted)]">
                <th className="px-4 py-3 text-left text-[10px] font-mono tracking-wider text-[var(--muted-foreground)]">
                  EVENT PATTERN
                </th>
                <th className="px-4 py-3 text-left text-[10px] font-mono tracking-wider text-[var(--muted-foreground)]">
                  TASK ID
                </th>
                <th className="px-4 py-3 text-left text-[10px] font-mono tracking-wider text-[var(--muted-foreground)]">
                  SCOPE
                </th>
                <th className="px-4 py-3 text-center text-[10px] font-mono tracking-wider text-[var(--muted-foreground)]">
                  STATUS
                </th>
                <th className="px-4 py-3 text-right text-[10px] font-mono tracking-wider text-[var(--muted-foreground)]">
                  ACTIONS
                </th>
              </tr>
            </thead>
            <tbody>
              {triggers.map((trigger) => (
                <tr
                  key={trigger.task_id}
                  className="border-b border-[var(--border)] last:border-b-0 hover:bg-[var(--muted)]/50 cursor-pointer"
                  onClick={() => router.push(`/settings/triggers/${trigger.task_id}`)}
                >
                  <td className="px-4 py-3">
                    <span className="text-xs font-mono text-[var(--foreground)]">
                      {trigger.event_pattern}
                    </span>
                    {trigger.source_filter && (
                      <span className="ml-2 text-[10px] font-mono text-[var(--muted-foreground)]">
                        ({trigger.source_filter})
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-xs font-mono text-[var(--muted-foreground)]">
                      {trigger.task_id.substring(0, 8)}...
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono tracking-wider ${
                        trigger.scope === 'org'
                          ? 'bg-blue-500/10 text-blue-500'
                          : 'bg-purple-500/10 text-purple-500'
                      }`}
                    >
                      {trigger.scope === 'org' ? (
                        <BuildingOfficeIcon className="w-3 h-3" />
                      ) : (
                        <UserIcon className="w-3 h-3" />
                      )}
                      {trigger.scope.toUpperCase()}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleToggle(trigger);
                      }}
                      disabled={updatingId === trigger.task_id}
                      className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${
                        trigger.enabled
                          ? 'bg-emerald-500'
                          : 'bg-[var(--muted)]'
                      } ${updatingId === trigger.task_id ? 'opacity-50' : ''}`}
                    >
                      <span
                        className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                          trigger.enabled ? 'translate-x-4' : 'translate-x-0.5'
                        }`}
                      />
                    </button>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDelete(trigger);
                      }}
                      disabled={deletingId === trigger.task_id}
                      className="p-1.5 rounded text-[var(--muted-foreground)] hover:text-[var(--destructive)] hover:bg-[var(--destructive)]/10 transition-colors disabled:opacity-50"
                    >
                      <TrashIcon className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
