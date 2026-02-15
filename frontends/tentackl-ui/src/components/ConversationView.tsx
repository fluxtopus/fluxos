import React, { useEffect, useState } from 'react';
import {
  ChatBubbleLeftIcon,
  ChatBubbleLeftEllipsisIcon,
  CpuChipIcon,
  ClockIcon,
  ExclamationCircleIcon,
  ArrowPathIcon,
  InformationCircleIcon
} from '@heroicons/react/24/outline';

interface Message {
  id: string;
  timestamp: string;
  agent_id: string;
  message_type: string;
  direction: string | null;
  role: string;
  content_text: string;
  content_data: any;
  model?: string;
  temperature?: number;
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  latency_ms?: number;
  error?: string;
}

interface Conversation {
  id: string;
  workflow_id: string;
  agent_id: string;
  start_time: string;
  end_time: string | null;
  status: string;
  messages: Message[];
}

interface ConversationViewProps {
  workflowId: string;
  agentId: string;
}

const messageTypeConfig = {
  llm_prompt: {
    icon: ChatBubbleLeftIcon,
    color: 'text-blue-600 dark:text-blue-400',
    bgColor: 'bg-blue-50 dark:bg-blue-900/30',
    label: 'Prompt'
  },
  llm_response: {
    icon: ChatBubbleLeftEllipsisIcon,
    color: 'text-green-600 dark:text-green-400',
    bgColor: 'bg-green-50 dark:bg-green-900/30',
    label: 'Response'
  },
  state_update: {
    icon: CpuChipIcon,
    color: 'text-purple-600 dark:text-purple-400',
    bgColor: 'bg-purple-50 dark:bg-purple-900/30',
    label: 'State Update'
  },
  error: {
    icon: ExclamationCircleIcon,
    color: 'text-red-600 dark:text-red-400',
    bgColor: 'bg-red-50 dark:bg-red-900/30',
    label: 'Error'
  },
  tool_call: {
    icon: ArrowPathIcon,
    color: 'text-indigo-600 dark:text-indigo-400',
    bgColor: 'bg-indigo-50 dark:bg-indigo-900/30',
    label: 'Tool Call'
  },
  tool_response: {
    icon: ArrowPathIcon,
    color: 'text-indigo-600 dark:text-indigo-400',
    bgColor: 'bg-indigo-50 dark:bg-indigo-900/30',
    label: 'Tool Response'
  },
  inter_agent: {
    icon: CpuChipIcon,
    color: 'text-orange-600 dark:text-orange-400',
    bgColor: 'bg-orange-50 dark:bg-orange-900/30',
    label: 'Inter-Agent'
  }
};

