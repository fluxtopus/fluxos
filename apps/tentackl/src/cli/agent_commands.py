import click
import asyncio
import json
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from src.agents.supervisor import AgentSupervisor
from src.agents.base import AgentConfig
from src.agents.registry import register_default_agents

console = Console()


@click.group(name="agent")
def agent_group():
    """Agent management commands"""
    pass


@agent_group.command(name="start")
@click.argument("agent_name")
@click.option("--type", "-t", default="worker", help="Agent type")
@click.option("--task", "-k", help="Task JSON string")
@click.option("--task-file", "-f", type=click.File('r'), help="Task JSON file")
def start_agent(agent_name, type, task, task_file):
    """Start a new agent"""
    async def _start():
        # Register agents
        register_default_agents()
        
        # Parse task
        task_data = {}
        if task:
            task_data = json.loads(task)
        elif task_file:
            task_data = json.load(task_file)
        
        # Create supervisor
        supervisor = AgentSupervisor()
        
        # Create agent config
        config = AgentConfig(
            name=agent_name,
            agent_type=type
        )
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            progress.add_task(f"Starting agent {agent_name}...", total=None)
            
            try:
                agent_id = await supervisor.spawn_agent(config)
                await supervisor.start_agent(agent_id, task_data)
                
                console.print(f"[green]✓[/green] Agent {agent_name} started with ID: {agent_id}")
                
            except Exception as e:
                console.print(f"[red]✗[/red] Failed to start agent: {e}")
    
    asyncio.run(_start())


@agent_group.command(name="stop")
@click.argument("agent_id")
def stop_agent(agent_id):
    """Stop a running agent"""
    async def _stop():
        supervisor = AgentSupervisor()
        
        try:
            await supervisor.stop_agent(agent_id)
            console.print(f"[green]✓[/green] Agent {agent_id} stopped")
        except Exception as e:
            console.print(f"[red]✗[/red] Failed to stop agent: {e}")
    
    asyncio.run(_stop())


@agent_group.command(name="restart")
@click.argument("agent_id")
@click.option("--task", "-k", help="New task JSON string")
def restart_agent(agent_id, task):
    """Restart an agent"""
    async def _restart():
        supervisor = AgentSupervisor()
        
        task_data = json.loads(task) if task else {}
        
        try:
            await supervisor.restart_agent(agent_id, task_data)
            console.print(f"[green]✓[/green] Agent {agent_id} restarted")
        except Exception as e:
            console.print(f"[red]✗[/red] Failed to restart agent: {e}")
    
    asyncio.run(_restart())


@agent_group.command(name="list")
def list_agents():
    """List all agents"""
    async def _list():
        supervisor = AgentSupervisor()
        agents = supervisor.get_all_agents()
        
        if not agents:
            console.print("[yellow]No agents found[/yellow]")
            return
        
        table = Table(title="Active Agents")
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Type", style="blue")
        table.add_column("Status", style="yellow")
        table.add_column("Created", style="magenta")
        
        for agent in agents:
            table.add_row(
                agent["id"][:8],
                agent["name"],
                agent["type"],
                agent["status"],
                agent["created_at"]
            )
        
        console.print(table)
    
    asyncio.run(_list())


@agent_group.command(name="status")
@click.argument("agent_id")
def agent_status(agent_id):
    """Get agent status"""
    async def _status():
        supervisor = AgentSupervisor()
        status = supervisor.get_agent_status(agent_id)
        
        if status:
            console.print(f"Agent {agent_id} status: [bold]{status.value}[/bold]")
        else:
            console.print(f"[red]Agent {agent_id} not found[/red]")
    
    asyncio.run(_status())


@agent_group.command(name="types")
def list_types():
    """List available agent types"""
    register_default_agents()
    from src.agents.factory import AgentFactory
    
    types = AgentFactory.get_registered_types()
    
    table = Table(title="Available Agent Types")
    table.add_column("Type", style="cyan")
    table.add_column("Description", style="green")
    
    descriptions = {
        "worker": "Basic worker agent for general tasks",
        "parent": "Parent agent that can spawn child agents"
    }
    
    for agent_type in types:
        table.add_row(
            agent_type,
            descriptions.get(agent_type, "Custom agent type")
        )
    
    console.print(table)