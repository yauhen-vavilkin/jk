"""The flow supervisor: conditions, stop and abort, resume, append."""

from __future__ import annotations

import asyncio
from urllib.parse import parse_qs

import httpx
import pytest

from jk.engine.flows import Decision, FlowSupervisor, evaluate, flow_result
from jk.engine.runner import RunEngine
from jk.jenkins.abort import JenkinsAborter
from jk.jenkins.read import JenkinsReader
from jk.jenkins.submit import JenkinsSubmitter
from jk.store.flows import FlowStore
from jk.store.models import StepState
from jk.store.presets import PresetStore
from jk.store.records import Condition, FlowStatus, ParamMode, ParamSetting
from jk.store.store import RunStore
from tests.webapp import BUILD_URL, FakeJenkins


@pytest.fixture
def presets(store: RunStore) -> PresetStore:
    return PresetStore(store)


@pytest.fixture
def flows(store: RunStore) -> FlowStore:
    return FlowStore(store)


def make_preset(presets: PresetStore, name: str = "step"):
    return presets.create(
        name=name,
        operation="Test",
        job_path=f"folder/{name}",
        summary_params=("CLUSTER",),
        params={
            "CLUSTER": ParamSetting(ParamMode.FIXED, "example-cluster"),
            "BRANCH": ParamSetting(ParamMode.ASK, None, "snapshot"),
            "PLATFORM": ParamSetting(ParamMode.DEFAULT, None),
        },
    )


def add_step(flows: FlowStore, flow_id: str, preset, **overrides) -> int:
    fields = {
        "preset_id": preset.id,
        "preset_name": preset.name,
        "job_path": preset.job_path,
        "destructive": preset.destructive,
        "summary_params": preset.summary_params,
    }
    fields.update(overrides)
    position = flows.append_step(flow_id, **fields)
    if not fields.get("held"):
        # What the Review does: fix the body the user saw as the one to send.
        flows.freeze_step_params(
            flow_id,
            position,
            preset.sent_values(fields.get("run_values") or {}),
            destructive=fields["destructive"],
        )
    return position


class FakeEngine:
    """Submits and monitors without a network, returning scripted results."""

    def __init__(self, store: RunStore, results: list[str] | None = None) -> None:
        self.store = store
        self.results = list(results or [])
        self.submitted: list[int] = []
        self.monitor_started = asyncio.Event()
        self.release_monitor = asyncio.Event()
        self.block_monitor = False

    def _next_result(self) -> str:
        return self.results.pop(0) if self.results else "SUCCESS"

    async def submit_step(self, run_id: str, position: int) -> StepState:
        self.submitted.append(position)
        assert self.store.claim_submit_pending(run_id, position, next_build_number=position + 1)
        self.store.mark_queued(
            run_id, position, queue_url=f"https://jenkins.invalid/queue/item/{position}/", note=None
        )
        self.store.mark_running(
            run_id, position, build_number=100 + position, build_url=BUILD_URL, queue_id=position
        )
        return StepState.RUNNING

    async def monitor_step(self, run_id: str, position: int, on_poll=None) -> StepState:
        self.monitor_started.set()
        if self.block_monitor:
            await self.release_monitor.wait()
        result = self._next_result()
        self.store.mark_final(run_id, position, result=result)
        return StepState(result)


def supervisor(store, flows, presets, engine, aborter=None) -> FlowSupervisor:
    return FlowSupervisor(store, flows, presets, engine, aborter)


async def run_to_rest(sup: FlowSupervisor, flow_id: str) -> None:
    await sup.run(flow_id)
    await sup.wait(flow_id)


@pytest.mark.parametrize("newer", ["stop", "claim", "attention"])
def test_a_late_preflight_failure_preserves_a_newer_decision(store, flows, presets, newer):
    preset = make_preset(presets)
    flow_id = flows.create(name="Flow")
    add_step(flows, flow_id, preset)
    flows.set_status(flow_id, FlowStatus.RUNNING, started=True)
    if newer == "stop":
        flows.set_status(flow_id, FlowStatus.STOPPED)
    elif newer == "claim":
        assert store.claim_submit_pending(flow_id, 0, next_build_number=41)
    else:
        store.mark_needs_attention(flow_id, 0, kind="other", message="newer decision")
    before_run, before_meta = flows.get(flow_id)

    assert not flows.stop_before_submit(flow_id, 0, message="late read failure")

    after_run, after_meta = flows.get(flow_id)
    assert after_meta.status is before_meta.status
    assert after_run.steps[0] == before_run.steps[0]
    assert after_run.error_kind == before_run.error_kind
    assert after_run.error_message == before_run.error_message


