#!/usr/bin/env python3
"""
Configurable Agent Demo

This example demonstrates:
- Creating agents from YAML configuration files (no code required)
- Loading pre-configured agent templates (code reviewer, data analyzer, API monitor)
- Budget control integration with spending limits
- State persistence across agent executions
- Real-time monitoring in the web UI

Prerequisites:
- OPENROUTER_API_KEY set in .env file
- Docker containers running
- Example YAML configs in src/examples/agent_configs/

Expected output:
- Creates and runs three different configurable agents
- Code Reviewer: Analyzes Python code for issues
- Data Analyzer: Processes sales data and finds trends
- API Monitor: Checks endpoint health (simulated)
- Shows cost tracking and budget enforcement
- Demonstrates state persistence between runs

Key concepts illustrated:
- YAML-based agent configuration
- AgentConfigParser for loading configs
- Capability-based agent design
- Budget limits and cost tracking
- Template-driven agent creation

Usage:
    docker compose exec app python src/examples/configurable_agent_demo.py
"""

import asyncio
import json
import os
import yaml
from pathlib import Path
from datetime import datetime

from src.agents.configurable_agent import ConfigurableAgent
from src.config.agent_config_parser import AgentConfigParser
from src.capabilities.capability_registry import CapabilityRegistry
from src.infrastructure.execution_runtime.prompt_executor import PromptExecutor
from src.llm.openrouter_client import OpenRouterClient

# Budget control
from src.budget.redis_budget_controller import RedisBudgetController
from src.interfaces.budget_controller import BudgetConfig, ResourceLimit, ResourceType

# State management
from src.infrastructure.state.redis_state_store import RedisStateStore
from src.interfaces.state_store import StateType

# Template versioning
from src.templates.redis_template_versioning import RedisTemplateVersioning

# Context management
from src.context.redis_context_manager import RedisContextManager
from src.interfaces.context_manager import ContextIsolationLevel


async def demo_basic_agent():
    """Demo 1: Basic ConfigurableAgent usage"""
    print("\n=== Demo 1: Basic ConfigurableAgent ===")
    
    # Load configuration from YAML
    config_path = Path(__file__).parent / "agent_configs" / "data_analyzer.yaml"
    with open(config_path, 'r') as f:
        config_dict = yaml.safe_load(f)
    
    # Parse configuration
    parser = AgentConfigParser()
    config = await parser.parse(config_dict)
    
    # Validate configuration
    validation = await parser.validate(config)
    print(f"Configuration valid: {validation['valid']}")
    if validation['warnings']:
        print(f"Warnings: {validation['warnings']}")
    
    # Setup components
    capability_registry = CapabilityRegistry()
    llm_client = OpenRouterClient()  # Make sure OPENROUTER_API_KEY is set
    prompt_executor = PromptExecutor(llm_client)
    
    # Create agent
    agent = ConfigurableAgent(
        agent_id="demo-analyzer-001",
        config=config,
        capability_binder=capability_registry,
        prompt_executor=prompt_executor
    )
    
    # Wait for initialization
    await asyncio.sleep(0.1)
    
    # Execute task
    task = {
        "data_type": "sales_metrics",
        "content": "Q4 2023: Revenue $2.5M (+15% YoY), New customers: 1,200 (+20% YoY), Churn rate: 2.5% (-0.5% YoY)"
    }
    
    print(f"\nExecuting task: {task}")
    result = await agent.execute(task)
    
    print(f"\nResult Status: {result.state}")
    print(f"Execution Time: {result.metadata.get('execution_time', 'N/A')}s")
    
    if result.result:
        print("\nAgent Output:")
        print(json.dumps(result.result, indent=2))
    
    if result.error:
        print(f"Error: {result.error}")
    
    # Clean up
    await agent.cleanup()


