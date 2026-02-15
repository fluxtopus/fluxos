# REVIEW:
# - Uses local YAML config from examples path and hard-coded recipients; production behavior is unclear.
# - Swallows all exceptions in LLM path, making failures silent.
import os
import json
from typing import Any, Dict, List

from src.agents.configurable_agent import ConfigurableAgent
from src.config.agent_config_parser import AgentConfigParser
from src.infrastructure.execution_runtime.prompt_executor import PromptExecutor
from src.llm.openrouter_client import OpenRouterClient


class CommunicationCoordinatorAgent:
    """
    Agent to generate personalized messages for affected bookings.
    Uses LLM if available; otherwise creates simple deterministic messages.
    """

    def __init__(self):
        self._llm_enabled = False
        # Controlled via env as in orchestrator: disable if variable is set truthy
        if os.getenv("WEATHER_DISABLE_LLM", "").lower() in ("1", "true", "yes"):
            self._llm_enabled = False
        else:
            self._llm_enabled = bool(os.getenv("OPENROUTER_API_KEY"))

    async def generate_messages(
        self,
        location: str,
        severity: str,
        proposals: List[Dict[str, Any]],
        channel: str = "sms",
    ) -> List[Dict[str, Any]]:
        # Try LLM path
        if self._llm_enabled:
            try:
                import yaml
                cfg_path = os.path.join(
                    os.getcwd(),
                    "src",
                    "examples",
                    "agent_configs",
                    "communication_coordinator.yaml",
                )
                with open(cfg_path, "r") as f:
                    cfg_data = yaml.safe_load(f)

                parser = AgentConfigParser()
                agent_cfg = await parser.parse(cfg_data)
                async with OpenRouterClient() as llm:
                    executor = PromptExecutor(
                        llm_client=llm,
                        default_model=agent_cfg.resources.model,
                        default_temperature=getattr(agent_cfg.resources, "temperature", 0.5),
                    )
                    agent = ConfigurableAgent(
                        agent_id="communication_coordinator",
                        config=agent_cfg,
                        prompt_executor=executor,
                    )
                    await agent.initialize()
                    task = {
                        "location": location,
                        "severity": severity,
                        "proposals": proposals,
                        "channel": channel,
                    }
                    res = await agent.execute(task)
                    if isinstance(res.result, dict) and "messages" in res.result:
                        return res.result["messages"]
            except Exception:
                pass

        # Fallback deterministic messages
        recipients = [
            {"name": "Alex Costa", "phone": "+351900000001", "email": "alex@example.com"},
            {"name": "Maria Silva", "phone": "+351900000002", "email": "maria@example.com"},
            {"name": "João Santos", "phone": "+351900000003", "email": "joao@example.com"},
        ]
        msgs: List[Dict[str, Any]] = []
        for i, alt in enumerate(proposals[:3] or [{"hour": 19, "field": "Field-1"}]):
            rec = recipients[i % len(recipients)]
            content = (
                f"Weather update for {location} (severity: {severity}). "
                f"Suggested reschedule: {alt.get('hour', '?')}:00 at {alt.get('field', 'Field-1')}. "
                "Reply YES to confirm or contact support."
            )
            msgs.append({"channel": channel, "to": rec, "content": content})
        return msgs
