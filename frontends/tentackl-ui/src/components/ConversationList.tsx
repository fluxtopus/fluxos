import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { PlusIcon, TrashIcon, ChatBubbleLeftRightIcon, ArrowPathIcon } from '@heroicons/react/24/outline';
import { useConversations, useDeleteConversation } from '../hooks/useConversations';
import { useArrowStore } from '../store/arrowStore';
import { format } from 'date-fns';

interface ConversationListProps {
  onNewConversation: () => void;
}

export const ConversationList: React.FC<ConversationListProps> = ({
  onNewConversation,
}) => {
  const { selectedConversationId, setSelectedConversation } = useArrowStore();

  // Use React Query for data fetching
  const { data: conversations = [], isLoading: loading } = useConversations();
  const deleteConversationMutation = useDeleteConversation();

  // Handle conversation click - update URL and state
  const handleConversationClick = (conversationId: string) => {
    // Update URL with conversation parameter
    const url = new URL(window.location.href);
    url.searchParams.set('conversationId', conversationId);
    window.history.pushState({}, '', url.toString());

    // Update Zustand state
    setSelectedConversation(conversationId);
  };

  const handleDeleteConversation = async (conversationId: string, e: React.MouseEvent) => {
    e.stopPropagation();

    if (!window.confirm('Are you sure you want to delete this conversation?')) {
      return;
    }

    try {
      await deleteConversationMutation.mutateAsync(conversationId);

      // If this is the selected conversation, clear selection
      if (selectedConversationId === conversationId) {
        setSelectedConversation(null);
      }
    } catch (error) {
      console.error('Failed to delete conversation:', error);
    }
  };

  const handleNewConversation = () => {
    onNewConversation();
  };

  return (
    <div className="h-full flex flex-col">
      {/* New Conversation Button */}
      <div className="mb-3">
        <button
          onClick={handleNewConversation}
          className="w-full px-3 py-2 bg-green-50 dark:bg-green-900/30 border border-green-500 dark:border-green-500 text-green-700 dark:text-green-400 hover:bg-green-100 dark:hover:bg-green-900/40 flex items-center justify-center gap-2 text-sm font-medium transition-all rounded-md"
        >
          <PlusIcon className="w-4 h-4" />
          New Session
        </button>
      </div>

      {/* Conversations List */}
      <div className="flex-1 overflow-y-auto -mx-4 px-4">
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <ArrowPathIcon className="w-5 h-5 animate-spin text-blue-500 dark:text-blue-400" />
          </div>
        ) : conversations.length === 0 ? (
          <div className="text-center py-8">
            <ChatBubbleLeftRightIcon className="w-12 h-12 mx-auto text-gray-300 dark:text-gray-600 mb-2" />
            <p className="text-sm text-gray-500 dark:text-gray-400">No conversations yet</p>
            <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
              Start a new one above
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            <AnimatePresence>
              {conversations.map((conv) => (
                <motion.div
                  key={conv.id}
                  initial={{ opacity: 0, y: -10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, x: -20 }}
                  onClick={() => handleConversationClick(conv.id)}
                  className={`p-3 cursor-pointer group transition-all border rounded-md ${
                    selectedConversationId === conv.id
                      ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-500 dark:border-blue-500'
                      : 'bg-white dark:bg-gray-700 border-gray-300 dark:border-gray-600 hover:border-blue-400 dark:hover:border-blue-500'
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">
                        {format(new Date(conv.created_at), 'MMM d, yyyy h:mm a')}
                      </p>
                      <p className={`text-sm truncate ${
                        selectedConversationId === conv.id
                          ? 'text-blue-700 dark:text-blue-400 font-medium'
                          : 'text-gray-700 dark:text-gray-300'
                      }`}>
                        {conv.last_message || 'Empty conversation'}
                      </p>
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                        {conv.message_count} {conv.message_count === 1 ? 'message' : 'messages'}
                      </p>
                    </div>
                    <button
                      onClick={(e) => handleDeleteConversation(conv.id, e)}
                      className="opacity-0 group-hover:opacity-100 transition-opacity p-1 border border-red-300 dark:border-red-600 rounded hover:border-red-500 dark:hover:border-red-500"
                      title="Delete conversation"
                    >
                      <TrashIcon className="w-3 h-3 text-red-600 dark:text-red-400" />
                    </button>
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        )}
      </div>
    </div>
  );
};
