import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { listConversations, getConversation, deleteConversation } from '../services/arrow';

// Query keys
export const conversationKeys = {
  all: ['conversations'] as const,
  lists: () => [...conversationKeys.all, 'list'] as const,
  list: () => [...conversationKeys.lists()] as const,
  details: () => [...conversationKeys.all, 'detail'] as const,
  detail: (id: string) => [...conversationKeys.details(), id] as const,
};

// Hook to get all conversations
export function useConversations() {
  return useQuery({
    queryKey: conversationKeys.list(),
    queryFn: listConversations,
  });
}

// Hook to get a single conversation
export function useConversation(conversationId: string | null | undefined) {
  return useQuery({
    queryKey: conversationKeys.detail(conversationId || ''),
    queryFn: () => getConversation(conversationId!),
    enabled: !!conversationId, // Only fetch if conversationId is provided
  });
}

// Hook to delete a conversation
export function useDeleteConversation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: deleteConversation,
    onSuccess: () => {
      // Invalidate and refetch conversations list
      queryClient.invalidateQueries({ queryKey: conversationKeys.lists() });
    },
  });
}
