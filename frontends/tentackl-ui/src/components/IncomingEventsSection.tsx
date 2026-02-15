'use client';

import { useState, useCallback } from 'react';
import {
  BoltIcon,
  PauseIcon,
  PlayIcon,
  ChevronDownIcon,
  ChevronUpIcon,
} from '@heroicons/react/24/outline';
import { useIntegrationSSE } from '../hooks/useIntegrationSSE';
import type { IntegrationEvent } from '../types/trigger';

interface IncomingEventsSectionProps {
  integrationId: string;
  direction: string;
}

export function IncomingEventsSection({ integrationId, direction }: IncomingEventsSectionProps) {
  const [isExpanded, setIsExpanded] = useState(true);
  const [isPaused, setIsPaused] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [events, setEvents] = useState<IntegrationEvent[]>([]);

  // Only show for inbound or bidirectional integrations
  const canReceiveEvents = direction === 'inbound' || direction === 'bidirectional';

  const handleEvent = useCallback((event: IntegrationEvent) => {
    if (!isPaused) {
      setEvents((prev) => [event, ...prev].slice(0, 50));
    }
  }, [isPaused]);

  const handleConnected = useCallback(() => {
    setIsConnected(true);
  }, []);

  const handleError = useCallback((err: string) => {
    console.error('Integration SSE error:', err);
    setIsConnected(false);
  }, []);

  useIntegrationSSE(integrationId, {
    onEvent: handleEvent,
    onConnected: handleConnected,
    onError: handleError,
  }, canReceiveEvents && !isPaused);

  if (!canReceiveEvents) {
    return null;
  }

  return (
    <div className="rounded border border-[var(--border)] bg-[var(--card)]">
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center justify-between w-full p-4 border-b border-[var(--border)] hover:bg-[var(--muted)]/50 transition-colors"
      >
        <div className="flex items-center gap-2">
          <p className="text-xs font-mono tracking-wider text-[var(--foreground)]">
            INCOMING EVENTS
          </p>
          <span
            className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono ${
              isConnected
                ? 'bg-emerald-500/10 text-emerald-500'
                : 'bg-[var(--muted)] text-[var(--muted-foreground)]'
            }`}
          >
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                isConnected ? 'bg-emerald-500 animate-pulse' : 'bg-[var(--muted-foreground)]'
              }`}
            />
            {isConnected ? 'LIVE' : 'DISCONNECTED'}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {isExpanded && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                setIsPaused(!isPaused);
              }}
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
          )}
          {isExpanded ? (
            <ChevronUpIcon className="w-4 h-4 text-[var(--muted-foreground)]" />
          ) : (
            <ChevronDownIcon className="w-4 h-4 text-[var(--muted-foreground)]" />
          )}
        </div>
      </button>

      {/* Content */}
      {isExpanded && (
        <div className="p-4 max-h-64 overflow-y-auto">
          {events.length === 0 ? (
            <div className="text-center py-8">
              <BoltIcon className="w-8 h-8 mx-auto text-[var(--muted-foreground)] mb-2" />
              <p className="text-xs font-mono text-[var(--muted-foreground)]">
                No events yet
              </p>
              <p className="text-[10px] font-mono text-[var(--muted-foreground)] mt-1">
                Incoming webhook events will appear here in real-time
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {events.map((event, index) => (
                <div
                  key={`${event.event_id}-${index}`}
                  className="flex items-start gap-3 p-2 rounded bg-[var(--muted)]"
                >
                  <BoltIcon className="w-4 h-4 flex-shrink-0 mt-0.5 text-[var(--accent)]" />
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-mono text-[var(--foreground)]">
                      {event.data.event_type || event.type}
                    </p>
                    {event.data.preview && (
                      <p className="text-[10px] font-mono text-[var(--muted-foreground)] truncate">
                        {event.data.preview}
                      </p>
                    )}
                  </div>
                  <span className="text-[10px] font-mono text-[var(--muted-foreground)] flex-shrink-0">
                    {new Date(event.timestamp).toLocaleTimeString()}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