@pytest.mark.parametrize(
    ("condition", "previous", "expected"),
    [
        (Condition.UNLESS_FAILURE, None, Decision.RUN),
        (Condition.UNLESS_FAILURE, StepState.SUCCESS, Decision.RUN),
        (Condition.UNLESS_FAILURE, StepState.UNSTABLE, Decision.RUN),
        (Condition.UNLESS_FAILURE, StepState.FAILURE, Decision.FAIL_FLOW),
        (Condition.UNLESS_FAILURE, StepState.ABORTED, Decision.FAIL_FLOW),
        (Condition.AFTER_SUCCESS, None, Decision.RUN),
        (Condition.AFTER_SUCCESS, StepState.SUCCESS, Decision.RUN),
        (Condition.AFTER_SUCCESS, StepState.UNSTABLE, Decision.SKIP),
        (Condition.AFTER_SUCCESS, StepState.FAILURE, Decision.SKIP),
        (Condition.AFTER_SUCCESS, StepState.ABORTED, Decision.SKIP),
        (Condition.ALWAYS, StepState.FAILURE, Decision.RUN),
        (Condition.ALWAYS, StepState.SUCCESS, Decision.RUN),
        (Condition.AFTER_FAILURE, StepState.FAILURE, Decision.RUN),
        (Condition.AFTER_FAILURE, StepState.ABORTED, Decision.RUN),
        (Condition.AFTER_FAILURE, StepState.SUCCESS, Decision.SKIP),
        (Condition.AFTER_FAILURE, StepState.UNSTABLE, Decision.SKIP),
        (Condition.AFTER_FAILURE, None, Decision.SKIP),
    ],
)
def test_every_condition_and_previous_result(condition, previous, expected) -> None:
    assert evaluate(condition, previous) is expected


async def test_a_flow_of_successes_finishes(store, flows, presets) -> None:
    preset = make_preset(presets)
    flow_id = flows.create(name="Flow")
    add_step(flows, flow_id, preset)
    add_step(flows, flow_id, preset)
    engine = FakeEngine(store, ["SUCCESS", "SUCCESS"])

    await run_to_rest(supervisor(store, flows, presets, engine), flow_id)

    run, meta = flows.get(flow_id)
    assert engine.submitted == [0, 1]
    assert meta.status is FlowStatus.FINISHED
    assert flow_result(run) == "SUCCESS"


async def test_unstable_lets_the_next_default_step_run(store, flows, presets) -> None:
    preset = make_preset(presets)
    flow_id = flows.create(name="Flow")
    add_step(flows, flow_id, preset)
    add_step(flows, flow_id, preset)
    engine = FakeEngine(store, ["UNSTABLE", "SUCCESS"])

    await run_to_rest(supervisor(store, flows, presets, engine), flow_id)

    run, meta = flows.get(flow_id)
    assert engine.submitted == [0, 1]
    assert meta.status is FlowStatus.FINISHED
    assert flow_result(run) == "UNSTABLE"


async def test_failure_stops_the_flow_and_leaves_the_rest_planned(store, flows, presets) -> None:
    preset = make_preset(presets)
    flow_id = flows.create(name="Flow")
    for _ in range(3):
        add_step(flows, flow_id, preset)
    engine = FakeEngine(store, ["SUCCESS", "FAILURE"])

    await run_to_rest(supervisor(store, flows, presets, engine), flow_id)

    run, meta = flows.get(flow_id)
    assert engine.submitted == [0, 1]
    assert meta.status is FlowStatus.FAILED
    assert meta.failed_at_position == 2
    assert run.steps[2].state is StepState.PREPARED


async def test_only_after_success_is_skipped_after_unstable(store, flows, presets) -> None:
    preset = make_preset(presets)
    flow_id = flows.create(name="Flow")
    add_step(flows, flow_id, preset)
    add_step(flows, flow_id, preset, condition=Condition.AFTER_SUCCESS)
    add_step(flows, flow_id, preset)
    engine = FakeEngine(store, ["UNSTABLE", "SUCCESS"])

    await run_to_rest(supervisor(store, flows, presets, engine), flow_id)

    _, meta = flows.get(flow_id)
    assert engine.submitted == [0, 2]
    assert meta.steps[1].skipped is True
    assert meta.status is FlowStatus.FINISHED


