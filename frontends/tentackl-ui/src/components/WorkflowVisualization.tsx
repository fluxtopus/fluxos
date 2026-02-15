import React, { useCallback, useMemo, useState } from 'react';
import {
  ReactFlow,
  ReactFlowProvider,
  Node as FlowNode,
  Edge as FlowEdge,
  Controls,
  Background,
  BackgroundVariant,
  useNodesState,
  useEdgesState,
  MarkerType,
  Panel,
  Handle,
  Position,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import dagre from 'dagre';
import { useWorkflowStore } from '../store/workflowStore';
import { Node, NodeStatus } from '../types/workflow';
import { NodeDetailsPanel } from './NodeDetailsPanel';

// Node status colors - clean, modern palette
const statusColors = {
  [NodeStatus.PENDING]: '#6B7280', // gray-500
  [NodeStatus.RUNNING]: '#3B82F6', // blue-500
  [NodeStatus.COMPLETED]: '#10B981', // green-500
  [NodeStatus.FAILED]: '#EF4444', // red-500
  [NodeStatus.PAUSED]: '#F59E0B', // amber-500
  [NodeStatus.CANCELLED]: '#9CA3AF', // gray-400
};

// Border colors - slightly darker for better contrast
const borderColors = {
  [NodeStatus.PENDING]: '#4B5563', // gray-600
  [NodeStatus.RUNNING]: '#2563EB', // blue-600
  [NodeStatus.COMPLETED]: '#059669', // green-600
  [NodeStatus.FAILED]: '#DC2626', // red-600
  [NodeStatus.PAUSED]: '#D97706', // amber-600
  [NodeStatus.CANCELLED]: '#6B7280', // gray-500
};

// Custom node component
const CustomNode = ({ data, id }: { data: any; id: string }) => {
  const status = data.status as NodeStatus;
  const isRootNode = id === 'root' || data.agent_type === 'root';

  // Root node gets special styling
  const backgroundColor = isRootNode
    ? '#8B5CF6'  // Purple for root
    : statusColors[status] || '#6B7280';
  const borderColor = isRootNode
    ? '#7C3AED'  // Darker purple for root
    : borderColors[status] || '#4B5563';
  const isPulsing = status === NodeStatus.RUNNING;

  return (
    <>
      {/* Target handle (input) on the left - hidden for root node */}
      {!isRootNode && (
        <Handle
          type="target"
          position={Position.Left}
          style={{
            background: borderColor,
            width: 10,
            height: 10,
          }}
        />
      )}

      <div
        className={`px-4 py-2 border-2 shadow-lg ${isPulsing ? 'animate-pulse' : ''}`}
        style={{
          backgroundColor,
          borderColor,
          minWidth: '120px',
          maxWidth: '200px',
          borderRadius: isRootNode ? '0' : '0.5rem',
          // Cut corner effect for root node using clip-path
          clipPath: isRootNode
            ? 'polygon(12px 0%, calc(100% - 12px) 0%, 100% 12px, 100% calc(100% - 12px), calc(100% - 12px) 100%, 12px 100%, 0% calc(100% - 12px), 0% 12px)'
            : 'none',
        }}
      >
        <div className="text-white text-sm font-semibold text-center break-words">
          {isRootNode && (
            <span className="mr-1">▶</span>
          )}
          {data.label}
        </div>
      </div>

      {/* Source handle (output) on the right */}
      <Handle
        type="source"
        position={Position.Right}
        style={{
          background: borderColor,
          width: 10,
          height: 10,
        }}
      />
    </>
  );
};

const nodeTypes = {
  custom: CustomNode,
};

// Layout configuration
const nodeWidth = 180;
const nodeHeight = 60;

// Function to calculate layout using dagre
const getLayoutedElements = (nodes: FlowNode[], edges: FlowEdge[]) => {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));

  // Set graph layout direction to left-to-right
  dagreGraph.setGraph({
    rankdir: 'LR',
    nodesep: 100,  // Horizontal spacing between nodes
    ranksep: 150,  // Vertical spacing between ranks
    edgesep: 50,
  });

  // Add nodes to the graph
  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: nodeWidth, height: nodeHeight });
  });

  // Add edges to the graph
  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  // Calculate layout
  dagre.layout(dagreGraph);

  // Apply calculated positions to nodes
  const layoutedNodes = nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    return {
      ...node,
      position: {
        x: nodeWithPosition.x - nodeWidth / 2,
        y: nodeWithPosition.y - nodeHeight / 2,
      },
    };
  });

  return { nodes: layoutedNodes, edges };
};

