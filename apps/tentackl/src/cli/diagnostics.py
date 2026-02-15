import asyncio
import json
import click
from rich.console import Console
from rich.table import Table

from src.core.config import settings
from src.llm.openrouter_client import OpenRouterClient
from src.interfaces.llm import LLMMessage


console = Console()


@click.group()
def diagnostics():
    """Diagnostics and connectivity checks"""
    pass


@diagnostics.command("openrouter")
@click.option(
    "--model",
    default="openai/gpt-4o-mini",
    help="Model ID to test (via OpenRouter)",
    show_default=True,
)
@click.option(
    "--prompt",
    default="Reply with JSON: {\"reply\": \"pong\"}",
    help="Prompt to send in the test request",
    show_default=True,
)
@click.option(
    "--max-tokens",
    default=64,
    help="Max tokens for the test completion",
    show_default=True,
)
def openrouter_diag(model: str, prompt: str, max_tokens: int):
    """Test OpenRouter connectivity and a sample completion"""

    async def _run():
        # Check API key
        if not settings.OPENROUTER_API_KEY:
            console.print("[red]OPENROUTER_API_KEY is not set in the environment (.env).[/red]")
            console.print("Set it and try again.")
            return

        client = OpenRouterClient()
        try:
            async with client:
                # Health check
                healthy = await client.health_check()
                status = "healthy" if healthy else "unreachable"

                # Prepare a small request
                system = (
                    "You are a diagnostic assistant. Respond exactly as requested,"
                    " keep output short."
                )
                messages = [
                    LLMMessage(role="system", content=system),
                    LLMMessage(role="user", content=prompt),
                ]

                # Send completion
                result = await client.create_completion(
                    messages=messages,
                    model=model,
                    temperature=0.1,
                    max_tokens=max_tokens,
                )

                # Render results
                table = Table(title="OpenRouter Diagnostics")
                table.add_column("Check", style="cyan")
                table.add_column("Result", style="green")
                table.add_row("Health", status)
                table.add_row("Model", result.model or model)
                usage_str = json.dumps(result.usage or {}, indent=0)
                table.add_row("Usage", usage_str)

                console.print(table)

                console.print("[bold]Sample Response:[/bold]")
                console.print(result.content)

        except Exception as e:
            console.print(f"[red]OpenRouter test failed:[/red] {e}")

    asyncio.run(_run())


__all__ = ["diagnostics"]

