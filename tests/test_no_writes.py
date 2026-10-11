"""Structural guard: only two modules may write to Jenkins.

`jenkins/submit.py` starts a build. `jenkins/abort.py` stops one the user asked
to stop. Everything else in `src/jk` reads. The check looks at calls on an
httpx client, so a FastAPI route decorator -- `router.post(...)` -- is not a
Jenkins write and does not trip it.
"""

import ast
from pathlib import Path

SOURCE = Path(__file__).parent.parent / "src" / "jk"

WRITE_METHODS = {"post", "put", "delete", "patch"}
MAY_WRITE = {Path("jenkins/submit.py"), Path("jenkins/abort.py")}


def _receiver(node: ast.Attribute) -> str:
    """The text of what the method was called on, e.g. `self._client`."""
    parts: list[str] = []
    current: ast.expr = node.value
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return ".".join(reversed(parts))


def test_only_the_submitter_and_the_aborter_write_to_jenkins():
    offenders = []
    for path in SOURCE.rglob("*.py"):
        relative = path.relative_to(SOURCE)
        if relative in MAY_WRITE:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in WRITE_METHODS
                and "client" in _receiver(node.func).lower()
            ):
                offenders.append(f"{relative}:{node.lineno} calls {node.func.attr}")
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and "buildWithParameters" in node.value
            ):
                offenders.append(f"{relative}:{node.lineno} contains buildWithParameters")
    assert offenders == [], offenders


def test_the_submitter_contains_exactly_one_post_call():
    text = (SOURCE / "jenkins" / "submit.py").read_text()
    assert text.count("self._client.post(") == 1


def test_the_aborter_contains_exactly_one_post_call():
    text = (SOURCE / "jenkins" / "abort.py").read_text()
    assert text.count("self._client.post(") == 1
