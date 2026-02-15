import { useState, useEffect } from 'react';

/**
 * Returns `true` only after `isLoading` has been continuously `true` for
 * the specified delay (default 500 ms). Resets immediately when `isLoading`
 * becomes `false`.
 *
 * This prevents skeleton flicker on fast loads.
 */
export function useDelayedLoading(isLoading: boolean, delayMs = 500): boolean {
  const [showLoading, setShowLoading] = useState(false);

  useEffect(() => {
    if (!isLoading) {
      setShowLoading(false);
      return;
    }

    const timer = setTimeout(() => setShowLoading(true), delayMs);
    return () => clearTimeout(timer);
  }, [isLoading, delayMs]);

  return showLoading;
}
