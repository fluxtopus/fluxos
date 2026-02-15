"""Workflow compiler service - converts visual workflow JSON to Tentackl spec"""

from typing import Dict, Any, List

class WorkflowCompiler:
    """Service for compiling visual workflow definitions to Tentackl workflow specs"""
    
    def compile(self, workflow_definition: Dict[str, Any]) -> Dict[str, Any]:
        """Compile a visual workflow definition to Tentackl workflow spec format"""
        # Extract workflow metadata
        name = workflow_definition.get("name", "notification_workflow")
        description = workflow_definition.get("description", "")
        nodes = workflow_definition.get("nodes", [])
        edges = workflow_definition.get("edges", [])
        
        # Build workflow steps from nodes and edges
        steps = self._build_steps(nodes, edges)
        
        # Create Tentackl workflow spec
        tentackl_spec = {
            "name": name,
            "description": description,
            "version": "1.0",
            "inputs": self._extract_inputs(nodes),
            "steps": steps
        }
        
        return tentackl_spec
    
    def _extract_inputs(self, nodes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Extract input definitions from workflow nodes"""
        inputs = {}
        
        # Find trigger nodes
        for node in nodes:
            if node.get("type") == "trigger":
                # Extract input parameters from trigger node
                node_inputs = node.get("inputs", {})
                for key, value in node_inputs.items():
                    inputs[key] = {
                        "type": value.get("type", "string"),
                        "required": value.get("required", False),
                        "default": value.get("default")
                    }
        
        return inputs
    
    def _build_steps(self, nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Build workflow steps from nodes and edges"""
        steps = []
        
        # Create a map of node IDs to nodes
        node_map = {node["id"]: node for node in nodes}
        
        # Find start node (trigger)
        start_node = next((n for n in nodes if n.get("type") == "trigger"), None)
        if not start_node:
            return steps
        
        # Build steps by traversing the graph
        visited = set()
        self._traverse_node(start_node, node_map, edges, steps, visited)
        
        return steps
    
    def _traverse_node(
        self,
        node: Dict[str, Any],
        node_map: Dict[str, Any],
        edges: List[Dict[str, Any]],
        steps: List[Dict[str, Any]],
        visited: set
    ):
        """Traverse workflow graph and build steps"""
        if node["id"] in visited:
            return
        
        visited.add(node["id"])
        
        # Convert node to step
        step = self._node_to_step(node)
        if step:
            steps.append(step)
        
        # Find outgoing edges
        outgoing_edges = [e for e in edges if e.get("source") == node["id"]]
        
        # Traverse connected nodes
        for edge in outgoing_edges:
            target_id = edge.get("target")
            if target_id and target_id in node_map:
                target_node = node_map[target_id]
                self._traverse_node(target_node, node_map, edges, steps, visited)
    
    def _node_to_step(self, node: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a workflow node to a Tentackl workflow step"""
        node_type = node.get("type")
        
        if node_type == "trigger":
            # Trigger nodes don't become steps, they define inputs
            return None
        
        elif node_type == "condition":
            # Conditional step
            return {
                "id": node["id"],
                "type": "conditional",
                "condition": node.get("condition", ""),
                "then": node.get("then", []),
                "else": node.get("else", [])
            }
        
        elif node_type == "action":
            # Action step (notification delivery)
            action_type = node.get("action_type", "notify")
            
            if action_type == "notify":
                return {
                    "id": node["id"],
                    "agent": {
                        "type": "notifier",
                        "config": node.get("config", {})
                    },
                    "task": {
                        "provider": node.get("provider", "email"),
                        "recipient": node.get("recipient", "${inputs.recipient}"),
                        "content": node.get("content", "${inputs.content}"),
                        "template_id": node.get("template_id"),
                        **node.get("metadata", {})
                    },
                    "retry": {
                        "max_attempts": node.get("max_attempts", 3),
                        "delay": node.get("delay", 5)
                    }
                }
        
        # Default: return basic step structure
        return {
            "id": node["id"],
            "type": node_type,
            "config": node.get("config", {})
        }

