'use client';

import { useEffect, useState, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  ArrowLeftIcon,
  ArrowPathIcon,
  BoltIcon,
  PauseIcon,
  PlayIcon,
  UserIcon,
  BuildingOfficeIcon,
  CheckCircleIcon,
  XCircleIcon,
  ClockIcon,
} from '@heroicons/react/24/outline';
import * as triggersApi from '../../../../../services/triggersApi';
import { useTriggerSSE } from '../../../../../hooks/useTriggerSSE';
import type { Trigger, TriggerEvent, TriggerExecution } from '../../../../../types/trigger';

export default function TriggerDetailPage() {
  const params = useParams();
  const router = useRouter();
  const taskId = params.id as string;

  const [trigger, setTrigger] = useState<Trigger | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isUpdating, setIsUpdating] = useState(false);

  // Live events
  const [liveEvents, setLiveEvents] = useState<TriggerEvent[]>([]);
  const [isPaused, setIsPaused] = useState(false);
  const [isConnected, setIsConnected] = useState(false);

  // Execution history
  const [executions, setExecutions] = useState<TriggerExecution[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);

  const loadTrigger = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const result = await triggersApi.getTrigger(taskId);
      setTrigger(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load trigger');
    } finally {
      setIsLoading(false);
    }
  };

  const loadHistory = async () => {
    setIsLoadingHistory(true);
    try {
      const result = await triggersApi.getTriggerHistory(taskId);
      setExecutions(result.executions);
    } catch (err) {
      console.error('Failed to load history:', err);
    } finally {
      setIsLoadingHistory(false);
    }
  };

  useEffect(() => {
    loadTrigger();
    loadHistory();
  }, [taskId]);

  // Handle live events
  const handleEvent = useCallback((event: TriggerEvent) => {
    if (!isPaused) {
      setLiveEvents((prev) => [event, ...prev].slice(0, 50));
    }
  }, [isPaused]);

  const handleSSEConnected = useCallback(() => {
    setIsConnected(true);
  }, []);

  const handleSSEError = useCallback((err: string) => {
    console.error('SSE error:', err);
    setIsConnected(false);
  }, []);

  useTriggerSSE(taskId, {
    onEvent: handleEvent,
    onConnected: handleSSEConnected,
    onError: handleSSEError,
  }, !isPaused);

  const handleToggle = async () => {
    if (!trigger) return;
    setIsUpdating(true);
    try {
      const updated = await triggersApi.updateTrigger(taskId, { enabled: !trigger.enabled });
      setTrigger(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update trigger');
    } finally {
      setIsUpdating(false);
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

  if (error || !trigger) {
    return (
      <div>
        <button
          onClick={() => router.push('/settings/triggers')}
          className="flex items-center gap-2 text-xs font-mono tracking-wider text-[var(--muted-foreground)] hover:text-[var(--foreground)] mb-6"
        >
          <ArrowLeftIcon className="w-4 h-4" />
          BACK TO TRIGGERS
        </button>
        <div className="p-4 rounded border border-[var(--destructive)]/30 bg-[var(--card)] text-xs font-mono text-[var(--destructive)]">
          {error || 'Trigger not found'}
        </div>
      </div>
    );
  }

  return (
    <div>
      {/* Back link */}
      <button
        onClick={() => router.push('/settings/triggers')}
        className="flex items-center gap-2 text-xs font-mono tracking-wider text-[var(--muted-foreground)] hover:text-[var(--foreground)] mb-6"
      >
        <ArrowLeftIcon className="w-4 h-4" />
        BACK TO TRIGGERS
      </button>

      {/* Header */}
      <div className="flex items-center gap-4 mb-8">
        <div className="flex-shrink-0 w-12 h-12 rounded border border-[var(--border)] bg-[var(--muted)] flex items-center justify-center">
          <BoltIcon className="w-6 h-6 text-[var(--accent)]" />
        </div>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-bold font-mono text-[var(--foreground)]">
              {trigger.event_pattern}
            </h2>
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
          </div>
          <p className="text-xs font-mono text-[var(--muted-foreground)] mt-1">
            Task: {trigger.task_id}
          </p>
        </div>
        <button
          onClick={handleToggle}
          disabled={isUpdating}
          className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
            trigger.enabled ? 'bg-emerald-500' : 'bg-[var(--muted)]'
          } ${isUpdating ? 'opacity-50' : ''}`}
        >
          <span
            className={`inline-block h-5 w-5 transform rounded-full bg-white transition-transform ${
              trigger.enabled ? 'translate-x-5' : 'translate-x-0.5'
            }`}
          />
        </button>
      </div>

      <div className="space-y-6">
        {/* Configuration Section */}
        <div className="rounded border border-[var(--border)] bg-[var(--card)]">
          <div className="p-4 border-b border-[var(--border)]">
            <p className="text-xs font-mono tracking-wider text-[var(--foreground)]">
              CONFIGURATION
            </p>
          </div>
          <div className="p-4 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono tracking-wider text-[var(--muted-foreground)]">
                EVENT PATTERN
              </span>
              <span className="text-xs font-mono text-[var(--foreground)]">
                {trigger.event_pattern}
              </span>
            </div>
            {trigger.source_filter && (
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-mono tracking-wider text-[var(--muted-foreground)]">
                  SOURCE FILTER
                </span>
                <span className="text-xs font-mono text-[var(--foreground)]">
                  {trigger.source_filter}
                </span>
              </div>
            )}
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-mono tracking-wider text-[var(--muted-foreground)]">
                TYPE
              </span>
              <span className="text-xs font-mono text-[var(--foreground)]">
                {trigger.type}
              </span>
            </div>
            {trigger.condition && (
              <div>
                <span className="text-[10px] font-mono tracking-wider text-[var(--muted-foreground)] block mb-2">
                  CONDITION
                </span>
                <pre className="text-xs font-mono text-[var(--foreground)] bg-[var(--muted)] p-2 rounded overflow-x-auto">
                  {JSON.stringify(trigger.condition, null, 2)}
                </pre>
              </div>
            )}
          </div>
        </div>

        {/* Live Events Section */}
        <div className="rounded border border-[var(--border)] bg-[var(--card)]">
          <div className="flex items-center justify-between p-4 border-b border-[var(--border)]">
            <div className="flex items-center gap-2">
              <p className="text-xs font-mono tracking-wider text-[var(--foreground)]">
                LIVE EVENTS
              </p>
              <span
                className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono ${
                  isConnected
                    ? 'bg-emerald-500/10 text-emerald-500'
                    : 'bg-[var(--muted)] text-[var(--muted-foreground)]'
                }`}
              >
                <span className={`w-1.5 h-1.5 rounded-full ${isConnected ? 'bg-emerald-500 animate-pulse' : 'bg-[var(--muted-foreground)]'}`} />
                {isConnected ? 'CONNECTED' : 'DISCONNECTED'}
              </span>
            </div>
            <button
              onClick={() => setIsPaused(!isPaused)}
              className={`inline-flex items-center gap-1 px-2 py-1 rounded text-[10px] font-mono tracking-wider transition-colors ${
                isPaused
                  ? 'bg-[var(--accent)] text-[var(--accent-foreground)]'
                  : 'bg-[var(--muted)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]'
              }`}
            >
              {isPaused ? (
                <>
                  <PlayIcon className="w-3 h-3" />
                  RESUME
                </>
              ) : (
                <>
                  <PauseIcon className="w-3 h-3" />
                  PAUSE
                </>
              )}
            </button>
          </div>
          <div className="p-4 max-h-80 overflow-y-auto">
            {liveEvents.length === 0 ? (
              <p className="text-center text-xs font-mono text-[var(--muted-foreground)] py-8">
                No events yet. Events will appear here in real-time.
              </p>
            ) : (
              <div className="space-y-2">
                {liveEvents.map((event) => (
                  <div
                    key={event.id}
                    className="flex items-start gap-3 p-2 rounded bg-[var(--muted)]"
                  >
                    <span
                      className={`flex-shrink-0 mt-0.5 ${
                        event.type === 'trigger.completed'
                          ? 'text-emerald-500'
                          : event.type === 'trigger.failed'
                          ? 'text-[var(--destructive)]'
                          : event.type === 'trigger.matched'
                          ? 'text-blue-500'
                          : 'text-[var(--accent)]'
                      }`}
                    >
                      {event.type === 'trigger.completed' ? (
                        <CheckCircleIcon className="w-4 h-4" />
                      ) : event.type === 'trigger.failed' ? (
                        <XCircleIcon className="w-4 h-4" />
                      ) : (
                        <BoltIcon className="w-4 h-4" />
                      )}
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-mono text-[var(--foreground)]">
                        {event.type}
                      </p>
                      <p className="text-[10px] font-mono text-[var(--muted-foreground)] truncate">
                        {event.data.preview || event.data.event_id}
                      </p>
                    </div>
                    <span className="text-[10px] font-mono text-[var(--muted-foreground)] flex-shrink-0">
                      {new Date(event.timestamp).toLocaleTimeString()}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Execution History Section */}
        <div className="rounded border border-[var(--border)] bg-[var(--card)]">
          <div className="flex items-center justify-between p-4 border-b border-[var(--border)]">
            <p className="text-xs font-mono tracking-wider text-[var(--foreground)]">
              EXECUTION HISTORY
            </p>
            <button
              onClick={loadHistory}
              disabled={isLoadingHistory}
              className="p-1.5 rounded text-[var(--muted-foreground)] hover:text-[var(--foreground)] transition-colors disabled:opacity-50"
            >
              <ArrowPathIcon className={`w-4 h-4 ${isLoadingHistory ? 'animate-spin' : ''}`} />
            </button>
          </div>
          <div className="p-4">
            {executions.length === 0 ? (
              <p className="text-center text-xs font-mono text-[var(--muted-foreground)] py-8">
                No execution history yet.
              </p>
            ) : (
              <div className="space-y-2">
                {executions.map((execution) => (
                  <div
                    key={execution.id}
                    className="flex items-center gap-3 p-2 rounded bg-[var(--muted)]"
                  >
                    <span
                      className={`flex-shrink-0 ${
                        execution.status === 'completed'
                          ? 'text-emerald-500'
                          : execution.status === 'failed'
                          ? 'text-[var(--destructive)]'
                          : 'text-[var(--accent)]'
                      }`}
                    >
                      {execution.status === 'completed' ? (
                        <CheckCircleIcon className="w-4 h-4" />
                      ) : execution.status === 'failed' ? (
                        <XCircleIcon className="w-4 h-4" />
                      ) : (
                        <ClockIcon className="w-4 h-4 animate-spin" />
                      )}
                    </span>
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-mono text-[var(--foreground)]">
                        {execution.status.toUpperCase()}
                      </p>
                      {execution.error && (
                        <p className="text-[10px] font-mono text-[var(--destructive)] truncate">
                          {execution.error}
                        </p>
                      )}
                    </div>
                    <span className="text-[10px] font-mono text-[var(--muted-foreground)] flex-shrink-0">
                      {new Date(execution.started_at).toLocaleString()}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
