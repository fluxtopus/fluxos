'use client';

import { useRef, useEffect } from 'react';

interface LoadMoreTriggerProps {
  onLoadMore: () => void;
  loadingMore: boolean;
}

/**
 * IntersectionObserver-based trigger that fires `onLoadMore` when the
 * element enters the viewport. Shows a spinner while loading.
 */
export function LoadMoreTrigger({ onLoadMore, loadingMore }: LoadMoreTriggerProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !loadingMore) {
          onLoadMore();
        }
      },
      { rootMargin: '200px' }
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, [onLoadMore, loadingMore]);

  return (
    <div ref={ref} className="flex items-center justify-center py-4">
      {loadingMore && (
        <svg
          className="animate-spin h-5 w-5 text-[var(--muted-foreground)]"
          viewBox="0 0 24 24"
          fill="none"
        >
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="4"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
          />
        </svg>
      )}
    </div>
  );
}
