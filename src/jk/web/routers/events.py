"""The live stream the board listens to."""

from __future__ import annotations

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from jk.web.deps import services_of

router = APIRouter(prefix="/api", tags=["events"])


@router.get("/events")
async def events(request: Request) -> EventSourceResponse:
    bus = services_of(request).bus
    return EventSourceResponse(bus.stream(bus.subscribe()))
