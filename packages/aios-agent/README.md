# aios-agent

Python port of `pi-mono/packages/agent`.

`aios-agent` provides:
- Stateful agent runtime (`Agent`) with prompt/continue flows
- Agent loop primitives (`agent_loop`, `agent_loop_continue`)
- Tool execution with streaming update events
- Steering and follow-up queues
- Optional proxy stream adapter (`stream_proxy`)

## Installation

```bash
pip install -e packages/aios-agent
```

## Quick Start

```python
import asyncio

from aios_agent import Agent, AgentOptions
from aios_agent.types import (
    AssistantDoneEvent,
    AssistantMessage,
    Context,
    Model,
    TextContent,
    Usage,
    UsageCost,
)
from aios_agent.event_stream import EventStream


class MockAssistantStream(EventStream):
    def __init__(self):
        super().__init__(
            lambda event: event.type in {"done", "error"},
            lambda event: event.message if event.type == "done" else event.error,
        )


def stream_fn(model: Model, context: Context, options):
    stream = MockAssistantStream()
    message = AssistantMessage(
        content=[TextContent(text="Hello from Python agent")],
        api=model.api,
        provider=model.provider,
        model=model.id,
        usage=Usage(cost=UsageCost()),
        stop_reason="stop",
    )
    stream.push(AssistantDoneEvent(reason="stop", message=message))
    return stream


async def main():
    agent = Agent(
        AgentOptions(
            stream_fn=stream_fn,
            initial_state={
                "system_prompt": "You are helpful.",
                "model": Model(id="mock", name="mock", api="mock", provider="mock"),
            },
        )
    )

    agent.subscribe(lambda event: print(event.type))
    await agent.prompt("Hello")


asyncio.run(main())
```

## Testing

```bash
cd packages/aios-agent
pip install -e ".[dev]"
pytest tests/unit -v
```

Run full suite (unit + e2e scaffolding):

```bash
pytest tests -v
```

## Release Tracking

- Keep package changes tracked in `CHANGELOG.md`.
- For every release:
  1. Update `pyproject.toml` version.
  2. Add a new dated section in `CHANGELOG.md`.
  3. Publish and tag the release.
