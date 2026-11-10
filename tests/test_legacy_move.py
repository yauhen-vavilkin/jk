"""The one-time move of the run database from the old Docker volume into `.jk/`."""

from __future__ import annotations

import fcntl
import hashlib
import io
import os
import sqlite3
import stat
from pathlib import Path

import pytest

from jk.store import legacy_move
from jk.store.legacy_move import (
    MARKER,
    TARGET_TAKEN,
    MoveError,
    TargetTaken,
    mark,
    read,
    write,
)
from jk.store.store import RunStore


def _rows(path: Path) -> dict[str, list[tuple]]:
    connection = sqlite3.connect(path)
    try:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            )
        ]
        return {
            table: sorted(connection.execute(f'SELECT * FROM "{table}"').fetchall())
            for table in tables
        }
    finally:
        connection.close()


@pytest.fixture
def legacy(tmp_path: Path) -> Path:
    """An old volume as the old panel left it: a JK database and its lock."""
    volume = tmp_path / "volume"
    volume.mkdir(mode=0o700)
    store = RunStore.open(volume / "runs.db")
    store.connection.execute(
        "INSERT INTO runs (id, kind, source_id, name, state, created_at, updated_at) "
        "VALUES ('run-1', 'flow', 'saved', 'Nightly', 'finished', 1, 2)"
    )
    store.close()
    (volume / "jk.lock").touch(mode=0o600)
    return volume


@pytest.fixture
def state(tmp_path: Path) -> Path:
    return tmp_path / "checkout" / ".jk"


def _write_only_to_the_log(volume: Path) -> sqlite3.Connection:
    """A writer that keeps its rows in the write-ahead log, as a running panel does."""
    connection = sqlite3.connect(volume / "runs.db", isolation_level=None)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA wal_autocheckpoint=0")
    for number in range(50):
        connection.execute(
            "INSERT INTO runs (id, kind, source_id, name, state, created_at, updated_at) "
            "VALUES (?, 'flow', 'saved', ?, 'finished', 1, 2)",
            (f"log-{number}", f"Only in the log {number}"),
        )
    assert (volume / "runs.db-wal").stat().st_size > 0
    return connection


def test_every_table_and_row_moves_including_rows_only_in_the_log(legacy, state) -> None:
    writer = _write_only_to_the_log(legacy)
    try:
        data = read(legacy)
    finally:
        writer.close()
    expected = _rows(legacy / "runs.db")

    assert write(state, data) == "moved"

    moved = _rows(state / "runs.db")
    assert moved == expected
    assert len(moved["runs"]) == 51
    assert sorted(path.name for path in state.iterdir()) == ["jk.lock", "runs.db"]


def test_the_moved_database_is_private_and_opens_as_the_panel_opens_it(legacy, state) -> None:
    write(state, read(legacy))

    assert stat.S_IMODE(state.stat().st_mode) == 0o700
    assert stat.S_IMODE((state / "runs.db").stat().st_mode) == 0o600
    store = RunStore.open(state / "runs.db")
    try:
        names = [row["name"] for row in store.connection.execute("SELECT name FROM runs")]
    finally:
        store.close()
    assert names == ["Nightly"]


def test_the_old_volume_keeps_every_row_and_gets_no_new_lock(legacy, state) -> None:
    (legacy / "jk.lock").unlink()
    before = _rows(legacy / "runs.db")

    write(state, read(legacy))
    mark(legacy)

    assert _rows(legacy / "runs.db") == before
    assert not (legacy / "jk.lock").exists()
    assert (legacy / MARKER).read_text().endswith("moved to .jk/runs.db in the JK checkout\n")
    assert stat.S_IMODE((legacy / MARKER).stat().st_mode) == 0o600


def test_a_running_old_panel_stops_the_move(legacy, state) -> None:
    holder = open(legacy / "jk.lock", "r+")  # noqa: SIM115
    fcntl.flock(holder.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        with pytest.raises(MoveError, match="docker compose down"):
            read(legacy, wait=0.1)
    finally:
        holder.close()

    assert not state.exists()


@pytest.mark.parametrize("present", ["runs.db", "runs.db-wal", "runs.db-journal"])
def test_a_database_already_in_state_is_never_replaced(legacy, state, present) -> None:
    state.mkdir(parents=True)
    (state / present).write_bytes(b"the user's own data")

    with pytest.raises(TargetTaken, match=present):
        write(state, read(legacy))

    assert (state / present).read_bytes() == b"the user's own data"
    assert sorted(path.name for path in state.iterdir()) == ["jk.lock", present]


def test_a_move_finished_before_the_marker_is_recognised(legacy, state) -> None:
    data = read(legacy)
    write(state, data)
    moved = (state / "runs.db").read_bytes()

    assert write(state, data) == "present"
    assert (state / "runs.db").read_bytes() == moved


def test_a_failed_check_leaves_no_database_and_no_copy(legacy, state, monkeypatch) -> None:
    data = read(legacy)
    original = legacy_move._sha256
    calls: list[int] = []

    def mismatch_on_read_back(content: bytes) -> str:
        calls.append(len(content))
        if len(calls) == 1:
            return "not the same"
        return original(content)

    monkeypatch.setattr(legacy_move, "_sha256", mismatch_on_read_back)

    with pytest.raises(MoveError, match="does not match"):
        write(state, data)

    assert sorted(path.name for path in state.iterdir()) == ["jk.lock"]


def test_a_broken_old_database_is_refused(tmp_path, state) -> None:
    volume = tmp_path / "volume"
    volume.mkdir()
    (volume / "runs.db").write_bytes(b"SQLite format 3\x00" + b"\xff" * 4080)

    with pytest.raises((MoveError, sqlite3.DatabaseError)):
        write(state, read(volume))

    assert not (state / "runs.db").exists()


def test_leftovers_of_an_interrupted_copy_are_cleared(legacy, state) -> None:
    state.mkdir(parents=True)
    (state / "runs.db.moving").write_bytes(b"half a copy")
    (state / "runs.db.moving-wal").write_bytes(b"its log")

    assert write(state, read(legacy)) == "moved"

    assert sorted(path.name for path in state.iterdir()) == ["jk.lock", "runs.db"]


def test_the_command_passes_the_bytes_through_and_names_a_taken_target(
    legacy, state, monkeypatch, capsys
) -> None:
    data = read(legacy)
    out = io.BytesIO()
    monkeypatch.setattr("sys.stdout", io.TextIOWrapper(out))

    assert legacy_move.main(["read", str(legacy)]) == 0
    assert hashlib.sha256(out.getvalue()).hexdigest() == hashlib.sha256(data).hexdigest()

    monkeypatch.undo()
    state.mkdir(parents=True)
    (state / "runs.db").write_bytes(b"other")
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(data)))

    assert legacy_move.main(["write", str(state)]) == TARGET_TAKEN
    assert "already holds a database" in capsys.readouterr().err


def test_the_command_reports_a_state_folder_owned_by_someone_else(
    legacy, state, monkeypatch, capsys
) -> None:
    state.mkdir(parents=True)
    monkeypatch.setattr(os, "geteuid", lambda: state.stat().st_uid + 1)
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(b"data")))

    assert legacy_move.main(["write", str(state)]) == 1
    assert "owner" in capsys.readouterr().err
