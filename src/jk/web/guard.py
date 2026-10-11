"""Only the panel itself may talk to the panel.

The server has no login: it is one person's tool on their own computer. That is
safe only if no other web page open in the same browser can use it.

- **Host.** Every request must name a loopback host. A page on another domain
  that re-points its name at 127.0.0.1 (DNS rebinding) sends its own name here
  and is refused, so it can neither read nor write.
- **Writes.** A request that changes anything must carry `X-JK-Panel: 1`. A
  browser does not let another site add a custom header without asking this
  server first, and this server never agrees, so a form post, an image, or a
  `no-cors` fetch from elsewhere is refused before it reaches a route.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
PANEL_HEADER = "x-jk-panel"
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

NOT_LOOPBACK = "JK answers only to its own address on this computer."
NOT_THE_PANEL = "JK accepts changes only from its own panel."


def host_of(value: str) -> str:
    """`127.0.0.1:8765` -> `127.0.0.1`; `[::1]:8765` -> `::1`."""
    return (urlsplit(f"//{value}").hostname or "").lower()


class PanelOnly:
    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        headers = {
            name.decode("latin-1").lower(): value.decode("latin-1")
            for name, value in scope["headers"]
        }

        if host_of(headers.get("host", "")) not in LOOPBACK_HOSTS:
            await _refuse(scope, receive, send, "not_loopback", NOT_LOOPBACK)
            return

        if scope["method"] not in SAFE_METHODS and headers.get(PANEL_HEADER) != "1":
            await _refuse(scope, receive, send, "not_the_panel", NOT_THE_PANEL)
            return

        await self._app(scope, receive, send)


async def _refuse(scope: Scope, receive: Receive, send: Send, code: str, message: str) -> None:
    response = JSONResponse(status_code=403, content={"error": {"code": code, "message": message}})
    await response(scope, receive, send)
