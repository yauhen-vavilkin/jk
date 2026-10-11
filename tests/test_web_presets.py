"""The saved-jobs API."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.webapp import FakeJenkins, build, client_for, listed

JOB_PATH = "folioRancher/manageNamespace/createNamespaceFromBranch"

DEFINITIONS = [
    {"name": "CLUSTER", "type": "StringParameterDefinition"},
    {"name": "NAMESPACE", "type": "StringParameterDefinition"},
    {
        "name": "FOLIO_BRANCH",
        "type": "StringParameterDefinition",
        "defaultParameterValue": {"value": "snapshot"},
    },
    {"name": "ADMIN_PASSWORD", "type": "PasswordParameterDefinition"},
]

BODY = {
    "job_path": JOB_PATH,
    "name": "snapshot edev rancher",
    "operation": "Create environment",
    "destructive": True,
    "params": {
        "CLUSTER": {"mode": "fixed", "value": "example-cluster"},
        "NAMESPACE": {"mode": "fixed", "value": "example-ns"},
        "FOLIO_BRANCH": {"mode": "ask", "value": None, "last_value": "example-feature"},
    },
}


@pytest.fixture
def jenkins() -> FakeJenkins:
    return FakeJenkins(definitions={JOB_PATH: DEFINITIONS})


async def test_creating_a_preset_fills_every_other_parameter_as_default(client) -> None:
    response = await client.post("/api/presets", json=BODY)

    assert response.status_code == 201
    preset = response.json()
    assert preset["params"]["ADMIN_PASSWORD"]["mode"] == "default"
    assert preset["job_url"].endswith(
        "/job/folioRancher/job/manageNamespace/job/createNamespaceFromBranch/"
    )


async def test_a_name_jenkins_does_not_define_is_refused(client) -> None:
    body = {**BODY, "params": {**BODY["params"], "KB_KEY2": {"mode": "fixed", "value": "x"}}}

    response = await client.post("/api/presets", json=body)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "param_not_defined"
    assert response.json()["error"]["message"] == (
        "Jenkins does not define a parameter named KB_KEY2."
    )


async def test_an_empty_fixed_password_is_refused(client) -> None:
    body = {
        **BODY,
        "params": {**BODY["params"], "ADMIN_PASSWORD": {"mode": "fixed", "value": ""}},
    }

    response = await client.post("/api/presets", json=body)

    assert response.status_code == 400
    assert response.json()["error"]["message"] == "A password parameter has no value."


async def test_listing_reading_and_updating(client) -> None:
    created = (await client.post("/api/presets", json=BODY)).json()

    assert len((await client.get("/api/presets")).json()) == 1
    assert (await listed(client, "presets", created["id"]))["name"] == created["name"]

    updated = await client.put(
        f"/api/presets/{created['id']}", json={"name": "renamed", "destructive": False}
    )
    assert updated.json()["name"] == "renamed"
    assert updated.json()["destructive"] is False


async def test_duplicating_copies_the_values_under_a_new_id(client) -> None:
    created = (await client.post("/api/presets", json=BODY)).json()

    copy = (await client.post(f"/api/presets/{created['id']}/duplicate")).json()

    assert copy["id"] != created["id"]
    assert copy["name"] == f"{created['name']} copy"

    again = (await client.post(f"/api/presets/{created['id']}/duplicate")).json()

    # The second copy counts instead of making a second identical name.
    assert again["name"] == f"{created['name']} copy 2"
    assert copy["params"] == created["params"]


async def test_a_preset_a_flow_still_uses_cannot_be_deleted(client) -> None:
    created = (await client.post("/api/presets", json=BODY)).json()
    flow = (await client.post("/api/flows", json={"steps": [{"preset_id": created["id"]}]})).json()

    response = await client.delete(f"/api/presets/{created['id']}")

    assert response.status_code == 409
    assert response.json()["error"]["message"] == (
        f"Used by {flow['name']}, step 1. Remove that step first."
    )
    assert (await client.get(f"/api/presets/{created['id']}/usage")).json() == {
        "steps": [{"flow_id": flow["id"], "flow_name": flow["name"], "position": 0}],
    }


async def test_the_usage_names_every_flow_and_step_that_uses_a_preset(client) -> None:
    created = (await client.post("/api/presets", json=BODY)).json()
    other = (await client.post("/api/presets", json={**BODY, "name": "other"})).json()
    first = (
        await client.post(
            "/api/flows",
            json={
                "name": "First",
                "steps": [{"preset_id": other["id"]}, {"preset_id": created["id"]}],
            },
        )
    ).json()
    second = (
        await client.post(
            "/api/flows", json={"name": "Second", "steps": [{"preset_id": created["id"]}]}
        )
    ).json()

    usage = (await client.get(f"/api/presets/{created['id']}/usage")).json()
    refused = await client.delete(f"/api/presets/{created['id']}")

    assert [(item["flow_id"], item["position"]) for item in usage["steps"]] == [
        (first["id"], 1),
        (second["id"], 0),
    ]
    assert refused.json()["error"]["message"] == (
        "Used by First, step 2 · Second, step 1. Remove those steps first."
    )


async def test_an_unused_preset_is_deleted(client) -> None:
    created = (await client.post("/api/presets", json=BODY)).json()

    assert (await client.delete(f"/api/presets/{created['id']}")).status_code == 204
    assert await listed(client, "presets", created["id"]) is None


async def test_a_saved_job_summary_is_its_first_four_sent_values(client) -> None:
    created = (await client.post("/api/presets", json=BODY)).json()

    assert created["summary_params"] == ["CLUSTER", "NAMESPACE", "FOLIO_BRANCH"]


async def test_an_unreachable_jenkins_is_reported_not_guessed(tmp_path: Path) -> None:
    jenkins = FakeJenkins(unreachable=True)
    services = build(tmp_path, jenkins)
    async with client_for(services) as client:
        response = await client.post("/api/presets", json=BODY)
    services.store.close()

    assert response.status_code == 502
    assert response.json()["error"]["message"] == "Jenkins could not be reached."


async def test_checking_the_token_asks_jenkins_whose_it_is(tmp_path: Path) -> None:
    jenkins = FakeJenkins(unauthorised=True)
    services = build(tmp_path, jenkins)
    async with client_for(services) as client:
        refused = (await client.post("/api/jenkins/check")).json()
        jenkins.unauthorised = False
        accepted = (await client.post("/api/jenkins/check")).json()
    services.store.close()

    assert ("GET", "/me/api/json") in jenkins.calls
    assert refused["auth_ok"] is False
    assert accepted["auth_ok"] is True


async def test_an_unreachable_jenkins_is_not_called_a_rejected_token(tmp_path: Path) -> None:
    services = build(tmp_path, FakeJenkins(unreachable=True))
    async with client_for(services) as client:
        status = (await client.post("/api/jenkins/check")).json()
    services.store.close()

    assert status["reachable"] is False
    assert status["auth_ok"] is True


async def test_the_status_asks_jenkins_again_only_while_it_is_unreachable(tmp_path: Path) -> None:
    jenkins = FakeJenkins(unreachable=True)
    services = build(tmp_path, jenkins)
    async with client_for(services) as client:
        await client.post("/api/jenkins/check")
        jenkins.unreachable = False
        status = (await client.get("/api/jenkins/status")).json()
        await client.get("/api/jenkins/status")
    services.store.close()

    assert status["reachable"] is True
    assert jenkins.calls.count(("GET", "/me/api/json")) == 2


async def test_one_job_refused_does_not_call_the_token_rejected(tmp_path: Path) -> None:
    jenkins = FakeJenkins(forbidden=("/job/",))
    services = build(tmp_path, jenkins)
    async with client_for(services) as client:
        response = await client.post("/api/presets", json=BODY)
        status = (await client.get("/api/jenkins/status")).json()
    services.store.close()

    assert response.status_code == 502
    assert response.json()["error"]["message"] == "Jenkins refused this user access to this job."
    assert ("GET", "/me/api/json") in jenkins.calls
    assert status["auth_ok"] is True


async def test_a_rejected_token_is_reported_as_such(tmp_path: Path) -> None:
    jenkins = FakeJenkins(unauthorised=True)
    services = build(tmp_path, jenkins)
    async with client_for(services) as client:
        response = await client.post("/api/presets", json=BODY)
        status = (await client.get("/api/jenkins/status")).json()
    services.store.close()

    assert response.status_code == 502
    assert response.json()["error"]["message"] == "Jenkins rejected the API token."
    assert status["auth_ok"] is False
