"""Stopping a build the user asked to stop.

The second and last place JK writes to Jenkins. Every rule the submitter obeys
applies here: one attempt, never retried, and an unknown outcome is reported as
a failed request rather than tried again.
"""

from __future__ import annotations

from urllib.parse import urlparse

import httpx

#: What happened to the one request. The card shows the word.
REQUESTED = "requested"
ACCEPTED = "accepted"
FAILED = "failed"


class JenkinsAborter:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def stop_build(self, build_url: str) -> str:
        """One `POST <build_url>/stop`. Returns ACCEPTED or FAILED."""
        path = urlparse(build_url).path.rstrip("/")
        return await self._write(f"{path}/stop", params=None)

    async def cancel_queue_item(self, queue_id: int) -> str:
        """One `POST /queue/cancelItem?id=<id>`. Returns ACCEPTED or FAILED."""
        return await self._write("/queue/cancelItem", params={"id": str(queue_id)})

    async def _write(self, path: str, *, params: dict[str, str] | None) -> str:
        try:
            response = await self._client.post(path, params=params)
        except httpx.HTTPError:
            # The request may or may not have reached Jenkins. It is never re-sent.
            return FAILED
        # Jenkins answers a stop with 200, or with a redirect back to the build.
        return ACCEPTED if response.status_code < 400 else FAILED
