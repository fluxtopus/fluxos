import { create } from 'zustand';
import { devtools } from 'zustand/middleware';
import { playgroundApi, PlanResponse, ExecuteResponse, ExecutionStatus, ExampleWorkflow } from '../services/playgroundApi';

// Playground states
export type PlaygroundState =
  | 'idle'           // Initial state, waiting for input
  | 'planning'       // AI is generating the workflow
  | 'planned'        // Workflow is planned, ready to execute
  | 'executing'      // Workflow is running
  | 'completed'      // Workflow finished successfully
  | 'failed';        // Something went wrong

// Planning phases for two-phase planning
export type PlanningPhase = 'none' | 'intent' | 'yaml' | 'done';

interface PlaygroundStore {
  // State
  state: PlaygroundState;
  prompt: string;
  planResult: PlanResponse | null;
  executeResult: ExecuteResponse | null;
  executionStatus: ExecutionStatus | null;
  examples: ExampleWorkflow[];
  error: string | null;

  // Node selection for details panel
  selectedNodeId: string | null;

  // Two-phase planning state
  planningPhase: PlanningPhase;
  rephrasedIntent: string | null;
  workflowOutline: string[] | null;
  intentDuration: number | null;
  yamlDuration: number | null;

  // Timing
  planningStartTime: number | null;
  planningDuration: number | null;
  executionStartTime: number | null;
  executionDuration: number | null;

  // Actions
  extractIntentAndPlan: (prompt: string) => Promise<void>;
  executeWorkflow: () => Promise<void>;
  pollExecutionStatus: () => Promise<void>;
  loadExamples: () => Promise<void>;
  selectExample: (example: ExampleWorkflow) => void;
  selectNode: (nodeId: string | null) => void;
  prepareRerun: () => void;
  reset: () => void;
  clearError: () => void;
}

export const usePlaygroundStore = create<PlaygroundStore>()(
  devtools(
    (set, get) => ({
      // Initial state
      state: 'idle',
      prompt: '',
      planResult: null,
      executeResult: null,
      executionStatus: null,
      examples: [],
      error: null,

      // Node selection for details panel
      selectedNodeId: null,

      // Two-phase planning
      planningPhase: 'none',
      rephrasedIntent: null,
      workflowOutline: null,
      intentDuration: null,
      yamlDuration: null,

      // Timing
      planningStartTime: null,
      planningDuration: null,
      executionStartTime: null,
      executionDuration: null,

      // Two-phase planning: extract intent first, then plan
      extractIntentAndPlan: async (prompt: string) => {
        const intentStartTime = Date.now();
        set({
          state: 'planning',
          prompt,
          error: null,
          planResult: null,
          planningPhase: 'intent',
          rephrasedIntent: null,
          workflowOutline: null,
          planningStartTime: intentStartTime,
          planningDuration: null,
          intentDuration: null,
          yamlDuration: null,
          executionStartTime: null,
          executionDuration: null
        });

        try {
          // Phase 1: Fast intent extraction
          const intentResult = await playgroundApi.extractIntent(prompt);
          const intentDuration = Date.now() - intentStartTime;

          // Update with intent results, start YAML phase
          const yamlStartTime = Date.now();
          set({
            planningPhase: 'yaml',
            rephrasedIntent: intentResult.rephrased_intent,
            workflowOutline: intentResult.workflow_outline,
            intentDuration
          });

          // Phase 2: Full YAML generation
          const result = await playgroundApi.plan(prompt);
          const yamlDuration = Date.now() - yamlStartTime;
          const totalDuration = Date.now() - intentStartTime;

          if (result.valid) {
            set({
              state: 'planned',
              planResult: result,
              planningPhase: 'done',
              planningDuration: totalDuration,
              yamlDuration,
            });
          } else {
            set({
              state: 'idle',
              planResult: result,
              planningPhase: 'none',
              planningDuration: totalDuration,
              yamlDuration,
              error: `Workflow validation failed: ${result.issues.map(i => i.message).join(', ')}`
            });
          }
        } catch (error) {
          const duration = Date.now() - intentStartTime;
          set({
            state: 'idle',
            planningPhase: 'none',
            planningDuration: duration,
            error: error instanceof Error ? error.message : 'Failed to plan workflow'
          });
        }
      },

      // Execute planned workflow
      executeWorkflow: async () => {
        const { planResult } = get();
        if (!planResult?.session_id) {
          set({ error: 'No planned workflow to execute' });
          return;
        }

        const startTime = Date.now();
        set({ state: 'executing', error: null, executionStartTime: startTime, executionDuration: null });

        try {
          const result = await playgroundApi.execute(planResult.session_id);
          set({ executeResult: result });

          // Start polling for status
          get().pollExecutionStatus();
        } catch (error) {
          const duration = Date.now() - startTime;
          set({
            state: 'failed',
            executionDuration: duration,
            error: error instanceof Error ? error.message : 'Failed to execute workflow'
          });
        }
      },

      // Poll execution status
      pollExecutionStatus: async () => {
        const { executeResult, executionStartTime } = get();
        if (!executeResult?.execution_id) return;

        const poll = async () => {
          try {
            const status = await playgroundApi.getExecutionStatus(executeResult.execution_id);
            const failedNodes = status.nodes?.filter(n => n.status === 'failed') || [];
            const hasFailedNodes = failedNodes.length > 0;
            const isCompleted = status.status === 'completed';
            const isFailed = status.status === 'failed' || hasFailedNodes;

            set({ executionStatus: status });

            if (isCompleted) {
              const duration = executionStartTime ? Date.now() - executionStartTime : null;
              set({ state: 'completed', executionDuration: duration });
            } else if (isFailed) {
              const duration = executionStartTime ? Date.now() - executionStartTime : null;
              set({
                state: 'failed',
                executionDuration: duration,
                error: hasFailedNodes
                  ? `Failed: ${failedNodes.map(n => n.name || n.id).join(', ')}`
                  : 'Execution failed'
              });
            } else {
              // Continue polling
              setTimeout(poll, 1000);
            }
          } catch (error) {
            // Continue polling on error
            setTimeout(poll, 2000);
          }
        };

        poll();
      },

      // Select a node for details panel
      selectNode: (nodeId: string | null) => {
        set({ selectedNodeId: nodeId });
      },

      // Load example workflows
      loadExamples: async () => {
        try {
          const examples = await playgroundApi.getExamples();
          set({ examples });
        } catch (error) {
          console.error('Failed to load examples:', error);
        }
      },

      // Select an example
      selectExample: (example: ExampleWorkflow) => {
        set({ prompt: example.prompt, state: 'idle', planResult: null, error: null });
      },

      // Prepare for rerun - go back to planned state
      prepareRerun: () => {
        set({
          state: 'planned',
          executeResult: null,
          executionStatus: null,
          error: null,
          executionStartTime: null,
          executionDuration: null,
        });
      },

      // Reset playground
      reset: () => {
        set({
          state: 'idle',
          prompt: '',
          planResult: null,
          executeResult: null,
          executionStatus: null,
          error: null,
          selectedNodeId: null,
          planningPhase: 'none',
          rephrasedIntent: null,
          workflowOutline: null,
          intentDuration: null,
          yamlDuration: null,
          planningStartTime: null,
          planningDuration: null,
          executionStartTime: null,
          executionDuration: null,
        });
      },

      // Clear error
      clearError: () => {
        set({ error: null });
      },
    }),
    {
      name: 'playground-store',
    }
  )
);
