"""The ambiguous-submission screen, over the API."""

from __future__ import annotations

import httpx
import pytest

from jk.store.records import FlowStatus
from jk.web import attention
from tests.webapp import BASE_URL, FakeJenkins, listed, start_reviewed

JOB_PATH = "folder/createNamespace"
DEFINITIONS = [
    {"name": "CLUSTER", "type": "StringParameterDefinition"},
    {"name": "NAMESPACE", "type": "StringParameterDefinition"},
]


class DroppingJenkins(FakeJenkins):
    """Accepts every read, and drops the connection while the POST is going out."""

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            self.calls.append((request.method, request.url.path))
            raise httpx.ConnectError("the connection dropped")
        tree = request.url.params.get("tree") or ""
        self.calls.append((request.method, request.url.path))
        if tree.startswith("builds["):
            return httpx.Response(200, json={"builds": [self._build(41)]})
        if tree.startswith("actions["):
            return httpx.Response(
                200,
                json={
                    "actions": [
                        {
                            "parameters": [
                                {"name": "CLUSTER", "value": "example-cluster"},
                                {"name": "NAMESPACE", "value": "example-ns"},
                            ]
                        }
                    ]
                },
            )
        self.calls.pop()
        return super().handle(request)

    @staticmethod
    def _build(number: int) -> dict:
        return {
            "number": number,
            "queueId": 7,
            "building": True,
            "result": None,
            "timestamp": 2_000_000_000_000,
            "duration": 0,
            "estimatedDuration": 1000,
            "url": f"{BASE_URL}/job/folder/job/createNamespace/{number}/",
        }


@pytest.fixture
def jenkins() -> DroppingJenkins:
    return DroppingJenkins(definitions={JOB_PATH: list(DEFINITIONS)})


async def make_preset(client) -> dict:
    return (
        await client.post(
            "/api/presets",
            json={
                "job_path": JOB_PATH,
                "name": "Example environment",
                "operation": "Create environment",
                "destructive": False,
                "params": {
                    "CLUSTER": {"mode": "fixed", "value": "example-cluster"},
                    "NAMESPACE": {"mode": "fixed", "value": "example-ns"},
                },
            },
        )
    ).json()


async def start_ambiguous(client, services) -> dict:
    preset = await make_preset(client)
    flow = (await client.post("/api/flows", json={"steps": [{"preset_id": preset["id"]}]})).json()
    await start_reviewed(client, flow["id"])
    await services.supervisor.wait(flow["id"])
    return await listed(client, "flows", flow["id"])


async def test_a_dropped_connection_moves_the_flow_to_needs_attention(client, services) -> None:
    flow = await start_ambiguous(client, services)

    assert flow["status"] == "needs_attention"
    assert flow["steps"][0]["state"] == "needs_attention"


async def test_the_reason_names_the_saved_job_and_the_step_keeps_the_error(
    client, services
) -> None:
    flow = await start_ambiguous(client, services)

    found = (
        await client.get(f"/api/flows/{flow['id']}/steps/{flow['steps'][0]['id']}/attention")
    ).json()

    assert found["reason"] == (
        "Connection dropped while sending Example environment. Jenkins may have started it."
    )
    assert found["never_again_text"] == "JK will not send it again."
    assert found["job_path"] == JOB_PATH
    assert found["next_build_number"] == 41
    note = flow["steps"][0]["note"]
    assert note.startswith("the connection failed while the request was being sent")
    assert "the connection dropped" in note


async def test_a_submission_jk_stopped_during_names_the_saved_job(client, services) -> None:
    preset = await make_preset(client)
    flow = (await client.post("/api/flows", json={"steps": [{"preset_id": preset["id"]}]})).json()
    services.flows.set_status(flow["id"], FlowStatus.RUNNING, started=True)
    assert services.store.claim_submit_pending(flow["id"], 0, next_build_number=41)
    services.store.recover_pending_submissions()

    found = (
        await client.get(f"/api/flows/{flow['id']}/steps/{flow['steps'][0]['id']}/attention")
    ).json()

    assert found["reason"] == (
        "JK stopped while sending Example environment. Jenkins may have started it."
    )


async def test_the_candidates_are_the_builds_that_match_what_jk_sent(client, services) -> None:
    flow = await start_ambiguous(client, services)

    found = (
        await client.get(f"/api/flows/{flow['id']}/steps/{flow['steps'][0]['id']}/attention")
    ).json()

    assert [item["number"] for item in found["candidates"]] == [41]
    assert found["candidates"][0]["state"] == "RUNNING"
    assert "CLUSTER example-cluster" in found["candidates"][0]["detail"]
    assert "Sent to: example-cluster / example-ns." in (found["agreement_text"] or "")


