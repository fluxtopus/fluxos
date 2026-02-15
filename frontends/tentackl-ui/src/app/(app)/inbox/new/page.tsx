'use client';

import { useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { ChatBubbleLeftRightIcon } from '@heroicons/react/24/outline';
import { useInboxStore } from '@/store/inboxStore';
import { ChatInput } from '@/components/Inbox/ChatInput';
import type { FileReference } from '@/services/fileService';

/**
 * New Conversation page.
 *
 * Renders an empty chat interface. On first message, the backend creates
 * a conversation and streams the response. We navigate to the conversation
 * page immediately — the streaming state lives in the Zustand store so
 * the conversation page picks it up seamlessly.
 */
export default function NewConversationPage() {
  const router = useRouter();
  const startNewConversationStream = useInboxStore((s) => s.startNewConversationStream);
  const isStreaming = useInboxStore((s) => s.isStreaming);

  const handleSend = useCallback(
    async (text: string, fileReferences?: FileReference[]) => {
      // Start the stream (resolves once the backend sends the conversation ID)
      const conversationId = await startNewConversationStream(text, false, fileReferences);
      // Navigate immediately — InboxThreadView reads streaming state from the store
      router.replace(`/inbox/${conversationId}`);
    },
    [startNewConversationStream, router],
  );

  return (
    <div className="h-full flex flex-col">
      <div className="flex-1 min-h-0 flex flex-col">
        {/* Empty state */}
        <div className="flex-1 overflow-y-auto px-3 flex flex-col">
          <div className="flex-1 flex flex-col items-center justify-center text-center">
            <div className="h-12 w-12 rounded-full bg-[var(--accent)]/10 flex items-center justify-center mb-4">
              <ChatBubbleLeftRightIcon className="h-6 w-6 text-[var(--accent)]" />
            </div>
            <p className="text-sm text-[var(--muted-foreground)] max-w-sm">
              Start a conversation with Flux. Ask questions, create tasks, search the web, or send notifications.
            </p>
          </div>
        </div>

        {/* Chat input */}
        <div className="px-3 pb-3">
          <ChatInput
            onSubmit={handleSend}
            disabled={isStreaming}
            placeholder="Type a message to start..."
          />
        </div>
      </div>
    </div>
  );
}
