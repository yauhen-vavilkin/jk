import httpx
import pytest

from jk.engine.runner import RunEngine
from jk.jenkins.client import JenkinsConfig, build_client
from jk.jenkins.read import JenkinsReader
from jk.jenkins.submit import JenkinsSubmitter
from jk.store.models import StepState
from jk.store.store import RunStore
from tests.seed import seed_run, step

CONFIG = JenkinsConfig(base_url="https://jenkins.invalid", user_id="t", api_token="t")


async def no_sleep(_seconds):
    return None


def engine_for(store, mock_transport, handler):
    client = build_client(CONFIG, transport=mock_transport(handler))
    return (
        RunEngine(store, JenkinsReader(client), JenkinsSubmitter(client), sleep=no_sleep),
        client,
    )


def queued_run(store, queue_url="https://jenkins.invalid/queue/item/183759/") -> str:
    run_id = seed_run(store, step("create", {"P": "v"}, job_path="folioRancher/manageNamespace/x"))
    assert store.claim_submit_pending(run_id, 0, next_build_number=9929, now=1787849700)
    store.mark_queued(run_id, 0, queue_url=queue_url, note=None)
    return run_id


def running_run(store, number: int = 9928, queue_id: int = 1) -> str:
    run_id = queued_run(store)
    url = f"https://jenkins.invalid/x/{number}/"
    store.mark_running(run_id, 0, build_number=number, build_url=url, queue_id=queue_id)
    return run_id


async def test_queue_item_reporting_a_build_moves_to_running(store, mock_transport, fixture_json):
    def handler(request):
        if "/queue/item/" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "id": 183759,
                    "cancelled": False,
                    "executable": {"number": 9929, "url": "https://jenkins.invalid/x/9929/"},
                },
            )
        return httpx.Response(200, json=fixture_json("build_running"))

    engine, client = engine_for(store, mock_transport, handler)
    run_id = queued_run(store)
    async with client:
        state = await engine.poll_step_once(run_id, 0)

    assert state is StepState.RUNNING
    assert store.get_run(run_id).steps[0].build_number == 9929


async def test_cancelled_queue_item_becomes_aborted(store, mock_transport):
    def handler(request):
        return httpx.Response(200, json={"id": 1, "cancelled": True, "executable": None})

    engine, client = engine_for(store, mock_transport, handler)
    run_id = queued_run(store)
    async with client:
        state = await engine.poll_step_once(run_id, 0)

    assert state is StepState.ABORTED


async def test_queue_item_404_falls_back_to_scanning_builds(store, mock_transport, fixture_json):
    # This is the normal case: Jenkins forgets a queue item once the build starts.
    def handler(request):
        if "/queue/item/" in request.url.path:
            return httpx.Response(404, text="Not Found")
        return httpx.Response(200, json=fixture_json("builds_list"))

    engine, client = engine_for(store, mock_transport, handler)
    run_id = queued_run(store)
    async with client:
        state = await engine.poll_step_once(run_id, 0)

    step = store.get_run(run_id).steps[0]
    assert state is StepState.RUNNING
    assert step.build_number == 9929  # matched by queueId 183759
    assert step.jenkins_queue_id == 183759
    assert step.build_started_at_ms == 1787849729605
    assert step.build_duration_ms == 0
    assert step.estimated_duration_ms is None


async def test_scan_with_no_matching_build_eventually_needs_attention(store, mock_transport):
    def handler(request):
        if "/queue/item/" in request.url.path:
            return httpx.Response(404, text="Not Found")
        return httpx.Response(200, json={"builds": []})

    engine, client = engine_for(store, mock_transport, handler)
    run_id = queued_run(store)
    async with client:
        for _attempt in range(3):
            state = await engine.poll_step_once(run_id, 0)

    assert state is StepState.NEEDS_ATTENTION
    assert store.get_run(run_id).error_kind == "target_not_found"


async def test_running_build_that_finished_records_the_result(store, mock_transport, fixture_json):
    def handler(request):
        return httpx.Response(200, json=fixture_json("build_finished"))

    engine, client = engine_for(store, mock_transport, handler)
    run_id = running_run(store, queue_id=183738)
    async with client:
        state = await engine.poll_step_once(run_id, 0)

    assert state is StepState.SUCCESS
    step = store.get_run(run_id).steps[0]
    assert step.build_started_at_ms == 1787844779464
    assert step.build_duration_ms == 2131152
    assert step.estimated_duration_ms == 2619692


async def test_building_false_with_null_result_is_not_final(store, mock_transport):
    payload = {
        "number": 9929,
        "building": False,
        "result": None,
        "timestamp": 1,
        "duration": 0,
        "url": "https://jenkins.invalid/x/9929/",
    }

    def handler(request):
        return httpx.Response(200, json=payload)

    engine, client = engine_for(store, mock_transport, handler)
    run_id = running_run(store, 9929)
    async with client:
        state = await engine.poll_step_once(run_id, 0)

    assert state is StepState.RUNNING
    step = store.get_run(run_id).steps[0]
    assert step.build_started_at_ms == 1
    assert step.build_duration_ms == 0
    assert step.estimated_duration_ms is None


