'use client';

import { useState, useEffect, useCallback } from 'react';
import { useInboxStore } from '@/store/inboxStore';
import { useDelayedLoading } from '@/hooks/useDelayedLoading';
import { useInboxChat } from '@/hooks/useInboxChat';
import { InboxThread } from './InboxThread';
import type { InboxThread as InboxThreadType } from '@/types/inbox';
import type { FileReference } from '@/services/fileService';

interface InboxThreadViewProps {
  conversationId: string;
}

export function InboxThreadView({ conversationId }: InboxThreadViewProps) {
  const { loadThread } = useInboxStore();

  // Store-level streaming (started on /inbox/new, survives navigation)
  const storeStreamingConvId = useInboxStore((s) => s.streamingConversationId);
  const storeIsStreaming = useInboxStore((s) => s.isStreaming);
  const storeStreamingContent = useInboxStore((s) => s.streamingContent);
  const storeStreamingStatus = useInboxStore((s) => s.streamingStatus);
  const clearStreaming = useInboxStore((s) => s.clearStreaming);

  // SSE-driven thread refresh
  const setActiveThread = useInboxStore((s) => s.setActiveThread);
  const threadRefreshKey = useInboxStore((s) => s.threadRefreshKey);

  const storeStreamingActive = storeStreamingConvId === conversationId && storeIsStreaming;

  const [thread, setThread] = useState<InboxThreadType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const showLoading = useDelayedLoading(loading);

  // Chat hook for conversational interaction (subsequent messages)
  const chat = useInboxChat({
    conversationId,
    onMessageComplete: useCallback(
      (_content: string, _convId: string) => {
        // Reload thread to get persisted messages
        loadThread(conversationId).then(setThread).catch(console.error);
      },
      [conversationId, loadThread],
    ),
  });

  // Register this thread as active so layout SSE can trigger refreshes
  useEffect(() => {
    setActiveThread(conversationId);
    return () => setActiveThread(null);
  }, [conversationId, setActiveThread]);

  // When SSE delivers a new message for this thread, reload it (skip if streaming)
  useEffect(() => {
    if (threadRefreshKey > 0 && !storeStreamingActive && !chat.isStreaming) {
      loadThread(conversationId).then(setThread).catch(console.error);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threadRefreshKey]);

  // When store-level streaming finishes, reload the thread and clear store state
  useEffect(() => {
    if (storeStreamingConvId === conversationId && !storeIsStreaming && storeStreamingContent) {
      loadThread(conversationId).then(setThread).catch(console.error);
      clearStreaming();
    }
  }, [storeIsStreaming, storeStreamingConvId, storeStreamingContent, conversationId, loadThread, clearStreaming]);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const data = await loadThread(conversationId);
        if (!cancelled) setThread(data);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load thread');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();
    return () => { cancelled = true; };
  }, [conversationId, loadThread]);

  const handleSendMessage = useCallback(
    async (text: string, fileReferences?: FileReference[]) => {
      // Optimistically add user message to the thread
      if (thread) {
        const now = new Date().toISOString();
        const userMessage = {
          id: 'local-user-' + Date.now(),
          role: 'user',
          content_text: text,
          content_data: null,
          message_type: 'user_input',
          timestamp: now,
        };
        setThread({
          ...thread,
          messages: [...thread.messages, userMessage],
        });
      }

      // Send via chat hook (starts streaming)
      await chat.sendMessage(text, fileReferences);
    },
    [thread, chat],
  );

  if (error) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-sm text-[var(--destructive)]">{error}</p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      <div className="flex-1 min-h-0">
        <InboxThread
          thread={thread}
          loading={showLoading}
          onSendMessage={handleSendMessage}
          isStreaming={storeStreamingActive || chat.isStreaming}
          streamingContent={storeStreamingActive ? storeStreamingContent : chat.streamingContent}
          streamingStatus={storeStreamingActive ? storeStreamingStatus : chat.streamingStatus}
        />
      </div>
    </div>
  );
}
