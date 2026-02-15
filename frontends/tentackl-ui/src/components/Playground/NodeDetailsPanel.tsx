import React, { useState } from 'react';
import { ExecutionNode } from '../../services/playgroundApi';

interface NodeDetailsPanelProps {
  node: ExecutionNode | null;
  onClose: () => void;
}

export const NodeDetailsPanel: React.FC<NodeDetailsPanelProps> = ({
  node,
  onClose,
}) => {
  const [activeTab, setActiveTab] = useState<'output' | 'raw'>('output');

  if (!node) {
    return null;
  }

  const statusColors: Record<string, string> = {
    completed: 'text-green-400 bg-green-900/30 border-green-500/50',
    running: 'text-blue-400 bg-blue-900/30 border-blue-500/50',
    failed: 'text-red-400 bg-red-900/30 border-red-500/50',
    pending: 'text-gray-400 bg-gray-800/50 border-gray-600/50',
  };

  const statusBadgeColor = statusColors[node.status] || statusColors.pending;

  // Extract meaningful output data
  const result = (node.result || {}) as Record<string, unknown>;
  const hasJson = result.json !== undefined;
  const hasResult = result.result !== undefined;
  const hasStatus = result.status !== undefined;

  // Type-safe accessors
  const statusCode = hasStatus ? (result.status as number) : undefined;
  const resultText = hasResult && typeof result.result === 'string' ? result.result : undefined;
  const jsonData = result.json;
  const metadata = result.metadata as { model?: string; usage?: { prompt_tokens?: number; completion_tokens?: number } } | undefined;

  // Format JSON nicely, truncate if too long
  const formatValue = (value: unknown, maxLength = 5000): string => {
    if (value === undefined || value === null) return 'null';
    if (typeof value === 'string') {
      return value.length > maxLength ? value.slice(0, maxLength) + '...' : value;
    }
    const formatted = JSON.stringify(value, null, 2);
    return formatted.length > maxLength ? formatted.slice(0, maxLength) + '...' : formatted;
  };

  return (
    <div className="rounded-lg border border-[oklch(0.22_0.03_260)] bg-[oklch(0.12_0.02_260/0.95)] backdrop-blur-md overflow-hidden">
      {/* Header */}
      <div className="px-4 py-2 border-b border-[oklch(0.22_0.03_260)] flex items-center justify-between bg-[oklch(0.08_0.02_260/0.5)]">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <svg className="h-4 w-4 text-[oklch(0.7_0.15_280)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
            <span className="font-mono text-xs tracking-wider text-[oklch(0.7_0.15_280)] uppercase">
              Node Details
            </span>
          </div>
          <span className={`px-2 py-0.5 rounded text-[10px] font-mono uppercase border ${statusBadgeColor}`}>
            {node.status}
          </span>
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded hover:bg-[oklch(0.2_0.02_260)] transition-colors"
        >
          <svg className="h-4 w-4 text-[oklch(0.5_0.01_260)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Node Name & ID */}
      <div className="px-4 py-3 border-b border-[oklch(0.18_0.02_260)]">
        <h3 className="font-mono text-sm text-[oklch(0.9_0.02_90)]">
          {node.name || node.id}
        </h3>
        {node.name && node.name !== node.id && (
          <p className="font-mono text-[10px] text-[oklch(0.5_0.01_260)] mt-1">
            ID: {node.id}
          </p>
        )}
        {node.started_at && (
          <div className="flex items-center gap-4 mt-2 font-mono text-[10px] text-[oklch(0.5_0.01_260)]">
            <span>Started: {new Date(node.started_at).toLocaleTimeString()}</span>
            {node.completed_at && (
              <span>Completed: {new Date(node.completed_at).toLocaleTimeString()}</span>
            )}
          </div>
        )}
      </div>

      {/* Error Display */}
      {node.error && (
        <div className="px-4 py-3 border-b border-[oklch(0.3_0.1_25)] bg-[oklch(0.15_0.05_25/0.3)]">
          <div className="flex items-center gap-2 mb-2">
            <svg className="h-4 w-4 text-[oklch(0.65_0.25_25)]" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
            </svg>
            <span className="font-mono text-xs text-[oklch(0.65_0.25_25)] uppercase">Error</span>
          </div>
          <pre className="font-mono text-[11px] text-[oklch(0.8_0.15_25)] whitespace-pre-wrap overflow-auto max-h-32">
            {typeof node.error === 'string' ? node.error : JSON.stringify(node.error, null, 2)}
          </pre>
        </div>
      )}

      {/* Tabs */}
      {(hasJson || hasResult || Object.keys(result).length > 0) && (
        <>
          <div className="flex border-b border-[oklch(0.18_0.02_260)]">
            <button
              onClick={() => setActiveTab('output')}
              className={`flex-1 px-4 py-2 font-mono text-[10px] tracking-wider uppercase transition-colors ${
                activeTab === 'output'
                  ? 'text-[oklch(0.78_0.22_150)] border-b-2 border-[oklch(0.78_0.22_150)] bg-[oklch(0.15_0.02_260)]'
                  : 'text-[oklch(0.5_0.01_260)] hover:text-[oklch(0.7_0.01_260)] hover:bg-[oklch(0.12_0.02_260)]'
              }`}
            >
              Output
            </button>
            <button
              onClick={() => setActiveTab('raw')}
              className={`flex-1 px-4 py-2 font-mono text-[10px] tracking-wider uppercase transition-colors ${
                activeTab === 'raw'
                  ? 'text-[oklch(0.78_0.22_150)] border-b-2 border-[oklch(0.78_0.22_150)] bg-[oklch(0.15_0.02_260)]'
                  : 'text-[oklch(0.5_0.01_260)] hover:text-[oklch(0.7_0.01_260)] hover:bg-[oklch(0.12_0.02_260)]'
              }`}
            >
              Raw Data
            </button>
          </div>

          {/* Tab Content */}
          <div className="p-4 max-h-80 overflow-auto">
            {activeTab === 'output' && (
              <div className="space-y-4">
                {/* HTTP Status */}
                {statusCode !== undefined && (
                  <div>
                    <div className="font-mono text-[10px] tracking-wider text-[oklch(0.5_0.01_260)] uppercase mb-1">
                      HTTP Status
                    </div>
                    <span className={`font-mono text-sm ${
                      statusCode >= 200 && statusCode < 300
                        ? 'text-green-400'
                        : statusCode >= 400
                          ? 'text-red-400'
                          : 'text-yellow-400'
                    }`}>
                      {statusCode}
                    </span>
                  </div>
                )}

                {/* LLM Result Text */}
                {resultText && (
                  <div>
                    <div className="font-mono text-[10px] tracking-wider text-[oklch(0.5_0.01_260)] uppercase mb-1">
                      Result
                    </div>
                    <div className="font-mono text-xs text-[oklch(0.85_0.02_90)] leading-relaxed whitespace-pre-wrap bg-[oklch(0.08_0.02_260)] border border-[oklch(0.18_0.02_260)] rounded p-3 max-h-48 overflow-auto">
                      {resultText}
                    </div>
                  </div>
                )}

                {/* JSON Response */}
                {hasJson && (
                  <div>
                    <div className="font-mono text-[10px] tracking-wider text-[oklch(0.5_0.01_260)] uppercase mb-1">
                      JSON Response
                    </div>
                    <pre className="font-mono text-[10px] text-[oklch(0.7_0.15_180)] bg-[oklch(0.06_0.01_260)] border border-[oklch(0.18_0.02_260)] rounded p-3 overflow-auto max-h-48">
                      {formatValue(jsonData)}
                    </pre>
                  </div>
                )}

                {/* Metadata (tokens, model) */}
                {metadata && (
                  <div>
                    <div className="font-mono text-[10px] tracking-wider text-[oklch(0.5_0.01_260)] uppercase mb-1">
                      Metadata
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      {metadata.model && (
                        <div className="rounded bg-[oklch(0.08_0.02_260)] border border-[oklch(0.18_0.02_260)] p-2">
                          <span className="block font-mono text-[9px] text-[oklch(0.5_0.01_260)] uppercase">Model</span>
                          <span className="font-mono text-xs text-[oklch(0.75_0.15_280)]">{metadata.model}</span>
                        </div>
                      )}
                      {metadata.usage && (
                        <>
                          <div className="rounded bg-[oklch(0.08_0.02_260)] border border-[oklch(0.18_0.02_260)] p-2">
                            <span className="block font-mono text-[9px] text-[oklch(0.5_0.01_260)] uppercase">Input Tokens</span>
                            <span className="font-mono text-xs text-[oklch(0.75_0.01_260)]">{metadata.usage.prompt_tokens?.toLocaleString() || 0}</span>
                          </div>
                          <div className="rounded bg-[oklch(0.08_0.02_260)] border border-[oklch(0.18_0.02_260)] p-2">
                            <span className="block font-mono text-[9px] text-[oklch(0.5_0.01_260)] uppercase">Output Tokens</span>
                            <span className="font-mono text-xs text-[oklch(0.75_0.01_260)]">{metadata.usage.completion_tokens?.toLocaleString() || 0}</span>
                          </div>
                        </>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}

            {activeTab === 'raw' && (
              <pre className="font-mono text-[10px] text-[oklch(0.6_0.1_180)] whitespace-pre-wrap">
                {formatValue(result, 10000)}
              </pre>
            )}
          </div>
        </>
      )}

      {/* No data message */}
      {!hasJson && !hasResult && Object.keys(result).length === 0 && !node.error && (
        <div className="px-4 py-8 text-center">
          <span className="font-mono text-xs text-[oklch(0.5_0.01_260)]">
            {node.status === 'pending' ? 'Waiting to execute...' :
             node.status === 'running' ? 'Executing...' :
             'No output data available'}
          </span>
        </div>
      )}
    </div>
  );
};

export default NodeDetailsPanel;
