"""The FastAPI application `jk serve` runs.

It has no authentication, because it is one person's own tool talking to their
own database. It also has no CORS: the panel is served from the same origin as
the API. `guard.PanelOnly` keeps every other web page in the browser out.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from jk.web import static
from jk.web.deps import Services
from jk.web.errors import ApiError
from jk.web.guard import PanelOnly
from jk.web.routers import events, flows, jenkins, presets, saved_flows

WEB_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"


def create_app(
    services: Services,
    *,
    dist: Path | None = None,
    serve_static: bool = True,
    background: bool = True,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        tasks: list[asyncio.Task[None]] = []
        if background:
            await services.supervisor.start()
            tasks.append(asyncio.create_task(_first_look(services)))
            tasks.append(asyncio.create_task(services.drift.run_forever(services.publish_preset)))
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            for task in tasks:
                # A task that failed long ago raises again when awaited; the
                # supervisor and the bus are shut down all the same.
                with suppress(asyncio.CancelledError, Exception):
                    await task
            await services.supervisor.shutdown()
            await services.bus.shutdown()

    app = FastAPI(title="JK", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.services = services

    @app.exception_handler(ApiError)
    async def api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})

    for router in (
        presets.router,
        saved_flows.router,
        flows.router,
        jenkins.router,
        events.router,
    ):
        app.include_router(router)

    if serve_static:
        static.mount(app, dist or WEB_DIST)
    app.add_middleware(PanelOnly)
    return app


async def _first_look(services: Services) -> None:
    """Check the token and index the controller once, in the background."""
    await services.check_token()
    await services.indexer.refresh()
    services.bus.publish("index.refreshed", {})
