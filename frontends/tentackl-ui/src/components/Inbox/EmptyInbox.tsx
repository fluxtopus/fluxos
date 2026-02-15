'use client';

import {
  InboxIcon,
  CheckCircleIcon,
  ArchiveBoxIcon,
  BellAlertIcon,
} from '@heroicons/react/24/outline';
import type { InboxFilter } from '@/types/inbox';

interface EmptyInboxProps {
  filter?: InboxFilter;
}

const emptyStates: Record<
  InboxFilter,
  { icon: typeof InboxIcon; heading: string; subtext: string }
> = {
  unread: {
    icon: CheckCircleIcon,
    heading: 'All caught up',
    subtext: 'No unread messages. New activity will show up here.',
  },
  attention: {
    icon: BellAlertIcon,
    heading: 'Nothing needs attention',
    subtext: 'When a task needs your input, it will appear here.',
  },
  archived: {
    icon: ArchiveBoxIcon,
    heading: 'No archived messages',
    subtext: 'Messages you archive will be stored here.',
  },
  all: {
    icon: InboxIcon,
    heading: 'No messages yet',
    subtext: 'Create a task and Flux will report here.',
  },
};

export function EmptyInbox({ filter = 'all' }: EmptyInboxProps) {
  const state = emptyStates[filter];
  const Icon = state.icon;

  return (
    <div className="flex items-center justify-center py-16">
      <div className="text-center">
        <div className="flex justify-center mb-6">
          <Icon className="h-12 w-12 text-[var(--muted-foreground)]" />
        </div>
        <p className="text-lg font-medium text-[var(--foreground)] mb-1">
          {state.heading}
        </p>
        <p className="text-sm text-[var(--muted-foreground)]">
          {state.subtext}
        </p>
      </div>
    </div>
  );
}
