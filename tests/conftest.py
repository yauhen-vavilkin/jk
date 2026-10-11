"""Shared offline test fixtures.

The default suite uses httpx.MockTransport and never reads the real `.env`.
The opt-in tests under ``tests/contract`` are the only exception and are
read-only by contract.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path

from tests.network_safety import install_pytest_process_tcp_guard

if os.environ.get("JK_CONTRACT") != "1":
    # Root conftest is imported before pytest imports test modules for collection.
    install_pytest_process_tcp_guard()

import httpx
import pytest

from jk.jenkins import client as jenkins_client
from jk.store.store import RunStore

FIXTURES = Path(__file__).parent / "fixtures"

#: The owner's real credentials. Tests that start JK point it at a stand-in
#: checkout under tmp_path instead.
REAL_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


@pytest.fixture(autouse=True)
def never_read_the_real_env_file(request, monkeypatch) -> None:
    """Fail any test that would load `.env` at the repository root.

    The opt-in contract checks are the one exception: they read the real
    controller with the real credentials.
    """
    if request.node.get_closest_marker("contract") is not None:
        return
    original = jenkins_client._with_env_file

    def guarded(path: Path, values: dict[str, str]) -> dict[str, str]:
        if path.resolve() == REAL_ENV_FILE:
            raise AssertionError("a test tried to read the real .env at the repository root")
        return original(path, values)

    monkeypatch.setattr(jenkins_client, "_with_env_file", guarded)


@pytest.fixture
def fixture_json() -> Callable[[str], dict]:
    def load(name: str) -> dict:
        return json.loads((FIXTURES / f"{name}.json").read_text())

    return load


@pytest.fixture
def call_log() -> list[tuple[str, str]]:
    return []


@pytest.fixture
def mock_transport(call_log: list[tuple[str, str]]) -> Callable[..., httpx.MockTransport]:
    """Build a MockTransport that records every request it sees.

    `routes` maps an exact request path to a response, or is a callable taking
    the request and returning a response.
    """

    def build(routes: dict[str, httpx.Response] | Callable[[httpx.Request], httpx.Response]):
        def handler(request: httpx.Request) -> httpx.Response:
            call_log.append((request.method, request.url.path))
            if callable(routes):
                return routes(request)
            response = routes.get(request.url.path)
            if response is None:
                return httpx.Response(404, text=f"no route for {request.url.path}")
            return response

        return httpx.MockTransport(handler)

    return build


@pytest.fixture
def store(tmp_path: Path):
    opened = RunStore.open(tmp_path / "runs.db")
    yield opened
    opened.close()


@pytest.fixture
def services(tmp_path: Path, jenkins):
    from tests.webapp import build

    built = build(tmp_path, jenkins)
    yield built
    built.store.close()


@pytest.fixture
async def client(services):
    from tests.webapp import client_for

    async with client_for(services) as opened:
        yield opened
