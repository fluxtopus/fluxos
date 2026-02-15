#!/usr/bin/env python3
"""Simple test to generate agent execution metrics."""

import asyncio
import aiohttp
from src.agents.factory import AgentFactory
from src.agents.registry import register_default_agents
from src.agents.base import AgentConfig


async def check_metrics():
    """Check metrics endpoint."""
    async with aiohttp.ClientSession() as session:
        async with session.get('http://api:8000/metrics') as response:
            if response.status == 200:
                content = await response.text()
                
                # Look for specific metrics
                print("\n=== Checking Metrics ===")
                metrics = [
                    "tentackl_agent_executions_total",
                    "tentackl_agent_execution_duration_seconds",
                    "tentackl_workflow_active",
                    "tentackl_errors_total",
                    "tentackl_event_bus_messages_total",
                    "tentackl_redis_operations_total",
                    "tentackl_db_operations_total"
                ]
                
                for metric in metrics:
                    lines = [l for l in content.split('\n') if metric in l and not l.startswith('#')]
                    if lines:
                        print(f"✅ {metric}: {len(lines)} entries")
                        for line in lines[:2]:  # Show first 2
                            print(f"   {line}")
                    else:
                        print(f"❌ {metric}: Not found")


async def test_agent_metrics():
    """Run a simple agent to generate metrics."""
    print("Starting agent metrics test...")
    
    # Register default agents
    register_default_agents()
    
    # Check metrics before
    print("\n=== BEFORE ===")
    await check_metrics()
    
    # Create a simple worker agent
    config = AgentConfig(
        name="test-agent",
        agent_type="worker",
        timeout=10,
        capabilities=["test"]
    )
    
    # Create agent
    agent = AgentFactory.create(config)
    print(f"\nCreated agent: {agent.id}")
    
    # Execute agent
    task = {"action": "test", "data": "Hello metrics!"}
    try:
        print("Starting agent execution...")
        await agent.start(task)
        print("✅ Agent execution completed")
    except Exception as e:
        print(f"❌ Agent execution failed: {e}")
    
    # Wait for metrics to update
    await asyncio.sleep(1)
    
    # Check metrics after
    print("\n=== AFTER ===")
    await check_metrics()
    
    print("\nMetrics test completed!")


if __name__ == "__main__":
    asyncio.run(test_agent_metrics())