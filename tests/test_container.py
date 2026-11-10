"""How the Docker image chooses its user and moves the old volume, without Docker."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from jk import container
from jk.container import ContainerError, filesystem_type, owner, runs_as

MOUNTINFO = """\
22 1 0:21 / / rw,relatime - overlay overlay rw
1654 22 0:52 /Users/me/jk/.jk /app/.jk rw,relatime - fakeowner /run/host_mark/Users rw
1660 22 8:1 /var/lib/docker/volumes/jk-data/_data /legacy rw,relatime - ext4 /dev/vda1 rw
1661 22 8:1 /home/me/my\\040jk/.jk /srv/my\\040state rw,relatime - ext4 /dev/sda1 rw
"""


def test_the_filesystem_is_the_closest_mount_above_the_path() -> None:
    assert filesystem_type(Path("/app/.jk"), MOUNTINFO) == "fakeowner"
    assert filesystem_type(Path("/app/.jk/runs.db"), MOUNTINFO) == "fakeowner"
    assert filesystem_type(Path("/legacy"), MOUNTINFO) == "ext4"
    assert filesystem_type(Path("/app"), MOUNTINFO) == "overlay"
    assert filesystem_type(Path("/srv/my state"), MOUNTINFO) == "ext4"
    assert filesystem_type(Path("/app/.jkx"), MOUNTINFO) == "overlay"


def test_jk_runs_as_the_owner_of_its_state_folder(tmp_path) -> None:
    info = tmp_path.stat()

    assert runs_as(tmp_path, "") == (info.st_uid, info.st_gid)


def test_on_docker_desktop_sharing_jk_runs_as_the_image_user(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(container, "image_user", lambda: (1000, 1000))
    mountinfo = f"1 0 0:1 / {tmp_path} rw - fakeowner shared rw\n"

    assert runs_as(tmp_path, mountinfo) == (1000, 1000)


@pytest.mark.parametrize("kind", ["link", "file", "missing"])
def test_a_state_that_is_not_a_plain_folder_is_refused(tmp_path, kind) -> None:
    path = tmp_path / "state"
    if kind == "link":
        (tmp_path / "elsewhere").mkdir()
        path.symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    elif kind == "file":
        path.write_text("")

    with pytest.raises(ContainerError):
        owner(path)


def test_root_gives_up_groups_then_group_then_user(monkeypatch) -> None:
    calls: list[tuple] = []
    monkeypatch.setenv("HOME", os.environ.get("HOME", "/"))  # restored after the test
    monkeypatch.setattr(os, "setgroups", lambda groups: calls.append(("groups", groups)))
    monkeypatch.setattr(os, "setgid", lambda gid: calls.append(("gid", gid)))
    monkeypatch.setattr(os, "setuid", lambda uid: calls.append(("uid", uid)))
    monkeypatch.setattr(container, "_home", lambda uid: "/home/jk")

    container.become((1000, 1001))

    assert calls == [("groups", []), ("gid", 1001), ("uid", 1000)]
    assert os.environ["HOME"] == "/home/jk"


@pytest.fixture
def started(tmp_path, monkeypatch):
    """`start` with Docker's paths in tmp_path and nothing really executed."""
    state = tmp_path / "state"
    state.mkdir()
    legacy = tmp_path / "legacy"
    monkeypatch.setattr(container, "STATE", state)
    monkeypatch.setattr(container, "LEGACY", legacy)
    record: dict[str, list] = {"steps": [], "became": [], "exec": []}
    monkeypatch.setattr(container, "become", lambda user: record["became"].append(user))
    monkeypatch.setattr(os, "execv", lambda path, args: record["exec"].append(args))

    def step(name, directory, user, **_kwargs):
        record["steps"].append((name, directory, user))
        return subprocess.CompletedProcess([], record.get(name, 0), stdout=b"bytes")

    monkeypatch.setattr(container, "_step", step)
    record["state"], record["legacy"] = state, legacy
    return record


def test_not_root_changes_no_user_anywhere(started, monkeypatch) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    started["legacy"].mkdir()
    (started["legacy"] / "runs.db").write_bytes(b"old")

    container.start(["--host", "0.0.0.0"])

    assert [(name, user) for name, _, user in started["steps"]] == [
        ("read", None),
        ("write", None),
        ("mark", None),
    ]
    assert started["became"] == []
    assert started["exec"] == [[container.JK, "serve", "--host", "0.0.0.0"]]


def test_root_moves_each_side_as_its_owner_then_drops(started, monkeypatch) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    started["legacy"].mkdir()
    (started["legacy"] / "runs.db").write_bytes(b"old")
    owners = {started["state"]: (501, 20), started["legacy"]: (1000, 1000)}
    monkeypatch.setattr(container, "runs_as", lambda path: owners[path])

    container.start([])

    assert [(name, user) for name, _, user in started["steps"]] == [
        ("read", (1000, 1000)),
        ("write", (501, 20)),
        ("mark", (1000, 1000)),
    ]
    assert started["became"] == [(501, 20)]


def test_root_owned_state_keeps_root_as_in_rootless_docker(started, monkeypatch) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(container, "runs_as", lambda path: (0, 0))

    container.start([])

    assert started["became"] == []
    assert started["steps"] == []
    assert len(started["exec"]) == 1


def test_a_marked_volume_or_one_without_a_database_is_not_read(started, monkeypatch) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    started["legacy"].mkdir()

    container.start([])
    (started["legacy"] / "runs.db").write_bytes(b"old")
    (started["legacy"] / "MIGRATED").write_text("done")
    container.start([])

    assert started["steps"] == []
    assert len(started["exec"]) == 2


@pytest.mark.parametrize(
    ("failing", "message"),
    [
        ("read", "could not be read"),
        ("write", "could not be written"),
        ("mark", "could not be marked"),
    ],
)
def test_a_failed_step_stops_the_start(started, monkeypatch, capsys, failing, message) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    started["legacy"].mkdir()
    (started["legacy"] / "runs.db").write_bytes(b"old")
    started[failing] = 1

    assert container.main([]) == 2

    assert message in capsys.readouterr().err
    assert started["exec"] == []


def test_two_databases_stop_the_start_and_say_where_to_read(started, monkeypatch, capsys) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    started["legacy"].mkdir()
    (started["legacy"] / "runs.db").write_bytes(b"old")
    started["write"] = container.TARGET_TAKEN

    assert container.main([]) == 2

    error = capsys.readouterr().err
    assert "two databases" in error
    assert "Two databases" in error
    assert [name for name, _, _ in started["steps"]] == ["read", "write"]
    assert started["exec"] == []


def test_a_step_runs_as_its_user_only_when_one_is_given() -> None:
    assert container._as(None) == {}
    arguments = container._as((1000, 1000))
    assert (arguments["user"], arguments["group"], arguments["extra_groups"]) == (1000, 1000, [])
