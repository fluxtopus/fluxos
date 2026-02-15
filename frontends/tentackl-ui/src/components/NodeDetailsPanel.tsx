import React, { useEffect, useState } from 'react';
import { 
  XMarkIcon,
  ChevronRightIcon,
  ArrowPathIcon,
  ClockIcon,
  CheckCircleIcon,
  XCircleIcon,
  ExclamationTriangleIcon,
  PauseIcon,
  ChatBubbleLeftRightIcon
} from '@heroicons/react/24/outline';
import { Node, NodeStatus } from '../types/workflow';
import { ConversationView } from './ConversationView';
import { useWorkflowStore } from '../store/workflowStore';
import api from '../services/api';
import { sendMessage, rejectMessage } from '../services/messages';

interface NodeDetailsPanelProps {
  node: Node | null;
  isOpen: boolean;
  onClose: () => void;
}

const statusIcons = {
  [NodeStatus.PENDING]: ExclamationTriangleIcon,
  [NodeStatus.RUNNING]: ArrowPathIcon,
  [NodeStatus.COMPLETED]: CheckCircleIcon,
  [NodeStatus.FAILED]: XCircleIcon,
  [NodeStatus.PAUSED]: PauseIcon,
  [NodeStatus.CANCELLED]: XCircleIcon,
};

const statusColors = {
  [NodeStatus.PENDING]: 'text-gray-500 dark:text-gray-400',
  [NodeStatus.RUNNING]: 'text-blue-500 dark:text-blue-400',
  [NodeStatus.COMPLETED]: 'text-green-500 dark:text-green-400',
  [NodeStatus.FAILED]: 'text-red-500 dark:text-red-400',
  [NodeStatus.PAUSED]: 'text-yellow-500 dark:text-yellow-400',
  [NodeStatus.CANCELLED]: 'text-gray-500 dark:text-gray-400',
};

