'use client';

import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { usePlaygroundStore } from '@/store/playgroundStore';
import { ExamplesMenu } from '@/components/Playground/ExamplesMenu';
import { PlaygroundWorkflowGraph } from '@/components/Playground/PlaygroundWorkflowGraph';
import { NodeDetailsPanel } from '@/components/Playground/NodeDetailsPanel';
import { ExecutionNode } from '@/services/playgroundApi';

// Planning Steps Animation Component
function PlanningSteps() {
  const [currentStep, setCurrentStep] = useState(0);

  const steps = [
    { text: 'Analyzing your request...', icon: '🔍' },
    { text: 'Identifying required capabilities...', icon: '🧩' },
    { text: 'Designing workflow nodes...', icon: '⚙️' },
    { text: 'Connecting dependencies...', icon: '🔗' },
    { text: 'Validating workflow structure...', icon: '✓' },
  ];

  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentStep((prev) => (prev + 1) % steps.length);
    }, 2500);
    return () => clearInterval(interval);
  }, [steps.length]);

  return (
    <div className="space-y-2">
      {steps.map((step, idx) => {
        const isActive = idx === currentStep;
        const isPast = idx < currentStep;

        return (
          <motion.div
            key={idx}
            initial={{ opacity: 0.3 }}
            animate={{
              opacity: isActive ? 1 : isPast ? 0.6 : 0.3,
              x: isActive ? 4 : 0,
            }}
            transition={{ duration: 0.3 }}
            className={`flex items-center gap-3 py-1 ${
              isActive ? 'text-[oklch(0.65_0.25_180)]' : 'text-[oklch(0.5_0.05_180)]'
            }`}
          >
            <span className="text-sm">{step.icon}</span>
            <span className={`font-mono text-xs ${isActive ? 'font-medium' : ''}`}>
              {step.text}
            </span>
            {isActive && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: [0.3, 1, 0.3] }}
                transition={{ duration: 1.5, repeat: Infinity }}
                className="ml-auto flex gap-1"
              >
                <div className="w-1 h-1 rounded-full bg-[oklch(0.65_0.25_180)]" />
                <div className="w-1 h-1 rounded-full bg-[oklch(0.65_0.25_180)]" />
                <div className="w-1 h-1 rounded-full bg-[oklch(0.65_0.25_180)]" />
              </motion.div>
            )}
          </motion.div>
        );
      })}
    </div>
  );
}