async def test_even_after_failure_runs_and_the_flow_keeps_going(store, flows, presets) -> None:
    preset = make_preset(presets)
    flow_id = flows.create(name="Flow")
    add_step(flows, flow_id, preset)
    add_step(flows, flow_id, preset, condition=Condition.ALWAYS)
    engine = FakeEngine(store, ["FAILURE", "SUCCESS"])

    await run_to_rest(supervisor(store, flows, presets, engine), flow_id)

    run, meta = flows.get(flow_id)
    assert engine.submitted == [0, 1]
    assert meta.status is FlowStatus.FINISHED
    assert flow_result(run) == "FAILURE"


async def test_only_after_failure_is_skipped_after_success(store, flows, presets) -> None:
    preset = make_preset(presets)
    flow_id = flows.create(name="Flow")
    add_step(flows, flow_id, preset)
    add_step(flows, flow_id, preset, condition=Condition.AFTER_FAILURE)
    engine = FakeEngine(store, ["SUCCESS"])

    await run_to_rest(supervisor(store, flows, presets, engine), flow_id)

    _, meta = flows.get(flow_id)
    assert engine.submitted == [0]
    assert meta.steps[1].skipped is True


async def test_a_skipped_step_passes_the_previous_result_through(store, flows, presets) -> None:
    preset = make_preset(presets)
    flow_id = flows.create(name="Flow")
    add_step(flows, flow_id, preset)
    add_step(flows, flow_id, preset, condition=Condition.AFTER_FAILURE)
    add_step(flows, flow_id, preset, condition=Condition.AFTER_SUCCESS)
    engine = FakeEngine(store, ["SUCCESS", "SUCCESS"])

    await run_to_rest(supervisor(store, flows, presets, engine), flow_id)

    _, meta = flows.get(flow_id)
    # Step 2 was skipped; step 3 reads step 1's SUCCESS, not "no result".
    assert engine.submitted == [0, 2]
    assert meta.steps[1].skipped is True


async def test_resume_continues_from_the_step_that_refused(store, flows, presets) -> None:
    preset = make_preset(presets)
    flow_id = flows.create(name="Flow")
    for _ in range(3):
        add_step(flows, flow_id, preset)
    engine = FakeEngine(store, ["FAILURE"])
    sup = supervisor(store, flows, presets, engine)
    await run_to_rest(sup, flow_id)
    assert flows.get(flow_id)[1].failed_at_position == 1

    engine.results = ["SUCCESS", "SUCCESS"]
    await sup.resume(flow_id)
    await sup.wait(flow_id)

    _, meta = flows.get(flow_id)
    assert engine.submitted == [0, 1, 2]
    assert meta.status is FlowStatus.FINISHED
    assert meta.failed_at_position is None


async def test_resume_from_a_later_step_skips_the_ones_before_it(store, flows, presets) -> None:
    preset = make_preset(presets)
    flow_id = flows.create(name="Flow")
    for _ in range(3):
        add_step(flows, flow_id, preset)
    engine = FakeEngine(store, ["FAILURE"])
    sup = supervisor(store, flows, presets, engine)
    await run_to_rest(sup, flow_id)

    engine.results = ["SUCCESS"]
    await sup.resume(flow_id, from_position=2)
    await sup.wait(flow_id)

    _, meta = flows.get(flow_id)
    assert engine.submitted == [0, 2]
    assert meta.steps[1].skipped is True


async def test_a_step_added_while_running_starts_after_the_current_one(
    store, flows, presets
) -> None:
    preset = make_preset(presets)
    flow_id = flows.create(name="Flow")
    add_step(flows, flow_id, preset)
    engine = FakeEngine(store, ["SUCCESS", "SUCCESS"])
    engine.block_monitor = True
    sup = supervisor(store, flows, presets, engine)

    await sup.run(flow_id)
    await engine.monitor_started.wait()

    add_step(flows, flow_id, preset, added_while_running=True)
    await sup.appended(flow_id)
    engine.release_monitor.set()
    await sup.wait(flow_id)

    _, meta = flows.get(flow_id)
    assert engine.submitted == [0, 1]
    assert meta.status is FlowStatus.FINISHED
    assert meta.steps[1].added_while_running is True


async def test_stop_sends_nothing_further_and_lets_the_build_finish(store, flows, presets) -> None:
    preset = make_preset(presets)
    flow_id = flows.create(name="Flow")
    add_step(flows, flow_id, preset)
    add_step(flows, flow_id, preset)
    engine = FakeEngine(store, ["SUCCESS", "SUCCESS"])
    engine.block_monitor = True
    sup = supervisor(store, flows, presets, engine)

    await sup.run(flow_id)
    await engine.monitor_started.wait()
    await sup.stop(flow_id, abort_current=False)
    engine.release_monitor.set()
    await sup.wait(flow_id)

    run, meta = flows.get(flow_id)
    assert engine.submitted == [0]
    assert meta.status is FlowStatus.STOPPED
    assert run.steps[0].state is StepState.SUCCESS
    assert run.steps[1].state is StepState.PREPARED


