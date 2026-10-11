"""The opt-in contract suite reaches the real controller only through this transport."""

from __future__ import annotations

import httpx
import pytest

from tests.contract import ReadOnlyTransport


@pytest.mark.parametrize("method", ("DELETE", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"))
async def test_read_only_transport_rejects_non_get_before_wrapped_transport(
    method: str,
) -> None:
    """A missing method check would let a live contract test write to Jenkins."""
    wrapped_calls: list[str] = []

    async def wrapped_handler(request: httpx.Request) -> httpx.Response:
        wrapped_calls.append(request.method)
        return httpx.Response(204)

    transport = ReadOnlyTransport(httpx.MockTransport(wrapped_handler))
    async with httpx.AsyncClient(transport=transport, base_url="https://example.invalid") as client:
        with pytest.raises(RuntimeError, match="only GET requests"):
            await client.request(method, "/dangerous")

    assert wrapped_calls == []


async def test_read_only_transport_allows_get_to_reach_wrapped_transport() -> None:
    """Rejecting GET would make the opt-in contract suite unable to inspect Jenkins."""
    wrapped_calls: list[str] = []

    async def wrapped_handler(request: httpx.Request) -> httpx.Response:
        wrapped_calls.append(request.method)
        return httpx.Response(204)

    transport = ReadOnlyTransport(httpx.MockTransport(wrapped_handler))
    async with httpx.AsyncClient(transport=transport, base_url="https://example.invalid") as client:
        response = await client.get("/safe")

    assert response.status_code == 204
    assert wrapped_calls == ["GET"]
