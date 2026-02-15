'use client';

import { useEffect, useState } from 'react';
import {
  TrashIcon,
  CheckCircleIcon,
  XCircleIcon,
  ArrowPathIcon,
} from '@heroicons/react/24/outline';
import type { Preference, PreferenceStats } from '../../../../types/task';
import * as taskApi from '../../../../services/taskApi';

export default function PreferencesPage() {
  const [preferences, setPreferences] = useState<Preference[]>([]);
  const [stats, setStats] = useState<PreferenceStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [prefsData, statsData] = await Promise.all([
        taskApi.getPreferences(),
        taskApi.getPreferenceStats(),
      ]);
      setPreferences(prefsData);
      setStats(statsData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load preferences');
    } finally {
      setIsLoading(false);
    }
  };

  const handleDelete = async (preferenceId: string) => {
    setDeletingId(preferenceId);
    try {
      await taskApi.deletePreference(preferenceId);
      setPreferences(prefs => prefs.filter(p => p.id !== preferenceId));
      if (stats) {
        setStats({
          ...stats,
          total_preferences: stats.total_preferences - 1,
        });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete preference');
    } finally {
      setDeletingId(null);
    }
  };

  if (isLoading) {
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
      {/* Header with refresh */}
      <div className="flex items-center justify-between mb-6">
        <p className="text-xs font-mono text-[var(--muted-foreground)] tracking-wider">
          LEARNED FROM YOUR DECISIONS
        </p>
        <button
          onClick={loadData}
          disabled={isLoading}
          className="p-2 rounded border border-[var(--border)] bg-[var(--background)] text-[var(--muted-foreground)] hover:text-[var(--foreground)] hover:border-[var(--accent)] transition-colors disabled:opacity-50"
        >
          <ArrowPathIcon className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Stats */}
      {stats && stats.total_preferences > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-8">
          <div className="p-4 rounded border border-[var(--border)] bg-[var(--card)]">
            <p className="text-2xl font-bold font-mono text-[var(--foreground)]">
              {stats.total_preferences}
            </p>
            <p className="text-[10px] font-mono tracking-wider text-[var(--muted-foreground)]">
              TOTAL LEARNED
            </p>
          </div>
          <div className="p-4 rounded border border-emerald-500/30 bg-[var(--card)]">
            <p className="text-2xl font-bold font-mono text-emerald-500">
              {stats.approvals}
            </p>
            <p className="text-[10px] font-mono tracking-wider text-[var(--muted-foreground)]">
              AUTO-APPROVALS
            </p>
          </div>
          <div className="p-4 rounded border border-[var(--destructive)]/30 bg-[var(--card)]">
            <p className="text-2xl font-bold font-mono text-[var(--destructive)]">
              {stats.rejections}
            </p>
            <p className="text-[10px] font-mono tracking-wider text-[var(--muted-foreground)]">
              AUTO-REJECTIONS
            </p>
          </div>
          <div className="p-4 rounded border border-[var(--accent)]/30 bg-[var(--card)]">
            <p className="text-2xl font-bold font-mono text-[var(--accent)]">
              {stats.high_confidence}
            </p>
            <p className="text-[10px] font-mono tracking-wider text-[var(--muted-foreground)]">
              HIGH CONFIDENCE
            </p>
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="mb-6 p-4 rounded border border-[var(--destructive)]/30 bg-[var(--card)] text-xs font-mono text-[var(--destructive)]">
          {error}
        </div>
      )}

      {/* Empty state */}
      {preferences.length === 0 && (
        <div className="text-center py-20">
          <div className="inline-block p-4 rounded border border-[var(--border)] mb-4">
            <div className="w-8 h-8 border border-dashed border-[var(--muted-foreground)] rounded" />
          </div>
          <p className="text-sm text-[var(--muted-foreground)] mb-1">
            No learned preferences yet
          </p>
          <p className="text-xs font-mono text-[var(--muted-foreground)]/60 max-w-sm mx-auto">
            When you approve or reject checkpoints with &quot;Remember this choice&quot; enabled,
            I&apos;ll learn your preferences and apply them automatically.
          </p>
        </div>
      )}

      {/* Preferences list */}
      {preferences.length > 0 && (
        <div className="space-y-2">
          <div className="text-[10px] font-mono tracking-wider text-[var(--muted-foreground)] mb-3">
            PREFERENCE RULES ({preferences.length})
          </div>
          {preferences.map((pref) => (
            <div
              key={pref.id}
              className={`group flex items-center gap-4 p-4 rounded border bg-[var(--card)] transition-colors ${
                pref.decision === 'approved'
                  ? 'border-emerald-500/30 hover:border-emerald-500/50'
                  : 'border-[var(--destructive)]/30 hover:border-[var(--destructive)]/50'
              }`}
            >
              {/* Decision indicator */}
              <div className={`
                flex-shrink-0 w-8 h-8 rounded border flex items-center justify-center
                ${pref.decision === 'approved'
                  ? 'border-emerald-500/50 text-emerald-500'
                  : 'border-[var(--destructive)]/50 text-[var(--destructive)]'
                }
              `}>
                {pref.decision === 'approved' ? (
                  <CheckCircleIcon className="w-4 h-4" />
                ) : (
                  <XCircleIcon className="w-4 h-4" />
                )}
              </div>

              {/* Details */}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-mono text-[var(--foreground)] truncate">
                  {pref.preference_key}
                </p>
                <p className="text-[10px] font-mono tracking-wider text-[var(--muted-foreground)]">
                  USED {pref.usage_count}x • {Math.round(pref.confidence * 100)}% CONFIDENCE
                </p>
              </div>

              {/* Delete button */}
              <button
                onClick={() => handleDelete(pref.id)}
                disabled={deletingId === pref.id}
                className="flex-shrink-0 p-2 rounded border border-transparent text-[var(--muted-foreground)] hover:text-[var(--destructive)] hover:border-[var(--destructive)]/30 transition-colors opacity-0 group-hover:opacity-100 disabled:opacity-50"
                title="Remove preference"
              >
                {deletingId === pref.id ? (
                  <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
                ) : (
                  <TrashIcon className="w-4 h-4" />
                )}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
