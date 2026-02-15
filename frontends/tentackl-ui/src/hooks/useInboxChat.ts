'use client';

import { useState, useCallback, useRef } from 'react';
import { sendInboxChatMessage } from '@/services/inboxApi';
import type { FileReference } from '@/services/fileService';

type StreamingStatus = 'thinking' | 'tool_execution' | 'responding' | null;

interface UseInboxChatReturn {
  sendMessage: (text: string, fileReferences?: FileReference[]) => Promise<void>;
  isStreaming: boolean;
  streamingContent: string;
  streamingStatus: StreamingStatus;
  conversationId: string | undefined;
  setConversationId: (id: string | undefined) => void;
}

/**
 * Hook for managing inbox chat streaming state.
 *
 * Usage:
 *   const chat = useInboxChat({ conversationId, onMessageComplete });
 *   chat.sendMessage("Hello");
 */
export function useInboxChat(options?: {
  conversationId?: string;
  onMessageComplete?: (content: string, conversationId: string) => void;
  onConversationCreated?: (conversationId: string) => void;
}): UseInboxChatReturn {
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [streamingStatus, setStreamingStatus] = useState<StreamingStatus>(null);
  const [conversationId, setConversationId] = useState<string | undefined>(
    options?.conversationId,
  );
  const abortRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback(
    async (text: string, fileReferences?: FileReference[]) => {
      if (isStreaming) return;

      setIsStreaming(true);
      setStreamingContent('');
      setStreamingStatus('thinking');

      let resolvedConversationId = conversationId;
      let accumulatedContent = '';

      try {
        const controller = await sendInboxChatMessage(text, conversationId, {
          onConversationId: (id) => {
            resolvedConversationId = id;
            setConversationId(id);
            options?.onConversationCreated?.(id);
          },
          onStatus: (status) => {
            if (status === 'tool_execution') {
              setStreamingStatus('tool_execution');
            } else if (status === 'thinking') {
              setStreamingStatus('thinking');
            }
          },
          onContent: (content) => {
            accumulatedContent += content;
            setStreamingContent(accumulatedContent);
            setStreamingStatus('responding');
          },
          onDone: () => {
            setIsStreaming(false);
            setStreamingStatus(null);
            if (resolvedConversationId && accumulatedContent) {
              options?.onMessageComplete?.(accumulatedContent, resolvedConversationId);
            }
          },
          onError: (error) => {
            console.error('Inbox chat error:', error);
            setIsStreaming(false);
            setStreamingStatus(null);
          },
        }, undefined, fileReferences);

        abortRef.current = controller;
      } catch (error) {
        console.error('Failed to send inbox chat message:', error);
        setIsStreaming(false);
        setStreamingStatus(null);
      }
    },
    [isStreaming, conversationId, options],
  );

  return {
    sendMessage,
    isStreaming,
    streamingContent,
    streamingStatus,
    conversationId,
    setConversationId,
  };
}
