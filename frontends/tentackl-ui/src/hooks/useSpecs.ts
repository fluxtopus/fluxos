import { useQuery } from '@tanstack/react-query';
import { getConversationSpecs, getSpecRuns, type WorkflowSpec, type WorkflowRun } from '../services/arrow';

// Query keys
export const specKeys = {
  all: ['specs'] as const,
  lists: () => [...specKeys.all, 'list'] as const,
  list: (conversationId: string) => [...specKeys.lists(), conversationId] as const,
  runs: () => [...specKeys.all, 'runs'] as const,
  runsList: (specId: string) => [...specKeys.runs(), specId] as const,
};

// Hook to get specs for a conversation
export function useConversationSpecs(conversationId: string | null | undefined) {
  return useQuery({
    queryKey: specKeys.list(conversationId || ''),
    queryFn: () => getConversationSpecs(conversationId!),
    enabled: !!conversationId, // Only fetch if conversationId is provided
  });
}

// Hook to get runs for a spec
export function useSpecRuns(specId: string | null | undefined) {
  return useQuery({
    queryKey: specKeys.runsList(specId || ''),
    queryFn: () => getSpecRuns(specId!),
    enabled: !!specId, // Only fetch if specId is provided
  });
}
