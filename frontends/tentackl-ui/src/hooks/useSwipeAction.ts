'use client';

import { useState, useRef, useCallback } from 'react';

interface UseSwipeActionOptions {
  /** Minimum horizontal distance to trigger the action (default: 80) */
  threshold?: number;
  /** Maximum reveal distance (default: 120) */
  maxReveal?: number;
  /** Called when swipe past threshold completes */
  onSwipe: () => void;
}

interface UseSwipeActionReturn {
  /** Current horizontal offset in px (negative = swiped left) */
  offsetX: number;
  /** Whether a swipe gesture is currently active */
  isSwiping: boolean;
  /** Touch event handlers to spread onto the swipeable element */
  handlers: {
    onTouchStart: (e: React.TouchEvent) => void;
    onTouchMove: (e: React.TouchEvent) => void;
    onTouchEnd: () => void;
  };
  /** Reset the swipe offset to 0 */
  reset: () => void;
}

export function useSwipeAction({
  threshold = 80,
  maxReveal = 120,
  onSwipe,
}: UseSwipeActionOptions): UseSwipeActionReturn {
  const [offsetX, setOffsetX] = useState(0);
  const touchStartX = useRef(0);
  const touchStartY = useRef(0);
  const swiping = useRef(false);

  const onTouchStart = useCallback((e: React.TouchEvent) => {
    touchStartX.current = e.touches[0].clientX;
    touchStartY.current = e.touches[0].clientY;
    swiping.current = false;
  }, []);

  const onTouchMove = useCallback(
    (e: React.TouchEvent) => {
      const dx = e.touches[0].clientX - touchStartX.current;
      const dy = e.touches[0].clientY - touchStartY.current;

      // Only start horizontal swipe if movement is mostly horizontal
      if (!swiping.current && Math.abs(dx) > 10 && Math.abs(dx) > Math.abs(dy) * 1.5) {
        swiping.current = true;
      }

      if (swiping.current && dx < 0) {
        setOffsetX(Math.max(dx, -maxReveal));
      }
    },
    [maxReveal],
  );

  const onTouchEnd = useCallback(() => {
    if (offsetX < -threshold) {
      setOffsetX(-maxReveal);
      onSwipe();
      setTimeout(() => setOffsetX(0), 300);
    } else {
      setOffsetX(0);
    }
    swiping.current = false;
  }, [offsetX, threshold, maxReveal, onSwipe]);

  const reset = useCallback(() => {
    setOffsetX(0);
    swiping.current = false;
  }, []);

  return {
    offsetX,
    isSwiping: swiping.current,
    handlers: { onTouchStart, onTouchMove, onTouchEnd },
    reset,
  };
}
