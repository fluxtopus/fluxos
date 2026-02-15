'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { PlusIcon } from '@heroicons/react/24/outline';

/** Dispatch this event from anywhere to open the composer. */
export const OPEN_COMPOSER_EVENT = 'inbox:open-composer';

/**
 * Floating action button that navigates to the new conversation page.
 */
export function InlineTaskCreator({ onTaskCreated: _onTaskCreated }: { onTaskCreated?: () => void }) {
  const router = useRouter();

  const goToNew = () => router.push('/inbox/new');

  // Allow other components (e.g. sidebar) to trigger navigation
  useEffect(() => {
    const handler = () => goToNew();
    window.addEventListener(OPEN_COMPOSER_EVENT, handler);
    return () => window.removeEventListener(OPEN_COMPOSER_EVENT, handler);
  });

  return (
    <button
      onClick={goToNew}
      className="fixed bottom-6 right-6 z-50 p-4 rounded-full shadow-lg transition-all duration-200 delegation-cta text-white hover:scale-105"
    >
      <PlusIcon className="h-6 w-6" />
    </button>
  );
}
