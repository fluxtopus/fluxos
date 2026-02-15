import { useState, useEffect } from 'react';

/**
 * SSR-safe media query hook.
 * Returns `false` during server render, syncs via `window.matchMedia` on mount.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false);

  useEffect(() => {
    const mql = window.matchMedia(query);
    setMatches(mql.matches);

    const handler = (e: MediaQueryListEvent) => setMatches(e.matches);
    mql.addEventListener('change', handler);
    return () => mql.removeEventListener('change', handler);
  }, [query]);

  return matches;
}

/**
 * Returns `true` when viewport is below the `lg` breakpoint (1024px).
 * Matches the existing Tailwind `lg:` breakpoint used throughout the app.
 */
export function useIsMobile(): boolean {
  return !useMediaQuery('(min-width: 1024px)');
}
