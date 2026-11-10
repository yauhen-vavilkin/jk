"""The one-time move of the run database from the old Docker volume into `.jk/`.

Earlier releases kept the Docker panel's state in the named volume `jk-data`;
now it lives in the checkout's `.jk/`, bind-mounted into the container. The
container start (`jk.container`) runs each step below in its own process, as
the owner of the side it touches, so no file on either side gets a new owner:

- ``read``: under the old panel's lock, the whole old database as one byte
  string, rows still in its write-ahead log included;
- ``write``: under the new state directory's lock, those bytes become
  ``runs.db``, checked before they replace anything;
- ``mark``: the old volume is marked as moved, so it is never read again.

The old database itself is left in the volume as a backup.
"""

from __future__ import annotations

import fcntl
import hashlib
import os
import sqlite3
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from jk.errors import StateAccessError
from jk.state import open_private_file, prepare_state_directory

DATABASE = "runs.db"
LOCK = "jk.lock"
#: Written into the old volume once its database is in `.jk/`.
MARKER = "MIGRATED"
#: The copy being checked, before it takes the place of `runs.db`.
MOVING = "runs.db.moving"
SIDECARS = ("-wal", "-shm", "-journal")

#: The `write` step's exit code when `.jk/` already holds a different database.
TARGET_TAKEN = 3


class MoveError(Exception):
    """The move cannot go on; nothing was replaced."""


class TargetTaken(MoveError):
    """`.jk/` already holds a database that is not the one being moved."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _exists(path: Path) -> bool:
    return os.path.lexists(path)


@contextmanager
def _locked(path: Path, *, create: bool, wait: float) -> Iterator[None]:
    """Hold JK's state lock; a lock file that is not there means no panel holds it."""
    try:
        handle = open_private_file(path, create=create)
    except FileNotFoundError:
        yield
        return
    with handle:
        deadline = time.monotonic() + wait
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise MoveError(
                        f"another JK panel is still using {path.parent}; "
                        "stop it (docker compose down), then start again"
                    ) from None
                time.sleep(0.5)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _check_integrity(connection: sqlite3.Connection, what: str) -> None:
    result = connection.execute("PRAGMA integrity_check").fetchall()
    if [tuple(row) for row in result] != [("ok",)]:
        raise MoveError(f"{what} failed SQLite's integrity check: {result[:3]}")


def read(legacy: Path, *, wait: float = 30.0) -> bytes:
    """The whole old database, read through SQLite under the old panel's lock.

    Opening it normally lets SQLite recover its write-ahead log, and closing it
    folds the log into the old `runs.db`: the volume keeps the same data.
    """
    with _locked(legacy / LOCK, create=False, wait=wait):
        connection = sqlite3.connect(legacy / DATABASE, isolation_level=None, timeout=30)
        try:
            _check_integrity(connection, f"the database in {legacy}")
            return connection.serialize()
        finally:
            connection.close()


def _remove_moving(state: Path) -> None:
    for suffix in ("", *SIDECARS):
        Path(f"{state / MOVING}{suffix}").unlink(missing_ok=True)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _install(state: Path, data: bytes) -> None:
    moving = state / MOVING
    with open_private_file(moving) as handle:
        handle.truncate()
        handle.buffer.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    if _sha256(moving.read_bytes()) != _sha256(data):
        raise MoveError("the copy in .jk/ does not match what was read")
    connection = sqlite3.connect(moving, isolation_level=None)
    try:
        _check_integrity(connection, "the copy in .jk/")
    finally:
        connection.close()
    log = Path(f"{moving}-wal")
    if _exists(log) and log.stat().st_size:
        raise MoveError("checking the copy left a write-ahead log behind")
    for suffix in SIDECARS:
        Path(f"{moving}{suffix}").unlink(missing_ok=True)
    os.replace(moving, state / DATABASE)
    _fsync_directory(state)


def write(state: Path, data: bytes, *, wait: float = 30.0) -> str:
    """Make `data` the state directory's `runs.db`; "moved" or "present".

    A database already there is never replaced: one with exactly these bytes is
    this move, finished before the volume was marked; any other is refused.
    """
    if not data:
        raise MoveError("the old volume gave an empty database")
    prepare_state_directory(state)
    with _locked(state / LOCK, create=True, wait=wait):
        target = state / DATABASE
        present = [
            path for path in (target, *(Path(f"{target}{s}") for s in SIDECARS)) if _exists(path)
        ]
        if present:
            if present == [target] and _sha256(target.read_bytes()) == _sha256(data):
                return "present"
            raise TargetTaken(
                f"{state} already holds a database ({', '.join(p.name for p in present)})"
            )
        _remove_moving(state)
        try:
            _install(state, data)
        except BaseException:
            _remove_moving(state)
            raise
        return "moved"


def mark(legacy: Path) -> None:
    """Record in the old volume that its database now lives in `.jk/`."""
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open_private_file(legacy / MARKER) as handle:
        handle.truncate()
        handle.write(f"{stamp} moved to .jk/{DATABASE} in the JK checkout\n")
        handle.flush()
        os.fsync(handle.fileno())
    _fsync_directory(legacy)


def main(argv: list[str]) -> int:
    """`python -m jk.store.legacy_move read|write|mark <directory>`."""
    step, directory = argv
    path = Path(directory)
    try:
        if step == "read":
            sys.stdout.buffer.write(read(path))
            sys.stdout.buffer.flush()
        elif step == "write":
            print(write(path, sys.stdin.buffer.read()))
        elif step == "mark":
            mark(path)
        else:
            raise MoveError(f"unknown step {step!r}")
    except TargetTaken as exc:
        print(f"JK cannot start: {exc}.", file=sys.stderr)
        return TARGET_TAKEN
    except (MoveError, StateAccessError, OSError, sqlite3.Error) as exc:
        print(f"JK cannot start: {exc}.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
