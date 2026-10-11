"""Starting the panel: the command line, the lock, and the static shell."""

from __future__ import annotations

import sqlite3
import stat
from pathlib import Path

import httpx
import pytest

from jk.__main__ import StateDirectoryLock, parse_arguments, run_serve
from jk.errors import StateAccessError
from jk.jenkins.client import JenkinsConfig
from jk.web import serve as serve_module
from jk.web.app import create_app
from jk.web.serve import ADDRESS_FILE, DEFAULT_PORT, running_url, serve, url_of
from tests.webapp import FakeJenkins


def test_serve_takes_a_port_and_can_keep_the_browser_closed() -> None:
    arguments = parse_arguments(["serve", "--port", "9100", "--no-open"])

    assert arguments.command == "serve"
    assert arguments.port == 9100
    assert arguments.no_open is True
    assert arguments.dev is False


def test_serve_defaults_to_the_loopback_port_in_the_readme() -> None:
    assert parse_arguments(["serve"]).port == DEFAULT_PORT
    assert url_of(DEFAULT_PORT) == "http://127.0.0.1:8765"


def test_serve_listens_on_loopback_unless_told_otherwise() -> None:
    assert parse_arguments(["serve"]).host == "127.0.0.1"
    assert parse_arguments(["serve", "--host", "0.0.0.0"]).host == "0.0.0.0"


def test_no_subcommand_prints_the_usage_and_exits_2(capsys) -> None:
    with pytest.raises(SystemExit) as raised:
        parse_arguments([])

    assert raised.value.code == 2
    assert "usage: jk" in capsys.readouterr().err


def test_serve_recovers_pending_submissions_before_anything_can_reach_jenkins(
    tmp_path: Path, monkeypatch
) -> None:
    """A crash during a POST must never be resumed into a second POST."""
    events: list[str] = []

    class Store:
        @classmethod
        def open(cls, _path: Path) -> Store:
            events.append("store_open")
            return cls()

        def recover_pending_submissions(self) -> list[str]:
            events.append("recover_pending")
            return []

        def close(self) -> None:
            events.append("store_close")

    def record(name: str):
        def call(*_args, **_kwargs) -> object:
            events.append(name)
            return object()

        return call

    monkeypatch.setattr(serve_module, "RunStore", Store)
    monkeypatch.setattr(serve_module, "build_client", record("build_client"))
    monkeypatch.setattr(serve_module, "build_services", record("build_services"))
    monkeypatch.setattr(serve_module, "create_app", record("create_app"))

    def run_server(*_args, **_kwargs):
        events.append("uvicorn_run")
        assert stat.S_IMODE((tmp_path / ADDRESS_FILE).stat().st_mode) == 0o600

    monkeypatch.setattr(serve_module.uvicorn, "run", run_server)
    monkeypatch.setattr(serve_module.webbrowser, "open", record("browser_open"))

    code = serve(
        jenkins_config=JenkinsConfig(
            base_url="https://jenkins.invalid", user_id="t", api_token="t"
        ),
        state_path=tmp_path,
        open_browser=False,
    )

    assert code == 0
    assert events == [
        "store_open",
        "recover_pending",
        "build_client",
        "build_services",
        "create_app",
        "uvicorn_run",
        "store_close",
    ]
    assert not (tmp_path / ADDRESS_FILE).exists()


def test_a_second_start_can_find_the_url_of_the_first(tmp_path: Path) -> None:
    assert running_url(tmp_path) is None

    (tmp_path / ADDRESS_FILE).write_text("http://127.0.0.1:8765")

    assert running_url(tmp_path) == "http://127.0.0.1:8765"


def test_a_refused_address_marker_closes_the_database_and_keeps_the_link(tmp_path, monkeypatch):
    state = tmp_path / ".jk"
    state.mkdir()
    target = tmp_path / "outside"
    target.write_text("keep")
    marker = state / ADDRESS_FILE
    marker.symlink_to(target)
    opened = []
    original = serve_module.RunStore.open

    def open_store(path):
        store = original(path)
        opened.append(store)
        return store

    monkeypatch.setattr(serve_module.RunStore, "open", open_store)
    with pytest.raises(StateAccessError):
        serve(
            jenkins_config=JenkinsConfig(
                base_url="https://jenkins.invalid", user_id="t", api_token="t"
            ),
            state_path=state,
            open_browser=False,
        )

    assert marker.is_symlink()
    assert target.read_text() == "keep"
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        opened[0].connection.execute("SELECT 1")


def test_a_second_serve_prints_the_url_of_the_first_and_exits_zero(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    state = tmp_path / ".jk"
    state.mkdir()
    (state / "serve.url").write_text("http://127.0.0.1:8765")
    monkeypatch.setattr("jk.__main__.checkout_root", lambda: tmp_path)
    monkeypatch.setattr("jk.__main__._environment", lambda root: object())

    held = StateDirectoryLock(state / "jk.lock")
    held.acquire()
    try:
        code = run_serve(parse_arguments(["serve", "--no-open"]))
    finally:
        held.release()

    assert code == 0
    assert "already running at http://127.0.0.1:8765" in capsys.readouterr().out


@pytest.fixture
def jenkins() -> FakeJenkins:
    return FakeJenkins()


async def test_an_unknown_path_serves_the_application_shell(services, tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>JK</title>")
    app = create_app(services, dist=dist, background=False)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8765"
    ) as client:
        assert (await client.get("/")).text.startswith("<!doctype html>")
        assert (await client.get("/library/some-preset")).text.startswith("<!doctype html>")
        assert (await client.get("/api/presets")).json() == []


async def test_a_missing_build_says_how_to_make_one(services, tmp_path: Path) -> None:
    app = create_app(services, dist=tmp_path / "never-built", background=False)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8765"
    ) as client:
        response = await client.get("/")

    assert response.status_code == 503
    assert "npm run build" in response.text
