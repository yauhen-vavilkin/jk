"""Crawl the controller once and remember which jobs take parameters.

The index is what the Library searches. It is a cache of what Jenkins answered
and when; nothing is ever launched from it without reading the live definitions
first.
"""

from __future__ import annotations

import asyncio

from jk.errors import JenkinsAuthError, JenkinsUnavailable, TargetNotFound
from jk.jenkins.read import JenkinsReader
from jk.store.jenkins_jobs import JenkinsJobStore
from jk.store.records import JenkinsJobRecord

#: What is read of one job. `lastSuccessfulBuild[duration]` is how long the job
#: took the last time it worked: the estimate for a step that has not run yet.
_JOB = "name,url,_class,property[parameterDefinitions[name]],lastSuccessfulBuild[duration]"

#: Three levels of folders in one request; anything deeper costs one more.
TREE = f"jobs[{_JOB},jobs[{_JOB},jobs[{_JOB}]]]"

MAX_DEPTH = 6


def is_folder(entry: dict) -> bool:
    return "Folder" in str(entry.get("_class", ""))


def typical_ms(entry: dict) -> int | None:
    """How long the last successful build took, if there has been one."""
    duration = (entry.get("lastSuccessfulBuild") or {}).get("duration")
    return int(duration) if isinstance(duration, int | float) and duration > 0 else None


def parameter_names(entry: dict) -> list[str]:
    names: list[str] = []
    for prop in entry.get("property") or []:
        for definition in prop.get("parameterDefinitions") or []:
            name = definition.get("name")
            if name:
                names.append(name)
    return names


class JenkinsIndexer:
    def __init__(self, jobs: JenkinsJobStore, reader: JenkinsReader) -> None:
        self._jobs = jobs
        self._reader = reader
        self._complete = True
        #: One crawl at a time: `_complete` belongs to the crawl in progress.
        self._lock = asyncio.Lock()

    async def refresh(self) -> None:
        """Re-crawl the controller.

        A crawl that could not read every folder is thrown away: the index JK
        already has stays as it was, rather than being replaced by a partial or
        empty one because Jenkins was unreachable for a moment.
        """
        async with self._lock:
            found: list[JenkinsJobRecord] = []
            self._complete = True
            await self._walk("", [], found, depth=0)
            if self._complete:
                self._jobs.replace_index(found)

    async def _walk(
        self,
        rest_path: str,
        segments: list[str],
        found: list[JenkinsJobRecord],
        *,
        depth: int,
    ) -> None:
        if depth > MAX_DEPTH:
            return
        try:
            payload = await self._reader.jobs_tree(rest_path, TREE)
        except JenkinsUnavailable, JenkinsAuthError, TargetNotFound:
            self._complete = False
            return
        await self._collect(payload, segments, found, depth=depth)

    async def _collect(
        self,
        payload: dict,
        segments: list[str],
        found: list[JenkinsJobRecord],
        *,
        depth: int,
    ) -> None:
        for entry in payload.get("jobs") or []:
            name = entry.get("name")
            if not name:
                continue
            path = [*segments, name]
            if not is_folder(entry):
                names = parameter_names(entry)
                if names:
                    found.append(
                        JenkinsJobRecord(
                            job_path="/".join(path),
                            name=name,
                            folder=" / ".join(path[:-1]),
                            url=entry.get("url", ""),
                            param_count=len(names),
                            typical_ms=typical_ms(entry),
                        )
                    )
                continue
            if entry.get("jobs") is not None:
                await self._collect(entry, path, found, depth=depth + 1)
            else:
                # The tree stopped here; ask this folder for its own children.
                rest = "/".join(f"job/{segment}" for segment in path)
                await self._walk(rest, path, found, depth=depth + 1)
