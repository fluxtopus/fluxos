# Tentackl Examples

Workflow YAML examples are deprecated and have been removed. The system now centers on Tasks and Flux (InboxAgent) for durable execution and orchestration.

**Maintained Examples**
- `configurable_agent_demo.py` — YAML-based agent configuration (capabilities + templates).
- `simple_llm_demo.py` — basic LLM agent execution.
- `external_events_demo.py` — event gateway / external event publishing demo.
- `workspace_events_demo.py` — workspace event ingestion and handling.
- `memory_showcase.sh` — memory storage + retrieval demo.
- `weather_field_management.py` — end-to-end multi-agent orchestration using Tasks + event bus patterns.
- `mock_roundtrip_demo.py` — event flow and webhook roundtrip demo.
- `resource_monitoring_demo.py` — resource monitoring and reporting.
- `monitor_redis_events.py` — Redis event visibility.
- `test_metrics.py` — Prometheus metrics sanity check.
- `test_metrics_simple_agent.py` — agent execution metrics smoke test.

**Running Examples**
```bash
docker compose exec tentackl python src/examples/simple_llm_demo.py
docker compose exec tentackl python src/examples/configurable_agent_demo.py
```

**Prerequisites**
- Docker + Docker Compose
- `.env` with LLM credentials as needed (e.g., `OPENROUTER_API_KEY`)

**Notes**
- Files prefixed `test_` are ad-hoc scripts for manual debugging and may rely on running services.
- Examples that depended on workflow YAML or workflow state APIs were removed to prevent drift.
