'use client';

import { useCallback, useMemo } from 'react';
import { useSearchParams, useRouter, usePathname } from 'next/navigation';
import type { InboxFilter, InboxQueryParams } from '@/types/inbox';

/**
 * URL-driven inbox filter state.
 *
 * Reads `filter` and `q` from the URL search params and provides
 * helpers to update them via `router.push`.
 */
export function useInboxFilters() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const filter: InboxFilter = (searchParams.get('filter') as InboxFilter) || 'all';
  const searchQuery: string = searchParams.get('q') || '';

  const setFilter = useCallback(
    (f: InboxFilter) => {
      const params = new URLSearchParams(searchParams.toString());
      if (f === 'all') {
        params.delete('filter');
      } else {
        params.set('filter', f);
      }
      // Reset to first page on filter change
      params.delete('offset');
      const qs = params.toString();
      router.push(qs ? `${pathname}?${qs}` : pathname);
    },
    [searchParams, router, pathname]
  );

  const setSearch = useCallback(
    (q: string) => {
      const params = new URLSearchParams(searchParams.toString());
      if (q) {
        params.set('q', q);
      } else {
        params.delete('q');
      }
      params.delete('offset');
      const qs = params.toString();
      router.push(qs ? `${pathname}?${qs}` : pathname);
    },
    [searchParams, router, pathname]
  );

  /** Convert current URL state to API query params. */
  const toApiParams = useMemo((): InboxQueryParams => {
    const params: InboxQueryParams = {};

    switch (filter) {
      case 'unread':
        params.read_status = 'unread';
        break;
      case 'attention':
        params.priority = 'attention';
        break;
      case 'archived':
        params.read_status = 'archived';
        break;
      // 'all' sends no filter — backend excludes archived by default
    }

    if (searchQuery) {
      params.q = searchQuery;
    }

    return params;
  }, [filter, searchQuery]);

  return { filter, searchQuery, setFilter, setSearch, toApiParams };
}
