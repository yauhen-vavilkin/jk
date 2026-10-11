import os
import stat
from pathlib import Path

import pytest

from jk.__main__ import StateDirectoryLock, _environment, main

CREDENTIALS = ("JENKINS_URL", "JENKINS_USER_ID", "JENKINS_API_TOKEN")


@pytest.fixture
def checkout(tmp_path: Path, monkeypatch) -> Path:
    """A stand-in checkout, so no test reads the real .env at the repository root."""
    root = tmp_path / "checkout"
    root.mkdir()
    (root / "pyproject.toml").write_text('[project]\nname = "jk"\n')
    monkeypatch.setattr("jk.__main__.REPO_ROOT", root)
    for name in CREDENTIALS:
        monkeypatch.delenv(name, raising=False)
    return root


def test_state_directory_lock_allows_only_one_owner(tmp_path):
    first = StateDirectoryLock(tmp_path / "jk.lock")
    second = StateDirectoryLock(tmp_path / "jk.lock")
    first.acquire()

    with pytest.raises(RuntimeError, match="another JK process"):
        second.acquire()

    first.release()
    second.acquire()
    second.release()


def test_state_and_lock_are_private_even_with_a_permissive_umask(tmp_path):
    state = tmp_path / ".jk"
    lock = StateDirectoryLock(state / "jk.lock")
    previous_umask = os.umask(0)
    try:
        lock.acquire()
        assert stat.S_IMODE(state.stat().st_mode) == 0o700
        assert stat.S_IMODE(lock.path.stat().st_mode) == 0o600
    finally:
        lock.release()
        os.umask(previous_umask)


def test_an_existing_state_and_lock_are_made_private_without_replacing_them(tmp_path):
    state = tmp_path / ".jk"
    state.mkdir(mode=0o777)
    state.chmod(0o777)
    path = state / "jk.lock"
    path.write_text("existing lock")
    path.chmod(0o666)
    original_inode = path.stat().st_ino
    lock = StateDirectoryLock(path)
    lock.acquire()
    try:
        assert stat.S_IMODE(state.stat().st_mode) == 0o700
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert path.stat().st_ino == original_inode
        assert path.read_text() == "existing lock"
    finally:
        lock.release()


@pytest.mark.parametrize("target", ["directory", "lock"])
def test_a_state_symlink_refuses_start_without_changing_its_target(
    checkout, tmp_path, monkeypatch, capsys, target
):
    monkeypatch.setattr("jk.__main__.serve", lambda **_kwargs: 0)
    for name in CREDENTIALS:
        monkeypatch.setenv(name, "https://jenkins.invalid" if name == "JENKINS_URL" else "t")
    state = checkout / ".jk"
    outside = tmp_path / "outside"
    outside.mkdir()
    original_mode = stat.S_IMODE(outside.stat().st_mode)
    if target == "directory":
        state.symlink_to(outside, target_is_directory=True)
    else:
        state.mkdir()
        other = outside / "lock"
        other.write_text("keep")
        other.chmod(0o644)
        (state / "jk.lock").symlink_to(other)

    assert main(["serve", "--no-open"]) == 2

    output = capsys.readouterr()
    assert "JK cannot start" in output.err
    assert "already running" not in output.out
    assert stat.S_IMODE(outside.stat().st_mode) == original_mode
    if target == "lock":
        assert other.read_text() == "keep"
        assert stat.S_IMODE(other.stat().st_mode) == 0o644


def test_state_owned_by_a_different_user_refuses_start(checkout, monkeypatch, capsys):
    monkeypatch.setattr("jk.__main__.serve", lambda **_kwargs: 0)
    for name in CREDENTIALS:
        monkeypatch.setenv(name, "https://jenkins.invalid" if name == "JENKINS_URL" else "t")
    state = checkout / ".jk"
    state.mkdir()
    original_mode = stat.S_IMODE(state.stat().st_mode)
    monkeypatch.setattr(os, "geteuid", lambda: state.stat().st_uid + 1)

    assert main(["serve", "--no-open"]) == 2

    output = capsys.readouterr()
    assert "owner" in output.err
    assert "already running" not in output.out
    assert stat.S_IMODE(state.stat().st_mode) == original_mode


def test_the_credentials_come_from_the_env_at_the_checkout_root(checkout):
    (checkout / ".env").write_text(
        'JENKINS_URL="https://jenkins.invalid"\n'
        'JENKINS_USER_ID="tester"\n'
        'JENKINS_API_TOKEN="token"\n'
    )

    config = _environment(checkout)

    assert config.base_url == "https://jenkins.invalid"
    assert config.user_id == "tester"
    assert config.api_token == "token"


def test_a_config_env_is_no_longer_read(checkout, capsys):
    (checkout / "config").mkdir()
    (checkout / "config" / ".env").write_text(
        "JENKINS_URL=https://jenkins.invalid\nJENKINS_USER_ID=tester\nJENKINS_API_TOKEN=token\n"
    )

    assert _environment(checkout) == 2
    assert "JENKINS_API_TOKEN" in capsys.readouterr().err


def test_missing_credentials_produce_a_clear_message(checkout, capsys):
    code = main(["serve", "--no-open"])
    captured = capsys.readouterr()

    assert code == 2
    assert "JENKINS_URL" in captured.err
    assert "JENKINS_API_TOKEN" in captured.err
    assert ".env" in captured.err
    assert str(checkout) not in captured.err


def test_running_outside_a_checkout_fails_with_a_clear_message(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("jk.__main__.REPO_ROOT", tmp_path)

    assert main(["serve", "--no-open"]) == 2
    captured = capsys.readouterr()
    assert "JK cannot start" in captured.err
    assert "checkout" in captured.err
