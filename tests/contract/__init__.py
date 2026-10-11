"""The opt-in live contract checks and the transport that keeps them read-only."""

from __future__ import annotations

import httpx


class ReadOnlyTransport(httpx.AsyncBaseTransport):
    """Permit only GET requests through the opt-in live contract transport."""

    def __init__(self, wrapped: httpx.AsyncBaseTransport) -> None:
        self._wrapped = wrapped

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.method != "GET":
            raise RuntimeError("live contract transport allows only GET requests")
        return await self._wrapped.handle_async_request(request)

    async def aclose(self) -> None:
        await self._wrapped.aclose()
