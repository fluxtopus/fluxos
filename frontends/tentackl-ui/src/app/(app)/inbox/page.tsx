'use client';

import { useEffect, useCallback, useState, Suspense } from 'react';
import { useRouter } from 'next/navigation';
import toast from 'react-hot-toast';
import { useAuthStore } from '@/store/authStore';
import { useInboxStore } from '@/store/inboxStore';
import { useInboxFilters } from '@/hooks/useInboxFilters';
import { InboxFilterBar } from '@/components/Inbox/InboxFilterBar';
import { InboxList } from '@/components/Inbox/InboxList';
import { LoadMoreTrigger } from '@/components/Inbox/LoadMoreTrigger';
import { WelcomeScreen } from '@/components/Inbox/WelcomeScreen';
import { PullToRefresh } from '@/components/PullToRefresh';
import type { InboxFilter } from '@/types/inbox';
import type { FileReference } from '@/services/fileService';

const ONBOARDING_DISMISSED_KEY = 'aios_onboarding_dismissed';

function InboxPageInner() {
  const router = useRouter();
  const { isAuthenticated, user } = useAuthStore();
  const { filter, searchQuery, setFilter, setSearch, toApiParams } = useInboxFilters();
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [onboardingDismissed, setOnboardingDismissed] = useState(() => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem(ONBOARDING_DISMISSED_KEY) === 'true';
    }
    return false;
  });

  const {
    items,
    total,
    loading,
    loadingMore,
    hasMore,
    unreadCount,
    attentionCount,
    isStreaming,
    startNewConversationStream,
    loadInbox,
    loadMore,
    loadUnreadCount,
    loadAttentionCount,
    archiveConversation,
    bulkMarkRead,
    bulkArchive,
  } = useInboxStore();

  const isFirstTimeUser = !loading && total === 0 && filter === 'all' && !onboardingDismissed;

  const handleOnboardingSend = useCallback(
    async (text: string, fileReferences?: FileReference[]) => {
      localStorage.setItem(ONBOARDING_DISMISSED_KEY, 'true');
      setOnboardingDismissed(true);
      const id = await startNewConversationStream(text, true, fileReferences);
      router.replace(`/inbox/${id}`);
    },
    [startNewConversationStream, router],
  );

  const handleOnboardingSkip = useCallback(() => {
    localStorage.setItem(ONBOARDING_DISMISSED_KEY, 'true');
    setOnboardingDismissed(true);
    router.push('/inbox/new');
  }, [router]);

  // Load inbox when auth or filter/search params change
  useEffect(() => {
    if (isAuthenticated) {
      loadInbox(toApiParams);
      loadUnreadCount();
      loadAttentionCount();
    }
  }, [isAuthenticated, toApiParams, loadInbox, loadUnreadCount, loadAttentionCount]);

  const handleFilterChange = useCallback(
    (f: InboxFilter) => {
      setFilter(f);
    },
    [setFilter]
  );

  const handleSearchChange = useCallback(
    (q: string) => {
      setSearch(q);
    },
    [setSearch]
  );

  const handleSelectConversation = useCallback(
    (conversationId: string) => {
      router.push(`/inbox/${conversationId}`);
    },
    [router]
  );

  const handleLoadMore = useCallback(() => {
    loadMore(toApiParams);
  }, [loadMore, toApiParams]);

  // === Bulk actions ===

  const handleMarkAllRead = useCallback(async () => {
    const unreadIds = items
      .filter((item) => item.read_status === 'unread')
      .map((item) => item.conversation_id);
    if (unreadIds.length === 0) return;
    await bulkMarkRead(unreadIds);
    toast.success('All marked as read');
  }, [items, bulkMarkRead]);

  const handleToggleSelectionMode = useCallback(() => {
    setSelectionMode((prev) => !prev);
    setSelectedIds(new Set());
  }, []);

  const handleToggleSelect = useCallback((conversationId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(conversationId)) {
        next.delete(conversationId);
      } else {
        next.add(conversationId);
      }
      return next;
    });
  }, []);

  const handleArchiveSelected = useCallback(async () => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;
    await bulkArchive(ids);
    setSelectionMode(false);
    setSelectedIds(new Set());
    toast.success(ids.length + ' archived');
  }, [selectedIds, bulkArchive]);

  const handleMarkSelectedRead = useCallback(async () => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;
    await bulkMarkRead(ids);
    setSelectionMode(false);
    setSelectedIds(new Set());
    toast.success(ids.length + ' marked as read');
  }, [selectedIds, bulkMarkRead]);

  const handleRefresh = useCallback(async () => {
    await loadInbox(toApiParams);
    await loadUnreadCount();
    await loadAttentionCount();
  }, [loadInbox, toApiParams, loadUnreadCount, loadAttentionCount]);

  if (isFirstTimeUser) {
    return (
      <WelcomeScreen
        onSendMessage={handleOnboardingSend}
        isStreaming={isStreaming}
        userName={user?.first_name}
        onSkip={handleOnboardingSkip}
      />
    );
  }

  return (
    <div className="px-4 py-6 flex flex-col h-full">
      {/* Filters + search (sticky on scroll) */}
      <div className="sticky top-0 z-10 bg-[var(--background)] -mx-4 px-4 pt-1 pb-2">
      <InboxFilterBar
        activeFilter={filter}
        onFilterChange={handleFilterChange}
        unreadCount={unreadCount}
        attentionCount={attentionCount}
        searchQuery={searchQuery}
        onSearchChange={handleSearchChange}
        onMarkAllRead={handleMarkAllRead}
        selectionMode={selectionMode}
        onToggleSelectionMode={handleToggleSelectionMode}
        selectedCount={selectedIds.size}
        onArchiveSelected={handleArchiveSelected}
        onMarkSelectedRead={handleMarkSelectedRead}
      />
      </div>

      {/* Inbox list with infinite scroll + pull-to-refresh */}
      <PullToRefresh onRefresh={handleRefresh}>
        <div className="flex-1 min-h-0 mt-4">
          <InboxList
            items={items}
            loading={loading}
            loadingMore={loadingMore}
            hasMore={hasMore}
            activeFilter={filter}
            onSelectConversation={handleSelectConversation}
            onArchive={archiveConversation}
            selectable={selectionMode}
            selectedIds={selectedIds}
            onToggleSelect={handleToggleSelect}
          />
          {!loading && hasMore && (
            <LoadMoreTrigger onLoadMore={handleLoadMore} loadingMore={loadingMore} />
          )}
        </div>
      </PullToRefresh>
    </div>
  );
}

export default function InboxPage() {
  return (
    <Suspense>
      <InboxPageInner />
    </Suspense>
  );
}