async def test_a_stopped_flow_resumes_from_its_first_planned_step(store, flows, presets) -> None:
    preset = make_preset(presets)
    flow_id = flows.create(name="Flow")
    add_step(flows, flow_id, preset)
    add_step(flows, flow_id, preset)
    engine = FakeEngine(store, ["SUCCESS"])
    engine.block_monitor = True
    sup = supervisor(store, flows, presets, engine)

    await sup.run(flow_id)
    await engine.monitor_started.wait()
    await sup.stop(flow_id, abort_current=False)
    engine.release_monitor.set()
    await sup.wait(flow_id)

    engine.results = ["SUCCESS"]
    await sup.resume(flow_id)
    await sup.wait(flow_id)

    assert engine.submitted == [0, 1]
    assert flows.get(flow_id)[1].status is FlowStatus.FINISHED


async def test_resume_before_the_stopped_build_reports_keeps_the_next_condition(
    store, flows, presets
) -> None:
    preset = make_preset(presets)
    flow_id = flows.create(name="Flow")
    add_step(flows, flow_id, preset)
    add_step(flows, flow_id, preset)
    engine = FakeEngine(store, ["FAILURE"])
    engine.block_monitor = True
    sup = supervisor(store, flows, presets, engine)

    await sup.run(flow_id)
    await engine.monitor_started.wait()
    await sup.stop(flow_id, abort_current=False)
    await sup.resume(flow_id)
    engine.release_monitor.set()
    await sup.wait(flow_id)

    _, meta = flows.get(flow_id)
    assert engine.submitted == [0]
    assert meta.status is FlowStatus.FAILED
    assert meta.failed_at_position == 1


def real_engine(store: RunStore, jenkins: FakeJenkins) -> tuple[RunEngine, JenkinsAborter]:
    client = httpx.AsyncClient(base_url="https://jenkins.invalid", transport=jenkins.transport())
    engine = RunEngine(
        store, JenkinsReader(client), JenkinsSubmitter(client), sleep=lambda _: asyncio.sleep(0)
    )
    return engine, JenkinsAborter(client)


async def test_the_submitted_body_is_fixed_plus_run_values_only(store, flows, presets) -> None:
    preset = make_preset(presets)
    flow_id = flows.create(name="Flow")
    add_step(flows, flow_id, preset, run_values={"BRANCH": "example-feature"})
    jenkins = FakeJenkins()
    engine, aborter = real_engine(store, jenkins)

    await run_to_rest(supervisor(store, flows, presets, engine, aborter), flow_id)

    assert [parse_qs(body.decode()) for body in jenkins.bodies] == [
        {"CLUSTER": ["example-cluster"], "BRANCH": ["example-feature"]}
    ]
    assert store.get_step_inputs(flow_id, 0) == {
        "BRANCH": "example-feature",
        "CLUSTER": "example-cluster",
    }


async def test_the_board_hears_the_build_start_before_it_ends(store, flows, presets) -> None:
    preset = make_preset(presets)
    flow_id = flows.create(name="Flow")
    add_step(flows, flow_id, preset)
    jenkins = FakeJenkins(building=True)
    engine, _ = real_engine(store, jenkins)
    running = asyncio.Event()

    async def heard(changed_id: str) -> None:
        step = store.get_run(changed_id).steps[0]
        if step.state is StepState.RUNNING and step.build_number == 41:
            running.set()

    sup = FlowSupervisor(store, flows, presets, engine, on_change=heard)
    await sup.run(flow_id)
    try:
        await asyncio.wait_for(running.wait(), 1)
    finally:
        jenkins.building = False
        await sup.wait(flow_id)


async def test_stop_and_abort_sends_exactly_one_stop_request(store, flows, presets) -> None:
    preset = make_preset(presets)
    flow_id = flows.create(name="Flow")
    add_step(flows, flow_id, preset)
    jenkins = FakeJenkins()
    engine, aborter = real_engine(store, jenkins)
    sup = supervisor(store, flows, presets, engine, aborter)

    flows.set_status(flow_id, FlowStatus.RUNNING, started=True)
    flows.freeze_step_params(flow_id, 0, {"CLUSTER": "example-cluster"})
    assert store.claim_submit_pending(flow_id, 0, next_build_number=41)
    store.mark_queued(flow_id, 0, queue_url="https://jenkins.invalid/queue/item/7/", note=None)
    store.mark_running(flow_id, 0, build_number=41, build_url=BUILD_URL, queue_id=7)

    await sup.stop(flow_id, abort_current=True)

    stops = [call for call in jenkins.calls if call[0] == "POST" and call[1].endswith("/stop")]
    assert len(stops) == 1
    assert flows.get(flow_id)[1].steps[0].abort_state == "accepted"