export const NodeDetailsPanel: React.FC<NodeDetailsPanelProps> = ({ node, isOpen, onClose }) => {
  const [nodeInputs, setNodeInputs] = useState<any>(null);
  const [nodeOutputs, setNodeOutputs] = useState<any>(null);
  const [activeTab, setActiveTab] = useState<'details' | 'conversation'>('details');
  const [hasConversations, setHasConversations] = useState(false);
  const { currentWorkflow } = useWorkflowStore();
  const [messagesState, setMessagesState] = useState<{ pending: any[]; sent: any[]; rejected: any[] } | null>(null);
  const [msgLoading, setMsgLoading] = useState(false);
  const [msgError, setMsgError] = useState<string | null>(null);
  const [inputsExpanded, setInputsExpanded] = useState(false);
  const [outputsExpanded, setOutputsExpanded] = useState(false);
  const [metadataExpanded, setMetadataExpanded] = useState(false);

  useEffect(() => {
    if (node) {
      // Extract inputs and outputs from node data
      setNodeInputs(node.data?.metadata?.inputs || {});
      setNodeOutputs(node.data?.result_data || {});
      
      // Check if this is an agent node that might have conversations
      const isAgentNode = node.data?.agent_id || node.id.includes('agent');
      setHasConversations(isAgentNode);
      
      // Reset to details tab when node changes
      setActiveTab('details');
      
      // Reset collapsible sections when node changes
      setInputsExpanded(false);
      setOutputsExpanded(false);
      setMetadataExpanded(false);

      // Load approvals-related messages if this is the approvals node
      if (node.id && node.id.startsWith('approvals-') && currentWorkflow?.id) {
        loadMessages(currentWorkflow.id);
      } else {
        setMessagesState(null);
        setMsgError(null);
      }
    }
  }, [node]);

  const loadMessages = async (workflowId: string) => {
    setMsgLoading(true);
    setMsgError(null);
    try {
      const res = await api.get(`/api/workflows/${workflowId}/state`);
      const messages = res.data?.state_data?.messages || {};
      setMessagesState({
        pending: messages.pending || [],
        sent: messages.sent || [],
        rejected: messages.rejected || [],
      });
    } catch (e: any) {
      setMsgError(e?.response?.data?.detail || e.message);
    } finally {
      setMsgLoading(false);
    }
  };

  const onApprove = async (index: number) => {
    if (!currentWorkflow?.id) return;
    setMsgLoading(true);
    setMsgError(null);
    try {
      await sendMessage(currentWorkflow.id, index);
      await loadMessages(currentWorkflow.id);
    } catch (e: any) {
      setMsgError(e?.response?.data?.detail || e.message);
    } finally {
      setMsgLoading(false);
    }
  };

  const onReject = async (index: number) => {
    if (!currentWorkflow?.id) return;
    setMsgLoading(true);
    setMsgError(null);
    try {
      await rejectMessage(currentWorkflow.id, index, 'Rejected from node panel');
      await loadMessages(currentWorkflow.id);
    } catch (e: any) {
      setMsgError(e?.response?.data?.detail || e.message);
    } finally {
      setMsgLoading(false);
    }
  };

  const formatJson = (data: any): string => {
    if (data === null || data === undefined) return 'None';
    if (typeof data === 'string') {
      // Try to parse if it's a JSON string
      try {
        const parsed = JSON.parse(data);
        return JSON.stringify(parsed, null, 2);
      } catch {
        return data;
      }
    }
    try {
      return JSON.stringify(data, null, 2);
    } catch {
      return String(data);
    }
  };

  const getNodeTypeLabel = (type: string): string => {
    return type.split('_')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  };

  if (!node || !isOpen) return null;

  const StatusIcon = statusIcons[node.status] || ExclamationTriangleIcon;

  return (
    <>
      {/* Overlay */}
      <div
        className={`fixed inset-0 bg-black bg-opacity-30 dark:bg-opacity-60 transition-opacity duration-300 z-40 ${
          isOpen ? 'opacity-100' : 'opacity-0 pointer-events-none'
        }`}
        onClick={onClose}
      />

      {/* Panel */}
      <div
        className={`fixed right-0 top-0 h-full w-[400px] bg-white dark:bg-gray-800 shadow-2xl transform transition-transform duration-300 z-50 ${
          isOpen ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        <div className="h-full flex flex-col">
          {/* Header */}
          <div className="border-b border-gray-200 dark:border-gray-700 px-6 py-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                  {getNodeTypeLabel(node.type)}
                </h2>
                <p className="text-sm text-gray-500 dark:text-gray-400 mt-1 font-mono">ID: {node.id}</p>
              </div>
              <button
                onClick={onClose}
                className="p-2 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
              >
                <XMarkIcon className="h-5 w-5 text-gray-500 dark:text-gray-400" />
              </button>
            </div>
            
            {/* Status */}
            <div className="mt-4 flex items-center space-x-2">
              <StatusIcon className={`h-5 w-5 ${statusColors[node.status]}`} />
              <span className={`text-sm font-medium ${statusColors[node.status]}`}>
                {node.status.charAt(0).toUpperCase() + node.status.slice(1)}
              </span>
              {node.data?.timestamp && (
                <span className="text-xs text-gray-400">
                  <ClockIcon className="inline h-3 w-3 mr-1" />
                  {new Date(node.data.timestamp).toLocaleTimeString()}
                </span>
              )}
            </div>
          </div>
          
          {/* Tab Navigation */}
          {hasConversations && (
            <div className="border-b border-gray-200 dark:border-gray-700">
              <nav className="-mb-px flex space-x-8 px-6" aria-label="Tabs">
                <button
                  onClick={() => setActiveTab('details')}
                  className={`py-2 px-1 border-b-2 font-medium text-sm ${
                    activeTab === 'details'
                      ? 'border-blue-500 dark:border-blue-400 text-blue-600 dark:text-blue-400'
                      : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:border-gray-300 dark:hover:border-gray-600'
                  }`}
                >
                  Details
                </button>
                <button
                  onClick={() => setActiveTab('conversation')}
                  className={`py-2 px-1 border-b-2 font-medium text-sm flex items-center ${
                    activeTab === 'conversation'
                      ? 'border-blue-500 dark:border-blue-400 text-blue-600 dark:text-blue-400'
                      : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:border-gray-300 dark:hover:border-gray-600'
                  }`}
                >
                  <ChatBubbleLeftRightIcon className="h-4 w-4 mr-1" />
                  Conversation
                </button>
              </nav>
            </div>
          )}
          
          {/* Content */}
          <div className="flex-1 overflow-y-auto">
            {activeTab === 'details' ? (
              <>
                {/* Inline Approvals UI for Message Approvals node */}
                {node.id?.startsWith('approvals-') && (
                  <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
                    <h3 className="text-sm font-semibold text-gray-700 dark:text-white mb-3">Message Approvals</h3>
                    {msgError && (
                      <div className="mb-2 bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 p-2 rounded text-xs">{msgError}</div>
                    )}
                    <div className="space-y-3">
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-gray-500 dark:text-gray-400">Pending</span>
                        <button
                          onClick={() => currentWorkflow?.id && loadMessages(currentWorkflow.id)}
                          className="text-xs px-2 py-0.5 rounded bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600"
                        >
                          Refresh
                        </button>
                      </div>
                      {msgLoading ? (
                        <div className="text-xs text-gray-500 dark:text-gray-400">Loading…</div>
                      ) : messagesState && messagesState.pending.length > 0 ? (
                        <div className="space-y-2 max-h-60 overflow-auto">
                          {messagesState.pending.map((m, idx) => {
                            // Safely convert values to strings to prevent React rendering errors
                            const channel = typeof m.channel === 'string' ? m.channel.toUpperCase() : 'SMS';
                            const toName = m.to?.name ? String(m.to.name) : '';
                            const toContact = m.to?.phone ? String(m.to.phone) : (m.to?.email ? String(m.to.email) : '');
                            const content = typeof m.content === 'string' ? m.content : JSON.stringify(m.content, null, 2);

                            return (
                              <div key={idx} className="border border-gray-300 dark:border-gray-600 rounded p-2 text-xs bg-white dark:bg-gray-700">
                                <div className="text-gray-500 dark:text-gray-400">{channel}</div>
                                <div className="text-gray-700 dark:text-gray-300">
                                  To: {toName} {toContact}
                                </div>
                                <pre className="whitespace-pre-wrap text-gray-800 dark:text-gray-200">{content}</pre>
                                <div className="mt-2 flex space-x-2">
                                  <button onClick={() => onApprove(idx)} className="px-2 py-1 rounded bg-green-600 text-white">Approve & Send</button>
                                  <button onClick={() => onReject(idx)} className="px-2 py-1 rounded bg-red-600 text-white">Reject</button>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      ) : (
                        <div className="text-xs text-gray-500 dark:text-gray-400">No pending messages.</div>
                      )}

                      {messagesState && (
                        <div className="grid grid-cols-2 gap-2 mt-2">
                          <div className="bg-gray-50 dark:bg-gray-700 rounded p-2">
                            <div className="text-xs font-semibold text-gray-700 dark:text-green-400">Sent</div>
                            <div className="text-xs text-gray-600 dark:text-gray-400">{messagesState.sent.length}</div>
                          </div>
                          <div className="bg-gray-50 dark:bg-gray-700 rounded p-2">
                            <div className="text-xs font-semibold text-gray-700 dark:text-red-400">Rejected</div>
                            <div className="text-xs text-gray-600 dark:text-gray-400">{messagesState.rejected.length}</div>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}
                {/* Timing Section */}
                {(node.data?.started_at || node.data?.completed_at || node.data?.created_at) && (
                  <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
                    <h3 className="text-sm font-semibold text-gray-700 dark:text-white mb-3 flex items-center">
                      <ClockIcon className="h-4 w-4 mr-1" />
                      Timing
                    </h3>
                    <div className="space-y-2 text-xs text-gray-700 dark:text-gray-300">
                      {node.data?.created_at && (
                        <div className="flex justify-between">
                          <span className="text-gray-500 dark:text-gray-400">Created:</span>
                          <span className="font-mono">{new Date(node.data.created_at).toLocaleString()}</span>
                        </div>
                      )}
                      {node.data?.started_at && (
                        <div className="flex justify-between">
                          <span className="text-gray-500 dark:text-gray-400">Started:</span>
                          <span className="font-mono">{new Date(node.data.started_at).toLocaleString()}</span>
                        </div>
                      )}
                      {node.data?.completed_at && (
                        <div className="flex justify-between">
                          <span className="text-gray-500 dark:text-gray-400">Completed:</span>
                          <span className="font-mono">{new Date(node.data.completed_at).toLocaleString()}</span>
                        </div>
                      )}
                      {node.data?.started_at && node.data?.completed_at && (
                        <div className="flex justify-between border-t border-gray-200 dark:border-gray-700 pt-2 mt-2">
                          <span className="text-gray-500 dark:text-gray-400 font-semibold">Duration:</span>
                          <span className="font-mono font-semibold text-blue-600 dark:text-blue-400">
                            {((new Date(node.data.completed_at).getTime() - new Date(node.data.started_at).getTime()) / 1000).toFixed(2)}s
                          </span>
                        </div>
                      )}
                    </div>
                  </div>
                )}
                {/* Inputs Section */}
                <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
              <button
                onClick={() => setInputsExpanded(!inputsExpanded)}
                className="w-full text-left"
              >
                <h3 className="text-sm font-semibold text-gray-700 dark:text-white mb-3 flex items-center cursor-pointer hover:text-gray-900 dark:hover:text-gray-100">
                  <ChevronRightIcon 
                    className={`h-4 w-4 mr-1 transition-transform duration-200 ${
                      inputsExpanded ? 'rotate-90' : ''
                    }`} 
                  />
                  Inputs
                </h3>
              </button>
              {inputsExpanded && (
                <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-3">
                  <pre className="text-xs text-gray-600 dark:text-gray-300 whitespace-pre-wrap font-mono">
                    {formatJson(nodeInputs)}
                  </pre>
                </div>
              )}
            </div>

            {/* Results Section */}
            <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
              <button
                onClick={() => setOutputsExpanded(!outputsExpanded)}
                className="w-full text-left"
              >
                <h3 className="text-sm font-semibold text-gray-700 dark:text-white mb-3 flex items-center cursor-pointer hover:text-gray-900 dark:hover:text-gray-100">
                  <ChevronRightIcon 
                    className={`h-4 w-4 mr-1 transition-transform duration-200 ${
                      outputsExpanded ? 'rotate-90' : ''
                    }`} 
                  />
                  Results
                </h3>
              </button>
              {outputsExpanded && (
                <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-3">
                  {/* Condition awareness */}
                  {(() => {
                    const out = nodeOutputs || {};
                    const hasCond = out?.when !== undefined || out?.skipped !== undefined || out?.evaluated !== undefined;
                    return hasCond ? (
                      <div className="mb-3 text-xs">
                        <div className="mb-1">
                          <span className="font-semibold text-gray-700 dark:text-white">Condition:</span>
                          <pre className="whitespace-pre-wrap text-gray-700 dark:text-gray-300">{JSON.stringify(out.when || null)}</pre>
                        </div>
                        <div className="flex space-x-4 text-gray-700 dark:text-gray-300">
                          <div>Evaluated: <span className="font-mono">{String(out.evaluated ?? true)}</span></div>
                          <div>Skipped: <span className="font-mono">{String(out.skipped ?? false)}</span></div>
                        </div>
                        <hr className="my-2 border-gray-300 dark:border-gray-600" />
                      </div>
                    ) : null;
                  })()}
                  {node.status === NodeStatus.RUNNING ? (
                    <div className="flex items-center justify-center py-4">
                      <ArrowPathIcon className="h-5 w-5 text-blue-500 dark:text-blue-400 animate-spin mr-2" />
                      <span className="text-sm text-gray-500 dark:text-gray-400">Processing...</span>
                    </div>
                  ) : node.status === NodeStatus.PENDING ? (
                    <div className="text-center py-4">
                      <span className="text-sm text-gray-500 dark:text-gray-400">Waiting to execute</span>
                    </div>
                  ) : (
                    <pre className="text-xs text-gray-600 dark:text-gray-300 whitespace-pre-wrap font-mono">
                      {formatJson(nodeOutputs)}
                    </pre>
                  )}
                </div>
              )}
            </div>

            {/* Metadata Section */}
            {node.data?.metadata && (
              <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
                <button
                  onClick={() => setMetadataExpanded(!metadataExpanded)}
                  className="w-full text-left"
                >
                  <h3 className="text-sm font-semibold text-gray-700 dark:text-white mb-3 flex items-center cursor-pointer hover:text-gray-900 dark:hover:text-gray-100">
                    <ChevronRightIcon 
                      className={`h-4 w-4 mr-1 transition-transform duration-200 ${
                        metadataExpanded ? 'rotate-90' : ''
                      }`} 
                    />
                    Metadata
                  </h3>
                </button>
                {metadataExpanded && (
                  <div className="space-y-3">
                    {Object.entries(node.data?.metadata || {}).map(([key, value]) => (
                      <div key={key} className="border-b border-gray-200 dark:border-gray-700 pb-2 last:border-b-0">
                        <div className="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-1 uppercase tracking-wide">
                          {key}
                        </div>
                        <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-3">
                          <pre className="text-xs text-gray-600 dark:text-gray-300 whitespace-pre-wrap font-mono">
                            {formatJson(value)}
                          </pre>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Error Section */}
            {node.status === NodeStatus.FAILED && (
              <div className="px-6 py-4 border-t border-red-200 dark:border-red-900 bg-red-50/30 dark:bg-red-900/10">
                <div className="flex items-start gap-2 mb-3">
                  <ExclamationTriangleIcon className="h-5 w-5 text-red-600 dark:text-red-400 mt-0.5" />
                  <h3 className="text-sm font-semibold text-red-600 dark:text-red-400">Error Details</h3>
                </div>
                <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-700 rounded-lg p-3">
                  {(() => {
                    // Check multiple possible locations for error data
                    const errorData = 
                      node.data?.error_data || 
                      node.data?.error || 
                      (node as any).error ||
                      node.data?.metadata?.error;
                    
                    if (errorData) {
                      // If error_data is an object with an 'error' key, extract it
                      const errorMessage = typeof errorData === 'object' && errorData !== null
                        ? (errorData.error || errorData.message || errorData)
                        : errorData;
                      
                      return (
                        <pre className="text-xs text-red-700 dark:text-red-400 whitespace-pre-wrap font-mono">
                          {formatJson(errorMessage)}
                        </pre>
                      );
                    }
                    
                    // If no error data found, show a generic message
                    return (
                      <div className="text-xs text-red-700 dark:text-red-400">
                        Node execution failed. No additional error details available.
                      </div>
                    );
                  })()}
                </div>
              </div>
            )}
              </>
            ) : (
              /* Conversation Tab */
              <div className="p-6">
                <ConversationView 
                  workflowId={currentWorkflow?.id || ''} 
                  agentId={node.data?.agent_id || node.id}
                />
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
};
