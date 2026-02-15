/**
 * Inbox Store
 *
 * Zustand state management for the agent inbox.
 * URL-driven: filters and selection are owned by the URL, not this store.
 * This store owns the item list, pagination, and status mutations.
 */

import { create } from 'zustand';
import { devtools } from 'zustand/middleware';
import * as inboxApi from '../services/inboxApi';
import type {
  InboxItem,
  InboxThread,
  InboxReadStatus,
  InboxQueryParams,
} from '../types/inbox';
import type { FileReference } from '../services/fileService';

/** Auth errors are already handled by the axios interceptor (session-expired redirect). */
function isAuthError(error: unknown): boolean {
  if (error instanceof Error && error.message === 'Token refresh failed') return true;
  if (typeof error === 'object' && error !== null && 'response' in error) {
    const status = (error as { response?: { status?: number } }).response?.status;
    if (status === 401) return true;
  }
  return false;
}

// ============================================
// Store Interface
// ============================================

type StreamingStatus = 'thinking' | 'tool_execution' | 'responding' | null;

interface InboxStore {
  // === State ===
  items: InboxItem[];
  total: number;
  hasMore: boolean;
  unreadCount: number;
  attentionCount: number;
  loading: boolean;
  loadingMore: boolean;
  errorMessage: string | null;

  // === Streaming (survives navigation) ===
  streamingConversationId: string | null;
  streamingContent: string;
  streamingStatus: StreamingStatus;
  isStreaming: boolean;

  // === Active thread (for SSE-driven refresh) ===
  activeThreadId: string | null;
  threadRefreshKey: number;

  // === Actions: Loading ===
  loadInbox: (params: InboxQueryParams) => Promise<void>;
  loadMore: (params: InboxQueryParams) => Promise<void>;
  loadUnreadCount: () => Promise<void>;
  loadAttentionCount: () => Promise<void>;
  loadThread: (conversationId: string) => Promise<InboxThread>;

  // === Actions: Status Updates ===
  markAsRead: (conversationId: string) => Promise<void>;
  markAsUnread: (conversationId: string) => Promise<void>;
  archiveConversation: (conversationId: string) => Promise<void>;

  // === Actions: Bulk Operations ===
  bulkMarkRead: (conversationIds: string[]) => Promise<void>;
  bulkArchive: (conversationIds: string[]) => Promise<void>;

  // === Actions: Follow-up ===
  createFollowUp: (conversationId: string, text: string) => Promise<void>;

  // === Actions: Active Thread ===
  setActiveThread: (id: string | null) => void;
  bumpThreadRefresh: () => void;

  // === Actions: Streaming ===
  /** Start a new-conversation stream. Returns the conversation ID once known. */
  startNewConversationStream: (message: string, onboarding?: boolean, fileReferences?: FileReference[]) => Promise<string>;
  clearStreaming: () => void;
}

// ============================================
// Helpers
// ============================================

function updateItemStatus(
  items: InboxItem[],
  conversationId: string,
  readStatus: InboxReadStatus
): InboxItem[] {
  return items.map((item) =>
    item.conversation_id === conversationId
      ? { ...item, read_status: readStatus }
      : item
  );
}

function countUnread(items: InboxItem[]): number {
  return items.filter((item) => item.read_status === 'unread').length;
}

// ============================================
// Store Implementation
// ============================================

