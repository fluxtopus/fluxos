'use client';

import React, { useState } from 'react';
import { Bars3Icon, XMarkIcon, DocumentTextIcon } from '@heroicons/react/24/outline';
import { useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { ConversationList } from './ConversationList';
import ArrowPanel from './ArrowPanel';
import SpecList from './SpecList';
import { useArrowStore } from '../store/arrowStore';
import { conversationKeys } from '../hooks/useConversations';

const ArrowLayout: React.FC = () => {
  const [isLeftPanelOpen, setIsLeftPanelOpen] = useState(false);
  const [isRightPanelOpen, setIsRightPanelOpen] = useState(false);
  const [sessionKey, setSessionKey] = useState(0);
  const queryClient = useQueryClient();
  const router = useRouter();

  const {
    selectedConversationId,
    setSelectedConversation,
    clearSelection
  } = useArrowStore();

  // Sync URL parameter with Zustand state on mount and URL changes
  React.useEffect(() => {
    const syncUrlToState = () => {
      const params = new URLSearchParams(window.location.search);
      const conversationId = params.get('conversationId');

      if (conversationId && conversationId !== selectedConversationId) {
        setSelectedConversation(conversationId);
      } else if (!conversationId && selectedConversationId) {
        // URL has no conversationId but state has one - clear state
        clearSelection();
      }
    };

    // Sync on mount
    syncUrlToState();

    // Listen for popstate (browser back/forward)
    window.addEventListener('popstate', syncUrlToState);

    return () => window.removeEventListener('popstate', syncUrlToState);
  }, [selectedConversationId, setSelectedConversation, clearSelection]);

  const handleNewConversation = () => {
    // Clear URL parameter
    const url = new URL(window.location.href);
    url.searchParams.delete('conversationId');
    window.history.pushState({}, '', url.toString());

    // Clear state
    clearSelection();

    // Force ArrowPanel remount by changing key
    setSessionKey(prev => prev + 1);

    // Close mobile panels
    setIsLeftPanelOpen(false);
  };

  const handleConversationCreated = () => {
    // Invalidate conversations query to trigger refetch
    queryClient.invalidateQueries({ queryKey: conversationKeys.lists() });
  };

  const handleRunClick = (runId: string) => {
    // Navigate to the workflows page with this run
    router.push(`/workflows?workflowRunId=${runId}`);
  };

  return (
    <div className="h-full flex relative bg-gray-50 dark:bg-gray-900">
      {/* Mobile Menu Buttons */}
      <div className="absolute top-4 left-4 z-30 flex gap-2 md:hidden">
        <button
          onClick={() => setIsLeftPanelOpen(!isLeftPanelOpen)}
          className="p-2 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-md shadow-md"
        >
          {isLeftPanelOpen ? (
            <XMarkIcon className="w-5 h-5 text-gray-700 dark:text-gray-300" />
          ) : (
            <Bars3Icon className="w-5 h-5 text-gray-700 dark:text-gray-300" />
          )}
        </button>
      </div>

      <div className="absolute top-4 right-4 z-30 md:hidden">
        <button
          onClick={() => setIsRightPanelOpen(!isRightPanelOpen)}
          className="p-2 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-md shadow-md"
        >
          {isRightPanelOpen ? (
            <XMarkIcon className="w-5 h-5 text-gray-700 dark:text-gray-300" />
          ) : (
            <DocumentTextIcon className="w-5 h-5 text-gray-700 dark:text-gray-300" />
          )}
        </button>
      </div>

      {/* Left Panel - Conversations */}
      <div
        className={`
          absolute md:relative
          top-0 bottom-0 left-0
          w-64 md:w-60
          transform transition-transform duration-300 ease-in-out
          ${isLeftPanelOpen ? 'translate-x-0' : '-translate-x-full'}
          md:translate-x-0
          z-20
          shadow-lg md:shadow-none
          bg-white dark:bg-gray-800
          border-r border-gray-200 dark:border-gray-700
        `}
      >
        <div className="h-full p-4">
          <ConversationList onNewConversation={handleNewConversation} />
        </div>
      </div>

      {/* Center Panel - Chat */}
      <div className="flex-1 flex flex-col min-w-0">
        <ArrowPanel
          key={sessionKey}
          conversationId={selectedConversationId || undefined}
          onConversationCreated={handleConversationCreated}
        />
      </div>

      {/* Right Panel - Specs */}
      <div
        className={`
          absolute md:relative
          top-0 bottom-0 right-0
          w-80 md:w-96
          transform transition-transform duration-300 ease-in-out
          ${isRightPanelOpen ? 'translate-x-0' : 'translate-x-full'}
          md:translate-x-0
          z-20
          shadow-lg md:shadow-none
          border-l border-gray-200 dark:border-gray-700
        `}
      >
        <SpecList onRunClick={handleRunClick} />
      </div>

      {/* Mobile Overlay */}
      {(isLeftPanelOpen || isRightPanelOpen) && (
        <div
          className="absolute inset-0 bg-black bg-opacity-50 z-10 md:hidden"
          onClick={() => {
            setIsLeftPanelOpen(false);
            setIsRightPanelOpen(false);
          }}
        />
      )}
    </div>
  );
};

export default ArrowLayout;
