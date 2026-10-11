"""The Docker packaging keeps the two things that must stay local, local.

The token lives in `.env` at the checkout root and reaches the container only
as environment variables; the run history lives in `.jk/`. Neither may be copied
into an image, and the panel may only be published on loopback.
"""

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


def test_compose_and_docker_run_use_the_same_named_volume() -> None:
    compose = YAML(typ="safe").load((ROOT / "compose.yaml").read_text())

    assert compose["volumes"]["jk-data"]["name"] == "jk-data"
    assert "jk-data:/app/.jk" in compose["services"]["jk"]["volumes"]
