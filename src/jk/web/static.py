"""Serve the built frontend, with the single-page fallback it needs.

Anything that is not a file and not an API route is the application shell: the
router in the browser decides what it means.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

NOT_BUILT = (
    "The web panel has not been built yet. Run `npm install && npm run build` in web/, "
    "or start `jk serve --dev` and use the Vite server."
)


def mount(app: FastAPI, dist: Path) -> None:
    index = dist / "index.html"

    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
    if (dist / "fonts").is_dir():
        app.mount("/fonts", StaticFiles(directory=dist / "fonts"), name="fonts")

    @app.get("/{path:path}", include_in_schema=False)
    async def shell(path: str):
        candidate = (dist / path).resolve()
        if path and dist.resolve() in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        if not index.is_file():
            return PlainTextResponse(NOT_BUILT, status_code=503)
        return FileResponse(index)
