import { create } from 'zustand';
import { devtools } from 'zustand/middleware';
import { Workflow, WorkflowSummary, WorkflowMetrics, Node, NodeStatus, WorkflowStatus } from '../types/workflow';
import { workflowApi } from '../services/api';
import { WorkflowWebSocket } from '../services/websocket';

interface WorkflowStore {
  // State
  workflows: WorkflowSummary[];
  currentWorkflow: Workflow | null;
  currentMetrics: WorkflowMetrics | null;
  loading: boolean;
  manualRefresh: boolean;  // Track if user manually triggered refresh
  error: string | null;
  wsConnection: WorkflowWebSocket | null;
  wsListConnection: WorkflowWebSocket | null;
  isConnected: boolean;

  // Actions
  fetchWorkflows: (manual?: boolean) => Promise<void>;
  selectWorkflow: (workflowId: string) => Promise<void>;
  updateNode: (nodeId: string, updates: Partial<Node>) => void;
  updateWorkflowInList: (workflowId: string, updates: Partial<WorkflowSummary>) => void;
  connectWebSocket: (workflowId: string) => Promise<void>;
  connectWorkflowsWebSocket: () => Promise<void>;
  disconnectWebSocket: () => void;
  addWorkflow: (workflow: WorkflowSummary) => void;
  clearError: () => void;
}