async def demo_agent_with_budget():
    """Demo 2: ConfigurableAgent with budget control"""
    print("\n\n=== Demo 2: Agent with Budget Control ===")
    
    # Setup budget controller
    budget_controller = RedisBudgetController(
        redis_url="redis://redis:6379",
        db=1,
        key_prefix="demo:budget"
    )
    
    # Create budget configuration
    budget_config = BudgetConfig(
        limits=[
            ResourceLimit(
                resource_type=ResourceType.LLM_CALLS,
                limit=5,
                hard_limit=True
            ),
            ResourceLimit(
                resource_type=ResourceType.LLM_TOKENS,
                limit=2000,
                hard_limit=True
            ),
            ResourceLimit(
                resource_type=ResourceType.LLM_COST,
                limit=0.10,  # $0.10
                hard_limit=True
            )
        ],
        owner="demo_user",
        created_at=datetime.utcnow(),
        metadata={"demo": True}
    )
    
    agent_id = "demo-budget-agent-001"
    await budget_controller.create_budget(agent_id, budget_config)
    
    # Load configuration
    config_path = Path(__file__).parent / "agent_configs" / "data_analyzer.yaml"
    with open(config_path, 'r') as f:
        config_dict = yaml.safe_load(f)
    
    parser = AgentConfigParser()
    config = await parser.parse(config_dict)
    
    # Create agent with budget control
    capability_registry = CapabilityRegistry()
    llm_client = OpenRouterClient()
    prompt_executor = PromptExecutor(llm_client)
    
    agent = ConfigurableAgent(
        agent_id=agent_id,
        config=config,
        budget_controller=budget_controller,
        capability_binder=capability_registry,
        prompt_executor=prompt_executor
    )
    
    await asyncio.sleep(0.1)
    
    # Execute multiple tasks to demonstrate budget tracking
    tasks = [
        {"data_type": "customer_feedback", "content": "Positive: 85%, Negative: 10%, Neutral: 5%"},
        {"data_type": "performance_metrics", "content": "API latency: 45ms, Error rate: 0.01%"},
        {"data_type": "financial_summary", "content": "Revenue: $500K, Expenses: $300K, Profit: $200K"}
    ]
    
    for i, task in enumerate(tasks):
        print(f"\n--- Task {i+1} ---")
        
        # Check budget before execution
        usage = await budget_controller.get_usage(agent_id)
        print("Current Budget Usage:")
        for u in usage:
            print(f"  {u.resource_type.value}: {u.current}/{u.limit}")
        
        # Execute task
        result = await agent.execute(task)
        print(f"Result: {result.state}")
        
        if result.state == "FAILED" and "Budget exceeded" in str(result.error):
            print("Budget exceeded! Stopping execution.")
            break
    
    # Final budget report
    print("\n--- Final Budget Report ---")
    usage = await budget_controller.get_usage(agent_id)
    for u in usage:
        percentage = (u.current / u.limit * 100) if u.limit > 0 else 0
        print(f"{u.resource_type.value}: {u.current}/{u.limit} ({percentage:.1f}%)")
    
    await agent.cleanup()


