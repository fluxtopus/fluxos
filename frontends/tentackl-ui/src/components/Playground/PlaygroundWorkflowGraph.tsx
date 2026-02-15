import React, { useMemo, useCallback } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Node,
  Edge,
  Position,
  Handle,
  NodeProps,
} from '@xyflow/react';
import dagre from 'dagre';
import '@xyflow/react/dist/style.css';
import { ExecutionNode } from '../../services/playgroundApi';

interface WorkflowEdge {
  from: string;
  to: string;
}

interface WorkflowNodeDef {
  id: string;
  name: string;
  executor?: string;
  for_each?: string;
}

interface PlaygroundWorkflowGraphProps {
  yaml: string;
  executionNodes: ExecutionNode[];
  onNodeClick?: (nodeId: string) => void;
  selectedNodeId?: string | null;
}

// Parse YAML to extract nodes and edges
function parseWorkflowYaml(yaml: string): { nodes: WorkflowNodeDef[]; edges: WorkflowEdge[] } {
  try {
    // Simple YAML parsing for workflow structure
    const lines = yaml.split('\n');
    const nodes: WorkflowNodeDef[] = [];
    const explicitEdges: WorkflowEdge[] = [];

    let inNodes = false;
    let inEdges = false;
    let currentNode: Partial<WorkflowNodeDef> | null = null;
    let currentNodeContent = ''; // Track full node content for reference detection

    for (const line of lines) {
      const trimmed = line.trim();

      // Detect sections
      if (trimmed === 'nodes:') {
        inNodes = true;
        inEdges = false;
        continue;
      }
      if (trimmed === 'edges:') {
        inNodes = false;
        inEdges = true;
        if (currentNode && currentNode.id) {
          // Store the node content for reference detection
          (currentNode as any).rawContent = currentNodeContent;
          nodes.push(currentNode as WorkflowNodeDef);
        }
        currentNode = null;
        currentNodeContent = '';
        continue;
      }
      if (trimmed === 'budgets:' || trimmed === 'parameters:' || trimmed === 'parameter_schema:') {
        inNodes = false;
        inEdges = false;
        if (currentNode && currentNode.id) {
          (currentNode as any).rawContent = currentNodeContent;
          nodes.push(currentNode as WorkflowNodeDef);
        }
        currentNode = null;
        currentNodeContent = '';
        continue;
      }

      // Parse nodes
      if (inNodes) {
        if (trimmed.startsWith('- id:')) {
          if (currentNode && currentNode.id) {
            (currentNode as any).rawContent = currentNodeContent;
            nodes.push(currentNode as WorkflowNodeDef);
          }
          currentNode = { id: trimmed.replace('- id:', '').trim() };
          currentNodeContent = line + '\n';
        } else if (currentNode) {
          currentNodeContent += line + '\n';
          if (trimmed.startsWith('name:')) {
            currentNode.name = trimmed.replace('name:', '').trim().replace(/^["']|["']$/g, '');
          } else if (trimmed.startsWith('executor:')) {
            currentNode.executor = trimmed.replace('executor:', '').trim();
          } else if (trimmed.startsWith('for_each:')) {
            currentNode.for_each = trimmed.replace('for_each:', '').trim();
          }
        }
      }

      // Parse explicit edges
      if (inEdges) {
        if (trimmed.startsWith('- from:')) {
          const from = trimmed.replace('- from:', '').trim();
          // Next line should have 'to:'
          const idx = lines.indexOf(line);
          if (idx < lines.length - 1) {
            const nextLine = lines[idx + 1].trim();
            if (nextLine.startsWith('to:')) {
              const to = nextLine.replace('to:', '').trim();
              explicitEdges.push({ from, to });
            }
          }
        }
      }
    }

    // Add final node if exists
    if (currentNode && currentNode.id) {
      (currentNode as any).rawContent = currentNodeContent;
      nodes.push(currentNode as WorkflowNodeDef);
    }

    // Infer edges from ${node.xxx} references in node content
    const inferredEdges: WorkflowEdge[] = [];
    const nodeIds = new Set(nodes.map(n => n.id));

    for (const node of nodes) {
      const rawContent = (node as any).rawContent || '';
      // Find all ${node.xxx references - xxx is the source node ID
      const nodeRefRegex = /\$\{node\.([a-zA-Z0-9_-]+)\./g;
      let match;
      const sourcesForThisNode = new Set<string>();

      while ((match = nodeRefRegex.exec(rawContent)) !== null) {
        const sourceNodeId = match[1];
        // Only add edge if the source node exists and we haven't added this edge yet
        if (nodeIds.has(sourceNodeId) && sourceNodeId !== node.id && !sourcesForThisNode.has(sourceNodeId)) {
          sourcesForThisNode.add(sourceNodeId);
          inferredEdges.push({ from: sourceNodeId, to: node.id });
        }
      }
    }

    // Combine explicit and inferred edges, removing duplicates
    const allEdges = [...explicitEdges];
    const edgeKeys = new Set(explicitEdges.map(e => `${e.from}->${e.to}`));

    for (const edge of inferredEdges) {
      const key = `${edge.from}->${edge.to}`;
      if (!edgeKeys.has(key)) {
        edgeKeys.add(key);
        allEdges.push(edge);
      }
    }

    return { nodes, edges: allEdges };
  } catch (e) {
    console.error('Error parsing workflow YAML:', e);
    return { nodes: [], edges: [] };
  }
}

// Get status info
function getStatusInfo(status: string): { color: string; bgColor: string; borderColor: string; animate: boolean } {
  switch (status) {
    case 'completed':
      return {
        color: 'text-green-700 dark:text-green-300',
        bgColor: 'bg-green-50 dark:bg-green-900/30',
        borderColor: 'border-green-500',
        animate: false
      };
    case 'running':
      return {
        color: 'text-blue-700 dark:text-blue-300',
        bgColor: 'bg-blue-50 dark:bg-blue-900/30',
        borderColor: 'border-blue-500',
        animate: true
      };
    case 'failed':
      return {
        color: 'text-red-700 dark:text-red-300',
        bgColor: 'bg-red-50 dark:bg-red-900/30',
        borderColor: 'border-red-500',
        animate: false
      };
    case 'expanded':
      return {
        color: 'text-purple-700 dark:text-purple-300',
        bgColor: 'bg-purple-50 dark:bg-purple-900/30',
        borderColor: 'border-purple-500',
        animate: false
      };
    default:
      return {
        color: 'text-gray-600 dark:text-gray-400',
        bgColor: 'bg-gray-50 dark:bg-gray-800',
        borderColor: 'border-gray-300 dark:border-gray-600',
        animate: false
      };
  }
}

// Custom node component
interface CustomNodeData extends Record<string, unknown> {
  label: string;
  status: string;
  executor?: string;
  isForEach?: boolean;
  isExpanded?: boolean;
  isSelected?: boolean;
  onClick?: () => void;
}

function CustomNode({ data }: NodeProps<Node<CustomNodeData>>) {
  const statusInfo = getStatusInfo(data.status);

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (data.onClick) {
      data.onClick();
    }
  };

  return (
    <div
      onClick={handleClick}
      className={`
        px-4 py-3 rounded-lg border-2 shadow-md min-w-[140px] max-w-[200px] cursor-pointer
        ${statusInfo.bgColor} ${statusInfo.borderColor}
        ${statusInfo.animate ? 'animate-pulse' : ''}
        ${data.isSelected ? 'ring-2 ring-[oklch(0.78_0.22_150)] ring-offset-1 ring-offset-transparent' : ''}
        transition-all duration-300 hover:scale-105
      `}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="w-2 h-2 !bg-gray-400 dark:!bg-gray-500"
      />

      <div className="flex items-center gap-2">
        {/* Status Icon */}
        <div className="flex-shrink-0">
          {data.status === 'completed' && (
            <svg className="h-4 w-4 text-green-500" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
            </svg>
          )}
          {data.status === 'running' && (
            <svg className="animate-spin h-4 w-4 text-blue-500" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
            </svg>
          )}
          {data.status === 'failed' && (
            <svg className="h-4 w-4 text-red-500" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
            </svg>
          )}
          {data.status === 'expanded' && (
            <svg className="h-4 w-4 text-purple-500" fill="currentColor" viewBox="0 0 20 20">
              <path d="M5 3a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2V5a2 2 0 00-2-2H5zM5 11a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2v-2a2 2 0 00-2-2H5zM11 5a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V5zM11 13a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
            </svg>
          )}
          {(data.status === 'pending' || !data.status) && (
            <div className="h-4 w-4 rounded-full bg-gray-300 dark:bg-gray-600" />
          )}
        </div>

        {/* Node Info */}
        <div className="flex-1 min-w-0">
          <p className={`text-xs font-medium truncate ${statusInfo.color}`}>
            {data.label}
          </p>
          <div className="flex items-center gap-1 mt-0.5">
            {data.executor && (
              <span className="text-[10px] text-gray-500 dark:text-gray-400">
                {data.executor}
              </span>
            )}
            {data.isForEach && (
              <span className="text-[10px] px-1 py-0.5 bg-purple-100 dark:bg-purple-900/50 text-purple-600 dark:text-purple-300 rounded">
                for_each
              </span>
            )}
          </div>
        </div>
      </div>

      <Handle
        type="source"
        position={Position.Right}
        className="w-2 h-2 !bg-gray-400 dark:!bg-gray-500"
      />
    </div>
  );
}

const nodeTypes = { custom: CustomNode };

// Dagre layout
const dagreGraph = new dagre.graphlib.Graph();
dagreGraph.setDefaultEdgeLabel(() => ({}));

function getLayoutedElements(
  nodes: Node[],
  edges: Edge[],
  direction = 'LR'
): { nodes: Node[]; edges: Edge[] } {
  const nodeWidth = 180;
  const nodeHeight = 60;

  dagreGraph.setGraph({ rankdir: direction, nodesep: 50, ranksep: 80 });

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: nodeWidth, height: nodeHeight });
  });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

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
}

