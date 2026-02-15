"""Tool for analyzing workflow execution results and trace data.

This tool allows the LLM to inspect execution details, identify errors, and suggest fixes.
"""

from typing import Dict, Any, List
import structlog

from .base import BaseTool, ToolDefinition, ToolResult

logger = structlog.get_logger(__name__)


class AnalyzeExecutionTool(BaseTool):
    """Tool for analyzing workflow execution results."""

    @property
    def name(self) -> str:
        return "analyze_execution"

    @property
    def description(self) -> str:
        return (
            "Analyze a completed workflow execution to identify errors, performance issues, "
            "and suggest improvements. Returns detailed analysis of node execution, timing, "
            "errors, and recommendations."
        )

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "run_id": {
                        "type": "string",
                        "description": "The workflow run ID to analyze"
                    },
                    "focus": {
                        "type": "string",
                        "enum": ["errors", "performance", "data_flow", "all"],
                        "description": "Analysis focus area. Default 'all'.",
                        "default": "all"
                    }
                },
                "required": ["run_id"]
            }
        )

    async def execute(self, arguments: Dict[str, Any], context: Dict[str, Any]) -> ToolResult:
        """Analyze workflow execution.

        Args:
            arguments: Tool arguments (run_id, focus)
            context: Execution context with execution_tree

        Returns:
            ToolResult with analysis report
        """
        try:
            run_id = arguments.get("run_id")
            focus = arguments.get("focus", "all")

            # Get execution_tree from context
            if not context or 'execution_tree' not in context:
                return ToolResult(
                    success=False,
                    error="Execution tree not available in context"
                )

            execution_tree = context['execution_tree']

            # Fetch run state with full trace
            run_state = await execution_tree.get_run_state(run_id, include_trace=True)

            if not run_state:
                return ToolResult(
                    success=False,
                    error=f"Run ID '{run_id}' not found"
                )

            # Initialize analysis report
            analysis = {
                "run_id": run_id,
                "status": run_state.get("status"),
                "total_duration_s": None,
                "node_count": 0,
                "errors": [],
                "warnings": [],
                "performance_issues": [],
                "data_flow_issues": [],
                "recommendations": []
            }

            # Extract trace data
            trace = run_state.get("trace", {})
            nodes_trace = trace.get("nodes", {})

            if not nodes_trace:
                return ToolResult(
                    success=False,
                    error="No trace data available for this run"
                )

            analysis["node_count"] = len(nodes_trace)

            # Calculate total duration
            start_times = []
            end_times = []
            for node_id, node_data in nodes_trace.items():
                if node_data.get("start_time"):
                    start_times.append(node_data["start_time"])
                if node_data.get("end_time"):
                    end_times.append(node_data["end_time"])

            if start_times and end_times:
                from datetime import datetime
                try:
                    earliest = min(datetime.fromisoformat(t.replace('Z', '+00:00')) for t in start_times)
                    latest = max(datetime.fromisoformat(t.replace('Z', '+00:00')) for t in end_times)
                    analysis["total_duration_s"] = (latest - earliest).total_seconds()
                except Exception:
                    pass

            # Analyze each node
            slow_nodes = []
            failed_nodes = []
            empty_outputs = []

            for node_id, node_data in nodes_trace.items():
                node_status = node_data.get("status")

                # Error analysis
                if focus in ["errors", "all"]:
                    if node_status == "failed":
                        error_msg = node_data.get("error", "Unknown error")
                        failed_nodes.append(node_id)
                        analysis["errors"].append({
                            "node_id": node_id,
                            "error": error_msg,
                            "severity": "critical"
                        })

                        # Suggest fixes based on error patterns
                        suggestion = self._suggest_fix(error_msg, node_data)
                        if suggestion:
                            analysis["recommendations"].append({
                                "node_id": node_id,
                                "type": "error_fix",
                                "suggestion": suggestion
                            })

                # Performance analysis
                if focus in ["performance", "all"]:
                    duration_ms = node_data.get("duration_ms", 0)
                    if duration_ms > 30000:  # > 30 seconds
                        slow_nodes.append({
                            "node_id": node_id,
                            "duration_ms": duration_ms
                        })
                        analysis["performance_issues"].append({
                            "node_id": node_id,
                            "issue": f"Slow execution ({duration_ms/1000:.1f}s)",
                            "severity": "warning"
                        })

                        # Suggest timeout or optimization
                        analysis["recommendations"].append({
                            "node_id": node_id,
                            "type": "performance",
                            "suggestion": (
                                f"Node took {duration_ms/1000:.1f}s to execute. "
                                "Consider adding timeout or optimizing the operation."
                            )
                        })

                # Data flow analysis
                if focus in ["data_flow", "all"]:
                    result_data = node_data.get("result_data", {})
                    if node_status == "completed" and not result_data:
                        empty_outputs.append(node_id)
                        analysis["data_flow_issues"].append({
                            "node_id": node_id,
                            "issue": "Node completed but produced no output data",
                            "severity": "warning"
                        })

            # Overall status analysis
            if analysis["status"] == "failed":
                analysis["warnings"].append(
                    f"Workflow failed. {len(failed_nodes)} node(s) failed: {', '.join(failed_nodes)}"
                )

            if analysis["status"] == "partial":
                analysis["warnings"].append(
                    "Workflow partially completed - some nodes failed while others succeeded"
                )

            # Performance summary
            if slow_nodes:
                slowest = max(slow_nodes, key=lambda x: x["duration_ms"])
                analysis["warnings"].append(
                    f"Performance: Slowest node '{slowest['node_id']}' took {slowest['duration_ms']/1000:.1f}s"
                )

            # Data flow summary
            if empty_outputs and analysis["status"] == "completed":
                analysis["warnings"].append(
                    f"{len(empty_outputs)} node(s) completed without output: {', '.join(empty_outputs)}"
                )

            # General recommendations
            if analysis["status"] == "completed" and not analysis["errors"]:
                analysis["recommendations"].append({
                    "type": "general",
                    "suggestion": "Workflow completed successfully with no errors"
                })
            elif failed_nodes:
                analysis["recommendations"].append({
                    "type": "general",
                    "suggestion": (
                        "Review failed nodes and check for: network issues, missing dependencies, "
                        "invalid input data, or insufficient timeouts"
                    )
                })

            # Build summary message
            error_count = len(analysis["errors"])
            warning_count = len(analysis["warnings"])
            perf_issue_count = len(analysis["performance_issues"])

            message_parts = [
                f"Analysis complete for run {run_id}:",
                f"{analysis['node_count']} nodes, status: {analysis['status']}"
            ]

            if error_count > 0:
                message_parts.append(f"{error_count} errors")
            if warning_count > 0:
                message_parts.append(f"{warning_count} warnings")
            if perf_issue_count > 0:
                message_parts.append(f"{perf_issue_count} performance issues")

            if analysis["total_duration_s"]:
                message_parts.append(f"Total duration: {analysis['total_duration_s']:.1f}s")

            message = ". ".join(message_parts)

            logger.info(
                "Analyzed execution",
                run_id=run_id,
                status=analysis["status"],
                error_count=error_count,
                warning_count=warning_count
            )

            return ToolResult(
                success=True,
                data=analysis,
                message=message
            )

        except Exception as e:
            logger.error("Analyze execution tool failed", error=str(e), run_id=arguments.get("run_id"))
            return ToolResult(
                success=False,
                error=f"Analysis failed: {str(e)}"
            )

    def _suggest_fix(self, error_msg: str, node_data: Dict[str, Any]) -> str:
        """Suggest a fix based on error message patterns."""
        error_lower = error_msg.lower()

        # Network/timeout errors
        if "timeout" in error_lower or "timed out" in error_lower:
            return "Increase timeout_seconds in node policies or check network connectivity"

        if "connection" in error_lower or "network" in error_lower:
            return "Check network connectivity and add retry policy with exponential backoff"

        # HTTP errors
        if "404" in error_msg or "not found" in error_lower:
            return "Verify the URL is correct and the resource exists"

        if "403" in error_msg or "forbidden" in error_lower:
            return "Check authentication credentials and permissions"

        if "500" in error_msg or "internal server error" in error_lower:
            return "External service error - add retry policy and contact service provider if persistent"

        # File errors
        if "file not found" in error_lower or "no such file" in error_lower:
            return "Verify file path is correct and file exists. Check previous node outputs."

        if "permission denied" in error_lower:
            return "Check file permissions and ensure write access to the directory"

        # Data errors
        if "json" in error_lower and ("parse" in error_lower or "decode" in error_lower):
            return "Check that the input data is valid JSON format"

        if "schema" in error_lower or "validation" in error_lower:
            return "Verify input data matches the expected schema/format"

        # Plugin errors
        if "plugin not found" in error_lower:
            return "Check plugin name is correct and plugin is registered in the registry"

        if "missing required" in error_lower or "required field" in error_lower:
            return "Add missing required input parameters to the node configuration"

        # Generic suggestion
        return "Review error message and node configuration. Check input data format and dependencies."
