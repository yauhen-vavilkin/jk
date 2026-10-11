"""Every path an independent review found that sent a build nobody asked for.

Each test is the review's reproduction turned around: the scenario is the same,
and the assertion is that Jenkins receives nothing it should not. All of it runs
offline against `FakeJenkins`.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from pathlib import Path

import httpx
import pytest

from jk.store.records import Drift, DriftEntry, SavedFlowStep
from jk.store.store import RunStore
from jk.web.deps import build_services
from tests.webapp import (
    BASE_URL,
    FakeJenkins,
    build,
    client_for,
    confirm_reviewed,
    listed,
    no_wait,
    resume_reviewed,
    start_reviewed,
)

CREATE = "folder/createNamespace"
DELETE = "folder/deleteNamespace"
DEFINITIONS = {
    CREATE: [
        {"name": "CLUSTER", "type": "StringParameterDefinition"},
        {"name": "NAMESPACE", "type": "StringParameterDefinition"},
        {"name": "FOLIO_BRANCH", "type": "StringParameterDefinition"},
    ],
    DELETE: [
        {"name": "CLUSTER", "type": "StringParameterDefinition"},
        {"name": "NAMESPACE", "type": "StringParameterDefinition"},
    ],
}


def fixed(value: str) -> dict:
    return {"mode": "fixed", "value": value}


def _cascade(name: str) -> dict:
    """An Active Choices parameter as Jenkins reports it with nothing to compute from."""
    return {
        "name": name,
        "type": "CascadeChoiceParameter",
        "defaultParameterValue": {"value": "error"},
    }


def _string(name: str) -> dict:
    return {"name": name, "type": "StringParameterDefinition"}


async def saved_job(client, job_path: str, params: dict, *, name="job", destructive=False) -> str:
    created = await client.post(
        "/api/presets",
        json={
            "job_path": job_path,
            "name": name,
            "operation": "Test",
            "destructive": destructive,
            "params": params,
        },
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def flow_of(client, *steps: dict) -> str:
    created = await client.post("/api/flows", json={"steps": list(steps)})
    assert created.status_code == 201, created.text
    return created.json()["id"]


def posts(jenkins: FakeJenkins) -> list[str]:
    return [path for method, path in jenkins.calls if method == "POST"]


async def settle(services, flow_id: str) -> None:
    for _ in range(20):
        await asyncio.sleep(0)
    await services.supervisor.wait(flow_id)


async def until(check, *, tries: int = 200) -> None:
    for _ in range(tries):
        if await check():
            return
        await asyncio.sleep(0.005)
    raise AssertionError("the condition never became true")


class HeldRead:
    """Holds the pre-claim `nextBuildNumber` read, or the submission itself, open."""

    def __init__(self, jenkins: FakeJenkins, *, submission: bool = False) -> None:
        self.jenkins = jenkins
        self.submission = submission
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    def _held(self, request: httpx.Request) -> bool:
        if self.submission:
            return request.url.path.endswith("/buildWithParameters")
        return request.url.params.get("tree") == "nextBuildNumber"

    async def handle(self, request: httpx.Request) -> httpx.Response:
        if self._held(request) and not self.release.is_set():
            self.entered.set()
            await self.release.wait()
        return self.jenkins.handle(request)


def services_with(tmp_path: Path, handler, *, sleep=no_wait):
    store = RunStore.open(tmp_path / "runs.db")
    client = httpx.AsyncClient(base_url=BASE_URL, transport=httpx.MockTransport(handler))
    return build_services(store=store, client=client, base_url=BASE_URL, sleep=sleep)


async def tick(_: float) -> None:
    await asyncio.sleep(0.002)


@pytest.fixture
def jenkins() -> FakeJenkins:
    return FakeJenkins(definitions=deepcopy(DEFINITIONS))


async def test_a_stop_during_the_pre_claim_read_sends_nothing(tmp_path: Path, jenkins) -> None:
    held = HeldRead(jenkins)
    services = services_with(tmp_path, held.handle)
    async with client_for(services) as client:
        job = await saved_job(client, CREATE, {"CLUSTER": fixed("a")})
        flow_id = await flow_of(client, {"preset_id": job})
        await start_reviewed(client, flow_id)
        await asyncio.wait_for(held.entered.wait(), 2)

        stopped = await client.post(f"/api/flows/{flow_id}/stop", json={"abort_current": True})
        held.release.set()
        await settle(services, flow_id)
        flow = await listed(client, "flows", flow_id)
    services.store.close()

    assert stopped.status_code == 200
    assert posts(jenkins) == []
    assert flow["status"] == "stopped"
    assert flow["steps"][0]["state"] == "planned"


@pytest.mark.parametrize("failure", ["connection", 403, 404])
async def test_a_failed_preflight_stops_until_a_reviewed_resume(tmp_path, jenkins, failure):
    failing = True

    def handler(request: httpx.Request) -> httpx.Response:
        if failing and request.url.params.get("tree") == "nextBuildNumber":
            jenkins.calls.append((request.method, request.url.path))
            if failure == "connection":
                raise httpx.ConnectError("offline", request=request)
            return httpx.Response(failure, text="no")
        return jenkins.handle(request)

    services = services_with(tmp_path, handler)
    try:
        async with client_for(services) as client:
            job = await saved_job(client, CREATE, {"CLUSTER": fixed("a")})
            flow_id = await flow_of(client, {"preset_id": job})
            await start_reviewed(client, flow_id)
            await settle(services, flow_id)
            flow = await listed(client, "flows", flow_id)

            assert flow["status"] == "stopped"
            assert flow["steps"][0]["state"] == "planned"
            assert flow["steps"][0]["held"] is False
            assert flow["steps"][0]["sent_at"] is None
            assert "Nothing was sent" in flow["steps"][0]["note"]
            assert "review and resume" in flow["steps"][0]["note"]
            assert posts(jenkins) == []

            # Startup must not treat the unsent step as permission to retry.
            failing = False
            await services.supervisor.shutdown()
            await services.supervisor.start()
            await services.supervisor.wait(flow_id)
            assert posts(jenkins) == []
            refused = await client.post(
                f"/api/flows/{flow_id}/resume", json={"review_token": "stale"}
            )
            assert refused.status_code == 409
            assert posts(jenkins) == []

            resumed = await resume_reviewed(client, flow_id)
            assert resumed.status_code == 200, resumed.text
            await settle(services, flow_id)
            flow = await listed(client, "flows", flow_id)
            assert len(posts(jenkins)) == 1
            assert flow["steps"][0]["state"] == "SUCCESS"
            assert flow["steps"][0]["note"] is None
    finally:
        await services.supervisor.shutdown()
        services.store.close()


async def test_a_stop_wins_when_the_pre_claim_read_later_fails(tmp_path, jenkins):
    entered = asyncio.Event()
    release = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("tree") == "nextBuildNumber":
            entered.set()
            await release.wait()
            raise httpx.ConnectError("offline", request=request)
        return jenkins.handle(request)

    services = services_with(tmp_path, handler)
    try:
        async with client_for(services) as client:
            job = await saved_job(client, CREATE, {"CLUSTER": fixed("a")})
            flow_id = await flow_of(client, {"preset_id": job})
            await start_reviewed(client, flow_id)
            await asyncio.wait_for(entered.wait(), 2)
            stopped = await client.post(f"/api/flows/{flow_id}/stop", json={"abort_current": True})
            release.set()
            await settle(services, flow_id)
            flow = await listed(client, "flows", flow_id)
            assert stopped.status_code == 200
            assert flow["status"] == "stopped"
            assert flow["steps"][0]["state"] == "planned"
            assert flow["steps"][0]["note"] is None
            assert posts(jenkins) == []
    finally:
        release.set()
        await services.supervisor.shutdown()
        services.store.close()


async def test_a_step_cannot_be_removed_or_moved_while_a_step_is_being_sent(
    tmp_path: Path, jenkins
) -> None:
    held = HeldRead(jenkins)
    services = services_with(tmp_path, held.handle)
    async with client_for(services) as client:
        first = await saved_job(client, CREATE, {"CLUSTER": fixed("A")}, name="A")
        second = await saved_job(client, DELETE, {"CLUSTER": fixed("B")}, name="B")
        flow_id = await flow_of(client, {"preset_id": first}, {"preset_id": second})
        await start_reviewed(client, flow_id)
        await asyncio.wait_for(held.entered.wait(), 2)

        removed = await client.delete(f"/api/flows/{flow_id}/steps/{flow_id}:0")
        moved = await client.patch(f"/api/flows/{flow_id}/steps/{flow_id}:1", json={"position": 0})
        held.release.set()
        await until(lambda: _has_posts(jenkins))
        await services.supervisor.shutdown()
    services.store.close()

    assert removed.status_code == 409
    assert moved.status_code == 409
    assert posts(jenkins)[0].endswith("/createNamespace/buildWithParameters")
    assert jenkins.bodies[0] == b"CLUSTER=A"


async def _has_posts(jenkins: FakeJenkins) -> bool:
    return bool(posts(jenkins))


async def test_a_start_without_the_review_token_is_refused(client, services, jenkins) -> None:
    job = await saved_job(client, CREATE, {"CLUSTER": fixed("a")})
    flow_id = await flow_of(client, {"preset_id": job})

    await client.patch(f"/api/flows/{flow_id}", json={"editing": False})

    without = await client.post(f"/api/flows/{flow_id}/start", json={})
    wrong = await client.post(f"/api/flows/{flow_id}/start", json={"review_token": "guess"})
    await settle(services, flow_id)

    assert without.status_code == 422
    # Named, so this cannot quietly start refusing for some other reason.
    assert wrong.json()["error"]["code"] == "review_required"
    assert posts(jenkins) == []


async def test_a_flow_that_is_still_being_edited_sends_nothing(client, services, jenkins) -> None:
    job = await saved_job(client, CREATE, {"CLUSTER": fixed("a")})
    flow_id = await flow_of(client, {"preset_id": job})
    token = (await client.post(f"/api/flows/{flow_id}/review", json={})).json()["review_token"]

    started = await client.post(f"/api/flows/{flow_id}/start", json={"review_token": token})
    await settle(services, flow_id)

    assert started.json()["error"]["code"] == "flow_editing"
    assert posts(jenkins) == []


async def test_a_drifted_saved_job_is_not_started(client, services, jenkins) -> None:
    job = await saved_job(client, CREATE, {"CLUSTER": fixed("a")})
    flow_id = await flow_of(client, {"preset_id": job})
    services.presets.set_drift(job, Drift(removed=(DriftEntry("CLUSTER", "a"),), seen_at=1))

    started = await start_reviewed(client, flow_id)
    await settle(services, flow_id)

    assert started.json()["error"]["code"] == "review_required"
    assert posts(jenkins) == []


async def test_an_active_choices_placeholder_is_not_started(client, jenkins) -> None:
    """Jenkins answers `error` when a cascade script has nothing to compute from."""
    jenkins.definitions[CREATE] = [_cascade("CLUSTER"), _string("NAMESPACE")]

    refused = await client.post(
        "/api/presets",
        json={
            "job_path": CREATE,
            "name": "job",
            "operation": "Test",
            "destructive": False,
            "params": {"CLUSTER": fixed(" error ")},
        },
    )

    assert refused.status_code == 400
    assert refused.json()["error"]["code"] == "placeholder_value"
    assert posts(jenkins) == []


async def test_a_cascade_parameter_left_to_jenkins_is_not_started(
    client, services, jenkins
) -> None:
    """Not sending it is the same placeholder: Jenkins fills it in with `error`."""
    jenkins.definitions[CREATE] = [_cascade("CLUSTER"), _string("NAMESPACE")]
    job = await saved_job(client, CREATE, {"NAMESPACE": fixed("example-ns")})
    flow_id = await flow_of(client, {"preset_id": job})

    started = await start_reviewed(client, flow_id)
    await settle(services, flow_id)

    assert started.json()["error"]["code"] == "review_required"
    assert posts(jenkins) == []


async def test_an_unanswered_value_asked_at_launch_is_not_started(
    client, services, jenkins
) -> None:
    job = await saved_job(
        client, CREATE, {"CLUSTER": fixed("a"), "FOLIO_BRANCH": {"mode": "ask", "value": None}}
    )
    flow_id = await flow_of(client, {"preset_id": job})

    started = await start_reviewed(client, flow_id)
    await settle(services, flow_id)

    assert started.json()["error"]["code"] == "review_required"
    assert posts(jenkins) == []


async def test_a_value_never_typed_is_offered_in_the_review_as_missing(client, jenkins) -> None:
    """Run stays off until it is filled, and the review says which one, with a
    field for it: never a placeholder complaint about a value nobody typed."""
    jenkins.definitions[CREATE] = [_string("CLUSTER"), _cascade("NAMESPACE")]
    job = await saved_job(
        client, CREATE, {"CLUSTER": fixed("a"), "NAMESPACE": {"mode": "ask", "value": None}}
    )
    flow_id = await flow_of(client, {"preset_id": job})

    review = (await client.post(f"/api/flows/{flow_id}/review", json={})).json()

    assert review["issues"] == []
    assert [item["names"] for item in review["missing_run_values"]] == [["NAMESPACE"]]
    assert {"name": "NAMESPACE", "value": "", "per_run": True} in review["steps"][0]["sent"]


async def test_an_edit_after_the_review_needs_a_new_review(client, services, jenkins) -> None:
    job = await saved_job(
        client,
        DELETE,
        {"CLUSTER": fixed("example-cluster"), "NAMESPACE": fixed("reviewed-ns")},
        destructive=True,
    )
    flow_id = await flow_of(client, {"preset_id": job})
    token = (await client.post(f"/api/flows/{flow_id}/review", json={})).json()["review_token"]

    await client.put(
        f"/api/presets/{job}",
        json={
            "destructive": False,
            "params": {"CLUSTER": fixed("example-cluster"), "NAMESPACE": fixed("OTHER-ns")},
        },
    )
    await client.patch(f"/api/flows/{flow_id}", json={"editing": False})
    started = await client.post(f"/api/flows/{flow_id}/start", json={"review_token": token})
    await settle(services, flow_id)

    assert started.json()["error"]["code"] == "review_required"
    assert posts(jenkins) == []


async def test_a_started_flow_sends_the_reviewed_body_even_if_the_job_is_edited(
    tmp_path: Path, jenkins
) -> None:
    jenkins.building = True
    services = services_with(tmp_path, jenkins.handle, sleep=tick)
    async with client_for(services) as client:
        job = await saved_job(client, DELETE, {"CLUSTER": fixed("c"), "NAMESPACE": fixed("seen")})
        flow_id = await flow_of(client, {"preset_id": job}, {"preset_id": job})
        await start_reviewed(client, flow_id)
        await until(lambda: _state(client, flow_id, 0, "running"))

        await client.put(
            f"/api/presets/{job}",
            json={"params": {"CLUSTER": fixed("c"), "NAMESPACE": fixed("edited")}},
        )
        jenkins.building = False
        await until(lambda: _count(jenkins, 2))
        await services.supervisor.shutdown()
    services.store.close()

    assert jenkins.bodies == [b"CLUSTER=c&NAMESPACE=seen", b"CLUSTER=c&NAMESPACE=seen"]


async def _state(client, flow_id: str, index: int, state: str) -> bool:
    return (await listed(client, "flows", flow_id))["steps"][index]["state"] == state


async def _count(jenkins: FakeJenkins, count: int) -> bool:
    return len(posts(jenkins)) >= count


async def test_a_step_added_while_running_waits_for_its_own_review(tmp_path: Path, jenkins) -> None:
    jenkins.building = True
    services = services_with(tmp_path, jenkins.handle, sleep=tick)
    async with client_for(services) as client:
        first = await saved_job(client, CREATE, {"CLUSTER": fixed("a")}, name="A")
        dangerous = await saved_job(
            client,
            DELETE,
            {"CLUSTER": fixed("example-cluster"), "NAMESPACE": {"mode": "ask", "value": None}},
            name="Delete",
            destructive=True,
        )
        flow_id = await flow_of(client, {"preset_id": first})
        await start_reviewed(client, flow_id)
        await until(lambda: _state(client, flow_id, 0, "running"))

        added = await client.post(f"/api/flows/{flow_id}/steps", json={"preset_id": dangerous})
        jenkins.building = False
        await until(lambda: _state(client, flow_id, 0, "SUCCESS"))
        await services.supervisor.wait(flow_id)
        waiting = await listed(client, "flows", flow_id)
        sent_before_review = list(posts(jenkins))

        step_id = waiting["steps"][1]["id"]
        confirmed = await confirm_reviewed(client, flow_id, {step_id: {"NAMESPACE": "example-ns"}})
        await until(lambda: _count(jenkins, 2))
        await services.supervisor.shutdown()
    services.store.close()

    assert added.json()["steps"][1]["held"] is True
    assert waiting["status"] == "running"
    assert waiting["steps"][1]["state"] == "planned"
    assert len(sent_before_review) == 1
    assert confirmed.status_code == 200
    assert jenkins.bodies[1] == b"CLUSTER=example-cluster&NAMESPACE=example-ns"


async def test_a_saved_flow_with_a_drifted_job_adds_nothing(client, services) -> None:
    first = await saved_job(client, CREATE, {"CLUSTER": fixed("a")}, name="A")
    second = await saved_job(client, DELETE, {"CLUSTER": fixed("b")}, name="B")
    template = services.saved_flows.save(
        name="t", steps=(SavedFlowStep(preset_id=first), SavedFlowStep(preset_id=second))
    )
    services.presets.set_drift(second, Drift(added=(DriftEntry("Z"),), seen_at=1))
    target = await flow_of(client)

    into = await client.post(
        f"/api/saved-flows/{template.id}/instantiate", json={"flow_id": target}
    )
    fresh = await client.post(f"/api/saved-flows/{template.id}/instantiate", json={})

    assert into.status_code == 409
    assert fresh.status_code == 409
    assert (await listed(client, "flows", target))["steps"] == []
    assert len(services.flows.list()) == 1


async def test_linking_a_build_on_a_stopped_flow_keeps_it_stopped(tmp_path: Path) -> None:
    from tests.test_web_attention import DEFINITIONS as ATTENTION_DEFINITIONS
    from tests.test_web_attention import JOB_PATH, DroppingJenkins

    jenkins = DroppingJenkins(definitions={JOB_PATH: list(ATTENTION_DEFINITIONS)})
    services = build(tmp_path, jenkins)
    async with client_for(services) as client:
        job = await saved_job(
            client,
            JOB_PATH,
            {"CLUSTER": fixed("example-cluster"), "NAMESPACE": fixed("example-ns")},
        )
        flow_id = await flow_of(client, {"preset_id": job}, {"preset_id": job})
        await start_reviewed(client, flow_id)
        await services.supervisor.wait(flow_id)
        sent = len(posts(jenkins))

        await client.post(f"/api/flows/{flow_id}/stop", json={"abort_current": False})
        linked = await client.post(
            f"/api/flows/{flow_id}/steps/{flow_id}:0/link", json={"build_number": 41}
        )
        await services.supervisor.wait(flow_id)
        flow = await listed(client, "flows", flow_id)
    services.store.close()

    assert linked.status_code == 200
    assert flow["status"] == "stopped"
    assert len(posts(jenkins)) == sent


async def test_a_stopped_flow_whose_monitoring_fails_stays_stopped_after_a_link(
    tmp_path: Path, jenkins
) -> None:
    jenkins.building = True
    services = services_with(tmp_path, jenkins.handle, sleep=tick)
    async with client_for(services) as client:
        job = await saved_job(client, CREATE, {"CLUSTER": fixed("a")})
        flow_id = await flow_of(client, {"preset_id": job}, {"preset_id": job})
        await start_reviewed(client, flow_id)
        await until(lambda: _state(client, flow_id, 0, "running"))

        await client.post(f"/api/flows/{flow_id}/stop", json={"abort_current": False})
        jenkins.unreachable = True
        await until(lambda: _state(client, flow_id, 0, "needs_attention"))
        await services.supervisor.wait(flow_id)
        jenkins.unreachable, jenkins.building, jenkins.recent = False, False, {41: {"CLUSTER": "a"}}
        linked = await client.post(
            f"/api/flows/{flow_id}/steps/{flow_id}:0/link", json={"build_number": 41}
        )
        await services.supervisor.wait(flow_id)
        flow = await listed(client, "flows", flow_id)
    services.store.close()

    assert linked.status_code == 200
    assert flow["status"] == "stopped"
    assert len([path for path in posts(jenkins) if path.endswith("/buildWithParameters")]) == 1


async def test_a_build_is_asked_to_stop_once_even_after_a_resume(tmp_path: Path, jenkins) -> None:
    jenkins.building = True
    services = services_with(tmp_path, jenkins.handle, sleep=tick)
    async with client_for(services) as client:
        job = await saved_job(client, CREATE, {"CLUSTER": fixed("a")})
        flow_id = await flow_of(client, {"preset_id": job}, {"preset_id": job})
        await start_reviewed(client, flow_id)
        await until(lambda: _state(client, flow_id, 0, "running"))

        first = await client.post(f"/api/flows/{flow_id}/stop", json={"abort_current": True})
        resumed = await resume_reviewed(client, flow_id)
        second = await client.post(f"/api/flows/{flow_id}/stop", json={"abort_current": True})
        await services.supervisor.shutdown()
    services.store.close()

    assert (first.status_code, resumed.status_code, second.status_code) == (200, 200, 200)
    assert [path for path in posts(jenkins) if path.endswith("/stop")] == [
        "/job/folder/job/job/41/stop"
    ]


async def test_a_skipped_step_before_a_running_one_cannot_be_removed(
    tmp_path: Path, jenkins
) -> None:
    jenkins.building = True
    services = services_with(tmp_path, jenkins.handle, sleep=tick)
    async with client_for(services) as client:
        job = await saved_job(client, CREATE, {"CLUSTER": fixed("a")})
        flow_id = await flow_of(
            client,
            {"preset_id": job, "condition": "after_failure"},
            {"preset_id": job},
        )
        await start_reviewed(client, flow_id)
        await until(lambda: _state(client, flow_id, 1, "running"))

        removed = await client.delete(f"/api/flows/{flow_id}/steps/{flow_id}:0")
        jenkins.building = False
        await until(lambda: _state(client, flow_id, 1, "SUCCESS"))
        await services.supervisor.shutdown()
    services.store.close()

    assert removed.status_code == 409


async def test_after_a_restart_linking_a_build_does_not_send_an_unreviewed_destructive_step(
    tmp_path: Path,
) -> None:
    from tests.test_web_attention import DEFINITIONS as ATTENTION_DEFINITIONS
    from tests.test_web_attention import JOB_PATH, DroppingJenkins

    jenkins = DroppingJenkins(definitions={JOB_PATH: list(ATTENTION_DEFINITIONS)})
    params = {"CLUSTER": fixed("example-cluster"), "NAMESPACE": fixed("example-ns")}
    first = build(tmp_path, jenkins)
    async with client_for(first) as client:
        plain = await saved_job(client, JOB_PATH, params, name="A")
        dangerous = await saved_job(client, JOB_PATH, params, name="D", destructive=True)
        flow_id = await flow_of(client, {"preset_id": plain}, {"preset_id": dangerous})
        await start_reviewed(client, flow_id)
        await first.supervisor.wait(flow_id)
    first.store.close()
    sent_before_restart = len(posts(jenkins))

    second = build(tmp_path, jenkins)
    second.store.recover_pending_submissions()
    await second.supervisor.start()
    async with client_for(second) as client:
        await client.post(f"/api/flows/{flow_id}/steps/{flow_id}:0/link", json={"build_number": 41})
        await second.supervisor.wait(flow_id)
        flow = await listed(client, "flows", flow_id)
    await second.supervisor.shutdown()
    second.store.close()

    assert flow["steps"][1]["held"] is True
    assert len(posts(jenkins)) == sent_before_restart


async def test_a_condition_changed_after_the_review_needs_a_new_review(
    client, services, jenkins
) -> None:
    first = await saved_job(client, CREATE, {"CLUSTER": fixed("a")}, name="A")
    dangerous = await saved_job(
        client, DELETE, {"CLUSTER": fixed("e"), "NAMESPACE": fixed("n")}, destructive=True
    )
    flow_id = await flow_of(
        client, {"preset_id": first}, {"preset_id": dangerous, "condition": "after_failure"}
    )
    token = (await client.post(f"/api/flows/{flow_id}/review", json={})).json()["review_token"]

    await client.patch(f"/api/flows/{flow_id}/steps/{flow_id}:1", json={"condition": "always"})
    await client.patch(f"/api/flows/{flow_id}", json={"editing": False})
    started = await client.post(f"/api/flows/{flow_id}/start", json={"review_token": token})
    await settle(services, flow_id)

    assert started.json()["error"]["code"] == "review_required"
    assert posts(jenkins) == []


async def test_a_stopped_flow_with_nothing_left_leaves_the_board(tmp_path: Path, jenkins) -> None:
    jenkins.building = True
    services = services_with(tmp_path, jenkins.handle, sleep=tick)
    async with client_for(services) as client:
        job = await saved_job(client, CREATE, {"CLUSTER": fixed("a")})
        flow_id = await flow_of(client, {"preset_id": job})
        await start_reviewed(client, flow_id)
        await until(lambda: _state(client, flow_id, 0, "running"))

        await client.post(f"/api/flows/{flow_id}/stop", json={"abort_current": False})
        jenkins.building = False
        await until(lambda: _state(client, flow_id, 0, "SUCCESS"))
        await services.supervisor.wait(flow_id)
        flow = await listed(client, "flows", flow_id)
        cleared = await client.patch(f"/api/flows/{flow_id}", json={"cleared": True})
        await services.supervisor.shutdown()
    services.store.close()

    assert flow["status"] == "finished"
    assert cleared.status_code == 200


async def test_stop_and_abort_during_the_submission_stops_the_build_once_it_exists(
    tmp_path: Path, jenkins
) -> None:
    jenkins.building = True
    held = HeldRead(jenkins, submission=True)
    services = services_with(tmp_path, held.handle, sleep=tick)
    async with client_for(services) as client:
        job = await saved_job(client, CREATE, {"CLUSTER": fixed("a")})
        flow_id = await flow_of(client, {"preset_id": job})
        await start_reviewed(client, flow_id)
        await asyncio.wait_for(held.entered.wait(), 2)

        stopped = await client.post(f"/api/flows/{flow_id}/stop", json={"abort_current": True})
        held.release.set()
        await until(lambda: _stop_posts(jenkins, 1))
        await asyncio.sleep(0.05)
        await services.supervisor.shutdown()
    services.store.close()

    assert stopped.status_code == 200
    assert len([path for path in posts(jenkins) if path.endswith(("/stop", "/cancelItem"))]) == 1


async def _stop_posts(jenkins: FakeJenkins, count: int) -> bool:
    return (
        len([path for path in posts(jenkins) if path.endswith(("/stop", "/cancelItem"))]) >= count
    )


async def test_a_resume_carries_the_values_asked_for_held_steps(tmp_path: Path, jenkins) -> None:
    jenkins.building = True
    services = services_with(tmp_path, jenkins.handle, sleep=tick)
    async with client_for(services) as client:
        first = await saved_job(client, CREATE, {"CLUSTER": fixed("a")}, name="A")
        asked = await saved_job(
            client, CREATE, {"FOLIO_BRANCH": {"mode": "ask", "value": None}}, name="Ask"
        )
        flow_id = await flow_of(client, {"preset_id": first})
        await start_reviewed(client, flow_id)
        await until(lambda: _state(client, flow_id, 0, "running"))
        await client.post(f"/api/flows/{flow_id}/steps", json={"preset_id": asked})
        await client.post(f"/api/flows/{flow_id}/stop", json={"abort_current": False})
        jenkins.building = False
        await until(lambda: _state(client, flow_id, 0, "SUCCESS"))
        await services.supervisor.wait(flow_id)

        review = (
            await client.post(f"/api/flows/{flow_id}/review", json={"scope": "resume"})
        ).json()
        resumed = await client.post(
            f"/api/flows/{flow_id}/resume",
            json={
                "review_token": review["review_token"],
                "run_values": {f"{flow_id}:1": {"FOLIO_BRANCH": "picked"}},
            },
        )
        await until(lambda: _count(jenkins, 2))
        await services.supervisor.shutdown()
    services.store.close()

    assert resumed.status_code == 200
    assert jenkins.bodies[1] == b"FOLIO_BRANCH=picked"


async def test_editing_turned_back_on_during_the_review_sends_nothing(
    tmp_path: Path, jenkins
) -> None:
    """The review awaits Jenkins; the flow may be reopened for changing while it does."""
    entered, release, armed = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def hold_the_review(request: httpx.Request) -> httpx.Response:
        # The start's own review reads the parameter definitions; hold that read,
        # and only that one: saving the job reads them too, before any of this.
        held = "parameterDefinitions" in (request.url.params.get("tree") or "")
        if held and armed.is_set() and not release.is_set():
            entered.set()
            await release.wait()
        return jenkins.handle(request)

    services = services_with(tmp_path, hold_the_review)
    async with client_for(services) as client:
        job = await saved_job(client, CREATE, {"CLUSTER": fixed("a")})
        flow_id = await flow_of(client, {"preset_id": job})
        await client.patch(f"/api/flows/{flow_id}", json={"editing": False})
        token = (await client.post(f"/api/flows/{flow_id}/review", json={})).json()["review_token"]

        # Editing goes back on while the server is still waiting on Jenkins.
        armed.set()
        starting = asyncio.ensure_future(
            client.post(f"/api/flows/{flow_id}/start", json={"review_token": token})
        )
        await asyncio.wait_for(entered.wait(), 2)
        reopened = await client.patch(f"/api/flows/{flow_id}", json={"editing": True})
        release.set()
        started = await asyncio.wait_for(starting, 5)
        await settle(services, flow_id)
        flow = await listed(client, "flows", flow_id)
    services.store.close()

    assert reopened.status_code == 200
    assert started.json()["error"]["code"] == "flow_editing"
    assert posts(jenkins) == []
    assert flow["status"] == "draft"