export const useInboxStore = create<InboxStore>()(
  devtools(
    (set, get) => ({
      items: [],
      total: 0,
      hasMore: false,
      unreadCount: 0,
      attentionCount: 0,
      loading: false,
      loadingMore: false,
      errorMessage: null,

      // Streaming state (persists across page navigation)
      streamingConversationId: null,
      streamingContent: '',
      streamingStatus: null,
      isStreaming: false,

      // Active thread (for SSE-driven refresh)
      activeThreadId: null,
      threadRefreshKey: 0,

      // ========================================
      // Loading
      // ========================================

      loadInbox: async (params) => {
        set({ loading: true, errorMessage: null });

        try {
          const response = await inboxApi.listInbox(params);
          const hasMore = response.offset + response.items.length < response.total;
          set({
            items: response.items,
            total: response.total,
            hasMore,
            loading: false,
          });
        } catch (error) {
          if (!isAuthError(error)) {
            set({
              loading: false,
              errorMessage: error instanceof Error ? error.message : 'Failed to load inbox',
            });
          } else {
            set({ loading: false });
          }
        }
      },

      loadMore: async (params) => {
        const { items, loadingMore, hasMore } = get();
        if (loadingMore || !hasMore) return;

        set({ loadingMore: true });

        try {
          const response = await inboxApi.listInbox({
            ...params,
            offset: items.length,
          });
          const newHasMore = items.length + response.items.length < response.total;
          set({
            items: [...items, ...response.items],
            total: response.total,
            hasMore: newHasMore,
            loadingMore: false,
          });
        } catch (error) {
          if (!isAuthError(error)) {
            set({
              loadingMore: false,
              errorMessage: error instanceof Error ? error.message : 'Failed to load more',
            });
          } else {
            set({ loadingMore: false });
          }
        }
      },

      loadUnreadCount: async () => {
        try {
          const count = await inboxApi.getUnreadCount();
          set({ unreadCount: count });
        } catch {
          // Auth errors handled by interceptor; other failures are non-critical.
        }
      },

      loadAttentionCount: async () => {
        try {
          const count = await inboxApi.getAttentionCount();
          set({ attentionCount: count });
        } catch {
          // Auth errors handled by interceptor; other failures are non-critical.
        }
      },

      loadThread: async (conversationId) => {
        const thread = await inboxApi.getThread(conversationId);

        // Auto-mark as read in the item list
        if (thread.read_status === 'unread') {
          get().markAsRead(conversationId);
        }

        return thread;
      },

      // ========================================
      // Status Updates
      // ========================================

      markAsRead: async (conversationId) => {
        const { items } = get();
        const updatedItems = updateItemStatus(items, conversationId, 'read');
        const updatedCount = Math.max(0, get().unreadCount - 1);

        set({ items: updatedItems, unreadCount: updatedCount });

        try {
          await inboxApi.updateReadStatus(conversationId, 'read');
        } catch (error) {
          set({
            items,
            unreadCount: countUnread(items),
            errorMessage: error instanceof Error ? error.message : 'Failed to mark as read',
          });
        }
      },

      markAsUnread: async (conversationId) => {
        const { items } = get();
        set({
          items: updateItemStatus(items, conversationId, 'unread'),
          unreadCount: get().unreadCount + 1,
        });

        try {
          await inboxApi.updateReadStatus(conversationId, 'unread');
        } catch (error) {
          set({
            items,
            unreadCount: countUnread(items),
            errorMessage: error instanceof Error ? error.message : 'Failed to mark as unread',
          });
        }
      },

      archiveConversation: async (conversationId) => {
        const { items } = get();
        const item = items.find((i) => i.conversation_id === conversationId);
        const wasUnread = item?.read_status === 'unread';

        set({
          items: updateItemStatus(items, conversationId, 'archived'),
          unreadCount: wasUnread ? Math.max(0, get().unreadCount - 1) : get().unreadCount,
        });

        try {
          await inboxApi.updateReadStatus(conversationId, 'archived');
        } catch (error) {
          set({
            items,
            unreadCount: countUnread(items),
            errorMessage: error instanceof Error ? error.message : 'Failed to archive conversation',
          });
        }
      },

      // ========================================
      // Bulk Operations
      // ========================================

      bulkMarkRead: async (conversationIds) => {
        const { items } = get();
        const updatedItems = items.map((item) =>
          conversationIds.includes(item.conversation_id)
            ? { ...item, read_status: 'read' as InboxReadStatus }
            : item
        );
        set({
          items: updatedItems,
          unreadCount: countUnread(updatedItems),
        });

        try {
          await inboxApi.bulkUpdateReadStatus(conversationIds, 'read');
        } catch (error) {
          set({
            items,
            unreadCount: countUnread(items),
            errorMessage: error instanceof Error ? error.message : 'Failed to bulk mark as read',
          });
        }
      },

      bulkArchive: async (conversationIds) => {
        const { items } = get();
        const updatedItems = items.map((item) =>
          conversationIds.includes(item.conversation_id)
            ? { ...item, read_status: 'archived' as InboxReadStatus }
            : item
        );
        set({
          items: updatedItems,
          unreadCount: countUnread(updatedItems),
        });

        try {
          await inboxApi.bulkUpdateReadStatus(conversationIds, 'archived');
        } catch (error) {
          set({
            items,
            unreadCount: countUnread(items),
            errorMessage: error instanceof Error ? error.message : 'Failed to bulk archive',
          });
        }
      },

      // ========================================
      // Follow-up
      // ========================================

      createFollowUp: async (conversationId, text) => {
        try {
          await inboxApi.createFollowUp(conversationId, text);
        } catch (error) {
          const message = error instanceof Error ? error.message : 'Failed to create follow-up';
          set({ errorMessage: message });
          throw error;
        }
      },

      // ========================================
      // Active Thread
      // ========================================

      setActiveThread: (id) => set({ activeThreadId: id }),

      bumpThreadRefresh: () => set({ threadRefreshKey: get().threadRefreshKey + 1 }),

      // ========================================
      // Streaming (survives navigation)
      // ========================================

      startNewConversationStream: (message, onboarding, fileReferences) => {
        return new Promise<string>((resolve) => {
          let accumulatedContent = '';

          set({
            isStreaming: true,
            streamingContent: '',
            streamingStatus: 'thinking',
            streamingConversationId: null,
          });

          inboxApi.sendInboxChatMessage(message, undefined, {
            onConversationId: (id) => {
              set({ streamingConversationId: id });
              resolve(id);
            },
            onStatus: (status) => {
              if (status === 'tool_execution') {
                set({ streamingStatus: 'tool_execution' });
              } else if (status === 'thinking') {
                set({ streamingStatus: 'thinking' });
              }
            },
            onContent: (content) => {
              accumulatedContent += content;
              set({ streamingContent: accumulatedContent, streamingStatus: 'responding' });
            },
            onDone: () => {
              set({
                isStreaming: false,
                streamingStatus: null,
              });
            },
            onError: (error) => {
              console.error('Inbox chat stream error:', error);
              set({
                isStreaming: false,
                streamingStatus: null,
              });
            },
          }, onboarding, fileReferences);
        });
      },

      clearStreaming: () => {
        set({
          streamingConversationId: null,
          streamingContent: '',
          streamingStatus: null,
          isStreaming: false,
        });
      },
    }),
    { name: 'inbox-store' }
  )
);
