'use client';

import { use } from 'react';
import { InboxThreadView } from '@/components/Inbox/InboxThreadView';

export default function InboxThreadPage({
  params,
}: {
  params: Promise<{ conversationId: string }>;
}) {
  const { conversationId } = use(params);
  return <InboxThreadView conversationId={conversationId} />;
}
