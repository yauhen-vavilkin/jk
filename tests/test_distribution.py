"""The built wheel is unusable outside the source checkout and refuses cleanly."""

from __future__ import annotations

import os
import subprocess
import sys
import zipfile
from pathlib import Path

from tests.network_safety import OFFLINE_SUBPROCESS_PREAMBLE


def test_installed_wheel_outside_a_checkout_refuses_to_start(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    dist = tmp_path / "dist"
    subprocess.run(
        [
            "uv",
            "build",
            "--offline",
            "--no-build-isolation",
            "--wheel",
            "--out-dir",
            str(dist),
        ],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )

    wheel = next(dist.glob("*.whl"))
    extracted = tmp_path / "wheel"
    with zipfile.ZipFile(wheel) as archive:
        archive.extractall(extracted)

    isolated_cwd = tmp_path / "cwd"
    isolated_home = tmp_path / "home"
    isolated_cwd.mkdir()
    isolated_home.mkdir()
    environment = os.environ.copy()
    environment.pop("PYTHONHOME", None)
    environment["HOME"] = str(isolated_home)
    environment["PYTHONPATH"] = str(extracted)
    environment["UV_OFFLINE"] = "1"
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            OFFLINE_SUBPROCESS_PREAMBLE
            + """
import sys

from jk.__main__ import main

sys.exit(main(["serve", "--no-open"]))
""",
        ],
        cwd=isolated_cwd,
        env=environment,
        capture_output=True,
        text=True,
    )

    assert probe.returncode == 2
    assert "JK cannot start" in probe.stderr
    assert "checkout" in probe.stderr
