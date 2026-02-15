"""
Agent Runtime

Provides the AgentRuntime class that manages agent capabilities.
This is infrastructure - NOT an agent itself.

Usage:
    from src.runtime import AgentRuntime
    from src.capabilities import AgentCapabilities
    from src.capabilities.conversation_tracking import ConversationTrackingImpl

    runtime = AgentRuntime(
        capabilities=AgentCapabilities(
            conversations=ConversationTrackingImpl(db)
        )
    )
    await runtime.initialize()

    agent = LLMAgent(config, runtime=runtime)
    result = await agent.execute(task)

    await runtime.shutdown()
"""

from src.runtime.agent_runtime import AgentRuntime

__all__ = ["AgentRuntime"]
