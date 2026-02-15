import { QueryClient } from '@tanstack/react-query';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30000, // 30 seconds - data considered fresh for 30s
      gcTime: 5 * 60 * 1000, // 5 minutes - cache garbage collection time
      refetchOnWindowFocus: false, // Don't auto-refetch on window focus
      retry: 1, // Retry failed requests once
    },
  },
});
