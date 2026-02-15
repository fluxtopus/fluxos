'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { PaperAirplaneIcon, ChevronDownIcon, ChevronUpIcon, ExclamationTriangleIcon, ArrowPathIcon } from '@heroicons/react/24/outline';
import { motion, AnimatePresence } from 'framer-motion';
import { useRouter } from 'next/navigation';
import { arrowChat, arrowChatStream, getExecutionTrace, getConversation, getConversationSpecs, getSpecRuns, ChatMessage, ChatResponse, ExecutionTrace } from '../services/arrow';
import { format } from 'date-fns';
import WorkflowSummary from './WorkflowSummary';
import WorldStatePanel from './WorldStatePanel';

interface Message {
  id: string;
  role: 'user' | 'assistant' | 'system' | 'workflow';  // 'workflow' is display-only
  content: string;
  timestamp: Date;
  yaml?: string;
  run_id?: string;
  execution_started?: boolean;
  issues?: Array<{ message: string; level?: string }>;
  thinking?: boolean;  // Show thinking indicator
  statusMessage?: string;  // Current status message
}

interface ArrowPanelProps {
  conversationId?: string;
  onConversationCreated?: () => void;
}

const ArrowPanel: React.FC<ArrowPanelProps> = ({ conversationId, onConversationCreated }) => {
  const router = useRouter();
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 'welcome',
      role: 'system',
      content: '👋 Welcome to the Workflow Builder! Describe the workflow you want to create, and I\'ll generate it for you.\n\nExample: "Create a workflow that fetches data from the PokeAPI for Pikachu"',
      timestamp: new Date(),
    }
  ]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [expandedYaml, setExpandedYaml] = useState<string | null>(null);
  const [expandedCodeBlocks, setExpandedCodeBlocks] = useState<Set<string>>(new Set());
  const [expandedStatusPills, setExpandedStatusPills] = useState<Set<string>>(new Set());
  const [executionTraces, setExecutionTraces] = useState<Record<string, ExecutionTrace>>({});
  const [pollingRunIds, setPollingRunIds] = useState<Set<string>>(new Set());
  const [traceErrors, setTraceErrors] = useState<Record<string, string>>({});
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const executionTracesRef = useRef<Record<string, ExecutionTrace>>({});
  const traceRetryCountRef = useRef<Record<string, number>>({});
  const loadingTracesRef = useRef<Set<string>>(new Set());
  const messageIdCounter = useRef<number>(0);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  // Calculate total workflow duration from execution trace
  const calculateWorkflowDuration = (trace: ExecutionTrace): number | null => {
    // Primary: Use duration from aggregated final_result if available
    if (trace.metadata?.final_result?.duration_seconds !== undefined) {
      return trace.metadata.final_result.duration_seconds;
    }

    // Fallback: Calculate from node timestamps
    const completedNodes = trace.nodes.filter(node => node.completed_at && node.started_at);
    if (completedNodes.length === 0) return null;

    // Find earliest start and latest completion
    const startTimes = completedNodes.map(n => new Date(n.started_at!).getTime());
    const endTimes = completedNodes.map(n => new Date(n.completed_at!).getTime());

    const earliestStart = Math.min(...startTimes);
    const latestEnd = Math.max(...endTimes);

    return (latestEnd - earliestStart) / 1000; // Convert to seconds
  };

  // Get the final result from the execution trace
  const getFinalResult = (trace: ExecutionTrace): any => {
    // Primary: Check execution tree metadata for aggregated final_result
    if (trace.metadata?.final_result) {
      return trace.metadata.final_result;
    }

    // Fallback: Try to find the root node's result_data (also contains aggregated result)
    const rootNode = trace.nodes.find(node => node.id === trace.root_node_id);
    if (rootNode && rootNode.result_data) {
      return rootNode.result_data;
    }

    // Last resort: Find the last completed node with result_data
    const completedWithResults = trace.nodes
      .filter(node => node.status === 'completed' && node.result_data)
      .sort((a, b) => {
        const aTime = a.completed_at ? new Date(a.completed_at).getTime() : 0;
        const bTime = b.completed_at ? new Date(b.completed_at).getTime() : 0;
        return bTime - aTime; // Sort descending by completion time
      });

    if (completedWithResults.length > 0) {
      return completedWithResults[0].result_data;
    }

    return null;
  };

  // Toggle status pill dropdown
  const toggleStatusPill = (runId: string) => {
    setExpandedStatusPills(prev => {
      const next = new Set(prev);
      if (next.has(runId)) {
        next.delete(runId);
      } else {
        next.add(runId);
      }
      return next;
    });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const fetchExecutionTrace = useCallback(async (runId: string, silent = false) => {
    // Use ref to check if already loading
    if (loadingTracesRef.current.has(runId)) return;

    // Check if we've already exceeded max retries using ref
    const currentRetries = traceRetryCountRef.current[runId] || 0;
    const MAX_RETRIES = 5;

    if (currentRetries >= MAX_RETRIES) {
      // Stop polling this workflow
      setPollingRunIds(prev => {
        const next = new Set(prev);
        next.delete(runId);
        return next;
      });
      return;
    }

    // Update ref
    loadingTracesRef.current.add(runId);

    try {
      const trace = await getExecutionTrace(runId);
      const previousTrace = executionTracesRef.current[runId];

      // Update refs
      executionTracesRef.current[runId] = trace;
      delete traceRetryCountRef.current[runId];

      // Update state for rendering
      setExecutionTraces(prev => ({ ...prev, [runId]: trace }));
      setTraceErrors(prev => {
        const next = { ...prev };
        delete next[runId];
        return next;
      });

      // Check if workflow is complete
      const isComplete = trace.overall_status === 'completed' || trace.overall_status === 'failed';

      if (isComplete) {
        // Stop polling this workflow
        setPollingRunIds(prev => {
          const next = new Set(prev);
          next.delete(runId);
          return next;
        });
        // Don't add intrusive completion messages - the status badge will show completion
      }

    } catch (error: any) {
      console.error('Failed to fetch execution trace:', error);

      // Increment retry count in ref
      const newRetryCount = currentRetries + 1;
      traceRetryCountRef.current[runId] = newRetryCount;

      // If we've reached max retries, show error and stop polling
      if (newRetryCount >= MAX_RETRIES) {
        const errorMsg = error?.response?.status === 404
          ? 'Workflow execution not found. The workflow may not have started yet or the run ID is invalid.'
          : `Failed to load execution trace: ${error?.message || 'Unknown error'}`;

        setTraceErrors(prev => ({ ...prev, [runId]: errorMsg }));

        // Stop polling this workflow
        setPollingRunIds(prev => {
          const next = new Set(prev);
          next.delete(runId);
          return next;
        });

        // Add error message to chat
        if (!silent) {
          const errorMessage: Message = {
            id: `trace-error-${runId}-${Date.now()}`,
            role: 'system',
            content: `❌ ${errorMsg}\n\nRetried ${MAX_RETRIES} times without success.`,
            timestamp: new Date(),
          };
          setMessages(prev => [...prev, errorMessage]);
        }
      }
    } finally {
      // Clean up ref
      loadingTracesRef.current.delete(runId);
    }
  }, []); // No dependencies!

  const loadConversation = useCallback(async (convId: string) => {
    try {
      const conversation = await getConversation(convId);

      // Convert conversation messages to UI messages (clean, just text)
      const uiMessages: Message[] = [];

      conversation.messages.forEach((msg, idx) => {
        uiMessages.push({
          id: `msg-${convId}-${idx}`,
          role: msg.role as 'user' | 'assistant',
          content: msg.content,
          timestamp: new Date(conversation.created_at),
        });
      });

      // Try to get workflow_runs from conversation response first
      let workflowRuns = (conversation as any).workflow_runs || [];

      // If workflow_runs not in response, fetch them from specs
      if (workflowRuns.length === 0) {
        try {
          const specs = await getConversationSpecs(convId);
          const allRuns: any[] = [];
          
          // Get runs for each spec
          for (const spec of specs) {
            try {
              const runs = await getSpecRuns(spec.id, 50);
              runs.forEach((run) => {
                allRuns.push({
                  run_id: run.run_id,
                  created_at: run.created_at,
                  execution_started: run.status !== 'pending',
                  yaml: null, // YAML not available from runs endpoint
                  issues: [],
                  message_index: uiMessages.length - 1, // Place at end if we don't know the index
                });
              });
            } catch (err) {
              console.error(`Failed to load runs for spec ${spec.id}:`, err);
            }
          }
          
          workflowRuns = allRuns;
        } catch (err) {
          console.error('Failed to fetch workflow runs from specs:', err);
        }
      }

      // Inject workflow display messages after their corresponding assistant messages
      workflowRuns.forEach((run: any, runIdx: number) => {
        // Insert workflow message right after the assistant message
        // If message_index is not available, append at the end
        const insertIndex = run.message_index !== undefined 
          ? run.message_index + 1 + runIdx 
          : uiMessages.length;

        uiMessages.splice(insertIndex, 0, {
          id: `workflow-${convId}-${runIdx}`,
          role: 'workflow',
          content: '', // No text content, this is purely for display
          timestamp: new Date(run.created_at || conversation.created_at),
          yaml: run.yaml,
          run_id: run.run_id,
          execution_started: run.execution_started,
          issues: run.issues,
        });
      });

      setMessages(uiMessages);

      // Fetch execution traces for all workflow runs
      if (workflowRuns.length > 0) {
        // Start fetching traces immediately, no delay needed
        workflowRuns.forEach((run: any) => {
          if (run.run_id) {
            fetchExecutionTrace(run.run_id);
          }
        });
      }
    } catch (error) {
      console.error('Failed to load conversation:', error);
    }
  }, [fetchExecutionTrace]);

  // Load conversation when conversationId changes
  useEffect(() => {
    if (conversationId) {
      loadConversation(conversationId);
    } else {
      // Reset to welcome message when no conversation is selected
      setMessages([
        {
          id: 'welcome',
          role: 'system',
          content: '👋 Welcome to the Workflow Builder! Describe the workflow you want to create, and I\'ll generate it for you.\n\nExample: "Create a workflow that fetches data from the PokeAPI for Pikachu"',
          timestamp: new Date(),
        }
      ]);
      // Clear input field when starting new session
      setInputValue('');
      // Reset all execution-related state
      executionTracesRef.current = {};
      traceRetryCountRef.current = {};
      loadingTracesRef.current = new Set();
      setExecutionTraces({});
      setPollingRunIds(new Set());
      setTraceErrors({});
      setExpandedCodeBlocks(new Set());
      setExpandedStatusPills(new Set());
      setExpandedYaml(null);
      setIsLoading(false);
    }
  }, [conversationId, loadConversation]);

  const sendMessage = async () => {
    if (!inputValue.trim() || isLoading) return;

    // Generate unique IDs using counter
    messageIdCounter.current += 1;
    const userMsgId = `msg-user-${messageIdCounter.current}`;
    messageIdCounter.current += 1;
    const assistantMsgId = `msg-assistant-${messageIdCounter.current}`;

    const userMessage: Message = {
      id: userMsgId,
      role: 'user',
      content: inputValue,
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    const userInput = inputValue;
    setInputValue('');
    setIsLoading(true);

    // Create assistant message immediately with empty content for streaming
    const assistantMessage: Message = {
      id: assistantMsgId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      thinking: true,
      statusMessage: '🤔 Processing your request...',
    };

    setMessages(prev => [...prev, assistantMessage]);

    let fullContent = '';

    try {
      // Stream the response
      await arrowChatStream(
        userInput,
        conversationId,
        // onChunk: append content as it arrives
        (chunk: string) => {
          fullContent += chunk;
          setMessages(prev => prev.map(msg =>
            msg.id === assistantMsgId
              ? { ...msg, content: fullContent, thinking: false, statusMessage: undefined }
              : msg
          ));
        },
        // onError: show error message
        (error: string) => {
          console.error('Streaming error:', error);
          messageIdCounter.current += 1;
          const errorMessage: Message = {
            id: `error-${messageIdCounter.current}`,
            role: 'system',
            content: `❌ Error: ${error}`,
            timestamp: new Date(),
          };
          setMessages(prev => [...prev, errorMessage]);
        },
        // onComplete: conversation is managed server-side
        (newConversationId: string) => {
          // If a new conversation was created (we weren't already in one), navigate to it
          if (!conversationId && newConversationId) {
            // Update URL with new conversation ID
            const url = new URL(window.location.href);
            url.searchParams.set('conversationId', newConversationId);
            window.history.pushState({}, '', url.toString());
          }

          // Notify parent that conversation was created/updated so it can refresh the list
          if (onConversationCreated) {
            onConversationCreated();
          }
        },
        // onWorkflow: handle workflow execution
        (runId: string, executionStarted: boolean) => {
          messageIdCounter.current += 1;
          const workflowMessage: Message = {
            id: `workflow-${messageIdCounter.current}`,
            role: 'workflow',
            content: '',
            timestamp: new Date(),
            run_id: runId,
            execution_started: executionStarted,
          };
          setMessages(prev => [...prev, workflowMessage]);

          // Start polling for execution trace
          setPollingRunIds(prev => new Set(prev).add(runId));

          // Fetch initial trace after a short delay
          setTimeout(() => {
            fetchExecutionTrace(runId);
          }, 1000);
        },
        // onStatus: handle status updates (thinking, tool execution, etc.)
        (status: string, statusMsg: string) => {
          setMessages(prev => prev.map(msg => {
            if (msg.id !== assistantMsgId) return msg;
            
            // Only show thinking if there's no content yet or if we're in a thinking status
            const hasContent = msg.content.trim().length > 0;
            const isThinking = !hasContent && (status === 'thinking' || status === 'tool_execution' || status === 'responding');
            
            return {
              ...msg,
              thinking: isThinking,
              statusMessage: statusMsg || (isThinking ? msg.statusMessage : undefined),
            };
          }));
        }
      );

    } catch (error: any) {
      console.error('Failed to send message:', error);
      const errorMessage: Message = {
        id: `error-${Date.now()}`,
        role: 'system',
        content: `❌ Error: ${error?.message || 'Failed to generate workflow'}`,
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  // Poll for execution updates
  useEffect(() => {
    if (pollingRunIds.size === 0) return;

    const interval = setInterval(() => {
      pollingRunIds.forEach((runId) => {
        fetchExecutionTrace(runId, true);
      });
    }, 3000); // Poll every 3 seconds

    return () => clearInterval(interval);
  }, [pollingRunIds, fetchExecutionTrace]);

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const loadExample = () => {
    setInputValue('Create a workflow that fetches data from the PokeAPI for Pikachu using the HTTP plugin');
  };

  // Parse markdown code blocks in message content
  const parseMessageContent = (content: string, messageId: string) => {
    const codeBlockRegex = /```(\w+)?\n([\s\S]*?)```/g;
    const parts: Array<{ type: 'text' | 'code'; content: string; language?: string; id: string }> = [];
    let lastIndex = 0;
    let match;
    let blockIndex = 0;

    while ((match = codeBlockRegex.exec(content)) !== null) {
      // Add text before code block
      if (match.index > lastIndex) {
        parts.push({
          type: 'text',
          content: content.substring(lastIndex, match.index),
          id: `${messageId}-text-${blockIndex}`,
        });
      }

      // Add code block
      parts.push({
        type: 'code',
        content: match[2].trim(),
        language: match[1] || 'text',
        id: `${messageId}-code-${blockIndex}`,
      });

      lastIndex = match.index + match[0].length;
      blockIndex++;
    }

    // Add remaining text
    if (lastIndex < content.length) {
      parts.push({
        type: 'text',
        content: content.substring(lastIndex),
        id: `${messageId}-text-${blockIndex}`,
      });
    }

    return parts.length > 0 ? parts : [{ type: 'text' as const, content, id: `${messageId}-text-0` }];
  };

  const toggleCodeBlock = (blockId: string) => {
    setExpandedCodeBlocks(prev => {
      const next = new Set(prev);
      if (next.has(blockId)) {
        next.delete(blockId);
      } else {
        next.add(blockId);
      }
      return next;
    });
  };

  return (
    <div className="h-full flex flex-col bg-white dark:bg-gray-900">
      {/* Header */}
      <div className="p-4 border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              Flux Workflow Builder
            </h3>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Describe your workflow in natural language
            </p>
          </div>
          <button
            onClick={loadExample}
            className="px-3 py-1.5 bg-purple-50 dark:bg-purple-900/30 border border-purple-500 dark:border-purple-500 text-purple-700 dark:text-purple-400 hover:bg-purple-100 dark:hover:bg-purple-900/40 text-sm rounded-md transition-all"
          >
            Try Example
          </button>
        </div>
      </div>

      {/* Workflow Summary - shown when conversation is loaded */}
      {conversationId && (
        <WorkflowSummary
          conversationId={conversationId}
          onRunClick={(runId) => {
            router.push(`/workflows?workflowRunId=${runId}`);
          }}
        />
      )}

      {/* World State - shows active tasks and pending checkpoints */}
      <WorldStatePanel
        onTaskClick={(taskId) => router.push(`/tasks?id=${taskId}`)}
      />

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        <AnimatePresence>
          {messages.map((message) => (
            <motion.div
              key={message.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className={`flex ${message.role === 'user' ? 'justify-end' : message.role === 'workflow' ? 'justify-start' : 'justify-start'}`}
            >
              <div className={`max-w-3xl ${message.role === 'user' ? 'w-auto' : 'w-full'}`}>
                {/* Workflow message header - always visible */}
                {message.role === 'workflow' && (
                  <div className="mb-2 p-3 bg-gradient-to-r from-purple-50 to-blue-50 dark:from-purple-900/30 dark:to-blue-900/30 border border-purple-300 dark:border-purple-700 rounded-lg">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="text-lg">⚙️</span>
                        <div>
                          <div className="font-semibold text-gray-900 dark:text-white text-sm">
                            {message.execution_started ? 'Workflow Executed' : 'Workflow Created'}
                          </div>
                          {message.run_id && (
                            <div className="text-xs text-gray-600 dark:text-gray-400 font-mono mt-0.5">
                              Run ID: {message.run_id.substring(0, 8)}...
                            </div>
                          )}
                        </div>
                      </div>
                      {message.run_id && (
                        <button
                          onClick={() => {
                            router.push(`/workflows?workflowRunId=${message.run_id}`);
                          }}
                          className="text-xs px-2 py-1 bg-blue-100 dark:bg-blue-900/50 text-blue-700 dark:text-blue-300 hover:bg-blue-200 dark:hover:bg-blue-900/70 rounded transition-colors"
                        >
                          View Details
                        </button>
                      )}
                    </div>
                  </div>
                )}

                {/* Only show text bubble for non-workflow messages */}
                {message.role !== 'workflow' && (
                  <div
                    className={`${
                      message.role === 'user'
                        ? 'bg-blue-50 dark:bg-blue-900/30 border border-blue-300 dark:border-blue-600 p-4 text-gray-900 dark:text-white rounded-lg'
                        : message.role === 'assistant'
                        ? 'bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-700 text-gray-900 dark:text-gray-200 p-4 rounded-lg'
                        : 'bg-yellow-50 dark:bg-yellow-900/30 text-yellow-900 dark:text-yellow-200 border border-yellow-300 dark:border-yellow-700 px-3 py-1.5 text-sm rounded-md'
                    }`}
                  >
                    {/* Thinking indicator */}
                    {message.thinking && message.statusMessage && (
                      <div className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400 mb-2 pb-2 border-b border-gray-200 dark:border-gray-700">
                        <ArrowPathIcon className="w-4 h-4 animate-spin" />
                        <span>{message.statusMessage}</span>
                      </div>
                    )}
                    <div>
                      {parseMessageContent(message.content, message.id).map((part) => {
                      if (part.type === 'text') {
                        return (
                          <div key={part.id} className="whitespace-pre-wrap">
                            {part.content}
                          </div>
                        );
                      } else {
                        const isExpanded = expandedCodeBlocks.has(part.id);
                        const lines = part.content.split('\n');
                        const preview = lines.slice(0, 3).join('\n');
                        const isTruncated = lines.length > 3;

                        return (
                          <div key={part.id} className="my-2 border border-gray-300 dark:border-gray-600 rounded-md overflow-hidden">
                            <button
                              onClick={() => toggleCodeBlock(part.id)}
                              className="w-full px-3 py-2 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 flex items-center justify-between text-xs font-medium text-gray-900 dark:text-white transition-all"
                            >
                              <span>
                                {part.language === 'yaml' && '📄 '}
                                {part.language === 'json' && '📋 '}
                                {part.language === 'python' && '🐍 '}
                                {part.language === 'javascript' && '⚡ '}
                                {part.language?.toUpperCase() || 'CODE'}
                                {isTruncated && !isExpanded && ` (${lines.length} lines)`}
                              </span>
                              {isTruncated && (
                                isExpanded ? (
                                  <ChevronUpIcon className="w-4 h-4" />
                                ) : (
                                  <ChevronDownIcon className="w-4 h-4" />
                                )
                              )}
                            </button>
                            <pre className="p-3 bg-white dark:bg-gray-900 text-green-700 dark:text-green-400 text-xs overflow-x-auto border-t border-gray-200 dark:border-gray-700">
                              {isExpanded || !isTruncated ? part.content : preview}
                              {!isExpanded && isTruncated && (
                                <div className="text-gray-500 dark:text-gray-500 italic mt-2">
                                  ... ({lines.length - 3} more lines)
                                </div>
                              )}
                            </pre>
                          </div>
                        );
                      }
                    })}
                  </div>
                  <p className="text-xs opacity-70 mt-2">
                    {format(message.timestamp, 'HH:mm:ss')}
                  </p>
                </div>
                )}

                {/* YAML Preview - shown for both assistant and workflow messages */}
                {message.yaml && (
                  <div className={`${message.role === 'workflow' ? 'mt-0' : 'mt-2'} border border-purple-300 dark:border-purple-700 rounded-md overflow-hidden`}>
                    <button
                      onClick={() => setExpandedYaml(expandedYaml === message.id ? null : message.id)}
                      className="w-full px-4 py-2 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 flex items-center justify-between text-sm font-medium text-purple-700 dark:text-purple-400 transition-all"
                    >
                      <span>📄 Generated Workflow (YAML)</span>
                      {expandedYaml === message.id ? (
                        <ChevronUpIcon className="w-4 h-4" />
                      ) : (
                        <ChevronDownIcon className="w-4 h-4" />
                      )}
                    </button>
                    {expandedYaml === message.id && (
                      <pre className="p-4 bg-white dark:bg-gray-900 text-green-700 dark:text-green-400 text-xs overflow-x-auto border-t border-purple-200 dark:border-purple-800">
                        {message.yaml}
                      </pre>
                    )}
                  </div>
                )}

                {/* Issues */}
                {message.issues && message.issues.length > 0 && (
                  <div className="mt-2 space-y-1">
                    {message.issues.map((issue, idx) => (
                      <div
                        key={idx}
                        className="inline-flex items-start gap-1.5 text-xs px-2 py-1 rounded bg-yellow-50 dark:bg-yellow-900/20 text-yellow-800 dark:text-yellow-200 border border-yellow-200 dark:border-yellow-800"
                      >
                        <ExclamationTriangleIcon className="w-3 h-3 mt-0.5 flex-shrink-0" />
                        <span>{issue.message}</span>
                      </div>
                    ))}
                  </div>
                )}

                {/* Execution Trace - Compact View */}
                {message.run_id && executionTraces[message.run_id] && (
                  <div className={`${message.role === 'workflow' ? 'mt-2' : 'mt-2'}`}>
                    <div
                      onClick={() => toggleStatusPill(message.run_id!)}
                      className="inline-flex items-center gap-2 text-xs bg-gray-100 dark:bg-gray-800 border border-blue-300 dark:border-blue-700 px-3 py-2 rounded-md hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors cursor-pointer"
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          toggleStatusPill(message.run_id!);
                        }
                      }}
                    >
                      {(() => {
                        const trace = executionTraces[message.run_id!];
                        const status = trace.overall_status;
                        const progress = (trace.summary.completed / trace.summary.total_nodes) * 100;
                        const isExpanded = expandedStatusPills.has(message.run_id!);

                        let statusIcon = '⏸️';
                        let statusColor = 'text-gray-400';

                        if (status === 'completed') {
                          statusIcon = '✅';
                          statusColor = 'text-green-600 dark:text-green-400';
                        } else if (status === 'failed') {
                          statusIcon = '❌';
                          statusColor = 'text-red-600 dark:text-red-400';
                        } else if (status === 'running') {
                          statusIcon = '🔄';
                          statusColor = 'text-blue-600 dark:text-blue-400';
                        } else if (status === 'pending') {
                          statusIcon = '⏳';
                          statusColor = 'text-yellow-600 dark:text-yellow-400';
                        }

                        return (
                          <>
                            <span className={statusColor}>{statusIcon}</span>
                            <span className="text-blue-600 dark:text-blue-400 font-medium">
                              {trace.summary.completed}/{trace.summary.total_nodes}
                            </span>
                            <div className="w-20 bg-gray-200 dark:bg-gray-700 rounded h-1.5">
                              <div
                                className={`h-1.5 rounded transition-all duration-500 ${
                                  status === 'completed' ? 'bg-green-500' :
                                  status === 'failed' ? 'bg-red-500' :
                                  'bg-blue-500'
                                }`}
                                style={{
                                  width: `${progress}%`,
                                }}
                              />
                            </div>
                            {pollingRunIds.has(message.run_id!) && (
                              <div className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-pulse" />
                            )}
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                router.push(`/workflows?workflowRunId=${message.run_id}`);
                              }}
                              className="ml-1 text-blue-600 dark:text-blue-400 hover:text-green-600 dark:hover:text-green-400 transition-colors"
                            >
                              View
                            </button>
                            {isExpanded ? (
                              <ChevronUpIcon className="w-4 h-4 text-gray-500" />
                            ) : (
                              <ChevronDownIcon className="w-4 h-4 text-gray-500" />
                            )}
                          </>
                        );
                      })()}
                    </div>

                    {/* Dropdown panel with result and duration */}
                    {expandedStatusPills.has(message.run_id!) && (() => {
                      const trace = executionTraces[message.run_id!];
                      const duration = calculateWorkflowDuration(trace);
                      const result = getFinalResult(trace);

                      return (
                        <motion.div
                          initial={{ opacity: 0, height: 0 }}
                          animate={{ opacity: 1, height: 'auto' }}
                          exit={{ opacity: 0, height: 0 }}
                          className="mt-2 border border-gray-300 dark:border-gray-600 rounded-lg overflow-hidden bg-white dark:bg-gray-800"
                        >
                          <div className="p-3 space-y-3">
                            {/* Duration */}
                            {duration !== null && (
                              <div>
                                <div className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1">
                                  Total Duration
                                </div>
                                <div className="text-sm text-gray-900 dark:text-white">
                                  {duration < 60
                                    ? `${duration.toFixed(2)}s`
                                    : `${Math.floor(duration / 60)}m ${(duration % 60).toFixed(0)}s`
                                  }
                                </div>
                              </div>
                            )}

                            {/* Result */}
                            {result && (
                              <div>
                                <div className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-1">
                                  Workflow Result
                                </div>
                                <div className="max-h-64 overflow-auto">
                                  <pre className="text-xs bg-gray-50 dark:bg-gray-900 p-2 rounded border border-gray-200 dark:border-gray-700 text-gray-900 dark:text-gray-100">
                                    {typeof result === 'string'
                                      ? result
                                      : JSON.stringify(result, null, 2)
                                    }
                                  </pre>
                                </div>
                              </div>
                            )}

                            {/* No result message */}
                            {!result && (
                              <div className="text-xs text-gray-500 dark:text-gray-400 italic">
                                No result data available
                              </div>
                            )}
                          </div>
                        </motion.div>
                      );
                    })()}

                    {/* Error messages for failed workflows */}
                    {(() => {
                      const trace = executionTraces[message.run_id!];
                      if (trace.overall_status === 'failed') {
                        const failedNodes = trace.nodes.filter(node => node.status === 'failed' && node.error);
                        if (failedNodes.length > 0) {
                          return (
                            <div className="mt-2 space-y-1">
                              {failedNodes.map((node, idx) => {
                                // Safely convert error to string to prevent React rendering errors
                                const errorText = typeof node.error === 'string'
                                  ? node.error
                                  : JSON.stringify(node.error, null, 2);

                                return (
                                  <div
                                    key={idx}
                                    className="flex items-start gap-2 text-xs px-3 py-2 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-800 dark:text-red-200 border border-red-200 dark:border-red-800"
                                  >
                                    <ExclamationTriangleIcon className="w-4 h-4 mt-0.5 flex-shrink-0" />
                                    <div className="flex-1">
                                      <div className="font-semibold">{node.name}</div>
                                      <pre className="mt-0.5 text-red-700 dark:text-red-300 whitespace-pre-wrap font-sans">
                                        {errorText}
                                      </pre>
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          );
                        }
                      }
                      return null;
                    })()}
                  </div>
                )}

                {/* Loading trace indicator */}
                {message.run_id && !executionTraces[message.run_id] && !traceErrors[message.run_id] && (
                  <div className={`${message.role === 'workflow' ? 'mt-2' : 'mt-2'} inline-flex items-center gap-2 text-xs text-gray-600 dark:text-gray-400 bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700 rounded-lg px-3 py-2`}>
                    <ArrowPathIcon className="w-3 h-3 animate-spin" />
                    <span>Loading execution status...</span>
                  </div>
                )}

                {/* Error loading trace */}
                {message.run_id && traceErrors[message.run_id] && (
                  <div className={`${message.role === 'workflow' ? 'mt-2' : 'mt-2'} inline-flex items-center gap-2 text-xs text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-700 rounded-lg px-3 py-2`}>
                    <ExclamationTriangleIcon className="w-3 h-3 flex-shrink-0" />
                    <span>Failed to load execution trace</span>
                  </div>
                )}

                {/* Workflow message timestamp */}
                {message.role === 'workflow' && (
                  <p className="text-xs opacity-70 mt-2">
                    {format(message.timestamp, 'HH:mm:ss')}
                  </p>
                )}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-4 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800">
        <div className="flex space-x-2">
          <textarea
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Describe your workflow..."
            rows={2}
            className="flex-1 px-4 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:border-blue-500 dark:focus:border-blue-400 resize-none rounded-md transition-all"
            disabled={isLoading}
          />
          <button
            onClick={sendMessage}
            disabled={isLoading || !inputValue.trim()}
            className={`px-4 py-2 transition-all flex items-center gap-2 rounded-md ${
              isLoading || !inputValue.trim()
                ? 'bg-gray-100 dark:bg-gray-700 border border-gray-400 dark:border-gray-600 text-gray-400 dark:text-gray-500 cursor-not-allowed'
                : 'bg-green-50 dark:bg-green-900/30 border border-green-500 dark:border-green-500 text-green-700 dark:text-green-400 hover:bg-green-100 dark:hover:bg-green-900/40'
            }`}
          >
            {isLoading ? (
              <>
                <ArrowPathIcon className="w-5 h-5 animate-spin" />
                <span>Gen...</span>
              </>
            ) : (
              <>
                <PaperAirplaneIcon className="w-5 h-5" />
                <span>Send</span>
              </>
            )}
          </button>
        </div>
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
          Press Enter to send • Workflows auto-execute after generation
        </p>
      </div>
    </div>
  );
};

export default ArrowPanel;
