"""Start the panel: recover, open the browser, serve.

The startup order must not change: pending submissions are recovered BEFORE
anything can reach Jenkins, so a crash during a POST can never be resumed into
a second POST.
"""

from __future__ import annotations

import threading
import webbrowser
from pathlib import Path

import uvicorn

from jk.jenkins.client import JenkinsConfig, build_client
from jk.state import open_private_file
from jk.store.store import RunStore
from jk.web.app import create_app
from jk.web.deps import build_services

DEFAULT_PORT = 8765
HOST = "127.0.0.1"
ADDRESS_FILE = "serve.url"


def url_of(port: int) -> str:
    return f"http://{HOST}:{port}"


def running_url(state_path: Path) -> str | None:
    """The URL of the `jk serve` that already holds this state directory."""
    marker = state_path / ADDRESS_FILE
    if not marker.is_file():
        return None
    text = marker.read_text().strip()
    return text or None


def serve(
    *,
    jenkins_config: JenkinsConfig,
    state_path: Path,
    host: str = HOST,
    port: int = DEFAULT_PORT,
    open_browser: bool = True,
    serve_static: bool = True,
) -> int:
    store = RunStore.open(state_path / "runs.db")

    # BEFORE anything can reach Jenkins.
    store.recover_pending_submissions()

    client = build_client(jenkins_config)
    services = build_services(
        store=store,
        client=client,
        base_url=jenkins_config.base_url,
    )
    app = create_app(services, serve_static=serve_static)

    address = url_of(port)
    marker_written = False
    try:
        with open_private_file(state_path / ADDRESS_FILE) as marker:
            marker.write(address)
            marker.truncate()
        marker_written = True
        print(f"JK is at {address}")
        if open_browser:
            threading.Timer(0.6, webbrowser.open, args=(address,)).start()
        uvicorn.run(app, host=host, port=port, log_level="warning", access_log=False)
    finally:
        if marker_written:
            (state_path / ADDRESS_FILE).unlink(missing_ok=True)
        store.close()
    return 0