async def test_a_refused_abort_is_still_sent_only_once(store, flows, presets) -> None:
    preset = make_preset(presets)
    flow_id = flows.create(name="Flow")
    add_step(flows, flow_id, preset)
    jenkins = FakeJenkins()
    jenkins.stop_status = 500
    engine, aborter = real_engine(store, jenkins)
    sup = supervisor(store, flows, presets, engine, aborter)

    flows.set_status(flow_id, FlowStatus.RUNNING, started=True)
    assert store.claim_submit_pending(flow_id, 0, next_build_number=41)
    store.mark_queued(flow_id, 0, queue_url="https://jenkins.invalid/queue/item/7/", note=None)
    store.mark_running(flow_id, 0, build_number=41, build_url=BUILD_URL, queue_id=7)

    await sup.stop(flow_id, abort_current=True)

    stops = [call for call in jenkins.calls if call[0] == "POST" and call[1].endswith("/stop")]
    assert len(stops) == 1
    assert flows.get(flow_id)[1].steps[0].abort_state == "failed"
    assert flows.get(flow_id)[1].status is FlowStatus.STOPPED


async def test_stop_flow_without_abort_sends_no_write_at_all(store, flows, presets) -> None:
    preset = make_preset(presets)
    flow_id = flows.create(name="Flow")
    add_step(flows, flow_id, preset)
    jenkins = FakeJenkins()
    engine, aborter = real_engine(store, jenkins)
    sup = supervisor(store, flows, presets, engine, aborter)

    flows.set_status(flow_id, FlowStatus.RUNNING, started=True)
    assert store.claim_submit_pending(flow_id, 0, next_build_number=41)
    store.mark_queued(flow_id, 0, queue_url="https://jenkins.invalid/queue/item/7/", note=None)
    store.mark_running(flow_id, 0, build_number=41, build_url=BUILD_URL, queue_id=7)

    await sup.stop(flow_id, abort_current=False)

    assert [call for call in jenkins.calls if call[0] == "POST"] == []


async def test_a_queued_step_is_cancelled_through_the_queue(store, flows, presets) -> None:
    preset = make_preset(presets)
    flow_id = flows.create(name="Flow")
    add_step(flows, flow_id, preset)
    jenkins = FakeJenkins()
    engine, aborter = real_engine(store, jenkins)
    sup = supervisor(store, flows, presets, engine, aborter)

    flows.set_status(flow_id, FlowStatus.RUNNING, started=True)
    assert store.claim_submit_pending(flow_id, 0, next_build_number=41)
    store.mark_queued(flow_id, 0, queue_url="https://jenkins.invalid/queue/item/7/", note=None)
    store.connection.execute(
        "UPDATE steps SET jenkins_queue_id = 7 WHERE run_id = ? AND position = 0", (flow_id,)
    )

    await sup.stop(flow_id, abort_current=True)

    cancels = [call for call in jenkins.calls if call[1] == "/queue/cancelItem"]
    assert len(cancels) == 1


async def test_an_ambiguous_submission_pauses_only_this_flow(store, flows, presets) -> None:
    preset = make_preset(presets)
    flow_id = flows.create(name="Flow")
    add_step(flows, flow_id, preset)
    add_step(flows, flow_id, preset)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            raise httpx.ConnectError("dropped")
        return httpx.Response(200, json={"nextBuildNumber": 41})

    client = httpx.AsyncClient(
        base_url="https://jenkins.invalid", transport=httpx.MockTransport(handler)
    )
    engine = RunEngine(store, JenkinsReader(client), JenkinsSubmitter(client))

    await run_to_rest(supervisor(store, flows, presets, engine), flow_id)

    run, meta = flows.get(flow_id)
    assert meta.status is FlowStatus.NEEDS_ATTENTION
    assert run.steps[0].state is StepState.NEEDS_ATTENTION
    assert run.steps[1].state is StepState.PREPARED


async def test_closing_an_attention_flow_sends_nothing(store, flows, presets) -> None:
    preset = make_preset(presets)
    flow_id = flows.create(name="Flow")
    add_step(flows, flow_id, preset)
    engine = FakeEngine(store)
    sup = supervisor(store, flows, presets, engine)

    await sup.close(flow_id)

    assert engine.submitted == []
    assert flows.get(flow_id)[1].status is FlowStatus.FAILED
