"""Every Jenkins GET request.

This module must never issue a POST, PUT or DELETE. `tests/test_no_writes.py`
enforces that by reading the source.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from jk.errors import JenkinsAuthError, JenkinsUnavailable, TargetNotFound
from jk.jenkins.models import BuildInfo, ParameterDefinition, QueueInfo, scalar_to_str

_DEFS_TREE = "property[parameterDefinitions[name,type,defaultParameterValue[value],choices[*]]]"
_BUILD_TREE = "number,queueId,building,result,timestamp,duration,estimatedDuration,url"


class JenkinsReader:
    """Read-only access to a Jenkins controller."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def _get(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        try:
            response = await self._client.get(path, params=params)
        except httpx.HTTPError as exc:
            raise JenkinsUnavailable(f"cannot reach Jenkins: {exc}") from exc
        if response.status_code in (401, 403):
            raise JenkinsAuthError(
                f"Jenkins refused the request with HTTP {response.status_code}. "
                f"Check JENKINS_USER_ID and JENKINS_API_TOKEN, and your permissions."
            )
        if response.status_code == 404:
            raise TargetNotFound(f"Jenkins has no {path}")
        if response.status_code >= 400:
            raise JenkinsUnavailable(f"Jenkins returned HTTP {response.status_code} for {path}")
        try:
            return response.json()
        except ValueError as exc:
            raise JenkinsUnavailable(f"Jenkins returned a non-JSON body for {path}") from exc

    async def whoami(self) -> None:
        """Ask Jenkins whose token this is. A refused token raises JenkinsAuthError."""
        await self._get("/me/api/json")

    async def parameter_definitions(self, rest_path: str) -> dict[str, ParameterDefinition]:
        raw = await self._get(f"/{rest_path}/api/json", {"tree": _DEFS_TREE})
        found: dict[str, ParameterDefinition] = {}
        for prop in raw.get("property", []) or []:
            for entry in prop.get("parameterDefinitions", []) or []:
                definition = ParameterDefinition.from_json(entry)
                if definition is not None:
                    found[definition.name] = definition
        return found

    async def jobs_tree(self, rest_path: str, tree: str) -> dict[str, Any]:
        """One `api/json?tree=...` read of a folder, for the Library index crawl."""
        path = f"/{rest_path}/api/json" if rest_path else "/api/json"
        return await self._get(path, {"tree": tree})

    async def next_build_number(self, rest_path: str) -> int:
        raw = await self._get(f"/{rest_path}/api/json", {"tree": "nextBuildNumber"})
        return int(raw["nextBuildNumber"])

    async def build_by_url(self, url: str) -> BuildInfo:
        path = urlparse(url).path.rstrip("/")
        raw = await self._get(f"{path}/api/json", {"tree": _BUILD_TREE})
        return BuildInfo.from_json(raw)

    async def queue_item(self, queue_url: str) -> QueueInfo:
        """Read a queue item. Raises TargetNotFound once the item has been dropped.

        Jenkins forgets a queue item shortly after its build starts, so a 404 here
        is NORMAL and the caller must fall back to scanning recent builds.
        """
        path = urlparse(queue_url).path.rstrip("/")
        raw = await self._get(f"{path}/api/json")
        return QueueInfo.from_json(raw)

    async def recent_builds(self, rest_path: str, *, limit: int = 30) -> list[BuildInfo]:
        tree = f"builds[{_BUILD_TREE}]{{0,{limit}}}"
        raw = await self._get(f"/{rest_path}/api/json", {"tree": tree})
        return [BuildInfo.from_json(entry) for entry in raw.get("builds", []) or []]

    async def build_parameters(self, rest_path: str, number: int) -> dict[str, str]:
        """Reported parameters of a build, as comparable strings.

        Password parameters come back with no `value` key at all, so they are
        simply absent -- there is nothing here that could leak.
        """
        tree = "actions[parameters[_class,name,value]]"
        raw = await self._get(f"/{rest_path}/{number}/api/json", {"tree": tree})
        values: dict[str, str] = {}
        for action in raw.get("actions", []) or []:
            for entry in action.get("parameters", []) or []:
                name = entry.get("name")
                if not name or "value" not in entry:
                    continue
                values[name] = scalar_to_str(entry["value"])
        return values
