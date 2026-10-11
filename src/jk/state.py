"""Owner-only local state, without following links or replacing existing data."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import TextIO

from jk.errors import StateAccessError


def _access_error(path: Path, problem: str) -> StateAccessError:
    return StateAccessError(
        f"cannot secure JK state at {path}: {problem}. "
        "Use ordinary files and a state directory owned by the user running JK; "
        "a Docker volume must belong to the container user."
    )


def _open_owned(path: Path, flags: int, *, directory: bool = False) -> int:
    descriptor = None
    try:
        descriptor = os.open(path, flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        info = os.fstat(descriptor)
        if info.st_uid != os.geteuid():
            raise _access_error(path, "it has a different owner")
        if directory:
            if not stat.S_ISDIR(info.st_mode):
                raise _access_error(path, "it is not a directory")
        elif not stat.S_ISREG(info.st_mode):
            raise _access_error(path, "it is not an ordinary file")
        os.fchmod(descriptor, 0o700 if directory else 0o600)
        return descriptor
    except OSError as exc:
        if descriptor is not None:
            os.close(descriptor)
        if isinstance(exc, FileNotFoundError) and not flags & os.O_CREAT:
            raise
        raise _access_error(path, exc.strerror or str(exc)) from exc
    except StateAccessError:
        if descriptor is not None:
            os.close(descriptor)
        raise


def prepare_state_directory(path: Path) -> None:
    """Harden only the dedicated state directory, never its checkout parents."""
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = _open_owned(path, os.O_RDONLY | os.O_DIRECTORY, directory=True)
    except OSError as exc:
        raise _access_error(path, exc.strerror or str(exc)) from exc
    os.close(descriptor)


def open_private_file(path: Path, *, create: bool = True) -> TextIO:
    """Open without truncating; existing files must belong to the current user."""
    flags = os.O_RDWR | (os.O_CREAT if create else 0)
    descriptor = _open_owned(path, flags)
    return os.fdopen(descriptor, "r+", encoding="utf-8")
