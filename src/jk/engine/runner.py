"""Submit and monitor the steps of a persisted run."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from jk.errors import (
    AmbiguousSubmission,
    JenkinsAuthError,
    JenkinsUnavailable,
    SubmissionPreflightFailed,
    SubmissionRejected,
    TargetNotFound,
)
from jk.jenkins.models import BuildInfo
from jk.jenkins.read import JenkinsReader
from jk.jenkins.submit import JenkinsSubmitter
from jk.store.models import FINAL_STEP_STATES, StepState, state_for_result
from jk.store.store import RunStore

QUEUE_POLL_SECONDS = 3.0
RUNNING_POLL_SECONDS = 15.0
MAX_SCAN_ATTEMPTS = 3
MAX_MONITOR_ERRORS = 5

SleepFn = Callable[[float], Awaitable[None]]


class RunEngine:
    def __init__(
        self,
        store: RunStore,
        reader: JenkinsReader,
        submitter: JenkinsSubmitter,
        *,
        sleep: SleepFn = asyncio.sleep,
    ) -> None:
        self._store = store
        self._reader = reader
        self._submitter = submitter
        self._sleep = sleep
        self._scan_misses: dict[tuple[str, int], int] = {}

    async def submit_step(self, run_id: str, position: int) -> StepState:
        """Claim and submit one persisted step at most once."""
        step = self._store.get_run(run_id).steps[position]
        if step.state is not StepState.PREPARED:
            return step.state

        rest_path = rest_path_of(step.job_path)
        try:
            next_number = await self._reader.next_build_number(rest_path)
        except (JenkinsUnavailable, JenkinsAuthError, TargetNotFound) as exc:
            raise SubmissionPreflightFailed(
                "JK could not check this job before starting it. Nothing was sent. "
                f"{exc} Fix the problem, then review and resume this flow."
            ) from exc

        if not self._store.claim_submit_pending(
            run_id,
            position,
            next_build_number=next_number,
        ):
            return self._store.get_run(run_id).steps[position].state
        return await self._submit_claimed_step(run_id, position)

    async def poll_step_once(self, run_id: str, position: int) -> StepState:
        step = self._store.get_run(run_id).steps[position]
        if step.state in FINAL_STEP_STATES:
            return step.state
        if step.state is StepState.QUEUED:
            return await self._poll_queue(run_id, position)
        if step.state is StepState.RUNNING:
            return await self._poll_build(run_id, position)
        return step.state

    async def _poll_queue(self, run_id: str, position: int) -> StepState:
        step = self._store.get_run(run_id).steps[position]
        assert step.queue_url is not None
        try:
            item = await self._reader.queue_item(step.queue_url)
        except TargetNotFound:
            return await self._scan_for_build(run_id, position)
        if item.cancelled:
            applied = self._store.mark_final(run_id, position, result="ABORTED")
            return StepState.ABORTED if applied else self._current_state(run_id, position)
        if item.build_number is not None and item.build_url:
            applied = self._store.mark_running(
                run_id,
                position,
                build_number=item.build_number,
                build_url=item.build_url,
                queue_id=item.id,
            )
            return StepState.RUNNING if applied else self._current_state(run_id, position)
        return StepState.QUEUED

    async def _scan_for_build(self, run_id: str, position: int) -> StepState:
        step = self._store.get_run(run_id).steps[position]
        rest_path = rest_path_of(step.job_path)
        queue_id = _queue_id_from_url(step.queue_url or "")
        builds = await self._reader.recent_builds(rest_path)
        for build in builds:
            if queue_id is not None and build.queue_id == queue_id:
                applied = self._store.mark_running(
                    run_id,
                    position,
                    build_number=build.number,
                    build_url=build.url,
                    queue_id=build.queue_id,
                )
                if not applied:
                    return self._current_state(run_id, position)
                self._scan_misses.pop((run_id, position), None)
                return await self._record_if_final(run_id, position, build)
        key = (run_id, position)
        self._scan_misses[key] = self._scan_misses.get(key, 0) + 1
        if self._scan_misses[key] >= MAX_SCAN_ATTEMPTS:
            applied = self._store.mark_needs_attention(
                run_id,
                position,
                kind="target_not_found",
                message=(
                    "The Jenkins queue item is gone and no build matches it. "
                    "JK kept the last known state and will not start anything."
                ),
            )
            return StepState.NEEDS_ATTENTION if applied else self._current_state(run_id, position)
        return StepState.QUEUED

    async def _poll_build(self, run_id: str, position: int) -> StepState:
        step = self._store.get_run(run_id).steps[position]
        assert step.build_url is not None
        try:
            build = await self._reader.build_by_url(step.build_url)
        except TargetNotFound:
            return await self._record_vanished_build(run_id, position)
        self._scan_misses.pop((run_id, position), None)
        return await self._record_if_final(run_id, position, build)

    async def _record_vanished_build(self, run_id: str, position: int) -> StepState:
        key = (run_id, position)
        self._scan_misses[key] = self._scan_misses.get(key, 0) + 1
        if self._scan_misses[key] >= MAX_SCAN_ATTEMPTS:
            applied = self._store.mark_needs_attention(
                run_id,
                position,
                kind="target_not_found",
                message=(
                    "The Jenkins build can no longer be found. "
                    "JK kept the last known state and will not start anything."
                ),
            )
            return StepState.NEEDS_ATTENTION if applied else self._current_state(run_id, position)
        return StepState.RUNNING

    async def _record_if_final(self, run_id: str, position: int, build: BuildInfo) -> StepState:
        if not self._store.update_build_timing(
            run_id,
            position,
            started_at_ms=build.timestamp_ms,
            duration_ms=build.duration_ms,
            estimated_duration_ms=build.estimated_ms,
        ):
            return self._current_state(run_id, position)
        if not build.is_final:
            return StepState.RUNNING
        raw_result = build.result
        state = state_for_result(raw_result)
        if state is None:
            applied = self._store.mark_needs_attention(
                run_id,
                position,
                kind="unknown_result",
                message=(
                    f"Jenkins reported the final result {raw_result!r}, which JK does not "
                    "know how to interpret. JK kept the last known state and will "
                    "not start anything."
                ),
            )
            return StepState.NEEDS_ATTENTION if applied else self._current_state(run_id, position)
        applied = self._store.mark_final(run_id, position, result=raw_result)
        return state if applied else self._current_state(run_id, position)

    async def monitor_step(
        self, run_id: str, position: int, on_poll: Callable[[], Awaitable[None]] | None = None
    ) -> StepState:
        start = self._current_state(run_id, position)
        errors = 0
        while True:
            try:
                state = await self.poll_step_once(run_id, position)
                errors = 0
            except JenkinsUnavailable as exc:
                errors += 1
                if errors >= MAX_MONITOR_ERRORS:
                    applied = self._store.mark_needs_attention(
                        run_id,
                        position,
                        kind="connection_failure",
                        message=f"Jenkins could not be reached while monitoring: {exc}",
                    )
                    return (
                        StepState.NEEDS_ATTENTION
                        if applied
                        else self._current_state(run_id, position)
                    )
                await self._sleep(RUNNING_POLL_SECONDS * errors)
                continue
            except JenkinsAuthError as exc:
                applied = self._store.mark_needs_attention(
                    run_id, position, kind="authentication", message=str(exc)
                )
                return (
                    StepState.NEEDS_ATTENTION if applied else self._current_state(run_id, position)
                )
            except TargetNotFound as exc:
                applied = self._store.mark_needs_attention(
                    run_id,
                    position,
                    kind="target_not_found",
                    message=f"Jenkins could not find the configured monitoring target: {exc}",
                )
                return (
                    StepState.NEEDS_ATTENTION if applied else self._current_state(run_id, position)
                )
            if state in FINAL_STEP_STATES or state is not start:
                return state
            if on_poll is not None:
                await on_poll()
            delay = QUEUE_POLL_SECONDS if state is StepState.QUEUED else RUNNING_POLL_SECONDS
            await self._sleep(delay)

    async def _submit_claimed_step(self, run_id: str, position: int) -> StepState:
        step = self._store.get_run(run_id).steps[position]
        body = self._store.get_step_inputs(run_id, position)
        try:
            outcome = await self._submitter.submit(rest_path_of(step.job_path), body)
        except AmbiguousSubmission as exc:
            applied = self._store.mark_needs_attention(
                run_id,
                position,
                kind="ambiguous_submission",
                message=str(exc),
            )
            return StepState.NEEDS_ATTENTION if applied else self._current_state(run_id, position)
        except (SubmissionRejected, JenkinsAuthError) as exc:
            applied = self._store.mark_rejected(run_id, position, message=str(exc))
            return StepState.REJECTED if applied else self._current_state(run_id, position)
        note = (
            "Jenkins attached this run to a queue item that already existed. "
            "The build may have been started elsewhere."
            if outcome.pre_existing
            else None
        )
        applied = self._store.mark_queued(run_id, position, queue_url=outcome.queue_url, note=note)
        return StepState.QUEUED if applied else self._current_state(run_id, position)

    def _current_state(self, run_id: str, position: int) -> StepState:
        return self._store.get_run(run_id).steps[position].state


def rest_path_of(job_path: str) -> str:
    return "/".join(f"job/{segment}" for segment in job_path.strip("/").split("/"))


def _queue_id_from_url(queue_url: str) -> int | None:
    parts = [part for part in queue_url.strip("/").split("/") if part]
    for index, part in enumerate(parts):
        if part == "item" and index + 1 < len(parts):
            try:
                return int(parts[index + 1])
            except ValueError:
                return None
    return None