async def test_candidate_details_do_not_claim_unreported_parameters_matched(
    client, services, monkeypatch
) -> None:
    flow = await start_ambiguous(client, services)

    async def reported_parameters(rest_path, number):
        return {"CLUSTER": "example-cluster"}

    monkeypatch.setattr(services.reader, "build_parameters", reported_parameters)
    found = (
        await client.get(f"/api/flows/{flow['id']}/steps/{flow['steps'][0]['id']}/attention")
    ).json()

    assert found["candidates"][0]["detail"] == "CLUSTER example-cluster"
    assert "Sent to: example-cluster / example-ns." in found["agreement_text"]
    assert "All matches" not in found["agreement_text"]


def test_a_reported_empty_value_is_identified_in_match_evidence() -> None:
    assert attention._detail({"EMPTY": ""}) == "EMPTY empty"


def test_a_matching_build_names_where_it_runs_first() -> None:
    detail = attention._detail(
        {"FOLIO_BRANCH": "x", "NAMESPACE": "example-ns", "CLUSTER": "example-cluster"}
    )

    assert detail == "CLUSTER example-cluster NAMESPACE example-ns FOLIO_BRANCH x"


async def test_linking_a_build_resumes_the_flow_without_sending_anything(
    client, services, jenkins
) -> None:
    flow = await start_ambiguous(client, services)
    posts_before = len([call for call in jenkins.calls if call[0] == "POST"])

    linked = await client.post(
        f"/api/flows/{flow['id']}/steps/{flow['steps'][0]['id']}/link",
        json={"build_number": 41},
    )
    await services.supervisor.wait(flow["id"])

    assert linked.status_code == 200
    assert linked.json()["steps"][0]["build_number"] == 41
    assert len([call for call in jenkins.calls if call[0] == "POST"]) == posts_before


async def test_closing_the_run_fails_the_flow_and_sends_nothing(client, services, jenkins) -> None:
    flow = await start_ambiguous(client, services)
    posts_before = len([call for call in jenkins.calls if call[0] == "POST"])

    closed = await client.post(f"/api/flows/{flow['id']}/close")

    assert closed.json()["status"] == "failed"
    assert len([call for call in jenkins.calls if call[0] == "POST"]) == posts_before


async def test_an_ended_step_is_not_linked_and_keeps_the_builds_it_matched(
    client, services
) -> None:
    flow = await start_ambiguous(client, services)

    closed = (
        await client.post(f"/api/flows/{flow['id']}/close", json={"build_numbers": [41, 40]})
    ).json()

    step = closed["steps"][0]
    assert step["state"] == "closed"
    assert step["note"] == "Ended without linking a build. Matching builds: #41, #40."


async def test_an_ended_step_says_when_no_build_matched(client, services) -> None:
    flow = await start_ambiguous(client, services)

    closed = (await client.post(f"/api/flows/{flow['id']}/close", json={})).json()

    assert closed["steps"][0]["note"] == "Ended without linking a build. No build matched."


async def test_a_stopped_flow_with_an_undecided_step_stays_until_it_is_ended(
    client, services
) -> None:
    flow = await start_ambiguous(client, services)
    await client.post(f"/api/flows/{flow['id']}/stop", json={"abort_current": False})

    stopped = await listed(client, "flows", flow["id"])
    refused = await client.patch(f"/api/flows/{flow['id']}", json={"cleared": True})
    ended = await client.post(f"/api/flows/{flow['id']}/close", json={"build_numbers": []})

    assert stopped["status"] == "stopped"
    assert refused.status_code == 409
    assert refused.json()["error"]["message"] == "Resolve step 1 first."
    assert ended.status_code == 200
    assert ended.json()["status"] == "failed"
    assert ended.json()["steps"][0]["state"] == "closed"
    cleared = await client.patch(f"/api/flows/{flow['id']}", json={"cleared": True})
    assert cleared.status_code == 200


async def test_linking_a_build_that_does_not_match_is_refused(client, services) -> None:
    flow = await start_ambiguous(client, services)

    response = await client.post(
        f"/api/flows/{flow['id']}/steps/{flow['steps'][0]['id']}/link",
        json={"build_number": 9999},
    )

    assert response.status_code == 409


async def test_a_step_that_is_not_waiting_has_no_attention_screen(client, services) -> None:
    flow = await start_ambiguous(client, services)
    await client.post(f"/api/flows/{flow['id']}/close")

    response = await client.get(f"/api/flows/{flow['id']}/steps/{flow['steps'][0]['id']}/attention")

    assert response.status_code == 409
