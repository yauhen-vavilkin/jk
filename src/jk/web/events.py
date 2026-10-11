"""The live stream the board listens to.

One queue per open browser tab. A flow that changes ten times a second is sent
once a second with the latest state, because the board only ever renders the
latest state anyway.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any

#: At most one `flow.updated` per flow per second.
THROTTLE_SECONDS = 1.0

#: A comment line keeps the connection open through a proxy that times out.
HEARTBEAT_SECONDS = 15.0

QUEUE_LIMIT = 256


#: What a subscriber's queue holds: the event name and its data.
Message = tuple[str, Any]


class EventBus:
    def __init__(self, *, throttle: float = THROTTLE_SECONDS) -> None:
        self._subscribers: set[asyncio.Queue[Message]] = set()
        self._throttle = throttle
        self._last_sent: dict[str, float] = {}
        self._pending: dict[str, asyncio.Task[None]] = {}

    def subscribe(self) -> asyncio.Queue[Message]:
        queue: asyncio.Queue[Message] = asyncio.Queue(maxsize=QUEUE_LIMIT)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[Message]) -> None:
        self._subscribers.discard(queue)

    def publish(self, event: str, data: Any) -> None:
        """Send now. A full queue drops the oldest event, never the newest."""
        message = (event, data)
        for queue in list(self._subscribers):
            if queue.full():
                with suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            with suppress(asyncio.QueueFull):
                queue.put_nowait(message)

    def publish_flow(self, flow_id: str, data: Any) -> None:
        """Coalesce per flow: at most one update a second, latest wins."""
        now = time.monotonic()
        last = self._last_sent.get(flow_id)
        waiting = self._pending.get(flow_id)
        if waiting is not None and not waiting.done():
            waiting.cancel()
        if last is None or now - last >= self._throttle:
            self._last_sent[flow_id] = now
            self.publish("flow.updated", data)
            return
        delay = self._throttle - (now - last)
        self._pending[flow_id] = asyncio.get_running_loop().create_task(
            self._publish_later(flow_id, data, delay)
        )

    async def _publish_later(self, flow_id: str, data: Any, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        self._last_sent[flow_id] = time.monotonic()
        self.publish("flow.updated", data)

    async def stream(
        self, queue: asyncio.Queue[Message], *, heartbeat: float = HEARTBEAT_SECONDS
    ) -> AsyncIterator[dict[str, Any]]:
        """Server-sent events for one subscriber, with a heartbeat between them."""
        try:
            while True:
                try:
                    event, data = await asyncio.wait_for(queue.get(), timeout=heartbeat)
                except TimeoutError:
                    yield {"comment": "ping"}
                    continue
                yield {"event": event, "data": json.dumps(data)}
        finally:
            self.unsubscribe(queue)

    async def shutdown(self) -> None:
        for task in list(self._pending.values()):
            task.cancel()
        self._pending.clear()
        self._subscribers.clear()