export const PlaygroundWorkflowGraph: React.FC<PlaygroundWorkflowGraphProps> = ({
  yaml,
  executionNodes,
  onNodeClick,
  selectedNodeId,
}) => {
  // Create a map of execution status by node ID
  const statusMap = useMemo(() => {
    const map = new Map<string, string>();
    executionNodes.forEach((node) => {
      map.set(node.id, node.status);
    });
    return map;
  }, [executionNodes]);

  // Build a map of expanded node counts and completed counts per parent
  const expandedNodeStats = useMemo(() => {
    const stats = new Map<string, { total: number; completed: number; running: number }>();
    executionNodes.forEach((execNode) => {
      const match = execNode.id.match(/^(.+)\[(\d+)\]$/);
      if (match) {
        const parentId = match[1];
        const current = stats.get(parentId) || { total: 0, completed: 0, running: 0 };
        current.total += 1;
        if (execNode.status === 'completed') current.completed += 1;
        if (execNode.status === 'running') current.running += 1;
        stats.set(parentId, current);
      }
    });
    return stats;
  }, [executionNodes]);

  // Parse workflow and build React Flow elements
  const { nodes, edges } = useMemo(() => {
    const parsed = parseWorkflowYaml(yaml);

    // Create nodes from YAML (only main workflow nodes, not expanded)
    const flowNodes: Node<CustomNodeData>[] = parsed.nodes.map((nodeDef) => {
      const isExpanded = statusMap.get(nodeDef.id) === 'expanded';
      const expandedStats = expandedNodeStats.get(nodeDef.id);

      // For expanded for_each nodes, show aggregate status
      let effectiveStatus = statusMap.get(nodeDef.id) || 'pending';
      if (isExpanded && expandedStats) {
        if (expandedStats.completed === expandedStats.total) {
          effectiveStatus = 'completed';
        } else if (expandedStats.running > 0 || expandedStats.completed > 0) {
          effectiveStatus = 'running';
        }
      }

      // Build label with progress for expanded nodes
      let label = nodeDef.name || nodeDef.id;
      if (isExpanded && expandedStats) {
        label = `${nodeDef.name || nodeDef.id} (${expandedStats.completed}/${expandedStats.total})`;
      }

      return {
        id: nodeDef.id,
        type: 'custom',
        data: {
          label,
          status: effectiveStatus,
          executor: nodeDef.executor,
          isForEach: !!nodeDef.for_each,
          isExpanded,
          isSelected: selectedNodeId === nodeDef.id,
          onClick: onNodeClick ? () => onNodeClick(nodeDef.id) : undefined,
        },
        position: { x: 0, y: 0 },
      };
    });

    // Create edges from YAML
    const flowEdges: Edge[] = parsed.edges.map((edge, idx) => {
      const sourceStatus = statusMap.get(edge.from);
      const sourceExpanded = expandedNodeStats.get(edge.from);

      // Determine edge color based on source status
      let isSourceComplete = sourceStatus === 'completed';
      if (sourceExpanded) {
        isSourceComplete = sourceExpanded.completed === sourceExpanded.total;
      }

      return {
        id: `e-${idx}`,
        source: edge.from,
        target: edge.to,
        animated: sourceStatus === 'running' || (sourceExpanded && sourceExpanded.running > 0),
        style: {
          stroke: isSourceComplete ? '#22c55e' : '#94a3b8',
          strokeWidth: 2,
        },
      };
    });

    // Apply dagre layout
    return getLayoutedElements(flowNodes, flowEdges);
  }, [yaml, statusMap, executionNodes, expandedNodeStats, selectedNodeId, onNodeClick]);

  // MiniMap node color callback
  const getNodeColor = useCallback((node: Node) => {
    const status = (node.data as CustomNodeData)?.status || 'pending';
    switch (status) {
      case 'completed': return '#22c55e';
      case 'running': return '#3b82f6';
      case 'failed': return '#ef4444';
      case 'expanded': return '#a855f7';
      default: return '#9ca3af';
    }
  }, []);

  if (nodes.length === 0) {
    return (
      <div className="h-full flex items-center justify-center text-gray-500 dark:text-gray-400">
        No workflow nodes to display
      </div>
    );
  }

  return (
    <div className="h-full w-full overflow-hidden bg-transparent">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        proOptions={{ hideAttribution: true }}
        minZoom={0.5}
        maxZoom={1.5}
      >
        <Background color="rgba(100, 116, 139, 0.35)" gap={12} size={1} />
        <Controls
          className="!bg-[oklch(0.12_0.02_260)] !border-[oklch(0.22_0.03_260)] rounded-lg !shadow-none"
          showInteractive={false}
        />
        <MiniMap
          nodeColor={getNodeColor}
          className="!bg-[oklch(0.1_0.02_260)] !border-[oklch(0.22_0.03_260)] rounded-lg"
          maskColor="rgba(0, 0, 0, 0.3)"
        />
      </ReactFlow>
    </div>
  );
};

export default PlaygroundWorkflowGraph;