async def demo_agent_with_state_persistence():
    """Demo 3: Agent with state persistence"""
    print("\n\n=== Demo 3: Agent with State Persistence ===")
    
    # Setup state store
    state_store = RedisStateStore(
        redis_url="redis://redis:6379",
        db=2,
        key_prefix="demo:state"
    )
    
    agent_id = "demo-persistent-agent-001"
    
    # Load configuration
    config_path = Path(__file__).parent / "agent_configs" / "code_reviewer.yaml"
    with open(config_path, 'r') as f:
        config_dict = yaml.safe_load(f)
    
    parser = AgentConfigParser()
    config = await parser.parse(config_dict)
    
    # Create agent with state persistence
    capability_registry = CapabilityRegistry()
    llm_client = OpenRouterClient()
    prompt_executor = PromptExecutor(llm_client)
    
    print("\n--- Creating first agent instance ---")
    agent1 = ConfigurableAgent(
        agent_id=agent_id,
        config=config,
        state_store=state_store,
        capability_binder=capability_registry,
        prompt_executor=prompt_executor
    )
    
    await asyncio.sleep(0.1)
    
    # Execute task
    task = {
        "language": "python",
        "filename": "example.py",
        "code": """
def calculate_average(numbers):
    total = 0
    for num in numbers:
        total += num
    return total / len(numbers)
"""
    }
    
    result1 = await agent1.execute(task)
    print(f"First execution result: {result1.state}")
    
    # Save some additional state
    agent1._state["review_count"] = 1
    agent1._state["last_review_date"] = datetime.utcnow().isoformat()
    
    # Clean up first agent
    await agent1.cleanup()
    print("\nFirst agent cleaned up, state saved to Redis")
    
    # Create second agent instance with same ID
    print("\n--- Creating second agent instance with same ID ---")
    agent2 = ConfigurableAgent(
        agent_id=agent_id,
        config=config,
        state_store=state_store,
        capability_binder=capability_registry,
        prompt_executor=prompt_executor
    )
    
    await asyncio.sleep(0.1)
    await agent2.initialize()
    
    # Check if state was restored
    print("\nRestored state:")
    print(f"  Review count: {agent2._state.get('review_count', 'Not found')}")
    print(f"  Last review date: {agent2._state.get('last_review_date', 'Not found')}")
    print(f"  Previous results available: {'quality_score' in agent2._state}")
    
    # Execute another task
    task2 = {
        "language": "python",
        "filename": "example2.py",
        "code": """
def divide_numbers(a, b):
    return a / b  # Missing zero check!
"""
    }
    
    result2 = await agent2.execute(task2)
    print(f"\nSecond execution result: {result2.state}")
    
    # Update state
    agent2._state["review_count"] = agent2._state.get("review_count", 0) + 1
    
    await agent2.cleanup()
    
    # Show state history
    print("\n--- State History ---")
    history = await state_store.get_state_history(agent_id, limit=5)
    for i, snapshot in enumerate(history):
        print(f"\nSnapshot {i+1}:")
        print(f"  ID: {snapshot.id}")
        print(f"  Type: {snapshot.state_type}")
        print(f"  Timestamp: {snapshot.timestamp}")
        print(f"  Review count: {snapshot.data.get('review_count', 'N/A')}")


async def demo_agent_from_template():
    """Demo 4: Creating agents from versioned templates"""
    print("\n\n=== Demo 4: Agent from Versioned Template ===")
    
    # Setup template versioning
    template_versioning = RedisTemplateVersioning(
        redis_url="redis://redis:6379",
        db=3,
        key_prefix="demo:templates"
    )
    
    # Create a template
    template_content = {
        "name": "api-health-checker",
        "type": "monitor",
        "version": "1.0.0",
        "description": "Template for API health monitoring agents",
        "parameters": [
            {"name": "check_interval", "type": "integer", "default": 60},
            {"name": "timeout", "type": "integer", "default": 30},
            {"name": "alert_threshold", "type": "float", "default": 0.95}
        ],
        "capabilities": [
            {
                "tool": "api_call",
                "config": {
                    "timeout": "{timeout}",
                    "retry_count": 3
                }
            }
        ],
        "prompt_template": """Check the health of the API endpoint:
URL: {url}
Method: {method}
Response: {response}
Response Time: {response_time}ms

Alert threshold: {alert_threshold}

Provide health assessment in JSON format.""",
        "execution_strategy": "sequential",
        "state_schema": {
            "required": ["url", "method"],
            "output": ["status", "health_score", "alert"]
        },
        "resources": {
            "model": "gpt-3.5-turbo",
            "max_tokens": 500,
            "timeout": "{timeout}"
        },
        "success_metrics": [
            {
                "metric": "health_score",
                "threshold": "{alert_threshold}",
                "operator": "gte"
            }
        ]
    }
    
    # Create and approve template
    template_id = "api-health-checker-v1"
    version = await template_versioning.create_template(
        template_id,
        template_content,
        "demo_user",
        "human",
        "Initial version of API health checker"
    )
    
    print(f"Created template: {template_id}")
    print(f"Version ID: {version.id}")
    
    # Approve template
    await template_versioning.approve_version(
        version.id,
        "demo_approver",
        "Approved for production use"
    )
    
    print("Template approved!")
    
    # Create agent from template with custom parameters
    parser = AgentConfigParser()
    
    # Get latest approved version
    latest = await template_versioning.get_latest_version(
        template_id,
        approved_only=True
    )
    
    # Customize parameters
    config_dict = latest.content.copy()
    config_dict["resources"]["timeout"] = 45  # Override default timeout
    config_dict["success_metrics"][0]["threshold"] = 0.90  # Lower threshold
    
    # Parse into config
    config = await parser.parse(config_dict)
    
    # Create agent
    capability_registry = CapabilityRegistry()
    llm_client = OpenRouterClient()
    prompt_executor = PromptExecutor(llm_client)
    
    agent = ConfigurableAgent(
        agent_id="demo-template-agent-001",
        config=config,
        capability_binder=capability_registry,
        prompt_executor=prompt_executor
    )
    
    await asyncio.sleep(0.1)
    
    # Execute monitoring task
    task = {
        "url": "https://api.example.com/health",
        "method": "GET",
        "response": '{"status": "ok", "uptime": 99.95}',
        "response_time": 45,
        "alert_threshold": 0.90
    }
    
    result = await agent.execute(task)
    print(f"\nExecution result: {result.state}")
    
    if result.result:
        print("\nHealth Check Result:")
        print(json.dumps(result.result, indent=2))
    
    # Show template usage stats
    stats = await template_versioning.get_usage_stats(template_id)
    print(f"\nTemplate Usage Stats:")
    print(f"  Total versions: {stats.get('total_versions', 0)}")
    print(f"  Active version: {stats.get('active_version', 'None')}")
    
    await agent.cleanup()


