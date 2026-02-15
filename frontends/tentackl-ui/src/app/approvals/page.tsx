'use client';

import { Suspense } from 'react';
import dynamic from 'next/dynamic';

const MessageApprovals = dynamic(() => import('../../components/MessageApprovals'), {
  ssr: false,
});

export default function ApprovalsPage() {
  return (
    <Suspense fallback={<div className="p-4">Loading…</div>}>
      <MessageApprovals />
    </Suspense>
  );
}

