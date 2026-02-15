'use client';

import type { InboxItem, InboxFilter } from '@/types/inbox';
import { InboxCard } from './InboxCard';
import { EmptyInbox } from './EmptyInbox';
import { useDelayedLoading } from '@/hooks/useDelayedLoading';

// === Skeleton Loader ===

function InboxCardSkeleton() {
  return (
    <div className="flex items-start gap-3 p-3 rounded-lg animate-pulse">
      <div className="mt-1.5 flex-shrink-0">
        <div className="h-2.5 w-2.5 rounded-full bg-[var(--muted)]" />
      </div>
      <div className="flex-1 min-w-0 space-y-2">
        <div className="flex items-start justify-between gap-2">
          <div className="h-4 w-3/4 rounded bg-[var(--muted)]" />
          <div className="h-3 w-12 rounded bg-[var(--muted)] flex-shrink-0" />
        </div>
        <div className="h-3 w-full rounded bg-[var(--muted)]" />
        <div className="h-3 w-2/3 rounded bg-[var(--muted)]" />
        <div className="flex items-center justify-between mt-2">
          <div className="h-5 w-16 rounded bg-[var(--muted)]" />
          <div className="h-3 w-20 rounded bg-[var(--muted)]" />
        </div>
      </div>
    </div>
  );
}

// === Component ===

interface InboxListProps {
  items: InboxItem[];
  loading: boolean;
  loadingMore?: boolean;
  hasMore?: boolean;
  activeFilter?: InboxFilter;
  onSelectConversation: (id: string) => void;
  onArchive?: (conversationId: string) => void;
  selectable?: boolean;
  selectedIds?: Set<string>;
  onToggleSelect?: (conversationId: string) => void;
}

export function InboxList({
  items,
  loading,
  activeFilter,
  onSelectConversation,
  onArchive,
  selectable,
  selectedIds,
  onToggleSelect,
}: InboxListProps) {
  const showSkeleton = useDelayedLoading(loading);

  if (loading && showSkeleton) {
    return (
      <div className="flex flex-col gap-1">
        <InboxCardSkeleton />
        <InboxCardSkeleton />
        <InboxCardSkeleton />
        <InboxCardSkeleton />
      </div>
    );
  }

  if (!loading && items.length === 0) {
    return <EmptyInbox filter={activeFilter} />;
  }

  return (
    <div className="flex flex-col divide-y divide-[var(--border)]">
      {items.map((item) => (
        <InboxCard
          key={item.conversation_id}
          item={item}
          onClick={onSelectConversation}
          onArchive={onArchive}
          selectable={selectable}
          selected={selectedIds ? selectedIds.has(item.conversation_id) : false}
          onToggleSelect={onToggleSelect}
        />
      ))}
    </div>
  );
}
