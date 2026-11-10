"""Shared HTTP client construction.

Credentials come from the process environment first. `from_environment`
additionally fills any missing variable from a `.env` file in the directory
the caller passes, which the `jk` command sets to the root of the checkout; the
process environment always wins.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

LOG = logging.getLogger("jk.jenkins")
#: The only parts of an answer that are written to the log, besides its status.
LOGGED_HEADERS = ("Location", "Content-Type", "X-Error")

TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=10.0)


@dataclass(frozen=True)
class JenkinsConfig:
    base_url: str
    user_id: str
    api_token: str

    @classmethod
    def from_environment(cls, config_dir: Path | None = None) -> JenkinsConfig:
        values = dict(os.environ)
        if config_dir is not None:
            values = _with_env_file(config_dir / ".env", values)
        missing = [
            key
            for key in ("JENKINS_URL", "JENKINS_USER_ID", "JENKINS_API_TOKEN")
            if not values.get(key)
        ]
        if missing:
            raise ValueError("these environment variables are not set: " + ", ".join(missing))
        return cls(
            base_url=values["JENKINS_URL"].rstrip("/"),
            user_id=values["JENKINS_USER_ID"],
            api_token=values["JENKINS_API_TOKEN"],
        )


def _with_env_file(path: Path, values: dict[str, str]) -> dict[str, str]:
    """Fill gaps from a .env file. The process environment always wins."""
    if not path.is_file():
        return values
    merged = dict(values)
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, raw = line.partition("=")
        key = key.strip()
        if merged.get(key):
            continue
        merged[key] = raw.strip().strip('"').strip("'")
    return merged


async def _log_request(request: httpx.Request) -> None:
    """Remember when the request left, to log how long Jenkins took."""
    request.extensions["jk_started"] = time.monotonic()


async def _log_response(response: httpx.Response) -> None:
    """One log line per Jenkins answer: what was asked and what came back.

    Only the method, the path, the status, the time and a few headers are written.
    The body of an answer is never logged (spec.md section 14, rule 9): a proxy
    may echo secrets in it. Neither are the token (a header), a request body (a
    saved job may hold a password) or a query string.
    """
    request = response.request
    started = request.extensions.get("jk_started")
    took = f"{time.monotonic() - started:.2f}s" if started else "?"
    line = f"{request.method} {request.url.path} -> HTTP {response.status_code} in {took}"
    for header in LOGGED_HEADERS:
        value = response.headers.get(header)
        if value:
            line += f" {header}={value[:200]}"
    LOG.warning(line) if response.status_code >= 400 else LOG.info(line)


def build_client(
    config: JenkinsConfig, transport: httpx.AsyncBaseTransport | None = None
) -> httpx.AsyncClient:
    """Build the shared async client. TLS verification is never disabled."""
    return httpx.AsyncClient(
        base_url=config.base_url,
        auth=(config.user_id, config.api_token),
        timeout=TIMEOUT,
        transport=transport,
        follow_redirects=False,
        event_hooks={"request": [_log_request], "response": [_log_response]},
    )