export const useWorkflowStore = create<WorkflowStore>()(
  devtools(
    (set, get) => ({
      // Initial state
      workflows: [],
      currentWorkflow: null,
      currentMetrics: null,
      loading: false,
      manualRefresh: false,
      error: null,
      wsConnection: null,
      wsListConnection: null,
      isConnected: false,

      // Fetch all workflows
      fetchWorkflows: async (manual = false) => {
        set({ loading: true, manualRefresh: manual, error: null });
        try {
          const workflows = await workflowApi.listWorkflows();
          set({ workflows, loading: false, manualRefresh: false });
        } catch (error) {
          set({
            error: error instanceof Error ? error.message : 'Failed to fetch workflows',
            loading: false,
            manualRefresh: false
          });
        }
      },

      // Select and load a specific workflow
      selectWorkflow: async (workflowId: string) => {
        set({ loading: true, error: null });
        
        // Disconnect previous WebSocket if any
        const { wsConnection } = get();
        if (wsConnection) {
          wsConnection.disconnect();
        }

        try {
          // Fetch workflow details and metrics in parallel
          const [workflow, metrics] = await Promise.all([
            workflowApi.getWorkflow(workflowId),
            workflowApi.getWorkflowMetrics(workflowId),
          ]);

          set({ 
            currentWorkflow: workflow, 
            currentMetrics: metrics,
            loading: false 
          });

          // Connect WebSocket for real-time updates
          await get().connectWebSocket(workflowId);
        } catch (error) {
          set({ 
            error: error instanceof Error ? error.message : 'Failed to load workflow',
            loading: false 
          });
        }
      },

      // Update a node in the current workflow
      updateNode: (nodeId: string, updates: Partial<Node>) => {
        const { currentWorkflow } = get();
        if (!currentWorkflow) return;

        const updatedNodes = currentWorkflow.nodes.map(node =>
          node.id === nodeId ? { ...node, ...updates } : node
        );

        const updatedWorkflow = {
          ...currentWorkflow,
          nodes: updatedNodes,
        };

        set({
          currentWorkflow: updatedWorkflow,
        });

        // Recalculate metrics from actual node states
        if (updates.status) {
          const metrics = get().currentMetrics;
          if (metrics) {
            // Count nodes by status from actual node array
            const statusCounts = updatedNodes.reduce((acc, node) => {
              acc[node.status] = (acc[node.status] || 0) + 1;
              return acc;
            }, {} as Record<string, number>);

            const completedNodes = statusCounts[NodeStatus.COMPLETED] || 0;
            const failedNodes = statusCounts[NodeStatus.FAILED] || 0;
            const pendingNodes = statusCounts[NodeStatus.PENDING] || 0;
            const runningNodes = statusCounts[NodeStatus.RUNNING] || 0;
            const totalNodes = updatedNodes.length;

            // Calculate timing metrics from node data
            let totalExecutionTime = 0;
            let completedWithTiming = 0;

            updatedNodes.forEach(node => {
              if (node.data?.started_at && node.data?.completed_at) {
                const duration = new Date(node.data.completed_at).getTime() - new Date(node.data.started_at).getTime();
                totalExecutionTime += duration;
                completedWithTiming++;
              }
            });

            const updatedMetrics = {
              ...metrics,
              total_nodes: totalNodes,
              completed_nodes: completedNodes,
              failed_nodes: failedNodes,
              pending_nodes: pendingNodes,
              success_rate: totalNodes > 0 ? (completedNodes / totalNodes) * 100 : 0,
              total_execution_time: totalExecutionTime,
              average_node_time: completedWithTiming > 0 ? totalExecutionTime / completedWithTiming : 0,
            };

            set({ currentMetrics: updatedMetrics });

            // Determine overall workflow status based on node statuses
            const hasRunning = runningNodes > 0;
            const hasFailed = failedNodes > 0;
            const allCompleted = completedNodes === totalNodes && totalNodes > 0;

            let workflowStatus = currentWorkflow.status;
            if (allCompleted) {
              workflowStatus = WorkflowStatus.COMPLETED;
            } else if (hasFailed) {
              workflowStatus = WorkflowStatus.FAILED;
            } else if (hasRunning) {
              workflowStatus = WorkflowStatus.RUNNING;
            }

            // Update the workflow in the list if status changed
            if (workflowStatus !== currentWorkflow.status) {
              get().updateWorkflowInList(currentWorkflow.id, { status: workflowStatus });
            }
          }
        }
      },

      // Update a workflow in the workflows list
      updateWorkflowInList: (workflowId: string, updates: Partial<WorkflowSummary>) => {
        set(state => ({
          workflows: state.workflows.map(w =>
            w.id === workflowId ? { ...w, ...updates } : w
          )
        }));
      },

      // Connect WebSocket for real-time updates
      connectWebSocket: async (workflowId: string) => {
        const ws = new WorkflowWebSocket(workflowId);
        
        // Subscribe to WebSocket messages
        ws.subscribe((message) => {
          switch (message.type) {
            case 'initial_state':
              if (message.data) {
                set({ currentWorkflow: message.data });
              }
              break;
              
            case 'node_update':
              const nodeUpdate = message.data;
              get().updateNode(nodeUpdate.node_id, {
                status: nodeUpdate.status,
                data: nodeUpdate.data ? { ...nodeUpdate.data } : undefined,
              });
              break;
              
            case 'state_update':
              // Handle state field updates
              const stateUpdate = message.data;
              const workflow = get().currentWorkflow;
              if (workflow) {
                const node = workflow.nodes.find(n => n.id === stateUpdate.node_id);
                if (node) {
                  get().updateNode(stateUpdate.node_id, {
                    data: {
                      ...node.data,
                      [stateUpdate.field]: stateUpdate.new_value,
                    },
                  });
                }
              }
              break;
              
            case 'metrics':
              set({ currentMetrics: message.data });
              break;
          }
        });

        try {
          await ws.connect();
          set({ wsConnection: ws, isConnected: true });
        } catch (error) {
          console.error('Failed to connect WebSocket:', error);
          set({ 
            error: 'Failed to establish real-time connection',
            isConnected: false 
          });
        }
      },

      // Disconnect WebSocket
      disconnectWebSocket: () => {
        const { wsConnection } = get();
        if (wsConnection) {
          wsConnection.disconnect();
          set({ wsConnection: null, isConnected: false });
        }
      },

      // Add a new workflow to the list
      addWorkflow: (workflow: WorkflowSummary) => {
        set(state => ({
          workflows: [workflow, ...state.workflows]
        }));
      },

      // Connect WebSocket for workflow list updates
      connectWorkflowsWebSocket: async () => {
        const ws = new WorkflowWebSocket('workflows');
        
        // Subscribe to WebSocket messages
        ws.subscribe((message) => {
          switch (message.type) {
            case 'workflows_list':
              if (message.data?.workflows) {
                set({ workflows: message.data.workflows });
              }
              break;
              
            case 'workflow_created':
              const newWorkflow = message.data as WorkflowSummary;
              get().addWorkflow(newWorkflow);
              break;
              
            case 'workflow_deleted':
              const deletedId = message.data.workflow_id;
              set(state => ({
                workflows: state.workflows.filter(w => w.id !== deletedId)
              }));
              break;
          }
        });

        try {
          await ws.connect();
          set({ wsListConnection: ws });
        } catch (error) {
          console.error('Failed to connect workflows WebSocket:', error);
        }
      },

      // Clear error
      clearError: () => {
        set({ error: null });
      },
    }),
    {
      name: 'workflow-store',
    }
  )
);