export default function PlaygroundPage() {
  const {
    state,
    prompt,
    planResult,
    executionStatus,
    examples,
    error,
    planningDuration,
    executionStartTime,
    executionDuration,
    // Two-phase planning
    planningPhase,
    rephrasedIntent,
    workflowOutline,
    intentDuration,
    // Node selection
    selectedNodeId,
    selectNode,
    extractIntentAndPlan,
    executeWorkflow,
    loadExamples,
    selectExample,
    prepareRerun,
    reset,
    clearError,
  } = usePlaygroundStore();

  // Format duration for display
  const formatDuration = (ms: number | null): string => {
    if (ms === null) return '...';
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
    const mins = Math.floor(ms / 60000);
    const secs = ((ms % 60000) / 1000).toFixed(0);
    return `${mins}m ${secs}s`;
  };

  // Live elapsed time for running execution
  const [liveElapsed, setLiveElapsed] = useState<number>(0);
  useEffect(() => {
    if (state === 'executing' && executionStartTime) {
      const interval = setInterval(() => {
        setLiveElapsed(Date.now() - executionStartTime);
      }, 100);
      return () => clearInterval(interval);
    } else {
      setLiveElapsed(0);
    }
  }, [state, executionStartTime]);

  // Bottom drawer state
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [drawerHeight, setDrawerHeight] = useState(50); // percentage

  // Load examples on mount
  useEffect(() => {
    loadExamples();
  }, [loadExamples]);

  // Auto-open drawer when results are ready
  useEffect(() => {
    if (state === 'completed' || state === 'failed') {
      setIsDrawerOpen(true);
    } else if (state === 'idle') {
      setIsDrawerOpen(false);
    }
  }, [state]);

  const nodes = executionStatus?.nodes ?? [];
  const isRunning = state === 'executing';
  const isCompleted = state === 'completed';
  const isFailed = state === 'failed';
  const hasWorkflow = planResult?.yaml;

  return (
    <div className="h-full flex flex-col overflow-hidden bg-[oklch(0.08_0.02_260)]">
      {/* Error Banner */}
      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="border-b border-[oklch(0.577_0.245_27/0.5)] bg-[oklch(0.577_0.245_27/0.1)]"
          >
            <div className="px-4 py-2 flex items-center gap-3">
              <div className="w-2 h-2 rounded-full bg-[oklch(0.577_0.245_27)] pulse-glow" />
              <span className="font-mono text-xs text-[oklch(0.577_0.245_27)] flex-1">{error}</span>
              <button onClick={clearError} className="text-[oklch(0.577_0.245_27)] hover:text-[oklch(0.7_0.25_27)]">
                <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                </svg>
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Main Content: 2-Panel Layout */}
      <div className="flex-1 flex overflow-hidden relative">
        {/* Left Panel: Input / Run Interface */}
        <div className="w-[400px] min-w-[350px] max-w-[500px] border-r border-[oklch(0.22_0.03_260)] flex flex-col bg-[oklch(0.1_0.02_260)]">
          {/* Panel Header */}
          <div className="px-4 py-3 border-b border-[oklch(0.22_0.03_260)] bg-[oklch(0.08_0.02_260)]">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${
                  state === 'idle' ? 'bg-[oklch(0.5_0.01_260)]' :
                  state === 'planning' ? 'bg-[oklch(0.65_0.25_180)] animate-pulse' :
                  state === 'planned' ? 'bg-[oklch(0.78_0.22_150)]' :
                  state === 'executing' ? 'bg-[oklch(0.65_0.25_180)] animate-pulse' :
                  state === 'completed' ? 'bg-[oklch(0.78_0.22_150)]' :
                  'bg-[oklch(0.65_0.25_25)]'
                }`} />
                <span className="font-mono text-xs tracking-wider text-[oklch(0.65_0.25_180)] uppercase">
                  {state === 'idle' ? 'WORKFLOW INPUT' :
                   state === 'planning' ? 'DESIGNING...' :
                   state === 'planned' ? 'READY TO RUN' :
                   state === 'executing' ? 'RUNNING' :
                   state === 'completed' ? 'COMPLETED' : 'FAILED'}
                </span>
              </div>
            </div>
          </div>

          {/* Panel Content */}
          <div className="flex-1 overflow-y-auto">
            {/* Idle State - Show Examples Only */}
            {state === 'idle' && (
              <div className="p-4">
                {examples.length > 0 && (
                  <ExamplesMenu
                    examples={examples}
                    onSelectExample={selectExample}
                    onBuildWorkflow={(example) => extractIntentAndPlan(example.prompt)}
                  />
                )}
              </div>
            )}

            {/* Planning State - Two-Phase Planning */}
            {state === 'planning' && (
              <div className="p-4 space-y-4">
                {/* Phase 1: Intent Extraction (fast) */}
                {planningPhase === 'intent' && (
                  <>
                    {/* Mission being analyzed */}
                    <div className="rounded border border-[oklch(0.22_0.03_260)] bg-[oklch(0.08_0.02_260/0.5)] overflow-hidden">
                      <div className="px-3 py-2 border-b border-[oklch(0.22_0.03_260)] bg-[oklch(0.06_0.01_260)]">
                        <span className="font-mono text-[10px] tracking-wider text-[oklch(0.5_0.01_260)] uppercase">
                          Your Request
                        </span>
                      </div>
                      <div className="p-3">
                        <p className="font-mono text-sm text-[oklch(0.8_0.01_260)] leading-relaxed break-words">{prompt}</p>
                      </div>
                    </div>

                    {/* Quick Intent Analysis */}
                    <div className="rounded border border-[oklch(0.35_0.15_180)] bg-gradient-to-br from-[oklch(0.12_0.05_180)] to-[oklch(0.1_0.03_260)] overflow-hidden">
                      <div className="px-3 py-2 border-b border-[oklch(0.25_0.1_180)] bg-[oklch(0.08_0.03_180/0.5)]">
                        <div className="flex items-center gap-2">
                          <div className="w-2 h-2 rounded-full bg-[oklch(0.65_0.25_180)] animate-pulse" />
                          <span className="font-mono text-[10px] tracking-wider text-[oklch(0.65_0.25_180)] uppercase">
                            Understanding your request...
                          </span>
                        </div>
                      </div>
                      <div className="p-4 flex items-center justify-center">
                        <div className="flex gap-1">
                          <div className="w-2 h-2 rounded-full bg-[oklch(0.65_0.25_180)] animate-bounce" style={{ animationDelay: '0ms' }} />
                          <div className="w-2 h-2 rounded-full bg-[oklch(0.65_0.25_180)] animate-bounce" style={{ animationDelay: '150ms' }} />
                          <div className="w-2 h-2 rounded-full bg-[oklch(0.65_0.25_180)] animate-bounce" style={{ animationDelay: '300ms' }} />
                        </div>
                      </div>
                    </div>
                  </>
                )}

                {/* Phase 2: YAML Generation (shows intent while generating) */}
                {planningPhase === 'yaml' && (
                  <>
                    {/* Intent Confirmation Card */}
                    <div className="rounded border border-[oklch(0.78_0.22_150)] bg-gradient-to-br from-[oklch(0.12_0.08_150)] to-[oklch(0.1_0.03_260)] overflow-hidden">
                      <div className="px-3 py-2 border-b border-[oklch(0.5_0.15_150)] bg-[oklch(0.08_0.05_150/0.5)]">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <div className="w-2 h-2 rounded-full bg-[oklch(0.78_0.22_150)]" />
                            <span className="font-mono text-[10px] tracking-wider text-[oklch(0.78_0.22_150)] uppercase">
                              I understood
                            </span>
                          </div>
                          {intentDuration && (
                            <span className="font-mono text-[10px] text-[oklch(0.5_0.1_150)]">
                              {intentDuration}ms
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="p-4 space-y-3">
                        {/* Rephrased Intent */}
                        <p className="font-mono text-sm text-[oklch(0.9_0.02_90)] leading-relaxed">
                          {rephrasedIntent || 'Processing your request...'}
                        </p>

                        {/* Workflow Outline */}
                        {workflowOutline && workflowOutline.length > 0 && (
                          <div className="flex flex-wrap gap-2 pt-2">
                            {workflowOutline.map((step, idx) => (
                              <span
                                key={idx}
                                className="inline-flex items-center gap-1 px-2 py-1 font-mono text-[10px] rounded bg-[oklch(0.15_0.05_180)] border border-[oklch(0.25_0.1_180)] text-[oklch(0.7_0.15_180)]"
                              >
                                <span className="text-[oklch(0.5_0.1_180)]">{idx + 1}.</span>
                                {step.replace(/_/g, ' ')}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* YAML Generation Progress */}
                    <div className="rounded border border-[oklch(0.35_0.15_180)] bg-gradient-to-br from-[oklch(0.12_0.05_180)] to-[oklch(0.1_0.03_260)] overflow-hidden">
                      <div className="px-3 py-2 border-b border-[oklch(0.25_0.1_180)] bg-[oklch(0.08_0.03_180/0.5)]">
                        <div className="flex items-center gap-2">
                          <div className="w-2 h-2 rounded-full bg-[oklch(0.65_0.25_180)] animate-pulse" />
                          <span className="font-mono text-[10px] tracking-wider text-[oklch(0.65_0.25_180)] uppercase">
                            Generating workflow...
                          </span>
                        </div>
                      </div>
                      <div className="p-4 space-y-3">
                        {/* Animated steps */}
                        <PlanningSteps />

                        {/* Time hint */}
                        <div className="pt-2 border-t border-[oklch(0.2_0.05_180)]">
                          <p className="font-mono text-[10px] text-[oklch(0.5_0.05_180)] text-center">
                            Building your workflow with {workflowOutline?.length || '...'} steps
                          </p>
                        </div>
                      </div>
                    </div>
                  </>
                )}

                {/* Fallback: Old planning UI for backwards compatibility */}
                {(!planningPhase || planningPhase === 'none') && (
                  <>
                    <div className="rounded border border-[oklch(0.22_0.03_260)] bg-[oklch(0.08_0.02_260/0.5)] overflow-hidden">
                      <div className="px-3 py-2 border-b border-[oklch(0.22_0.03_260)] bg-[oklch(0.06_0.01_260)]">
                        <span className="font-mono text-[10px] tracking-wider text-[oklch(0.5_0.01_260)] uppercase">
                          Your Request
                        </span>
                      </div>
                      <div className="p-3">
                        <p className="font-mono text-sm text-[oklch(0.8_0.01_260)] leading-relaxed break-words">{prompt}</p>
                      </div>
                    </div>
                    <div className="rounded border border-[oklch(0.35_0.15_180)] bg-gradient-to-br from-[oklch(0.12_0.05_180)] to-[oklch(0.1_0.03_260)] overflow-hidden">
                      <div className="px-3 py-2 border-b border-[oklch(0.25_0.1_180)] bg-[oklch(0.08_0.03_180/0.5)]">
                        <div className="flex items-center gap-2">
                          <div className="w-2 h-2 rounded-full bg-[oklch(0.65_0.25_180)] animate-pulse" />
                          <span className="font-mono text-[10px] tracking-wider text-[oklch(0.65_0.25_180)] uppercase">
                            AI is designing your workflow
                          </span>
                        </div>
                      </div>
                      <div className="p-4 space-y-3">
                        <PlanningSteps />
                        <div className="pt-2 border-t border-[oklch(0.2_0.05_180)]">
                          <p className="font-mono text-[10px] text-[oklch(0.5_0.05_180)] text-center">
                            This usually takes 5-15 seconds depending on complexity
                          </p>
                        </div>
                      </div>
                    </div>
                  </>
                )}
              </div>
            )}

            {/* Run Interface - Shows after planning */}
            {(state === 'planned' || state === 'executing' || state === 'completed' || state === 'failed') && (
              <div className="p-4 space-y-4">
                {/* Intent Confirmation Card - Persistent "I understood" section */}
                {rephrasedIntent ? (
                  <div className="rounded border border-[oklch(0.78_0.22_150)] bg-gradient-to-br from-[oklch(0.12_0.08_150)] to-[oklch(0.1_0.03_260)] overflow-hidden">
                    <div className="px-3 py-2 border-b border-[oklch(0.5_0.15_150)] bg-[oklch(0.08_0.05_150/0.5)]">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <div className="w-2 h-2 rounded-full bg-[oklch(0.78_0.22_150)]" />
                          <span className="font-mono text-[10px] tracking-wider text-[oklch(0.78_0.22_150)] uppercase">
                            I understood
                          </span>
                        </div>
                        {intentDuration && (
                          <span className="font-mono text-[10px] text-[oklch(0.5_0.1_150)]">
                            {intentDuration}ms
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="p-4 space-y-3">
                      {/* Rephrased Intent */}
                      <p className="font-mono text-sm text-[oklch(0.9_0.02_90)] leading-relaxed">
                        {rephrasedIntent}
                      </p>

                      {/* Workflow Outline */}
                      {workflowOutline && workflowOutline.length > 0 && (
                        <div className="flex flex-wrap gap-2 pt-2">
                          {workflowOutline.map((step, idx) => (
                            <span
                              key={idx}
                              className="inline-flex items-center gap-1 px-2 py-1 font-mono text-[10px] rounded bg-[oklch(0.15_0.05_180)] border border-[oklch(0.25_0.1_180)] text-[oklch(0.7_0.15_180)]"
                            >
                              <span className="text-[oklch(0.5_0.1_180)]">{idx + 1}.</span>
                              {step.replace(/_/g, ' ')}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                ) : (
                  /* Fallback: Simple Mission Brief when no intent data */
                  <div className="rounded border border-[oklch(0.22_0.03_260)] bg-[oklch(0.08_0.02_260/0.5)] overflow-hidden">
                    <div className="px-3 py-2 border-b border-[oklch(0.22_0.03_260)] bg-[oklch(0.06_0.01_260)]">
                      <span className="font-mono text-[10px] tracking-wider text-[oklch(0.5_0.01_260)] uppercase">
                        Mission
                      </span>
                    </div>
                    <div className="p-3">
                      <p className="font-mono text-sm text-[oklch(0.8_0.01_260)] leading-relaxed break-words">
                        {prompt}
                      </p>
                    </div>
                  </div>
                )}

                {/* Connector Resolution Warning */}
                {planResult?.connector_resolution && !planResult.connector_resolution.resolved && (
                  <div className="rounded border border-[oklch(0.5_0.2_30)] bg-[oklch(0.2_0.05_30/0.3)] overflow-hidden">
                    <div className="px-3 py-2 border-b border-[oklch(0.4_0.15_30)] bg-[oklch(0.15_0.05_30/0.5)]">
                      <div className="flex items-center gap-2">
                        <svg className="h-4 w-4 text-[oklch(0.7_0.2_30)]" fill="currentColor" viewBox="0 0 20 20">
                          <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                        </svg>
                        <span className="font-mono text-[10px] tracking-wider text-[oklch(0.7_0.2_30)] uppercase">
                          Unresolved Connectors
                        </span>
                      </div>
                    </div>
                    <div className="p-3 space-y-2">
                      <p className="font-mono text-xs text-[oklch(0.7_0.1_30)]">
                        The following hosts must be added to the allowlist before execution:
                      </p>
                      <ul className="space-y-1">
                        {planResult.connector_resolution.unresolved_slots.map((slot, idx) => (
                          <li key={idx} className="flex items-center gap-2 px-2 py-1.5 rounded bg-[oklch(0.15_0.03_30)] border border-[oklch(0.3_0.1_30)]">
                            <span className="font-mono text-xs text-[oklch(0.9_0.15_30)]">
                              {slot.host}
                            </span>
                            <span className="font-mono text-[10px] text-[oklch(0.5_0.05_30)]">
                              ({slot.node_name})
                            </span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                )}

                {/* Workflow Stats Card */}
                {planResult?.cost_estimate && (
                  <div className="rounded border border-[oklch(0.35_0.15_180)] bg-gradient-to-br from-[oklch(0.12_0.05_180)] to-[oklch(0.1_0.03_260)] overflow-hidden">
                    <div className="px-3 py-2 border-b border-[oklch(0.25_0.1_180)] bg-[oklch(0.08_0.03_180/0.5)]">
                      <span className="font-mono text-[10px] tracking-wider text-[oklch(0.65_0.25_180)] uppercase">
                        Workflow Stats
                      </span>
                    </div>
                    <div className="p-3 grid grid-cols-4 gap-2">
                      <div className="text-center">
                        <div className="font-mono text-xl text-[oklch(0.95_0.01_90)]">
                          {planResult.cost_estimate.node_count ?? 0}
                        </div>
                        <div className="font-mono text-[10px] text-[oklch(0.5_0.01_260)] uppercase">
                          Nodes
                        </div>
                      </div>
                      <div className="text-center">
                        <div className="font-mono text-xl text-[oklch(0.75_0.15_280)]">
                          {planResult.cost_estimate.llm_node_count ?? 0}
                        </div>
                        <div className="font-mono text-[10px] text-[oklch(0.5_0.01_260)] uppercase">
                          AI Nodes
                        </div>
                      </div>
                      <div className="text-center">
                        <div className="font-mono text-xl text-[oklch(0.65_0.25_180)]">
                          {isRunning ? (
                            <span className="animate-pulse">...</span>
                          ) : (
                            `${nodes.filter(n => n.status === 'completed').length}/${nodes.length || planResult.cost_estimate.node_count || 0}`
                          )}
                        </div>
                        <div className="font-mono text-[10px] text-[oklch(0.5_0.01_260)] uppercase">
                          Progress
                        </div>
                      </div>
                      <div className="text-center">
                        <div className="font-mono text-xl text-[oklch(0.7_0.15_60)]">
                          {isRunning ? (
                            <span>{formatDuration(liveElapsed)}</span>
                          ) : isCompleted || isFailed ? (
                            formatDuration(executionDuration)
                          ) : (
                            formatDuration(planningDuration)
                          )}
                        </div>
                        <div className="font-mono text-[10px] text-[oklch(0.5_0.01_260)] uppercase">
                          {isRunning || isCompleted || isFailed ? 'Exec Time' : 'Plan Time'}
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* Execution Timeline */}
                {(isRunning || isCompleted || isFailed) && nodes.length > 0 && (
                  <div className="rounded border border-[oklch(0.22_0.03_260)] bg-[oklch(0.08_0.02_260/0.5)] overflow-hidden">
                    <div className="px-3 py-2 border-b border-[oklch(0.22_0.03_260)] bg-[oklch(0.06_0.01_260)]">
                      <span className="font-mono text-[10px] tracking-wider text-[oklch(0.5_0.01_260)] uppercase">
                        Execution Timeline
                      </span>
                    </div>
                    <div className="p-2 max-h-[200px] overflow-y-auto">
                      {nodes.map((node, idx) => (
                        <div key={node.id || idx} className="flex items-center gap-2 px-2 py-1.5">
                          <div className={`w-2 h-2 rounded-full ${
                            node.status === 'completed' ? 'bg-[oklch(0.78_0.22_150)]' :
                            node.status === 'running' ? 'bg-[oklch(0.65_0.25_180)] animate-pulse' :
                            node.status === 'failed' ? 'bg-[oklch(0.65_0.25_25)]' :
                            'bg-[oklch(0.3_0.01_260)]'
                          }`} />
                          <span className="font-mono text-xs text-[oklch(0.7_0.01_260)] flex-1 truncate">
                            {node.name || node.id}
                          </span>
                          <span className="font-mono text-[10px] text-[oklch(0.5_0.01_260)] uppercase">
                            {node.status}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Action Buttons */}
          <div className="p-4 border-t border-[oklch(0.22_0.03_260)] bg-[oklch(0.08_0.02_260)] space-y-2">
            {state === 'planned' && (
              <button
                onClick={executeWorkflow}
                disabled={!planResult?.valid || (planResult?.connector_resolution !== null && planResult?.connector_resolution !== undefined && !planResult.connector_resolution.resolved)}
                className={`w-full flex items-center justify-center gap-2 px-4 py-3 font-mono text-sm tracking-wider uppercase rounded border transition-all ${
                  planResult?.valid && (!planResult?.connector_resolution || planResult.connector_resolution.resolved)
                    ? 'bg-[oklch(0.7_0.2_150/0.2)] border-[oklch(0.78_0.22_150)] text-[oklch(0.78_0.22_150)] hover:bg-[oklch(0.7_0.2_150/0.3)] hover:shadow-[0_0_20px_oklch(0.7_0.2_150/0.4)]'
                    : 'bg-[oklch(0.18_0.02_260)] border-[oklch(0.22_0.03_260)] text-[oklch(0.38_0.01_260)] cursor-not-allowed'
                }`}
              >
                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM9.555 7.168A1 1 0 008 8v4a1 1 0 001.555.832l3-2a1 1 0 000-1.664l-3-2z" clipRule="evenodd" />
                </svg>
                RUN WORKFLOW
              </button>
            )}

            {state === 'executing' && (
              <div className="w-full flex items-center justify-center gap-3 px-4 py-3 font-mono text-sm tracking-wider uppercase rounded border border-[oklch(0.65_0.25_180)] bg-[oklch(0.65_0.25_180/0.1)] text-[oklch(0.65_0.25_180)]">
                <div className="w-4 h-4 border-2 border-[oklch(0.65_0.25_180)] border-t-transparent rounded-full animate-spin" />
                EXECUTING...
              </div>
            )}

            {(isCompleted || isFailed) && (
              <button
                onClick={() => setIsDrawerOpen(true)}
                className="w-full flex items-center justify-center gap-2 px-4 py-3 font-mono text-sm tracking-wider uppercase rounded border bg-[oklch(0.65_0.25_180/0.2)] border-[oklch(0.65_0.25_180)] text-[oklch(0.65_0.25_180)] hover:bg-[oklch(0.65_0.25_180/0.3)] hover:shadow-[0_0_15px_oklch(0.65_0.25_180/0.3)] transition-all"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                VIEW RESULTS
              </button>
            )}

            {state !== 'idle' && (
              <button
                onClick={reset}
                className="w-full flex items-center justify-center gap-2 px-4 py-2 font-mono text-xs tracking-wider uppercase border border-[oklch(0.3_0.02_260)] bg-[oklch(0.12_0.02_260)] text-[oklch(0.58_0.01_260)] rounded hover:border-[oklch(0.65_0.25_180/0.5)] hover:text-[oklch(0.65_0.25_180)] transition-all"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                RESET
              </button>
            )}
          </div>
        </div>

        {/* Right Panel: Full-Size Visualization */}
        <div className="flex-1 flex flex-col bg-[oklch(0.08_0.02_260)]">
          {/* Visualization Header */}
          <div className="px-4 py-3 border-b border-[oklch(0.22_0.03_260)] flex items-center justify-between">
            <div className="flex items-center gap-3">
              <span className="font-mono text-xs tracking-wider text-[oklch(0.65_0.25_180)] uppercase">
                Workflow Visualization
              </span>
              {executionStatus?.execution_id && (
                <button
                  onClick={async () => {
                    await navigator.clipboard.writeText(executionStatus.execution_id);
                  }}
                  title="Click to copy"
                  className="group font-mono text-[10px] text-[oklch(0.5_0.01_260)] px-2 py-0.5 rounded bg-[oklch(0.15_0.02_260)] border border-[oklch(0.22_0.03_260)] hover:border-[oklch(0.65_0.25_180/0.5)] hover:text-[oklch(0.65_0.25_180)] transition-all cursor-pointer"
                >
                  <span className="group-hover:hidden">{executionStatus.execution_id.slice(0, 8)}...</span>
                  <span className="hidden group-hover:inline">{executionStatus.execution_id}</span>
                </button>
              )}
            </div>
            {hasWorkflow && (
              <div className="flex items-center gap-3 text-[10px] font-mono text-[oklch(0.5_0.01_260)]">
                <span className="flex items-center gap-1">
                  <div className="w-2 h-2 rounded-full bg-[oklch(0.5_0.01_260)]" />
                  PENDING
                </span>
                <span className="flex items-center gap-1">
                  <div className="w-2 h-2 rounded-full bg-[oklch(0.65_0.25_180)]" />
                  RUNNING
                </span>
                <span className="flex items-center gap-1">
                  <div className="w-2 h-2 rounded-full bg-[oklch(0.78_0.22_150)]" />
                  DONE
                </span>
              </div>
            )}
          </div>

          {/* Visualization Content - Full Size */}
          <div className="flex-1 relative h-full">
            {hasWorkflow ? (
              <div className="absolute inset-0">
                <PlaygroundWorkflowGraph
                  yaml={planResult.yaml}
                  executionNodes={nodes}
                  onNodeClick={selectNode}
                  selectedNodeId={selectedNodeId}
                />
              </div>
            ) : (
              <div className="h-full flex items-center justify-center">
                <div className="text-center">
                  <div className="relative inline-block">
                    <svg className="w-24 h-24 text-[oklch(0.2_0.02_260)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={0.5} d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                    <div className="absolute inset-0 flex items-center justify-center">
                      <div className="w-3 h-3 rounded-full bg-[oklch(0.3_0.02_260)]" />
                    </div>
                  </div>
                  <p className="mt-4 font-mono text-sm text-[oklch(0.4_0.01_260)]">
                    Build a workflow to see it visualized here
                  </p>
                  <p className="mt-1 font-mono text-[10px] text-[oklch(0.3_0.01_260)]">
                    Type a prompt or select an example to get started
                  </p>
                </div>
              </div>
            )}

            {/* Node Details Panel - Floating overlay */}
            {selectedNodeId && (() => {
              const selectedNode: ExecutionNode | null = nodes.find(n => n.id === selectedNodeId) || null;
              if (!selectedNode) return null;
              return (
                <div className="absolute bottom-4 right-4 w-96 max-h-[60%] z-10">
                  <NodeDetailsPanel
                    node={selectedNode}
                    onClose={() => selectNode(null)}
                  />
                </div>
              );
            })()}
          </div>
        </div>

        {/* Bottom Drawer - Results */}
        <AnimatePresence>
          {isDrawerOpen && (isCompleted || isFailed) && (
            <>
              {/* Backdrop */}
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                onClick={() => setIsDrawerOpen(false)}
                className="absolute inset-0 bg-[oklch(0_0_0/0.5)] z-10"
              />

              {/* Drawer */}
              <motion.div
                initial={{ y: '100%' }}
                animate={{ y: 0 }}
                exit={{ y: '100%' }}
                transition={{ type: 'spring', damping: 30, stiffness: 300 }}
                className="absolute bottom-0 left-0 right-0 z-20 bg-[oklch(0.1_0.02_260)] border-t border-[oklch(0.65_0.25_180)] rounded-t-xl"
                style={{ height: `${drawerHeight}%`, maxHeight: '80%', minHeight: '200px' }}
              >
                {/* Drawer Handle */}
                <div
                  className="flex justify-center py-2 cursor-ns-resize"
                  onMouseDown={(e) => {
                    const startY = e.clientY;
                    const startHeight = drawerHeight;
                    const onMouseMove = (moveE: MouseEvent) => {
                      const delta = startY - moveE.clientY;
                      const containerHeight = window.innerHeight;
                      const newHeight = Math.min(80, Math.max(20, startHeight + (delta / containerHeight) * 100));
                      setDrawerHeight(newHeight);
                    };
                    const onMouseUp = () => {
                      document.removeEventListener('mousemove', onMouseMove);
                      document.removeEventListener('mouseup', onMouseUp);
                    };
                    document.addEventListener('mousemove', onMouseMove);
                    document.addEventListener('mouseup', onMouseUp);
                  }}
                >
                  <div className="w-12 h-1 rounded-full bg-[oklch(0.3_0.02_260)]" />
                </div>

                {/* Drawer Header */}
                <div className="px-4 pb-2 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className={`w-2 h-2 rounded-full ${isCompleted ? 'bg-[oklch(0.78_0.22_150)]' : 'bg-[oklch(0.65_0.25_25)]'}`} />
                    <span className="font-mono text-sm tracking-wider text-[oklch(0.65_0.25_180)] uppercase">
                      {isCompleted ? 'Workflow Results' : 'Execution Failed'}
                    </span>
                  </div>
                  <button
                    onClick={() => setIsDrawerOpen(false)}
                    className="p-1 rounded hover:bg-[oklch(0.2_0.02_260)] transition-colors"
                  >
                    <svg className="w-5 h-5 text-[oklch(0.5_0.01_260)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>
                </div>

                {/* Drawer Content */}
                <div className="h-[calc(100%-60px)] overflow-y-auto px-4 pb-4">
                  <ResultsContent
                    result={executionStatus?.result || {}}
                    cost={executionStatus?.cost || planResult?.cost_estimate}
                    planningTime={planningDuration}
                    executionTime={executionDuration}
                    formatDuration={formatDuration}
                    onRerun={() => {
                      setIsDrawerOpen(false);
                      prepareRerun();
                    }}
                  />
                </div>
              </motion.div>
            </>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

// Results Content Component
interface ResultNode {
  node_id: string;
  name: string;
  output: {
    result?: string;
    metadata?: { usage?: { prompt_tokens?: number; completion_tokens?: number }; model?: string };
    [key: string]: unknown;
  };
}

interface WorkflowResult {
  nodes?: ResultNode[];
}

interface CostEstimate {
  total_estimated_cost?: number;
  planning_cost?: number;
  workflow_cost?: number;
}

interface ResultsContentProps {
  result: WorkflowResult;
  cost?: CostEstimate | null;
  planningTime: number | null;
  executionTime: number | null;
  formatDuration: (ms: number | null) => string;
  onRerun?: () => void;
}

function ResultsContent({ result, cost, planningTime, executionTime, formatDuration, onRerun }: ResultsContentProps) {
  const [showRaw, setShowRaw] = useState(false);
  const [copied, setCopied] = useState(false);

  const llmNodes = (result.nodes || []).filter(
    (node) => node.output?.result && typeof node.output.result === 'string'
  );

  const mainResult = llmNodes.find(n =>
    n.node_id.includes('analyze') || n.node_id.includes('summarize') ||
    n.name?.toLowerCase().includes('analyze') || n.name?.toLowerCase().includes('summarize')
  ) || llmNodes[llmNodes.length - 1];

  const secondaryResults = llmNodes.filter(n => n !== mainResult);

  const totalTime = (planningTime || 0) + (executionTime || 0);

  // Copy output to clipboard
  const handleCopy = async () => {
    if (mainResult?.output?.result) {
      try {
        await navigator.clipboard.writeText(mainResult.output.result);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      } catch (err) {
        console.error('Failed to copy:', err);
      }
    }
  };

  return (
    <div className="space-y-4">
      {/* Action Buttons Row */}
      <div className="flex gap-2">
        {mainResult && (
          <button
            onClick={handleCopy}
            className={`flex items-center gap-2 px-3 py-2 font-mono text-xs tracking-wider uppercase rounded border transition-all ${
              copied
                ? 'bg-[oklch(0.7_0.2_150/0.2)] border-[oklch(0.78_0.22_150)] text-[oklch(0.78_0.22_150)]'
                : 'border-[oklch(0.3_0.02_260)] bg-[oklch(0.12_0.02_260)] text-[oklch(0.65_0.25_180)] hover:border-[oklch(0.65_0.25_180/0.5)]'
            }`}
          >
            {copied ? (
              <>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                COPIED
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>
                COPY OUTPUT
              </>
            )}
          </button>
        )}
        {onRerun && (
          <button
            onClick={onRerun}
            className="flex items-center gap-2 px-3 py-2 font-mono text-xs tracking-wider uppercase rounded border border-[oklch(0.3_0.02_260)] bg-[oklch(0.12_0.02_260)] text-[oklch(0.7_0.15_60)] hover:border-[oklch(0.7_0.15_60/0.5)] transition-all"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            RUN AGAIN
          </button>
        )}
      </div>

      {/* Main Output */}
      {mainResult && (
        <div className="rounded-lg border border-[oklch(0.35_0.15_180)] bg-gradient-to-br from-[oklch(0.12_0.05_180)] to-[oklch(0.1_0.03_260)] overflow-hidden">
          <div className="px-4 py-3 border-b border-[oklch(0.25_0.1_180)] bg-[oklch(0.08_0.03_180/0.5)] flex items-center justify-between">
            <span className="font-mono text-xs tracking-wider text-[oklch(0.65_0.25_180)] uppercase">AI Output</span>
            {mainResult.output.metadata?.model && (
              <span className="font-mono text-[10px] text-[oklch(0.5_0.05_180)]">{mainResult.output.metadata.model}</span>
            )}
          </div>
          <div className="p-4">
            <div className="font-mono text-sm text-[oklch(0.9_0.02_90)] leading-relaxed whitespace-pre-wrap">
              {mainResult.output.result}
            </div>
          </div>
        </div>
      )}

      {/* Performance + Token Usage */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Time Summary */}
        <div className="rounded-lg border border-[oklch(0.22_0.03_260)] bg-[oklch(0.08_0.02_260/0.5)] p-4">
          <div className="flex items-center justify-between mb-3">
            <span className="font-mono text-[10px] tracking-wider text-[oklch(0.5_0.01_260)] uppercase">Performance</span>
            <span className="font-mono text-xl text-[oklch(0.7_0.15_60)] font-bold">{formatDuration(totalTime)}</span>
          </div>
          <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm font-mono">
            <div className="flex justify-between">
              <span className="text-[oklch(0.5_0.01_260)]">Planning:</span>
              <span className="text-[oklch(0.7_0.01_260)]">{formatDuration(planningTime)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[oklch(0.5_0.01_260)]">Execution:</span>
              <span className="text-[oklch(0.7_0.01_260)]">{formatDuration(executionTime)}</span>
            </div>
          </div>
        </div>

        {/* Token Usage & Cost - calculated from actual results */}
        {(() => {
          // Model pricing per 1M tokens
          const MODEL_COSTS: Record<string, { input: number; output: number }> = {
            'anthropic/claude-3-5-sonnet-20241022': { input: 3.00, output: 15.00 },
            'anthropic/claude-3.5-haiku': { input: 0.80, output: 4.00 },
            'anthropic/claude-3-haiku': { input: 0.25, output: 1.25 },
            'openai/gpt-4o-mini': { input: 0.15, output: 0.60 },
            'openai/gpt-4o': { input: 5.00, output: 15.00 },
            'x-ai/grok-4.1-fast': { input: 0.20, output: 0.50 },
            'x-ai/grok-4.1': { input: 0.20, output: 0.50 },
            'x-ai/grok-3-fast': { input: 0.20, output: 0.50 },
            'google/gemini-2.0-flash-001': { input: 0.10, output: 0.40 },
          };
          const DEFAULT_COST = { input: 1.00, output: 3.00 };

          const allNodes = result.nodes || [];
          let totalInput = 0;
          let totalOutput = 0;
          let totalCost = 0;

          allNodes.forEach(node => {
            const usage = node.output?.metadata?.usage;
            const model = node.output?.metadata?.model || '';
            if (usage) {
              const inputTokens = usage.prompt_tokens || 0;
              const outputTokens = usage.completion_tokens || 0;
              totalInput += inputTokens;
              totalOutput += outputTokens;

              // Calculate cost for this node
              const pricing = MODEL_COSTS[model] || DEFAULT_COST;
              const inputCost = (inputTokens / 1_000_000) * pricing.input;
              const outputCost = (outputTokens / 1_000_000) * pricing.output;
              totalCost += inputCost + outputCost;
            }
          });
          const totalTokens = totalInput + totalOutput;

          if (totalTokens > 0) {
            return (
              <div className="rounded-lg border border-[oklch(0.22_0.03_260)] bg-[oklch(0.08_0.02_260/0.5)] p-4">
                <div className="flex items-center justify-between mb-3">
                  <span className="font-mono text-[10px] tracking-wider text-[oklch(0.5_0.01_260)] uppercase">Usage & Cost</span>
                  <span className="font-mono text-xl text-[oklch(0.78_0.22_150)] font-bold">${totalCost.toFixed(4)}</span>
                </div>
                <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm font-mono">
                  <div className="flex justify-between">
                    <span className="text-[oklch(0.5_0.01_260)]">Input:</span>
                    <span className="text-[oklch(0.7_0.01_260)]">{totalInput.toLocaleString()} tokens</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-[oklch(0.5_0.01_260)]">Output:</span>
                    <span className="text-[oklch(0.7_0.01_260)]">{totalOutput.toLocaleString()} tokens</span>
                  </div>
                </div>
              </div>
            );
          }
          return null;
        })()}

        {/* Secondary Results */}
        {secondaryResults.length > 0 && (
          <div className="rounded-lg border border-[oklch(0.22_0.03_260)] bg-[oklch(0.08_0.02_260/0.5)] p-4">
            <span className="font-mono text-[10px] tracking-wider text-[oklch(0.5_0.01_260)] uppercase block mb-2">
              Additional Outputs ({secondaryResults.length})
            </span>
            <div className="space-y-2 max-h-[150px] overflow-y-auto">
              {secondaryResults.map((node, idx) => (
                <div key={idx} className="text-xs font-mono">
                  <span className="text-[oklch(0.58_0.01_260)]">{node.name || node.node_id}:</span>
                  <span className="text-[oklch(0.7_0.01_260)] ml-2 truncate block">{node.output.result?.substring(0, 100)}...</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Raw Data Toggle */}
      <button
        onClick={() => setShowRaw(!showRaw)}
        className="w-full px-4 py-2 font-mono text-[10px] tracking-wider text-[oklch(0.5_0.01_260)] uppercase border border-[oklch(0.22_0.03_260)] rounded hover:border-[oklch(0.3_0.02_260)] transition-colors flex items-center justify-between"
      >
        <span>Raw Data</span>
        <svg className={`w-4 h-4 transition-transform ${showRaw ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {showRaw && (
        <div className="rounded-lg border border-[oklch(0.18_0.02_260)] bg-[oklch(0.06_0.01_260)] p-4 overflow-auto max-h-[200px]">
          <pre className="font-mono text-[10px] text-[oklch(0.6_0.1_180)]">{JSON.stringify(result, null, 2)}</pre>
        </div>
      )}
    </div>
  );
}
