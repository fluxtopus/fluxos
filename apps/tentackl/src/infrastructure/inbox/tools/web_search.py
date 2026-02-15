# REVIEW: Web search is routed through the LLM with no guardrails on cost,
# REVIEW: quota, or result filtering. Consider explicit rate limits, caching,
# REVIEW: and a clearer separation between retrieval and summarization.
"""Inbox tool: Web search via OpenRouter's native web plugin."""

from typing import Any, Dict

import structlog

from src.infrastructure.flux_runtime.tools.base import BaseTool, ToolDefinition, ToolResult
from src.llm.openrouter_client import OpenRouterClient, WebPlugin
from src.llm.model_selector import ModelSelector, TaskType
from src.interfaces.llm import LLMMessage

logger = structlog.get_logger(__name__)


class WebSearchTool(BaseTool):
    """Search the web using OpenRouter's native web plugin.

    Uses the ModelSelector WEB_RESEARCH routing and OpenRouter's
    built-in web plugin for real-time search with citations.
    """

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "Search the web for current information. Returns a summary with source URLs."

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query string.",
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Number of results to return (default 5).",
                    },
                },
                "required": ["query"],
            },
        )

    async def execute(
        self, arguments: Dict[str, Any], context: Dict[str, Any]
    ) -> ToolResult:
        query = arguments["query"]
        num_results = arguments.get("num_results", 5)

        try:
            routing = ModelSelector.get_routing(TaskType.WEB_RESEARCH)
            plugin = WebPlugin(max_results=num_results, search_prompt=query)

            async with OpenRouterClient() as client:
                response = await client.create_completion(
                    messages=[
                        LLMMessage(
                            role="user",
                            content=(
                                f"Search the web and provide a comprehensive answer for: {query}\n\n"
                                "Include all relevant facts and data."
                            ),
                        ),
                    ],
                    routing=routing,
                    plugins=[plugin],
                    temperature=0.2,
                )

            summary = response.content or ""
            citations = response.metadata.get("citations", []) if response.metadata else []

            return ToolResult(
                success=True,
                data={
                    "summary": summary,
                    "citations": citations,
                    "query": query,
                },
            )

        except Exception as e:
            logger.error("Web search failed", error=str(e), query=query)
            return ToolResult(success=False, error=f"Web search failed: {str(e)}")
