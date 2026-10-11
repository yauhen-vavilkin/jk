"""Find the build an ambiguous submission may have created.

Read-only. This module never links a run to a build and never re-sends anything:
it produces candidates, and a human decides.

The comparison rule is deliberate. Naive full-map equality NEVER matches, because
Jenkins returns every parameter the job defines -- including ones JK never
declared and one with an empty name -- and returns BooleanParameterValue as a
JSON boolean while JK sends the strings "true"/"false".
"""

from __future__ import annotations

from dataclasses import dataclass

from jk.errors import JenkinsUnavailable, TargetNotFound
from jk.jenkins.read import JenkinsReader


@dataclass(frozen=True)
class Candidate:
    build_number: int
    build_url: str
    started_at_ms: int
    result: str | None
    building: bool
    matched: dict[str, str]
    seconds_after_submit: int | None


def normalise(value: str) -> str:
    """Make two spellings of the same value comparable."""
    return value.strip().lower()


async def find_candidates(
    reader: JenkinsReader,
    *,
    rest_path: str,
    sent_params: dict[str, str],
    search_from_build_number: int,
    search_from_timestamp: int,
) -> list[Candidate]:
    """Builds at or after the search window whose sent parameters all match."""
    if not sent_params:
        return []
    builds = await reader.recent_builds(rest_path)
    candidates: list[Candidate] = []

    for build in builds:
        if build.number < search_from_build_number:
            continue
        if build.timestamp_ms <= 0 or build.timestamp_ms // 1000 < search_from_timestamp:
            continue
        try:
            actual = await reader.build_parameters(rest_path, build.number)
        except JenkinsUnavailable, TargetNotFound:
            continue

        # Compare ONLY what JK declared and sent. A sent name that Jenkins does
        # not report back is unverifiable, not a mismatch: Jenkins omits the
        # value key for a password parameter. An unverifiable name is skipped
        # and never enters `matched`, so a build is a candidate only when at
        # least one parameter was positively compared.
        matched: dict[str, str] = {}
        agrees = True
        compared = 0
        for name, expected in sent_params.items():
            if name not in actual:
                continue
            if normalise(actual[name]) != normalise(expected):
                agrees = False
                break
            matched[name] = actual[name]
            compared += 1

        if not agrees or compared == 0:
            continue

        candidates.append(
            Candidate(
                build_number=build.number,
                build_url=build.url,
                started_at_ms=build.timestamp_ms,
                result=build.result,
                building=build.building,
                matched=matched,
                seconds_after_submit=int(build.timestamp_ms / 1000) - search_from_timestamp,
            )
        )

    return candidates