export const ConversationView: React.FC<ConversationViewProps> = ({ workflowId, agentId }) => {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedMessages, setExpandedMessages] = useState<Set<string>>(new Set());

  useEffect(() => {
    fetchConversations();
  }, [workflowId, agentId]);

  const fetchConversations = async () => {
    try {
      setLoading(true);
      
      // Fetch full conversations for the workflow and filter by agent
      const response = await fetch(`/api/workflows/${workflowId}/conversations`);
      
      if (!response.ok) {
        throw new Error(`Failed to fetch conversations: ${response.statusText}`);
      }

      const data = await response.json();
      
      // Filter conversations for this specific agent
      const agentConversations = data.conversations.filter(
        (conv: Conversation) => conv.agent_id === agentId
      );
      
      setConversations(agentConversations);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load conversations');
    } finally {
      setLoading(false);
    }
  };

  const toggleMessageExpansion = (messageId: string) => {
    setExpandedMessages(prev => {
      const newSet = new Set(prev);
      if (newSet.has(messageId)) {
        newSet.delete(messageId);
      } else {
        newSet.add(messageId);
      }
      return newSet;
    });
  };

  const formatTimestamp = (timestamp: string) => {
    return new Date(timestamp).toLocaleTimeString();
  };

  const formatLatency = (ms: number) => {
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(2)}s`;
  };

  const renderMessageContent = (message: Message, expanded: boolean) => {
    const config = messageTypeConfig[message.message_type as keyof typeof messageTypeConfig] || {
      icon: InformationCircleIcon,
      color: 'text-gray-600 dark:text-gray-400',
      bgColor: 'bg-gray-50 dark:bg-gray-700',
      label: message.message_type
    };

    const Icon = config.icon;

    return (
      <div
        className={`p-3 rounded-lg ${config.bgColor} cursor-pointer transition-all border border-gray-200 dark:border-gray-600 hover:border-gray-300 dark:hover:border-gray-500`}
        onClick={() => toggleMessageExpansion(message.id)}
      >
        <div className="flex items-start space-x-3">
          <Icon className={`h-5 w-5 ${config.color} mt-0.5 flex-shrink-0`} />
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between">
              <span className={`text-sm font-medium ${config.color}`}>
                {config.label}
              </span>
              <span className="text-xs text-gray-500 dark:text-gray-400 flex items-center">
                <ClockIcon className="h-3 w-3 mr-1" />
                {formatTimestamp(message.timestamp)}
              </span>
            </div>

            {/* Message preview or full content */}
            <div className="mt-1">
              {message.content_text && (
                <div className={`text-sm text-gray-700 dark:text-gray-300 ${!expanded ? 'line-clamp-2' : ''}`}>
                  {message.content_text}
                </div>
              )}

              {/* Additional metadata */}
              {expanded && (
                <div className="mt-2 space-y-1">
                  {message.model && (
                    <div className="text-xs text-gray-500 dark:text-gray-400">
                      Model: {message.model}
                      {message.temperature !== undefined && ` (temp: ${message.temperature})`}
                    </div>
                  )}

                  {message.latency_ms && (
                    <div className="text-xs text-gray-500 dark:text-gray-400">
                      Latency: {formatLatency(message.latency_ms)}
                    </div>
                  )}

                  {(message.prompt_tokens || message.completion_tokens) && (
                    <div className="text-xs text-gray-500 dark:text-gray-400">
                      Tokens: {message.prompt_tokens || 0} prompt, {message.completion_tokens || 0} completion
                    </div>
                  )}

                  {message.content_data && Object.keys(message.content_data).length > 0 && (
                    <div className="mt-2">
                      <div className="text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Data:</div>
                      <pre className="text-xs bg-gray-100 dark:bg-gray-800 p-2 rounded overflow-x-auto text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-gray-600">
                        {JSON.stringify(message.content_data, null, 2)}
                      </pre>
                    </div>
                  )}

                  {message.error && (
                    <div className="mt-2 text-xs text-red-600 dark:text-red-400">
                      Error: {message.error}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <ArrowPathIcon className="h-5 w-5 text-blue-500 dark:text-blue-400 animate-spin" />
        <span className="ml-2 text-sm text-gray-500 dark:text-gray-400">Loading conversations...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 bg-red-50 dark:bg-red-900/20 rounded-lg border border-red-200 dark:border-red-700">
        <div className="flex items-center">
          <ExclamationCircleIcon className="h-5 w-5 text-red-600 dark:text-red-400" />
          <span className="ml-2 text-sm text-red-800 dark:text-red-300">{error}</span>
        </div>
      </div>
    );
  }

  if (conversations.length === 0) {
    return (
      <div className="text-center py-8">
        <ChatBubbleLeftEllipsisIcon className="h-8 w-8 text-gray-400 dark:text-gray-600 mx-auto mb-2" />
        <p className="text-sm text-gray-500 dark:text-gray-400">No conversations recorded for this agent</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {conversations.map((conversation) => (
        <div key={conversation.id} className="space-y-2">
          <div className="text-xs text-gray-500 dark:text-gray-400 font-medium">
            Conversation {conversation.status}
          </div>
          <div className="space-y-2">
            {conversation.messages.map((message) => (
              <div key={message.id}>
                {renderMessageContent(message, expandedMessages.has(message.id))}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
};