"""Drive one flow: decide, submit once, monitor, decide again.

A flow is an ordered list of steps that run one after the other; flows run
beside each other. This module owns only the decisions the board shows -- which
step may start, what a FAILURE does to the rest, what stopping means. Submitting
and monitoring stay in `engine/runner.py`, and the exactly-once claim stays in
the store.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from enum import StrEnum, auto

from jk.engine.runner import RunEngine
from jk.errors import JKError, SubmissionPreflightFailed
from jk.jenkins.abort import FAILED, REQUESTED, JenkinsAborter
from jk.store.flows import FlowStore
from jk.store.models import Run, Step, StepState
from jk.store.presets import PresetStore
from jk.store.records import Condition, FlowMeta, FlowStatus
from jk.store.store import RunStore

#: A step that has left the queue and reported, in Jenkins' own words.
REAL_RESULTS = (StepState.SUCCESS, StepState.UNSTABLE, StepState.FAILURE, StepState.ABORTED)

#: Worst first: the flow result is the worst real result any of its steps had.
RESULT_SEVERITY = ("FAILURE", "ABORTED", "UNSTABLE", "SUCCESS")

IN_FLIGHT_STATES = frozenset({StepState.SUBMIT_PENDING, StepState.QUEUED, StepState.RUNNING})

OnChange = Callable[[str], Awaitable[None]]


class Decision(StrEnum):
    RUN = auto()
    SKIP = auto()
    FAIL_FLOW = auto()


def evaluate(condition: Condition, previous: StepState | None) -> Decision:
    """What the condition says about starting, given the previous real result.

    `previous` is None for the first step of a flow and for a step whose
    predecessors were all skipped: there is no result to be unhappy about, so
    every condition except `after_failure` lets the step start.
    """
    failed = previous in (StepState.FAILURE, StepState.ABORTED)
    if condition is Condition.ALWAYS:
        return Decision.RUN
    if condition is Condition.AFTER_FAILURE:
        return Decision.RUN if failed else Decision.SKIP
    if condition is Condition.AFTER_SUCCESS:
        return Decision.RUN if previous in (None, StepState.SUCCESS) else Decision.SKIP
    return Decision.FAIL_FLOW if failed else Decision.RUN


def effective_result(run: Run, meta: FlowMeta, position: int) -> StepState | None:
    """The last real result before `position`, looking past skipped steps."""
    for step in reversed(run.steps[:position]):
        if meta.steps.get(step.position) is not None and meta.steps[step.position].skipped:
            continue
        if step.state in REAL_RESULTS:
            return step.state
        if step.state is StepState.REJECTED:
            return StepState.FAILURE
    return None


def flow_result(run: Run) -> str | None:
    """The worst result any step of the flow reported, or None when there is none."""
    seen = {step.state.value for step in run.steps if step.state in REAL_RESULTS}
    if any(step.state is StepState.REJECTED for step in run.steps):
        seen.add("FAILURE")
    for result in RESULT_SEVERITY:
        if result in seen:
            return result
    return None


class FlowSupervisor:
    """One task per active flow. Never two, and never one that outlives its flow."""

    def __init__(
        self,
        store: RunStore,
        flows: FlowStore,
        presets: PresetStore,
        engine: RunEngine,
        aborter: JenkinsAborter | None = None,
        *,
        on_change: OnChange | None = None,
    ) -> None:
        self._store = store
        self._flows = flows
        self._presets = presets
        self._engine = engine
        self._aborter = aborter
        self._on_change = on_change
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()
        #: Flows with a step between its frozen body and the end of its submission.
        #: While a flow is here its positions must not change and it must not be
        #: resumed: the engine claims the step by position after an awaited read.
        self._sending: set[str] = set()
        #: "Stop and abort" arrived while a submission was still going out. The
        #: one stop request is sent as soon as Jenkins says where the build is.
        self._abort_after_send: set[str] = set()

    def is_sending(self, flow_id: str) -> bool:
        return flow_id in self._sending

    async def start(self) -> None:
        """Pick up every flow that was still going when the process last stopped.

        A destructive approval belongs to the session that gave it: after a
        restart every destructive step not yet sent, in any flow that has
        started, is held until the user reviews it again. A stopped flow whose
        build is still in Jenkins is watched until that build reports.
        """
        for flow_id in self._flows.list(active=True, include_cleared=True):
            run, meta = self._flows.get(flow_id)
            if meta.status is not FlowStatus.DRAFT:
                for step in run.steps:
                    if step.destructive and _is_pending(meta)(step):
                        self._flows.set_held(flow_id, step.position, True)
            in_flight = _first(run, lambda step: step.state in IN_FLIGHT_STATES)
            if meta.status is FlowStatus.RUNNING or in_flight is not None:
                await self.watch(flow_id)

    async def watch(self, flow_id: str) -> None:
        """Make sure exactly one task is driving this flow."""
        async with self._lock:
            current = self._tasks.get(flow_id)
            if current is not None and not current.done():
                return
            task = asyncio.create_task(self._drive(flow_id), name=f"jk-flow-{flow_id}")
            self._tasks[flow_id] = task
            task.add_done_callback(lambda done, owned=flow_id: self._discard(owned, done))

    async def wait(self, flow_id: str) -> None:
        task = self._tasks.get(flow_id)
        if task is not None:
            await asyncio.shield(task)

    async def shutdown(self) -> None:
        async with self._lock:
            tasks = list(self._tasks.values())
            self._tasks.clear()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def _discard(self, flow_id: str, task: asyncio.Task[None]) -> None:
        if self._tasks.get(flow_id) is task:
            self._tasks.pop(flow_id, None)

    async def run(self, flow_id: str) -> None:
        """Start a draft. Nothing is sent before this."""
        self._flows.set_status(flow_id, FlowStatus.RUNNING, started=True)
        await self._changed(flow_id)
        await self.watch(flow_id)

    async def resume(self, flow_id: str, *, from_position: int | None = None) -> None:
        """Continue a stopped or failed flow.

        Resuming *is* the answer to the question the condition asked, so the step the user
        resumes from starts whatever the previous result was. While the stopped build is still
        in Jenkins nothing is forced. Every later step is decided by its own condition again.
        """
        if from_position is not None:
            self._skip_before(flow_id, from_position)
        forced = self._first_pending_position(flow_id)
        self._flows.set_status(
            flow_id,
            FlowStatus.RUNNING,
            clear_failed=True,
            resume_from=forced,
            started=True,
        )
        await self._changed(flow_id)
        await self.watch(flow_id)

    async def stop(self, flow_id: str, *, abort_current: bool) -> None:
        """Send nothing more. With `abort_current`, ask Jenkins once to stop."""
        self._flows.set_status(flow_id, FlowStatus.STOPPED)
        if abort_current:
            run, _ = self._flows.get(flow_id)
            if flow_id in self._sending and _first(
                run, lambda step: step.state is StepState.SUBMIT_PENDING
            ):
                self._abort_after_send.add(flow_id)
            else:
                await self._abort_in_flight(flow_id)
        self._settle_stopped(flow_id)
        await self._changed(flow_id)

    def _settle_stopped(self, flow_id: str) -> None:
        """A stopped flow with nothing in Jenkins and nothing left to send is over.

        A step that still needs attention is not over: it waits for the user to
        link its build or end the flow.
        """
        run, meta = self._flows.get(flow_id)
        if meta.status is not FlowStatus.STOPPED:
            return
        if _first(run, lambda step: step.state in IN_FLIGHT_STATES) is not None:
            return
        if _first(run, lambda step: step.state is StepState.NEEDS_ATTENTION) is not None:
            return
        if _first(run, _is_pending(meta)) is not None:
            return
        self._flows.set_status(flow_id, FlowStatus.FINISHED, finished=True)

    async def appended(self, flow_id: str) -> None:
        """A step was added, moved or removed; wake the flow if its task has parked."""
        _, meta = self._flows.get(flow_id)
        if meta.status is FlowStatus.RUNNING:
            await self.watch(flow_id)
        await self._changed(flow_id)

    async def linked(self, flow_id: str) -> None:
        """A needs-attention step was linked to a build; monitoring continues.

        Only a flow that was waiting for this decision goes back to running. A
        stopped flow stays stopped: the linked build is watched, nothing after it
        is sent.
        """
        _, meta = self._flows.get(flow_id)
        if meta.status is FlowStatus.NEEDS_ATTENTION:
            self._flows.set_status(flow_id, FlowStatus.RUNNING)
        await self._changed(flow_id)
        await self.watch(flow_id)

    async def confirmed(self, flow_id: str) -> None:
        """Held steps were reviewed and released; a running flow goes on."""
        await self.appended(flow_id)

    async def close(self, flow_id: str) -> None:
        """End a flow whose step needs attention, stopped or not. Nothing is sent."""
        self._flows.set_status(flow_id, FlowStatus.FAILED, finished=True)
        await self._changed(flow_id)

    async def _drive(self, flow_id: str) -> None:
        try:
            await self._drive_loop(flow_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            await self._broke(flow_id)

    async def _broke(self, flow_id: str) -> None:
        """An unexpected error never leaves a flow silently 'running'.

        The card shows a sentence, not the program's error text.
        """
        run, meta = self._flows.get(flow_id)
        in_flight = _first(run, lambda step: step.state in IN_FLIGHT_STATES)
        if in_flight is not None:
            self._store.mark_needs_attention(
                flow_id,
                in_flight.position,
                kind="watcher_error",
                message=(
                    "Jenkins answered in a way JK did not expect, so JK stopped watching "
                    "this step. The build may still be running; check it in Jenkins."
                ),
            )
            if meta.status is FlowStatus.RUNNING:
                self._flows.set_status(flow_id, FlowStatus.NEEDS_ATTENTION)
        else:
            pending = _first(run, _is_pending(meta))
            if pending is not None:
                self._flows.set_held(flow_id, pending.position, True)
        await self._changed(flow_id)

    async def _drive_loop(self, flow_id: str) -> None:
        while True:
            run, meta = self._flows.get(flow_id)

            in_flight = _first(run, lambda step: step.state in IN_FLIGHT_STATES)
            if in_flight is not None:
                await self._engine.monitor_step(
                    flow_id, in_flight.position, on_poll=lambda: self._changed(flow_id)
                )
                await self._changed(flow_id)
                continue

            if _first(run, lambda step: step.state is StepState.NEEDS_ATTENTION) is not None:
                if meta.status is FlowStatus.RUNNING:
                    self._flows.set_status(flow_id, FlowStatus.NEEDS_ATTENTION)
                await self._changed(flow_id)
                return

            if meta.status is not FlowStatus.RUNNING:
                self._settle_stopped(flow_id)
                await self._changed(flow_id)
                return

            if _first(run, lambda step: step.state is StepState.REJECTED) is not None:
                self._flows.set_status(flow_id, FlowStatus.FAILED, finished=True)
                await self._changed(flow_id)
                return

            step = _first(run, _is_pending(meta))
            if step is None:
                self._flows.set_status(flow_id, FlowStatus.FINISHED, finished=True)
                await self._changed(flow_id)
                return

            if meta.steps[step.position].held:
                # Waiting for the user to review a step added after the start.
                return

            if meta.resume_from == step.position:
                self._flows.clear_resume_from(flow_id)
                decision = Decision.RUN
            else:
                decision = evaluate(
                    meta.steps[step.position].condition,
                    effective_result(run, meta, step.position),
                )
            if decision is Decision.FAIL_FLOW:
                self._flows.set_status(
                    flow_id, FlowStatus.FAILED, failed_at_position=step.position, finished=True
                )
                await self._changed(flow_id)
                return
            if decision is Decision.SKIP:
                self._flows.mark_skipped(flow_id, step.position)
                await self._changed(flow_id)
                continue

            if not await self._submit(flow_id, step):
                return
            await self._changed(flow_id)

    async def _submit(self, flow_id: str, step: Step) -> bool:
        """Freeze the body, claim the step once, submit it. False stops the loop."""
        _, meta = self._flows.get(flow_id)
        preset = self._presets.find(meta.steps[step.position].preset_id)
        if preset is None:
            self._store.mark_needs_attention(
                flow_id,
                step.position,
                kind="preset_missing",
                message=(
                    "The saved job this step points at is gone, so JK does not know what "
                    "to send. Nothing was sent."
                ),
            )
            self._flows.set_status(flow_id, FlowStatus.NEEDS_ATTENTION)
            await self._changed(flow_id)
            return False

        web_meta = meta.steps[step.position]
        if preset.drift is not None or not web_meta.frozen:
            # Jenkins changed the job, or nobody reviewed this body: send nothing
            # and wait for a review.
            self._flows.set_held(flow_id, step.position, True)
            await self._changed(flow_id)
            return False

        self._sending.add(flow_id)
        try:
            state = await self._engine.submit_step(flow_id, step.position)
        except SubmissionPreflightFailed as exc:
            self._flows.stop_before_submit(flow_id, step.position, message=str(exc))
            state = self._store.get_run(flow_id).steps[step.position].state
        finally:
            self._sending.discard(flow_id)
        if flow_id in self._abort_after_send:
            self._abort_after_send.discard(flow_id)
            if state in (StepState.QUEUED, StepState.RUNNING):
                await self._abort_in_flight(flow_id)

        if state in (StepState.QUEUED, StepState.RUNNING):
            return True
        _, meta = self._flows.get(flow_id)
        if meta.status is not FlowStatus.RUNNING:
            # The user stopped the flow meanwhile, and a Stop that landed during
            # the read refused the claim: their decision stands.
            await self._changed(flow_id)
            return False
        if state is StepState.PREPARED:
            # Refused for any other reason: nothing was sent; ask for a review
            # rather than trying again on our own.
            self._flows.set_held(flow_id, step.position, True)
            await self._changed(flow_id)
            return False
        if state is StepState.NEEDS_ATTENTION:
            self._flows.set_status(flow_id, FlowStatus.NEEDS_ATTENTION)
        else:
            self._flows.set_status(flow_id, FlowStatus.FAILED, finished=True)
        await self._changed(flow_id)
        return False

    async def _abort_in_flight(self, flow_id: str) -> None:
        """One request, for the one step that is in Jenkins right now."""
        if self._aborter is None:
            return
        run, meta = self._flows.get(flow_id)
        step = _first(run, lambda item: item.state in (StepState.QUEUED, StepState.RUNNING))
        if step is None:
            return
        if meta.steps[step.position].abort_state is not None:
            # One stop per build, ever: not after a failed one, not after a resume.
            return
        self._flows.set_abort_state(flow_id, step.position, REQUESTED)
        try:
            if step.state is StepState.RUNNING and step.build_url:
                outcome = await self._aborter.stop_build(step.build_url)
            elif (queue_id := _queue_id(step)) is not None:
                outcome = await self._aborter.cancel_queue_item(queue_id)
            else:
                outcome = FAILED
        except JKError:
            outcome = FAILED
        self._flows.set_abort_state(flow_id, step.position, outcome)

    def _first_pending_position(self, flow_id: str) -> int | None:
        run, meta = self._flows.get(flow_id)
        if _first(run, lambda step: step.state in IN_FLIGHT_STATES) is not None:
            return None  # The build has not reported: the next condition has not asked yet.
        step = _first(run, _is_pending(meta))
        return None if step is None else step.position

    def _skip_before(self, flow_id: str, from_position: int) -> None:
        """Resuming from step N leaves the steps before it out of the run."""
        run, _ = self._flows.get(flow_id)
        for step in run.steps:
            if step.position < from_position and step.state is StepState.PREPARED:
                self._flows.mark_skipped(flow_id, step.position)

    async def _changed(self, flow_id: str) -> None:
        if self._on_change is not None:
            await self._on_change(flow_id)


def _is_pending(meta: FlowMeta) -> Callable[[Step], bool]:
    """A step that is still waiting its turn, and was not skipped by a condition."""

    def matches(step: Step) -> bool:
        return step.state is StepState.PREPARED and not meta.steps[step.position].skipped

    return matches


def _queue_id(step: Step) -> int | None:
    """The queue item's id: stored once polled, otherwise read from `/queue/item/<id>/`."""
    if step.jenkins_queue_id is not None:
        return step.jenkins_queue_id
    found = re.search(r"/queue/item/(\d+)/?$", step.queue_url or "")
    return int(found.group(1)) if found else None


def _first(run: Run, matches: Callable[[Step], bool]) -> Step | None:
    for step in run.steps:
        if matches(step):
            return step
    return None
