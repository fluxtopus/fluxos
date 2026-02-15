export enum NodeStatus {
  PENDING = 'pending',
  RUNNING = 'running',
  COMPLETED = 'completed',
  FAILED = 'failed',
  PAUSED = 'paused',
  CANCELLED = 'cancelled',
}

export enum WorkflowStatus {
  PENDING = 'pending',
  RUNNING = 'running',
  COMPLETED = 'completed',
  FAILED = 'failed',
  PAUSED = 'paused',
  CANCELLED = 'cancelled',
}

export interface Node {
  id: string;
  type: string;
  status: NodeStatus;
  data: Record<string, any>;
  result_data?: any;  // Actual plugin execution results
  position?: {
    x: number;
    y: number;
  };
}

export interface Edge {
  id: string;
  source: string;
  target: string;
  data?: Record<string, any>;
}

export interface WorkflowMetadata {
  created_at?: string;
  updated_at?: string;
  created_by?: string;
  description?: string;
  tags: string[];
}

export interface Workflow {
  id: string;
  name: string;
  status: WorkflowStatus;
  nodes: Node[];
  edges: Edge[];
  metadata: WorkflowMetadata;
}

export interface WorkflowSummary {
  id: string;
  name: string;
  status: WorkflowStatus;
  created_at?: string;
  updated_at?: string;
}

export interface WorkflowMetrics {
  workflow_id: string;
  total_nodes: number;
  completed_nodes: number;
  failed_nodes: number;
  pending_nodes: number;
  total_execution_time: number;
  average_node_time: number;
  success_rate: number;
}

export interface StateUpdate {
  node_id: string;
  field: string;
  old_value: any;
  new_value: any;
  timestamp: string;
}

export interface NodeUpdate {
  node_id: string;
  status?: NodeStatus;
  data?: Record<string, any>;
  timestamp: string;
}

export interface EdgeUpdate {
  edge_id: string;
  data: Record<string, any>;
  timestamp: string;
}

export type WebSocketMessage = {
  type: 'initial_state' | 'state_update' | 'node_update' | 'edge_update' | 'metrics' | 'workflows_list' | 'workflow_created' | 'workflow_deleted';
  data: any;
  timestamp?: string;
}

// Workflow Spec types
export interface WorkflowSpec {
  id: string;
  name: string;
  spec_yaml: string;
  spec_compiled: Record<string, any>;
  description?: string;
  is_active: boolean;
  version: number;
  created_at: string;
  updated_at: string;
  created_by?: string;
  tags?: string[];
}

export interface WorkflowSpecSummary {
  id: string;
  name: string;
  description?: string;
  is_active: boolean;
  version: number;
  created_at: string;
  updated_at: string;
  run_count?: number;
}

// Workflow Run types
export interface WorkflowRun {
  workflow_id: string;
  spec_id?: string;
  spec_name?: string;
  run_number?: number;
  status: WorkflowStatus;
  run_parameters: Record<string, any>;
  triggered_by?: string;
  started_at?: string;
  completed_at?: string;
  created_at: string;
  updated_at: string;
}