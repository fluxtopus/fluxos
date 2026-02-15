'use client';

import { Suspense } from 'react';
import dynamic from 'next/dynamic';

const WebhooksPanel = dynamic(() => import('../../components/WebhooksPanel'), {
  ssr: false,
});

export default function WebhooksPage() {
  return (
    <Suspense fallback={<div className="p-4">Loading…</div>}>
      <WebhooksPanel />
    </Suspense>
  );
}

