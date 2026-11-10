"""The Docker packaging keeps the two things that must stay local, local.

The token lives in `.env` at the checkout root and reaches the container only
as environment variables; the run history lives in `.jk/`. Neither may be copied
into an image, and the panel may only be published on loopback.
"""

import subprocess
from pathlib import Path

from ruamel.yaml import YAML

ROOT = Path(__file__).parent.parent


def test_the_build_context_is_an_allowlist_that_never_lets_in_the_token_or_state() -> None:
    lines = [
        line.strip()
        for line in (ROOT / ".dockerignore").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]

    assert lines[0] == "*"
    allowed = [line[1:] for line in lines if line.startswith("!")]
    for private in (".jk", ".env"):
        assert not any(entry.lstrip("/").startswith(private) for entry in allowed), allowed


def test_the_image_copies_no_credentials_and_opens_no_browser() -> None:
    text = (ROOT / "Dockerfile").read_text()
    copies = [line for line in text.splitlines() if line.startswith("COPY")]

    assert copies
    assert not any(".env" in line or ".jk" in line for line in copies)
    assert '"--no-open"' in text


def test_compose_publishes_on_loopback_and_passes_the_token_through_env_file() -> None:
    service = YAML(typ="safe").load((ROOT / "compose.yaml").read_text())["services"]["jk"]

    assert all(str(port).startswith("127.0.0.1:") for port in service["ports"])
    # Required is Compose's default: a missing .env stops `up`.
    env_files = service["env_file"]
    if isinstance(env_files, str | dict):
        env_files = [env_files]
    assert len(env_files) == 1
    entry = env_files[0]
    if isinstance(entry, dict):
        assert entry.get("required", True) is not False
        entry = entry["path"]
    assert entry in (".env", "./.env")
    # No bind mount of the credentials, and no token written into compose.yaml.
    assert not any(".env" in str(volume) for volume in service["volumes"])
    assert "environment" not in service


def _jk_service() -> dict:
    return YAML(typ="safe").load((ROOT / "compose.yaml").read_text())["services"]["jk"]


def test_compose_keeps_the_database_in_the_checkout_s_own_folder() -> None:
    """A bind mount of .jk/, never made by Docker as root, labelled for SELinux."""
    mounts = [volume for volume in _jk_service()["volumes"] if isinstance(volume, dict)]

    assert mounts == [
        {
            "type": "bind",
            "source": "./.jk",
            "target": "/app/.jk",
            "bind": {"create_host_path": False, "selinux": "z"},
        }
    ]


def test_compose_reads_the_old_volume_only_where_the_move_looks_for_it() -> None:
    compose = YAML(typ="safe").load((ROOT / "compose.yaml").read_text())

    assert compose["volumes"]["jk-data"]["name"] == "jk-data"
    assert "jk-data:/legacy" in compose["services"]["jk"]["volumes"]
    assert not any("/app/.jk" in str(v) for v in compose["services"]["jk"]["volumes"][1:])


def test_the_image_starts_through_the_user_choice_and_the_move() -> None:
    text = (ROOT / "Dockerfile").read_text()

    assert '"-m", "jk.container"' in text
    # Root is given up by jk.container itself, after it has read the owners.
    assert not any(line.startswith("USER") for line in text.splitlines())
    assert "useradd --create-home --uid 1000 jk" in text


def test_the_state_folder_is_in_every_checkout_but_its_contents_are_not() -> None:
    def ignored(path: str) -> bool:
        return (
            subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT, check=False).returncode
            == 0
        )

    assert (ROOT / ".jk" / ".gitignore").is_file()
    assert not ignored(".jk/.gitignore")
    for private in (".jk/runs.db", ".jk/runs.db-wal", ".jk/jk.lock", ".jk/serve.url"):
        assert ignored(private), private
