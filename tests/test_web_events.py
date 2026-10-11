"""The SSE stream: coalescing, heartbeat, and what the board is told."""

from __future__ import annotations

import asyncio

import pytest

from jk.web.events import EventBus


@pytest.fixture
def bus() -> EventBus:
    return EventBus(throttle=0.05)


async def drain(queue: asyncio.Queue, *, settle: float = 0.15) -> list:
    await asyncio.sleep(settle)
    found = []
    while not queue.empty():
        found.append(queue.get_nowait())
    return found


async def test_flow_updates_are_coalesced_to_one_per_flow_per_window(bus: EventBus) -> None:
    queue = bus.subscribe()

    for index in range(10):
        bus.publish_flow("flow-a", {"id": "flow-a", "n": index})

    received = await drain(queue)

    # The first one goes out at once; the rest collapse into the latest state.
    assert [data["n"] for _, data in received] == [0, 9]


async def test_two_flows_do_not_throttle_each_other(bus: EventBus) -> None:
    queue = bus.subscribe()

    bus.publish_flow("flow-a", {"id": "flow-a"})
    bus.publish_flow("flow-b", {"id": "flow-b"})

    assert {data["id"] for _, data in await drain(queue)} == {"flow-a", "flow-b"}


async def test_the_stream_sends_a_heartbeat_when_nothing_happens(bus: EventBus) -> None:
    stream = bus.stream(bus.subscribe(), heartbeat=0.05)

    assert await asyncio.wait_for(anext(stream), timeout=1) == {"comment": "ping"}


async def test_the_stream_sends_the_data_as_json(bus: EventBus) -> None:
    stream = bus.stream(bus.subscribe())
    bus.publish("jenkins.status", {"reachable": True})

    assert await asyncio.wait_for(anext(stream), timeout=1) == {
        "event": "jenkins.status",
        "data": '{"reachable": true}',
    }


async def test_a_dropped_subscriber_is_forgotten(bus: EventBus) -> None:
    queue = bus.subscribe()

    bus.unsubscribe(queue)
    bus.publish("jenkins.status", {})

    assert queue.empty()