async def demo_hierarchical_agents():
    """Demo 5: Hierarchical agents with parent-child relationships"""
    print("\n\n=== Demo 5: Hierarchical Agents ===")
    
    # Setup components
    budget_controller = RedisBudgetController(
        redis_url="redis://redis:6379",
        db=4,
        key_prefix="demo:hierarchical"
    )
    
    context_manager = RedisContextManager(
        redis_url="redis://redis:6379",
        db=5,
        key_prefix="demo:context"
    )
    
    # Create parent budget
    parent_id = "demo-parent-agent"
    parent_budget = BudgetConfig(
        limits=[
            ResourceLimit(
                resource_type=ResourceType.LLM_CALLS,
                limit=10,
                hard_limit=True
            ),
            ResourceLimit(
                resource_type=ResourceType.LLM_TOKENS,
                limit=5000,
                hard_limit=True
            )
        ],
        owner="demo_user",
        created_at=datetime.utcnow(),
        metadata={"type": "parent"}
    )
    
    await budget_controller.create_budget(parent_id, parent_budget)
    
    # Create parent context with shared configuration
    parent_context_id = await context_manager.create_context(
        agent_id=parent_id,
        isolation_level=ContextIsolationLevel.DEEP,
        variables={
            "environment": "production",
            "api_key": os.environ.get("DEMO_SHARED_API_KEY", "demo-placeholder-key"),
            "base_url": "https://api.example.com"
        }
    )
    
    print(f"Created parent agent: {parent_id}")
    print(f"Parent context ID: {parent_context_id}")
    
    # Create child agents with different isolation levels
    child_configs = [
        {
            "id": "demo-child-analyzer",
            "type": "analyzer",
            "isolation": ContextIsolationLevel.SHALLOW,  # Inherits parent context
            "budget_limit": 3
        },
        {
            "id": "demo-child-validator",
            "type": "validator", 
            "isolation": ContextIsolationLevel.SANDBOXED,  # Isolated context
            "budget_limit": 2
        }
    ]
    
    capability_registry = CapabilityRegistry()
    llm_client = OpenRouterClient()
    prompt_executor = PromptExecutor(llm_client)
    
    for child_config in child_configs:
        child_id = child_config["id"]
        
        # Create child budget
        child_budget = BudgetConfig(
            limits=[
                ResourceLimit(
                    resource_type=ResourceType.LLM_CALLS,
                    limit=child_config["budget_limit"],
                    hard_limit=True
                )
            ],
            owner="demo_user",
            created_at=datetime.utcnow(),
            metadata={"type": "child", "parent": parent_id}
        )
        
        await budget_controller.create_child_budget(
            parent_id,
            child_id,
            child_budget
        )
        
        # Fork context with specified isolation
        from src.interfaces.context_manager import ContextForkOptions
        
        fork_options = ContextForkOptions(
            isolation_level=child_config["isolation"],
            inherit_variables=True,
            inherit_shared_resources=True
        )
        
        child_context_id = await context_manager.fork_context(
            parent_context_id,
            child_id,
            fork_options
        )
        
        print(f"\nCreated child agent: {child_id}")
        print(f"  Type: {child_config['type']}")
        print(f"  Isolation: {child_config['isolation'].value}")
        print(f"  Budget limit: {child_config['budget_limit']} calls")
        
        # Load appropriate config
        config_file = "data_analyzer.yaml" if child_config["type"] == "analyzer" else "code_reviewer.yaml"
        config_path = Path(__file__).parent / "agent_configs" / config_file
        
        with open(config_path, 'r') as f:
            config_dict = yaml.safe_load(f)
        
        parser = AgentConfigParser()
        config = await parser.parse(config_dict)
        
        # Create child agent
        agent = ConfigurableAgent(
            agent_id=child_id,
            config=config,
            budget_controller=budget_controller,
            context_manager=context_manager,
            capability_binder=capability_registry,
            prompt_executor=prompt_executor
        )
        
        await asyncio.sleep(0.1)
        
        # Execute task based on agent type
        if child_config["type"] == "analyzer":
            task = {
                "data_type": "performance",
                "content": "CPU: 45%, Memory: 60%, Disk: 75%"
            }
        else:
            task = {
                "language": "python",
                "filename": "test.py",
                "code": "print('Hello from child agent')"
            }
        
        result = await agent.execute(task)
        print(f"  Execution result: {result.state}")
        
        # Check context
        ctx = await context_manager.get_context(child_context_id)
        if child_config["isolation"] == ContextIsolationLevel.SHALLOW:
            print(f"  Has parent API key: {'api_key' in ctx.variables}")
        else:
            print(f"  Isolated from parent: {'api_key' not in ctx.variables}")
        
        await agent.cleanup()
    
    # Show final budget usage
    print("\n--- Hierarchical Budget Report ---")
    
    # Parent budget
    parent_usage = await budget_controller.get_usage(parent_id)
    print(f"\nParent Agent ({parent_id}):")
    for u in parent_usage:
        print(f"  {u.resource_type.value}: {u.current}/{u.limit}")
    
    # Child budgets
    for child_config in child_configs:
        child_usage = await budget_controller.get_usage(child_config["id"])
        print(f"\nChild Agent ({child_config['id']}):")
        for u in child_usage:
            print(f"  {u.resource_type.value}: {u.current}/{u.limit}")


async def main():
    """Run all demos"""
    print("=" * 60)
    print("ConfigurableAgent Demo Script")
    print("=" * 60)
    
    demos = [
        ("Basic Agent", demo_basic_agent),
        ("Agent with Budget Control", demo_agent_with_budget),
        ("Agent with State Persistence", demo_agent_with_state_persistence),
        ("Agent from Template", demo_agent_from_template),
        ("Hierarchical Agents", demo_hierarchical_agents)
    ]
    
    print("\nAvailable demos:")
    for i, (name, _) in enumerate(demos, 1):
        print(f"{i}. {name}")
    print(f"{len(demos) + 1}. Run all demos")
    print("0. Exit")
    
    while True:
        try:
            choice = input("\nSelect demo (0-6): ")
            choice = int(choice)
            
            if choice == 0:
                break
            elif 1 <= choice <= len(demos):
                await demos[choice - 1][1]()
            elif choice == len(demos) + 1:
                for name, demo_func in demos:
                    await demo_func()
            else:
                print("Invalid choice")
        except ValueError:
            print("Please enter a number")
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    # Run the demo
    asyncio.run(main())