async def test_running_poll_persists_updated_estimate_across_reopen(
    store, tmp_path, mock_transport
):
    payloads = iter(
        [
            {
                "number": 9929,
                "queueId": 1,
                "building": True,
                "result": None,
                "timestamp": 1_700_000_000_000,
                "duration": 500,
                "estimatedDuration": 4_000,
                "url": "https://jenkins.invalid/x/9929/",
            },
            {
                "number": 9929,
                "queueId": 1,
                "building": True,
                "result": None,
                "timestamp": 1_700_000_000_000,
                "duration": 1_500,
                "estimatedDuration": 5_000,
                "url": "https://jenkins.invalid/x/9929/",
            },
        ]
    )

    def handler(request):
        return httpx.Response(200, json=next(payloads))

    engine, client = engine_for(store, mock_transport, handler)
    run_id = running_run(store, 9929)
    async with client:
        await engine.poll_step_once(run_id, 0)
        await engine.poll_step_once(run_id, 0)

    reopened = RunStore.open(tmp_path / "runs.db")
    try:
        step = reopened.get_run(run_id).steps[0]
        assert step.build_started_at_ms == 1_700_000_000_000
        assert step.build_duration_ms == 1_500
        assert step.estimated_duration_ms == 5_000
    finally:
        reopened.close()


async def test_monitoring_survives_a_transient_connection_error(
    store, mock_transport, fixture_json
):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("boom", request=request)
        return httpx.Response(200, json=fixture_json("build_finished"))

    engine, client = engine_for(store, mock_transport, handler)
    run_id = running_run(store, queue_id=183738)
    async with client:
        state = await engine.monitor_step(run_id, 0)

    assert state is StepState.SUCCESS


async def test_monitoring_exhausts_bounded_read_only_retries(store, mock_transport):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("boom", request=request)

    engine, client = engine_for(store, mock_transport, handler)
    run_id = running_run(store, queue_id=183738)
    async with client:
        state = await engine.monitor_step(run_id, 0)

    assert state is StepState.NEEDS_ATTENTION
    assert calls == 5
    assert store.get_run(run_id).error_kind == "connection_failure"


async def test_monitoring_turns_missing_build_endpoint_into_attention(store, mock_transport):
    def handler(request):
        return httpx.Response(404, text="Not Found")

    engine, client = engine_for(store, mock_transport, handler)
    run_id = queued_run(store)
    async with client:
        state = await engine.monitor_step(run_id, 0)

    assert state is StepState.NEEDS_ATTENTION
    assert store.get_run(run_id).error_kind == "target_not_found"


async def test_monitoring_never_posts(store, mock_transport, fixture_json, call_log):
    def handler(request):
        return httpx.Response(200, json=fixture_json("build_finished"))

    engine, client = engine_for(store, mock_transport, handler)
    run_id = running_run(store, queue_id=183738)
    async with client:
        await engine.monitor_step(run_id, 0)

    assert {method for method, _ in call_log} == {"GET"}


async def test_vanished_running_build_eventually_needs_attention(store, mock_transport):
    def handler(request):
        return httpx.Response(404, text="Not Found")

    engine, client = engine_for(store, mock_transport, handler)
    run_id = running_run(store)
    async with client:
        for _attempt in range(3):
            state = await engine.poll_step_once(run_id, 0)

    assert state is StepState.NEEDS_ATTENTION
    assert store.get_run(run_id).error_kind == "target_not_found"


async def test_single_build_404_keeps_monitoring(store, mock_transport, fixture_json):
    replies = iter(
        [
            httpx.Response(404, text="Not Found"),
            httpx.Response(200, json=fixture_json("build_finished")),
        ]
    )

    def handler(request):
        return next(replies)

    engine, client = engine_for(store, mock_transport, handler)
    run_id = running_run(store)
    async with client:
        first = await engine.poll_step_once(run_id, 0)
        second = await engine.poll_step_once(run_id, 0)

    assert first is StepState.RUNNING
    assert second is StepState.SUCCESS


async def test_unknown_final_result_needs_attention(store, mock_transport):
    def handler(request):
        return httpx.Response(
            200,
            json={
                "number": 9928,
                "queueId": 1,
                "building": False,
                "result": "NOT_BUILT",
                "timestamp": 1787849729000,
                "duration": 1000,
                "estimatedDuration": 10,
                "url": "https://jenkins.invalid/x/9928/",
            },
        )

    engine, client = engine_for(store, mock_transport, handler)
    run_id = running_run(store)
    async with client:
        state = await engine.poll_step_once(run_id, 0)

    assert state is StepState.NEEDS_ATTENTION
    run = store.get_run(run_id)
    assert run.error_kind == "unknown_result"
    assert "NOT_BUILT" in (run.error_message or "")


@pytest.mark.parametrize("raw_result", [["unexpected"], {"unexpected": "payload"}, 0, False, ""])
async def test_malformed_final_result_needs_attention_without_crashing(
    store, mock_transport, raw_result
):
    def handler(request):
        return httpx.Response(
            200,
            json={
                "number": 9928,
                "queueId": 1,
                "building": False,
                "result": raw_result,
                "timestamp": 1787849729000,
                "duration": 1000,
                "estimatedDuration": 10,
                "url": "https://jenkins.invalid/x/9928/",
            },
        )

    engine, client = engine_for(store, mock_transport, handler)
    run_id = running_run(store)
    async with client:
        state = await engine.poll_step_once(run_id, 0)

    assert state is StepState.NEEDS_ATTENTION
    run = store.get_run(run_id)
    assert run.error_kind == "unknown_result"
    assert repr(raw_result) in (run.error_message or "")
