'use client';

import React, { useEffect } from 'react';
import { QueryClientProvider } from '@tanstack/react-query';
import { PostHogProvider } from 'posthog-js/react';
import { Toaster } from 'react-hot-toast';
import { queryClient } from '../lib/queryClient';
import { initPostHog, posthog } from '../lib/posthog';
import { ThemeProvider } from '../components/ThemeProvider';
import { useIsMobile } from '../hooks/useMediaQuery';

export function Providers({ children }: { children: React.ReactNode }) {
  const isMobile = useIsMobile();

  useEffect(() => {
    initPostHog();
  }, []);

  // Register service worker for PWA support
  useEffect(() => {
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw.js').catch(() => {
        // SW registration failed — non-critical
      });
    }
  }, []);

  return (
    <PostHogProvider client={posthog}>
      <QueryClientProvider client={queryClient}>
        <ThemeProvider>
          {children}
          <Toaster
            position={isMobile ? 'top-center' : 'top-right'}
            toastOptions={{ style: { maxWidth: isMobile ? '90vw' : '360px' } }}
          />
        </ThemeProvider>
      </QueryClientProvider>
    </PostHogProvider>
  );
}
