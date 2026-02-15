import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronUpIcon, ChevronDownIcon, ChatBubbleLeftRightIcon } from '@heroicons/react/24/outline';
import { OrchestratorChat } from './OrchestratorChat';

export const CollapsibleOrchestratorChat: React.FC = () => {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {/* Collapsible Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center justify-between px-4 py-2 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
      >
        <div className="flex items-center space-x-2">
          <ChatBubbleLeftRightIcon className="h-4 w-4 text-gray-600 dark:text-gray-400" />
          <span className="text-xs font-medium text-gray-700 dark:text-gray-300">
            Orchestrator Chat
          </span>
        </div>
        {isExpanded ? (
          <ChevronDownIcon className="h-4 w-4 text-gray-600 dark:text-gray-400" />
        ) : (
          <ChevronUpIcon className="h-4 w-4 text-gray-600 dark:text-gray-400" />
        )}
      </button>

      {/* Expandable Content */}
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: 'easeInOut' }}
            className="flex-1 overflow-hidden"
          >
            <div className="h-full">
              <OrchestratorChat />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
