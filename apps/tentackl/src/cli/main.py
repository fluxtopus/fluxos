import click
import asyncio
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from src.cli.agent_commands import agent_group
from src.cli.diagnostics import diagnostics
try:
    from src.cli.auth_cli import auth
except ImportError:
    auth = None

console = Console()


@click.group()
@click.version_option(version="0.1.0", prog_name="tentackl")
def cli():
    """
    Tentackl - Multi-Agent Task Management System
    
    Manage agents and orchestrate complex multi-agent tasks.
    """
    pass


# Add command groups
cli.add_command(agent_group)
cli.add_command(diagnostics)
if auth:
    cli.add_command(auth)


@cli.command()
def status():
    """Show system status"""
    console.print(Panel.fit(
        "[bold green]Tentackl System Status[/bold green]\n\n"
        "API: http://localhost:8000\n"
        "Flower: http://localhost:5555\n"
        "PostgreSQL: localhost:5432\n"
        "Redis: localhost:6379",
        title="System Status"
    ))


@cli.command()
def health():
    """Check system health"""
    import httpx
    
    async def check_health():
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get("http://localhost:8000/health")
                data = response.json()
                
                table = Table(title="Health Check Results")
                table.add_column("Service", style="cyan")
                table.add_column("Status", style="green")
                
                table.add_row("API", data.get("status", "unknown"))
                
                for service, info in data.get("checks", {}).items():
                    status = info.get("status", "unknown")
                    style = "green" if status == "healthy" else "red"
                    table.add_row(service.title(), f"[{style}]{status}[/{style}]")
                
                console.print(table)
                
        except Exception as e:
            console.print(f"[red]Error checking health: {e}[/red]")
    
    asyncio.run(check_health())


if __name__ == "__main__":
    cli()