const WorkflowVisualizationInner: React.FC = () => {
  const { currentWorkflow, isConnected, loading } = useWorkflowStore();
  const [selectedNode, setSelectedNode] = useState<Node | null>(null);
  const [isPanelOpen, setIsPanelOpen] = useState(false);

  // Convert workflow nodes and edges to React Flow format with layout
  const { flowNodes, flowEdges } = useMemo(() => {
    if (!currentWorkflow) return { flowNodes: [], flowEdges: [] };

    // Convert nodes
    const nodes: FlowNode[] = currentWorkflow.nodes.map((node) => {
      const resultData = (node.data as any)?.result_data || {};
      const pending = resultData?.pending ?? resultData?.pending_messages ?? 0;
      const baseLabel = (node.data as any)?.name || node.type;
      const isApprovals = node.id.startsWith('approvals-');
      const label = isApprovals && pending > 0 ? `${baseLabel} (${pending})` : baseLabel;

      return {
        id: node.id,
        type: 'custom',
        position: { x: 0, y: 0 }, // Will be calculated by dagre
        data: {
          label,
          status: node.status,
          ...node.data,
        },
      };
    });

    // Convert edges
    const edges: FlowEdge[] = currentWorkflow.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      type: 'smoothstep',
      animated: false,
      markerEnd: {
        type: MarkerType.ArrowClosed,
        width: 20,
        height: 20,
        color: '#6B7280',
      },
      style: {
        strokeWidth: 3,
        stroke: '#6B7280',
      },
    }));

    // Calculate layout
    const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(nodes, edges);

    return { flowNodes: layoutedNodes, flowEdges: layoutedEdges };
  }, [currentWorkflow]);

  const [nodes, setNodes, onNodesChange] = useNodesState(flowNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(flowEdges);

  // Update nodes when workflow changes
  React.useEffect(() => {
    setNodes(flowNodes);
  }, [flowNodes, setNodes]);

  // Update edges when workflow changes
  React.useEffect(() => {
    setEdges(flowEdges);
  }, [flowEdges, setEdges]);

  // Handle node click
  const onNodeClick = useCallback(
    (_event: React.MouseEvent, node: FlowNode) => {
      if (currentWorkflow) {
        const workflowNode = currentWorkflow.nodes.find((n) => n.id === node.id);
        if (workflowNode) {
          setSelectedNode(workflowNode);
          setIsPanelOpen(true);
        }
      }
    },
    [currentWorkflow]
  );

  // Handle pane click (background)
  const onPaneClick = useCallback(() => {
    setIsPanelOpen(false);
    setSelectedNode(null);
  }, []);

  // Show loading state while fetching workflow
  if (loading && !currentWorkflow) {
    return (
      <div className="flex items-center justify-center h-full bg-white dark:bg-gray-900">
        <div className="flex flex-col items-center gap-3">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 dark:border-blue-400"></div>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Loading workflow run...
          </p>
        </div>
      </div>
    );
  }

  if (!currentWorkflow) {
    return (
      <div className="flex items-center justify-center h-full bg-white dark:bg-gray-900">
        <p className="text-gray-500 dark:text-gray-400">
          Select a workflow run to visualize
        </p>
      </div>
    );
  }

  return (
    <div className="w-full h-full bg-white dark:bg-gray-900">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        onPaneClick={onPaneClick}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{
          padding: 0.2,
        }}
        minZoom={0.1}
        maxZoom={3}
        defaultEdgeOptions={{
          type: 'smoothstep',
          animated: false,
          style: { strokeWidth: 3, stroke: '#6B7280' },
        }}
      >
        <Background variant={BackgroundVariant.Dots} gap={12} size={1} />
        <Controls />

        {/* Connection Status */}
        <Panel position="top-left">
          <div
            className={`flex items-center space-x-2 px-3 py-1 text-xs rounded-md ${
              isConnected
                ? 'bg-white dark:bg-gray-800 border border-green-500 dark:border-green-500 text-green-700 dark:text-green-400'
                : 'bg-white dark:bg-gray-800 border border-red-500 dark:border-red-500 text-red-700 dark:text-red-400'
            }`}
          >
            <div
              className={`w-2 h-2 rounded-full ${
                isConnected ? 'bg-green-500 animate-pulse' : 'bg-red-500'
              }`}
            />
            <span>{isConnected ? 'Connected' : 'Disconnected'}</span>
          </div>
        </Panel>
      </ReactFlow>

      {/* Node Details Panel */}
      <NodeDetailsPanel
        node={selectedNode}
        isOpen={isPanelOpen}
        onClose={() => {
          setIsPanelOpen(false);
          setSelectedNode(null);
        }}
      />
    </div>
  );
};

// Wrap with ReactFlowProvider for proper context
export const WorkflowVisualization: React.FC = () => {
  return (
    <ReactFlowProvider>
      <WorkflowVisualizationInner />
    </ReactFlowProvider>
  );
};
