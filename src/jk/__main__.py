"""The `jk` command.

`jk serve` opens the web panel, the only thing JK does. Saved jobs are made in
its Library.
"""

from __future__ import annotations

import argparse
import fcntl
import sys
from pathlib import Path

from jk.errors import StateAccessError
from jk.jenkins.client import JenkinsConfig
from jk.state import open_private_file, prepare_state_directory
from jk.web.serve import DEFAULT_PORT, HOST, running_url, serve

# A source checkout is self-contained: `.env` at its root holds the credentials,
# and `.jk/` the run history. Nothing has to be created outside the folder.
REPO_ROOT = Path(__file__).resolve().parents[2]


def checkout_root() -> Path:
    """The checkout this package was imported from; JK does not run installed."""
    if not (REPO_ROOT / "pyproject.toml").is_file():
        raise RuntimeError("no JK checkout, run JK from the project directory")
    return REPO_ROOT


class StateDirectoryLock:
    """Keep recovery and watchers owned by one JK process per state directory."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle = None

    def acquire(self) -> None:
        prepare_state_directory(self.path.parent)
        handle = open_private_file(self.path)
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            handle.close()
            raise RuntimeError("another JK process is using this state directory") from exc
        self._handle = handle

    def release(self) -> None:
        if self._handle is None:
            return
        fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        self._handle.close()
        self._handle = None


def parse_arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="jk", description="Launch saved Jenkins jobs.")
    commands = parser.add_subparsers(dest="command", required=True)

    serve_command = commands.add_parser("serve", help="open the web panel")
    serve_command.add_argument("--port", type=int, default=DEFAULT_PORT)
    serve_command.add_argument(
        "--host",
        default=HOST,
        help="address to listen on; only the Docker image uses anything but loopback",
    )
    serve_command.add_argument(
        "--no-open", action="store_true", help="do not open a browser window"
    )
    serve_command.add_argument(
        "--dev",
        action="store_true",
        help="serve only the API; run the Vite server for the frontend",
    )

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    return run_serve(parse_arguments(argv if argv is not None else sys.argv[1:]))


def _environment(root: Path) -> JenkinsConfig | int:
    """The credentials, or an exit code."""
    try:
        return JenkinsConfig.from_environment(root)
    except ValueError as exc:
        print(
            f"JK cannot start: {exc}.\n"
            "Put them in .env at the root of the JK checkout (copy .env.example), "
            "or set them in your shell:\n"
            "  JENKINS_URL, JENKINS_USER_ID, JENKINS_API_TOKEN",
            file=sys.stderr,
        )
        return 2


def run_serve(arguments: argparse.Namespace) -> int:
    """One panel per state directory; a second start points at the first."""
    try:
        root = checkout_root()
    except RuntimeError as exc:
        print(f"JK cannot start: {exc}.", file=sys.stderr)
        return 2
    jenkins_config = _environment(root)
    if isinstance(jenkins_config, int):
        return jenkins_config

    state_path = root / ".jk"
    state_lock = StateDirectoryLock(state_path / "jk.lock")
    try:
        state_lock.acquire()
    except StateAccessError as exc:
        print(f"JK cannot start: {exc}", file=sys.stderr)
        return 2
    except RuntimeError:
        address = running_url(state_path)
        print(f"JK is already running at {address}" if address else "JK is already running.")
        return 0

    try:
        return serve(
            jenkins_config=jenkins_config,
            state_path=state_path,
            host=arguments.host,
            port=arguments.port,
            open_browser=not arguments.no_open and not arguments.dev,
            serve_static=not arguments.dev,
        )
    except StateAccessError as exc:
        print(f"JK cannot start: {exc}", file=sys.stderr)
        return 2
    finally:
        state_lock.release()


if __name__ == "__main__":
    raise SystemExit(main())
