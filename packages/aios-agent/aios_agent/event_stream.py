from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Generic, TypeVar

EventT = TypeVar("EventT")
ResultT = TypeVar("ResultT")


class EventStream(Generic[EventT, ResultT], AsyncIterator[EventT]):
    """A push-based async event stream with terminal result extraction."""

    def __init__(
        self,
        is_terminal_event: Callable[[EventT], bool],
        terminal_result: Callable[[EventT], ResultT],
    ) -> None:
        self._is_terminal_event = is_terminal_event
        self._terminal_result = terminal_result
        self._queue: asyncio.Queue[EventT | None] = asyncio.Queue()
        self._result_future: asyncio.Future[ResultT] = asyncio.get_running_loop().create_future()
        self._closed = False

    def push(self, event: EventT) -> None:
        if self._closed:
            return
        self._queue.put_nowait(event)

        if self._is_terminal_event(event) and not self._result_future.done():
            self._result_future.set_result(self._terminal_result(event))
            self._closed = True
            self._queue.put_nowait(None)

    def end(self, result: ResultT | None = None) -> None:
        if self._closed:
            return
        self._closed = True
        if result is not None and not self._result_future.done():
            self._result_future.set_result(result)
        elif result is None and not self._result_future.done():
            self._result_future.set_exception(RuntimeError("Event stream ended before terminal event"))
        self._queue.put_nowait(None)

    async def result(self) -> ResultT:
        return await self._result_future

    def __aiter__(self) -> EventStream[EventT, ResultT]:
        return self

    async def __anext__(self) -> EventT:
        item = await self._queue.get()
        if item is None:
            raise StopAsyncIteration
        return item

