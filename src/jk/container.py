"""How the Docker image starts JK: as the owner of its state, after a one-time move.

The image starts as root only to do two things before JK runs:

- choose the user JK runs as: the owner of `/app/.jk`, the checkout's `.jk/`
  bind-mounted there, so the database on the host belongs to the person who
  cloned the checkout on every platform (any user id on Linux, root inside a
  rootless Docker or Podman, which is that person). Docker Desktop's file
  sharing shows every user as the owner of every file, so there JK runs as the
  image's unprivileged `jk` user;
- move the database out of the old Docker volume, mounted at `/legacy`, once
  (`jk.store.legacy_move`), each side touched only as its own owner.

Then it gives up root for good and becomes `jk serve`. Started with
`docker run --user`, it is not root and changes no user at all. Nothing here
changes the owner of a file.
"""

from __future__ import annotations

import os
import pwd
import re
import stat
import subprocess
import sys
from pathlib import Path

from jk.store.legacy_move import DATABASE, MARKER, TARGET_TAKEN

STATE = Path("/app/.jk")
LEGACY = Path("/legacy")
JK = "/app/.venv/bin/jk"
#: The image's unprivileged user, from the Dockerfile.
IMAGE_USER = "jk"
#: Docker Desktop's file sharing: every user in the container sees itself as
#: the owner, so the owner tells nothing about who should run JK.
SHARED_OWNER_FILESYSTEMS = frozenset({"fakeowner"})

User = tuple[int, int]


class ContainerError(Exception):
    """The container cannot start JK; the message says why and what to do."""


def _unescape(field: str) -> str:
    """A mount point as /proc writes it, with spaces and the like octal-escaped."""
    return re.sub(r"\\([0-7]{3})", lambda match: chr(int(match.group(1), 8)), field)


def filesystem_type(path: Path, mountinfo: str | None = None) -> str | None:
    """The type of the filesystem `path` is on, from the closest mount above it."""
    if mountinfo is None:
        try:
            mountinfo = Path("/proc/self/mountinfo").read_text()
        except OSError:
            return None
    best: tuple[int, str] | None = None
    target = str(path)
    for line in mountinfo.splitlines():
        before, _, after = line.partition(" - ")
        fields = before.split()
        if len(fields) < 5 or not after:
            continue
        mount_point = _unescape(fields[4])
        inside = target == mount_point or target.startswith(mount_point.rstrip("/") + "/")
        if inside and (best is None or len(mount_point) > best[0]):
            best = (len(mount_point), after.split()[0])
    return best[1] if best else None


def owner(path: Path) -> User:
    """The user and group that own a state directory; a link is refused."""
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise ContainerError(f"{path} cannot be read: {exc.strerror or exc}") from exc
    if not stat.S_ISDIR(info.st_mode):
        raise ContainerError(f"{path} must be a directory, not a link or a file")
    return info.st_uid, info.st_gid


def image_user() -> User:
    entry = pwd.getpwnam(IMAGE_USER)
    return entry.pw_uid, entry.pw_gid


def runs_as(path: Path, mountinfo: str | None = None) -> User:
    """The user that owns what is kept in `path`, and so the one to touch it."""
    found = owner(path)
    if filesystem_type(path, mountinfo) in SHARED_OWNER_FILESYSTEMS:
        return image_user()
    return found


def _home(uid: int) -> str:
    try:
        return pwd.getpwuid(uid).pw_dir
    except KeyError:
        return "/tmp"


def _as(user: User | None) -> dict:
    """`subprocess` arguments that run a step as `user`; none when not root."""
    if user is None:
        return {}
    uid, gid = user
    return {
        "user": uid,
        "group": gid,
        "extra_groups": [],
        "env": {**os.environ, "HOME": _home(uid)},
    }


def _step(step: str, directory: Path, user: User | None, **kwargs) -> subprocess.CompletedProcess:
    command = [sys.executable, "-m", "jk.store.legacy_move", step, str(directory)]
    return subprocess.run(command, check=False, **_as(user), **kwargs)


def move_legacy(state_user: User | None, legacy_user: User | None) -> None:
    """Bring the old volume's database into `.jk/` once; the volume stays as it is."""
    if os.path.lexists(LEGACY / MARKER):
        print(f"JK: the old Docker volume was moved before; using .jk/{DATABASE}.")
        return
    if not os.path.lexists(LEGACY / DATABASE):
        return
    print("JK: moving the database from the old Docker volume into .jk/ ...", flush=True)
    read = _step("read", LEGACY, legacy_user, stdout=subprocess.PIPE)
    if read.returncode != 0:
        raise ContainerError(
            "the old Docker volume could not be read; its data is unchanged in jk-data"
        )
    written = _step("write", STATE, state_user, input=read.stdout, stdout=subprocess.PIPE)
    if written.returncode == TARGET_TAKEN:
        raise ContainerError(
            "two databases: one in .jk/ and one in the old Docker volume jk-data. "
            'README, "Two databases", says how to keep one; neither was changed'
        )
    if written.returncode != 0:
        raise ContainerError(
            "the database could not be written to .jk/; the old data is unchanged in jk-data"
        )
    if _step("mark", LEGACY, legacy_user).returncode != 0:
        raise ContainerError(
            ".jk/ holds the moved database, but the old volume could not be marked as moved"
        )
    print(f"JK: the database is now in .jk/{DATABASE}; jk-data keeps the old copy.")


def become(user: User) -> None:
    """Give up root for good: groups first, then group, then user."""
    uid, gid = user
    os.setgroups([])
    os.setgid(gid)
    os.setuid(uid)
    os.environ["HOME"] = _home(uid)


def start(arguments: list[str]) -> None:
    root = os.geteuid() == 0
    state_user = runs_as(STATE) if root else None
    if os.path.isdir(LEGACY):
        legacy_user = runs_as(LEGACY) if root else None
        move_legacy(state_user, legacy_user)
    # Root inside a rootless Docker or Podman is the person running it: stay.
    if state_user is not None and state_user[0] != 0:
        become(state_user)
    os.execv(JK, [JK, "serve", *arguments])


def main(argv: list[str] | None = None) -> int:
    try:
        start(sys.argv[1:] if argv is None else argv)
    except ContainerError as exc:
        print(f"JK cannot start: {exc}.", file=sys.stderr)
        return 2
    return 0  # pragma: no cover - execv does not return


if __name__ == "__main__":
    raise SystemExit(main())
