import React, { useState, useRef, useEffect } from 'react';
import { PaperAirplaneIcon, ArrowPathIcon } from '@heroicons/react/24/outline';
import { motion, AnimatePresence } from 'framer-motion';
import api from '../services/api';
import { useWorkflowStore } from '../store/workflowStore';
import { format } from 'date-fns';

interface Message {
  id: string;
  type: 'user' | 'orchestrator' | 'system';
  content: string;
  timestamp: Date;
  sender?: string;
}

export const OrchestratorChat: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [workflowState, setWorkflowState] = useState<any | null>(null);
  const [showStateData, setShowStateData] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const receivedResponseKeysRef = useRef<Set<string>>(new Set());
  const { currentWorkflow } = useWorkflowStore();

  // Auto-scroll to bottom when new messages arrive
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Load conversation history when workflow changes
  useEffect(() => {
    if (currentWorkflow?.id) {
      loadConversationHistory(currentWorkflow.id);
      loadWorkflowState(currentWorkflow.id);
    }
  }, [currentWorkflow]);

  const loadConversationHistory = async (workflowId: string) => {
    setIsLoadingHistory(true);
    try {
      const response = await api.get(`/api/event-bus/orchestrator/${workflowId}/conversations`);
      
      if (response.data.messages && response.data.messages.length > 0) {
        // Convert API messages to chat format
        const historicalMessages: Message[] = response.data.messages.map((msg: any) => ({
          id: msg.id,
          type: msg.type as 'user' | 'orchestrator',
          content: msg.content,
          timestamp: new Date(msg.timestamp),
          sender: msg.type === 'user' ? 'You' : 'Orchestrator'
        }));
        
        // Add a divider to show where history ends
        const dividerMessage: Message = {
          id: 'history-divider',
          type: 'system',
          content: '--- Previous conversation history ---',
          timestamp: new Date()
        };
        
        setMessages([...historicalMessages, dividerMessage]);
      } else {
        // No history, show welcome message
        const workflowName = currentWorkflow?.name || 'the workflow';
        setMessages([{
          id: 'welcome',
          type: 'system',
          content: `Connected to orchestrator for ${workflowName}. Try sending a message!`,
          timestamp: new Date()
        }]);
      }
    } catch (error) {
      console.error('Failed to load conversation history:', error);
      // Show welcome message on error
      const workflowName = currentWorkflow?.name || 'the workflow';
      setMessages([{
        id: 'welcome',
        type: 'system',
        content: `Connected to orchestrator for ${workflowName}. Try sending a message!`,
        timestamp: new Date()
      }]);
    } finally {
      setIsLoadingHistory(false);
    }
  };

  const loadWorkflowState = async (workflowId: string) => {
    try {
      const res = await api.get(`/api/workflows/${workflowId}/state`);
      setWorkflowState(res.data);
    } catch (e) {
      console.error('Failed to load workflow state', e);
      setWorkflowState(null);
    }
  };

  // Connect to WebSocket for orchestrator responses
  useEffect(() => {
    if (!currentWorkflow?.id) return;

    // Connect to the workflow WebSocket to receive orchestrator responses
    // Prefer explicit API WS host if provided to avoid proxy issues in dev
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const explicitWsHost = (process.env.REACT_APP_WS_URL || '').replace(/^https?:\/\//, '');
    const wsBase = explicitWsHost
      ? `${wsProtocol}//${explicitWsHost}`
      : `${wsProtocol}//${window.location.host}`;
    const wsUrl = `${wsBase}/ws/workflow/${currentWorkflow.id}`;
    
    let pingInterval: NodeJS.Timeout;
    
    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('Connected to workflow WebSocket for orchestrator messages');
        
        // Send ping every 30 seconds to keep connection alive
        pingInterval = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }));
          }
        }, 30000);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          console.log('WebSocket message received:', data);
          
          // Handle pong response
          if (data.type === 'pong') {
            console.log('Received pong from server');
            return;
          }
          
          // Handle orchestrator response events
          if (data.type === 'orchestrator_response') {
            const responseData = data.data;
            const key =
              responseData.id ||
              responseData.message_id ||
              `${responseData.message}|${responseData.timestamp || ''}|${responseData.original_message || ''}`;

            // Deduplicate identical responses (common in dev StrictMode or multi-subscribers)
            if (receivedResponseKeysRef.current.has(key)) {
              return;
            }
            // Bound the set size to avoid unbounded growth
            if (receivedResponseKeysRef.current.size > 200) {
              receivedResponseKeysRef.current.clear();
            }
            receivedResponseKeysRef.current.add(key);

            const orchestratorMessage: Message = {
              id: `orchestrator-${Date.now()}`,
              type: 'orchestrator',
              content: responseData.message,
              timestamp: new Date(),
              sender: 'Orchestrator'
            };
            setMessages(prev => prev.filter(m => m.content !== 'Message sent to orchestrator. Waiting for response...')
              .concat(orchestratorMessage));
          }
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error);
        }
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
      };

      ws.onclose = () => {
        console.log('Disconnected from workflow WebSocket');
      };

    } catch (error) {
      console.error('Failed to connect to WebSocket:', error);
    }

    // Cleanup on unmount
    return () => {
      if (pingInterval) {
        clearInterval(pingInterval);
      }
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.close();
      }
      // Clear dedupe cache on disconnect so new conversations work cleanly
      receivedResponseKeysRef.current.clear();
    };
  }, [currentWorkflow?.id]);

  const sendMessage = async () => {
    if (!inputValue.trim() || !currentWorkflow?.id) return;

    const userMessage: Message = {
      id: `msg-${Date.now()}`,
      type: 'user',
      content: inputValue,
      timestamp: new Date(),
      sender: 'You'
    };

    setMessages(prev => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);

    try {
      const response = await api.post(`/api/event-bus/orchestrator/${currentWorkflow.id}/message`, {
        message: inputValue,
        sender_id: 'web_user',
        metadata: {
          timestamp: new Date().toISOString()
        }
      });

      if (response.data.success) {
        // Add acknowledgment
        const ackMessage: Message = {
          id: `ack-${Date.now()}`,
          type: 'system',
          content: 'Message sent to orchestrator. Waiting for response...',
          timestamp: new Date()
        };
        setMessages(prev => [...prev, ackMessage]);
      }
    } catch (error) {
      console.error('Failed to send message:', error);
      const errorMessage: Message = {
        id: `error-${Date.now()}`,
        type: 'system',
        content: 'Failed to send message. Please try again.',
        timestamp: new Date()
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="flex flex-col h-full bg-white dark:bg-gray-800 rounded-lg shadow-lg">
      <div className="p-4 border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              Orchestrator Chat
            </h3>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Send messages to the workflow orchestrator
            </p>
          </div>
          <button
            onClick={() => currentWorkflow?.id && loadConversationHistory(currentWorkflow.id)}
            disabled={!currentWorkflow || isLoadingHistory}
            className={`p-2 rounded-lg transition-colors ${
              isLoadingHistory || !currentWorkflow
                ? 'bg-gray-100 dark:bg-gray-700 text-gray-400 cursor-not-allowed'
                : 'bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-600 dark:text-gray-300'
            }`}
            title="Refresh conversation history"
          >
            <ArrowPathIcon className={`w-5 h-5 ${isLoadingHistory ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {workflowState && (
          <div className="mb-3 p-3 rounded bg-blue-50 dark:bg-blue-900/20 text-sm text-blue-900 dark:text-blue-100 border border-blue-200 dark:border-blue-800">
            <div className="flex items-center justify-between mb-1">
              <span className="font-semibold">Workflow State</span>
              <button
                onClick={() => currentWorkflow?.id && loadWorkflowState(currentWorkflow.id)}
                className="text-xs px-2 py-0.5 rounded bg-blue-100 dark:bg-blue-800 hover:bg-blue-200 dark:hover:bg-blue-700"
              >
                Refresh
              </button>
            </div>
            <div className="mb-2 grid grid-cols-1 md:grid-cols-2 gap-2 text-xs text-blue-900 dark:text-blue-100">
              <div>
                <span className="font-semibold">Status:</span> {workflowState.status}
              </div>
              {workflowState.waiting_for && (
                <div>
                  <span className="font-semibold">Waiting For:</span> {workflowState.waiting_for?.signal_type}
                </div>
              )}
            </div>
            {workflowState.waiting_for && (
              <div className="mb-2 text-xs">
                <span className="font-semibold">Waiting Config:</span>
                <pre className="whitespace-pre-wrap overflow-auto max-h-24 mt-1">{JSON.stringify(workflowState.waiting_for, null, 2)}</pre>
              </div>
            )}
            <div>
              <div className="flex items-center justify-between">
                <span className="font-semibold text-xs">state_data</span>
                <button
                  className="text-[10px] px-2 py-0.5 rounded bg-blue-100 dark:bg-blue-800 hover:bg-blue-200 dark:hover:bg-blue-700"
                  onClick={() => setShowStateData((s) => !s)}
                >
                  {showStateData ? 'Hide' : 'Show'}
                </button>
              </div>
              {showStateData && (
                <pre className="whitespace-pre-wrap overflow-auto max-h-48 mt-1">{JSON.stringify(workflowState.state_data || {}, null, 2)}</pre>
              )}
            </div>
          </div>
        )}
        <AnimatePresence>
          {messages.map((message) => (
            <motion.div
              key={message.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className={`flex ${message.type === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-xs px-4 py-2 rounded-lg ${
                  message.type === 'user'
                    ? 'bg-primary-500 text-white'
                    : message.type === 'orchestrator'
                    ? 'bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-white'
                    : 'bg-yellow-100 dark:bg-yellow-900/20 text-yellow-800 dark:text-yellow-200'
                }`}
              >
                <p className="text-sm">{message.content}</p>
                <p className="text-xs opacity-70 mt-1">
                  {format(message.timestamp, 'HH:mm:ss')}
                </p>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
        <div ref={messagesEndRef} />
      </div>

      <div className="p-4 border-t border-gray-200 dark:border-gray-700">
        <div className="flex space-x-2">
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Type a message..."
            className="flex-1 px-4 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-primary-500"
            disabled={isLoading || !currentWorkflow}
          />
          <button
            onClick={sendMessage}
            disabled={isLoading || !inputValue.trim() || !currentWorkflow}
            className={`p-2 rounded-lg transition-colors ${
              isLoading || !inputValue.trim() || !currentWorkflow
                ? 'bg-gray-300 dark:bg-gray-600 text-gray-500 dark:text-gray-400 cursor-not-allowed'
                : 'bg-primary-500 hover:bg-primary-600 text-white'
            }`}
          >
            <PaperAirplaneIcon className="w-5 h-5" />
          </button>
        </div>
        {!currentWorkflow && (
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
            Select a workflow to send messages
          </p>
        )}
        {currentWorkflow && (
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
            Tip: The assistant sees a JSON snapshot of this workflow’s state in the system prompt.
          </p>
        )}
      </div>
    </div>
  );
};
