"""The board's API: flows, steps, review, start, stop, resume."""

from __future__ import annotations

import asyncio
import time
from copy import deepcopy

import pytest

from jk.store.records import (
    Drift,
    DriftEntry,
    FlowStatus,
    JenkinsJobRecord,
)
from jk.web import app as web_app
from tests.webapp import (
    FakeJenkins,
    listed,
    resume_reviewed,
    start_reviewed,
)

JOB_PATH = "folder/createNamespace"
CYPRESS_PATH = "folder/runCypressTests"

DEFINITIONS = {
    JOB_PATH: [
        {"name": "CLUSTER", "type": "StringParameterDefinition"},
        {"name": "NAMESPACE", "type": "StringParameterDefinition"},
        {"name": "FOLIO_BRANCH", "type": "StringParameterDefinition"},
        {"name": "PLATFORM", "type": "StringParameterDefinition"},
    ],
    CYPRESS_PATH: [
        {"name": "TENANT_ID", "type": "StringParameterDefinition"},
        {"name": "WORKERS", "type": "StringParameterDefinition"},
    ],
}


@pytest.fixture
def jenkins() -> FakeJenkins:
    return FakeJenkins(definitions=deepcopy(DEFINITIONS))


async def make_preset(client, **overrides) -> dict:
    body = {
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
    body.update(overrides)
    return (await client.post("/api/presets", json=body)).json()


async def make_cypress(client) -> dict:
    return await make_preset(
        client,
        job_path=CYPRESS_PATH,
        name="EDEV Cypress / diku",
        operation="Run Cypress tests",
        destructive=False,
        params={
            "TENANT_ID": {"mode": "fixed", "value": "diku"},
            "WORKERS": {"mode": "fixed", "value": "1"},
        },
    )


async def test_dropping_a_preset_creates_a_draft_named_after_it(client) -> None:
    preset = await make_preset(client)

    flow = (await client.post("/api/flows", json={"steps": [{"preset_id": preset["id"]}]})).json()

    assert flow["status"] == "draft"
    assert flow["name"] == preset["name"]
    assert flow["steps"][0]["state"] == "planned"
    assert flow["steps"][0]["condition"] == "unless_failure"


async def test_a_card_shows_the_summary_parameters_of_its_preset(client) -> None:
    preset = await make_preset(client)
    flow = (await client.post("/api/flows", json={"steps": [{"preset_id": preset["id"]}]})).json()

    assert [(item["name"], item["value"]) for item in flow["steps"][0]["summary"]] == [
        ("CLUSTER", "example-cluster"),
        ("NAMESPACE", "example-ns"),
        ("FOLIO_BRANCH", ""),
    ]


async def test_an_empty_draft_can_be_created_and_deleted(client) -> None:
    flow = (await client.post("/api/flows", json={})).json()

    assert flow["steps"] == []
    assert (await client.delete(f"/api/flows/{flow['id']}")).status_code == 204


async def test_a_drifted_preset_cannot_be_dropped_into_a_flow(client, services) -> None:
    preset = await make_preset(client)
    services.presets.set_drift(
        preset["id"], Drift(added=(DriftEntry("ENTITLEMENT_MODE"),), seen_at=1)
    )

    response = await client.post("/api/flows", json={"steps": [{"preset_id": preset["id"]}]})

    assert response.status_code == 409
    assert response.json()["error"]["message"] == (
        "This saved job changed in Jenkins. Repair it in Library first."
    )


async def test_a_draft_runs_without_being_closed_for_changes_first(client, services) -> None:
    preset = await make_cypress(client)
    flow = (await client.post("/api/flows", json={"steps": [{"preset_id": preset["id"]}]})).json()

    started = await start_reviewed(client, flow["id"])
    await services.supervisor.wait(flow["id"])

    assert started.status_code == 200
    assert "editing" not in started.json()


async def test_a_draft_can_always_be_changed(client) -> None:
    preset = await make_preset(client)
    flow = (await client.post("/api/flows", json={"steps": [{"preset_id": preset["id"]}]})).json()
    step = f"/api/flows/{flow['id']}/steps/{flow['steps'][0]['id']}"

    changes = [
        await client.post(f"/api/flows/{flow['id']}/steps", json={"preset_id": preset["id"]}),
        await client.patch(step, json={"condition": "always"}),
        await client.patch(step, json={"position": 1}),
        await client.patch(f"/api/flows/{flow['id']}", json={"name": "Something else"}),
        await client.delete(step),
    ]

    assert [change.status_code for change in changes] == [200, 200, 200, 200, 200]


async def test_a_saved_flow_holds_each_steps_job_condition_and_values_in_order(client) -> None:
    """What the board compares a flow with: Save writes the jobs, in order, with
    their conditions and the values typed for them -- not the flow's name."""
    snapshot = await make_preset(client)
    cypress = await make_cypress(client)
    flow = (
        await client.post(
            "/api/flows",
            json={"steps": [{"preset_id": snapshot["id"]}, {"preset_id": cypress["id"]}]},
        )
    ).json()
    steps = f"/api/flows/{flow['id']}/steps"
    await client.patch(f"{steps}/{flow['steps'][1]['id']}", json={"position": 0})
    # A step is addressed by its place, so the moved flow is read again.
    moved = await listed(client, "flows", flow["id"])
    last = moved["steps"][1]["id"]
    await client.patch(f"{steps}/{last}", json={"condition": "always"})
    await client.patch(f"{steps}/{last}", json={"run_values": {"FOLIO_BRANCH": "main"}})
    await client.patch(f"/api/flows/{flow['id']}", json={"name": "Renamed on the board"})

    kept_id = (await client.post(f"/api/flows/{flow['id']}/save")).json()["saved_flow_id"]
    kept = next(
        item for item in (await client.get("/api/saved-flows")).json() if item["id"] == kept_id
    )
    now = await listed(client, "flows", flow["id"])

    triples = [(step["preset_id"], step["condition"], step["run_values"]) for step in now["steps"]]
    assert triples == [
        (cypress["id"], triples[0][1], {}),
        (snapshot["id"], "always", {"FOLIO_BRANCH": "main"}),
    ]
    assert [
        (step["preset_id"], step["condition"], step["run_values"]) for step in kept["steps"]
    ] == triples


async def test_a_flow_taken_from_a_saved_flow_starts_with_its_values(client) -> None:
    snapshot = await make_preset(client)
    flow = (await client.post("/api/flows", json={"steps": [{"preset_id": snapshot["id"]}]})).json()
    step = f"/api/flows/{flow['id']}/steps/{flow['steps'][0]['id']}"
    await client.patch(step, json={"run_values": {"FOLIO_BRANCH": "main", "OTHER": " "}})
    kept_id = (await client.post(f"/api/flows/{flow['id']}/save")).json()["saved_flow_id"]

    taken = (await client.post(f"/api/saved-flows/{kept_id}/instantiate", json={})).json()
    kept = (await client.get("/api/saved-flows")).json()

    # A blank value is not kept: it would only stand for "not typed yet".
    assert taken["steps"][0]["run_values"] == {"FOLIO_BRANCH": "main"}
    assert next(item for item in kept if item["id"] == kept_id)["steps"][0]["run_values"] == {
        "FOLIO_BRANCH": "main"
    }


async def test_two_flows_on_the_board_cannot_share_a_name(client) -> None:
    first = (await client.post("/api/flows", json={"name": "Nightly"})).json()
    second = (await client.post("/api/flows", json={"name": "Something else"})).json()

    refused = await client.patch(f"/api/flows/{second['id']}", json={"name": "nightly"})

    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "name_taken"
    # Its own name is not taken by itself.
    kept = await client.patch(f"/api/flows/{first['id']}", json={"name": "Nightly"})
    assert kept.status_code == 200


async def test_the_board_names_a_second_flow_of_the_same_job_itself(client) -> None:
    preset = await make_preset(client)

    first = (await client.post("/api/flows", json={"steps": [{"preset_id": preset["id"]}]})).json()
    second = (await client.post("/api/flows", json={"steps": [{"preset_id": preset["id"]}]})).json()
    third = (await client.post("/api/flows", json={"steps": [{"preset_id": preset["id"]}]})).json()

    assert second["name"] == f"{first['name']} copy"
    assert third["name"] == f"{first['name']} copy 2"


async def test_a_run_that_ended_holds_its_name_until_it_leaves_the_board(client, services) -> None:
    preset = await make_cypress(client)
    flow = (
        await client.post(
            "/api/flows", json={"name": "Nightly", "steps": [{"preset_id": preset["id"]}]}
        )
    ).json()
    await start_reviewed(client, flow["id"])
    await services.supervisor.wait(flow["id"])

    # It is still on the board, so two cards would read the same.
    beside = (await client.post("/api/flows", json={"name": "Nightly"})).json()
    assert beside["name"] == "Nightly copy"

    await client.patch(f"/api/flows/{flow['id']}", json={"cleared": True})
    after = (await client.post("/api/flows", json={"name": "Nightly"})).json()

    # Cleared off the board it is History, and History holds the name twice.
    assert after["name"] == "Nightly"


async def test_a_flow_is_duplicated_with_a_free_name_and_open_to_change(client) -> None:
    preset = await make_preset(client)
    flow = (
        await client.post(
            "/api/flows", json={"name": "Nightly", "steps": [{"preset_id": preset["id"]}]}
        )
    ).json()
    kept = (await client.post(f"/api/flows/{flow['id']}/save")).json()["saved_flow_id"]

    copy = (await client.post(f"/api/flows/{flow['id']}/duplicate")).json()
    again = (await client.post(f"/api/flows/{flow['id']}/duplicate")).json()

    assert (copy["name"], again["name"]) == ("Nightly copy", "Nightly copy 2")
    assert [step["preset_id"] for step in copy["steps"]] == [preset["id"]]
    assert [step["state"] for step in copy["steps"]] == ["planned"]
    # A copy is a thing of its own: saving it cannot overwrite the template.
    assert kept is not None
    assert copy["saved_flow_id"] is None
    assert copy["pinned"] is False


async def test_a_running_flow_is_duplicated_as_planned_steps(client, services, jenkins) -> None:
    jenkins.building = True
    preset = await make_cypress(client)
    flow = (await client.post("/api/flows", json={"steps": [{"preset_id": preset["id"]}]})).json()
    await start_reviewed(client, flow["id"])

    copy = (await client.post(f"/api/flows/{flow['id']}/duplicate")).json()

    assert copy["status"] == "draft"
    assert [step["state"] for step in copy["steps"]] == ["planned"]
    assert [step["build_number"] for step in copy["steps"]] == [None]


async def test_a_copy_of_a_copy_counts_instead_of_stacking_the_word(client) -> None:
    flow = (await client.post("/api/flows", json={"name": "Nightly"})).json()

    once = (await client.post(f"/api/flows/{flow['id']}/duplicate")).json()
    twice = (await client.post(f"/api/flows/{once['id']}/duplicate")).json()
    thrice = (await client.post(f"/api/flows/{twice['id']}/duplicate")).json()

    assert [once["name"], twice["name"], thrice["name"]] == [
        "Nightly copy",
        "Nightly copy 2",
        "Nightly copy 3",
    ]


async def test_a_flow_that_started_is_not_renamed(client, services, jenkins) -> None:
    jenkins.building = True
    preset = await make_cypress(client)
    flow = (await client.post("/api/flows", json={"steps": [{"preset_id": preset["id"]}]})).json()
    await start_reviewed(client, flow["id"])

    renamed = await client.patch(f"/api/flows/{flow['id']}", json={"name": "Something else"})

    # The board offers no rename here either; the two agree.
    assert renamed.json()["error"]["code"] == "flow_started"
    jenkins.building = False
    await services.supervisor.wait(flow["id"])


async def test_a_draft_takes_the_values_asked_at_launch_and_a_condition(client) -> None:
    preset = await make_preset(client)
    flow = (await client.post("/api/flows", json={"steps": [{"preset_id": preset["id"]}]})).json()
    step = flow["steps"][0]["id"]

    # A value asked at launch belongs to this run, not to the shape of the flow.
    filled = await client.patch(
        f"/api/flows/{flow['id']}/steps/{step}", json={"run_values": {"FOLIO_BRANCH": "X-1"}}
    )
    moved = await client.patch(
        f"/api/flows/{flow['id']}/steps/{step}", json={"condition": "always"}
    )

    assert filled.status_code == 200
    assert filled.json()["steps"][0]["run_values"]["FOLIO_BRANCH"] == "X-1"
    assert moved.json()["steps"][0]["condition"] == "always"


async def test_run_again_from_history_does_not_land_on_a_name_in_use(client, services) -> None:
    preset = await make_cypress(client)
    flow = (
        await client.post(
            "/api/flows", json={"name": "Nightly", "steps": [{"preset_id": preset["id"]}]}
        )
    ).json()
    await start_reviewed(client, flow["id"])
    await services.supervisor.wait(flow["id"])
    # Taken off the board by the trash, so the name is free and reused.
    await client.patch(f"/api/flows/{flow['id']}", json={"cleared": True})
    await client.post("/api/flows", json={"name": "Nightly"})

    # Run again, from History, on the run that was cleared away.
    again = (await client.post(f"/api/flows/{flow['id']}/rerun")).json()

    assert again["name"] == "Nightly copy"
    board = [
        item["name"] for item in (await client.get("/api/flows")).json() if not item["cleared"]
    ]
    assert sorted(board) == ["Nightly", "Nightly copy"]


async def test_a_flow_needs_a_name(client) -> None:
    flow = (await client.post("/api/flows", json={"name": "Nightly"})).json()

    refused = await client.patch(f"/api/flows/{flow['id']}", json={"name": "   "})

    assert refused.status_code == 400
    assert refused.json()["error"]["code"] == "name_empty"


async def test_a_planned_step_can_change_its_condition_and_run_values(client) -> None:
    preset = await make_preset(client)
    flow = (await client.post("/api/flows", json={"steps": [{"preset_id": preset["id"]}]})).json()
    step = flow["steps"][0]["id"]

    updated = await client.patch(
        f"/api/flows/{flow['id']}/steps/{step}",
        json={
            "condition": "after_success",
            "run_values": {"FOLIO_BRANCH": "example-edited-feature"},
        },
    )

    assert updated.json()["steps"][0]["condition"] == "after_success"
    assert updated.json()["steps"][0]["run_values"] == {"FOLIO_BRANCH": "example-edited-feature"}


async def test_removing_a_planned_step_renumbers_the_rest(client) -> None:
    preset = await make_preset(client)
    other = await make_cypress(client)
    flow = (
        await client.post(
            "/api/flows",
            json={"steps": [{"preset_id": preset["id"]}, {"preset_id": other["id"]}]},
        )
    ).json()

    left = await client.delete(f"/api/flows/{flow['id']}/steps/{flow['steps'][0]['id']}")

    assert [step["position"] for step in left.json()["steps"]] == [0]
    assert left.json()["steps"][0]["preset_id"] == other["id"]


async def test_a_step_takes_the_place_it_was_dropped_on(client) -> None:
    preset = await make_preset(client)
    other = await make_cypress(client)
    flow = (
        await client.post(
            "/api/flows",
            json={"steps": [{"preset_id": preset["id"]}, {"preset_id": preset["id"]}]},
        )
    ).json()

    added = await client.post(
        f"/api/flows/{flow['id']}/steps",
        json={"preset_id": other["id"], "position": 1, "condition": "after_success"},
    )

    steps = added.json()["steps"]
    assert [step["preset_id"] for step in steps] == [preset["id"], other["id"], preset["id"]]
    assert [step["position"] for step in steps] == [0, 1, 2]
    assert steps[1]["condition"] == "after_success"


async def test_a_flow_that_started_takes_a_step_at_the_end_only(client, services, jenkins) -> None:
    jenkins.building = True
    preset = await make_cypress(client)
    flow = (await client.post("/api/flows", json={"steps": [{"preset_id": preset["id"]}]})).json()
    await start_reviewed(client, flow["id"])
    steps = f"/api/flows/{flow['id']}/steps"

    refused = await client.post(steps, json={"preset_id": preset["id"], "position": 0})

    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "flow_started"
    assert len((await listed(client, "flows", flow["id"]))["steps"]) == 1

    # Editing was turned off to run it; that must not close a running flow.
    added = await client.post(steps, json={"preset_id": preset["id"]})

    assert added.status_code == 200
    assert len(added.json()["steps"]) == 2
    assert added.json()["steps"][1]["added_while_running"] is True
    jenkins.building = False
    await services.supervisor.wait(flow["id"])


async def test_removing_the_held_step_a_running_flow_waits_at_ends_it(
    client, services, jenkins
) -> None:
    jenkins.building = True
    preset = await make_cypress(client)
    flow = (await client.post("/api/flows", json={"steps": [{"preset_id": preset["id"]}]})).json()
    await start_reviewed(client, flow["id"])
    added = await client.post(f"/api/flows/{flow['id']}/steps", json={"preset_id": preset["id"]})
    jenkins.building = False
    await services.supervisor.wait(flow["id"])
    assert (await listed(client, "flows", flow["id"]))["status"] == "running"

    await client.delete(f"/api/flows/{flow['id']}/steps/{added.json()['steps'][1]['id']}")
    await services.supervisor.wait(flow["id"])

    assert (await listed(client, "flows", flow["id"]))["status"] == "finished"


async def test_moving_the_held_step_a_running_flow_waits_at_sends_the_next(
    client, services, jenkins
) -> None:
    jenkins.building = True
    preset = await make_cypress(client)
    flow = (
        await client.post("/api/flows", json={"steps": [{"preset_id": preset["id"]}] * 3})
    ).json()
    await start_reviewed(client, flow["id"])
    services.flows.set_held(flow["id"], 1, True)  # as a restart or a changed job does
    jenkins.building = False
    await services.supervisor.wait(flow["id"])

    await client.patch(
        f"/api/flows/{flow['id']}/steps/{flow['steps'][1]['id']}", json={"position": 2}
    )
    await services.supervisor.wait(flow["id"])

    steps = (await listed(client, "flows", flow["id"]))["steps"]
    assert [step["state"] for step in steps] == ["SUCCESS", "SUCCESS", "planned"]


async def test_review_lists_what_will_be_sent_and_what_stays_on_defaults(client) -> None:
    preset = await make_preset(client)
    flow = (await client.post("/api/flows", json={"steps": [{"preset_id": preset["id"]}]})).json()
    await client.patch(
        f"/api/flows/{flow['id']}/steps/{flow['steps'][0]['id']}",
        json={"run_values": {"FOLIO_BRANCH": "example-feature"}},
    )

    review = (await client.post(f"/api/flows/{flow['id']}/review")).json()

    assert review["ok"] is True
    assert review["issues"] == []
    sent = {item["name"]: item for item in review["steps"][0]["sent"]}
    assert sent["CLUSTER"]["value"] == "example-cluster"
    assert sent["FOLIO_BRANCH"]["per_run"] is True
    assert "PLATFORM" not in sent
    assert review["steps"][0]["defaults_left"] == 1


async def test_a_step_and_a_review_step_carry_the_job_url(client) -> None:
    preset = await make_preset(client)
    flow = (await client.post("/api/flows", json={"steps": [{"preset_id": preset["id"]}]})).json()

    review = (await client.post(f"/api/flows/{flow['id']}/review")).json()

    assert flow["steps"][0]["job_url"] == preset["job_url"]
    assert review["steps"][0]["job_url"] == preset["job_url"]
    assert preset["job_url"].startswith("http")


async def test_review_names_a_parameter_jenkins_no_longer_defines(client, jenkins) -> None:
    preset = await make_preset(client)
    flow = (await client.post("/api/flows", json={"steps": [{"preset_id": preset["id"]}]})).json()
    jenkins.definitions[JOB_PATH] = [{"name": "NAMESPACE", "type": "StringParameterDefinition"}]

    review = (await client.post(f"/api/flows/{flow['id']}/review")).json()

    assert review["ok"] is False
    assert {issue["parameter"] for issue in review["issues"]} == {"CLUSTER"}
    assert review["issues"][0]["failure"] == "parameter is not defined by Jenkins"
    assert review["issues"][0]["action"] == "Update the saved job in Library."


async def test_review_names_a_job_jenkins_no_longer_has(client, jenkins) -> None:
    preset = await make_preset(client)
    flow = (await client.post("/api/flows", json={"steps": [{"preset_id": preset["id"]}]})).json()
    jenkins.missing = ("/job/folder/job/createNamespace/",)

    review = (await client.post(f"/api/flows/{flow['id']}/review")).json()
    status = (await client.get("/api/jenkins/status")).json()

    assert review["issues"][0]["failure"] == (
        "Jenkins has no job folder/createNamespace. Nothing was sent."
    )
    assert status["reachable"] is True
    assert ("GET", "/me/api/json") not in jenkins.calls


async def test_review_reports_an_unanswered_per_run_value(client) -> None:
    preset = await make_preset(client)
    flow = (await client.post("/api/flows", json={"steps": [{"preset_id": preset["id"]}]})).json()

    review = (await client.post(f"/api/flows/{flow['id']}/review")).json()

    assert review["missing_run_values"] == [
        {"step_id": flow["steps"][0]["id"], "names": ["FOLIO_BRANCH"]}
    ]


def send(services, flow_id: str, position: int, build_number: int | None = None) -> None:
    """Put a step of a flow that runs into Jenkins, without a supervisor: sending, then a build."""
    services.flows.set_status(flow_id, FlowStatus.RUNNING, started=True)
    assert services.store.claim_submit_pending(flow_id, position, next_build_number=41)
    if build_number is not None:
        services.store.mark_queued(flow_id, position, queue_url="/queue/item/7/", note=None)
        services.store.mark_running(
            flow_id, position, build_number=build_number, build_url="/job/x/41/", queue_id=7
        )


async def test_review_names_the_build_of_a_flow_running_on_the_same_namespace(
    client, services
) -> None:
    preset = await make_preset(client, destructive=False)
    first = (await client.post("/api/flows", json={"steps": [{"preset_id": preset["id"]}]})).json()
    second = (await client.post("/api/flows", json={"steps": [{"preset_id": preset["id"]}]})).json()
    send(services, first["id"], 0, build_number=41)

    review = (await client.post(f"/api/flows/{second['id']}/review")).json()

    assert review["same_target"] == [
        {
            "flow_id": first["id"],
            "flow_name": first["name"],
            "position": 0,
            "state": "running",
            "cluster": "example-cluster",
            "namespace": "example-ns",
            "build_number": 41,
        }
    ]
    assert review["ok"] is True


async def test_review_leaves_out_a_draft_on_the_same_namespace(client) -> None:
    preset = await make_preset(client, destructive=False)
    await client.post("/api/flows", json={"steps": [{"preset_id": preset["id"]}]})
    second = (await client.post("/api/flows", json={"steps": [{"preset_id": preset["id"]}]})).json()

    review = (await client.post(f"/api/flows/{second['id']}/review")).json()

    assert review["same_target"] == []


async def test_review_names_a_later_step_only_while_its_flow_runs(client, services) -> None:
    preset = await make_preset(client, destructive=False)
    cypress = await make_cypress(client)
    first = (
        await client.post(
            "/api/flows",
            json={"steps": [{"preset_id": cypress["id"]}, {"preset_id": preset["id"]}]},
        )
    ).json()
    second = (await client.post("/api/flows", json={"steps": [{"preset_id": preset["id"]}]})).json()
    send(services, first["id"], 0, build_number=41)

    running = (await client.post(f"/api/flows/{second['id']}/review")).json()["same_target"]
    services.flows.set_status(first["id"], FlowStatus.STOPPED)
    stopped = (await client.post(f"/api/flows/{second['id']}/review")).json()["same_target"]

    assert [(item["position"], item["state"], item["build_number"]) for item in running] == [
        (1, "planned", None)
    ]
    assert stopped == []


async def test_review_names_a_step_that_may_be_running(client, services) -> None:
    preset = await make_preset(client, destructive=False)
    first = (
        await client.post(
            "/api/flows",
            json={"steps": [{"preset_id": preset["id"]}, {"preset_id": preset["id"]}]},
        )
    ).json()
    second = (await client.post("/api/flows", json={"steps": [{"preset_id": preset["id"]}]})).json()
    send(services, first["id"], 0)
    services.store.mark_needs_attention(
        first["id"], 0, kind="ambiguous_submission", message="dropped"
    )
    services.flows.set_status(first["id"], FlowStatus.STOPPED)

    review = (await client.post(f"/api/flows/{second['id']}/review")).json()

    assert [(item["position"], item["state"]) for item in review["same_target"]] == [
        (0, "needs_attention")
    ]


async def test_review_lists_what_jenkins_uses_for_each_parameter_left_to_it(
    client, jenkins
) -> None:
    jenkins.definitions[JOB_PATH] = [
        *DEFINITIONS[JOB_PATH][:3],
        {
            "name": "PLATFORM",
            "type": "StringParameterDefinition",
            "defaultParameterValue": {"value": "EUREKA"},
        },
        {"name": "POSTGRESQL", "type": "StringParameterDefinition"},
    ]
    preset = await make_preset(client)
    flow = (await client.post("/api/flows", json={"steps": [{"preset_id": preset["id"]}]})).json()

    step = (await client.post(f"/api/flows/{flow['id']}/review")).json()["steps"][0]

    assert step["defaults"] == [
        {"name": "PLATFORM", "default": "EUREKA"},
        {"name": "POSTGRESQL", "default": None},
    ]
    assert step["defaults_left"] == 2


async def test_a_draft_step_shows_the_current_name_of_its_saved_job(client) -> None:
    preset = await make_preset(client)
    flow = (await client.post("/api/flows", json={"steps": [{"preset_id": preset["id"]}]})).json()

    await client.put(f"/api/presets/{preset['id']}", json={"name": "renamed"})

    step = (await listed(client, "flows", flow["id"]))["steps"][0]
    assert step["preset_name"] == "renamed"


async def test_starting_a_flow_sends_the_reviewed_values_once(client, services, jenkins) -> None:
    preset = await make_preset(client)
    flow = (await client.post("/api/flows", json={"steps": [{"preset_id": preset["id"]}]})).json()

    started = await start_reviewed(
        client, flow["id"], {flow["steps"][0]["id"]: {"FOLIO_BRANCH": "example-feature"}}
    )
    await services.supervisor.wait(flow["id"])

    assert started.status_code == 200
    submits = [call for call in jenkins.calls if call[1].endswith("/buildWithParameters")]
    assert len(submits) == 1
    body = jenkins.bodies[0].decode()
    assert "PLATFORM" not in body
    assert "FOLIO_BRANCH=example-feature" in body

    finished = await listed(client, "flows", flow["id"])
    assert finished["status"] == "finished"
    assert finished["steps"][0]["state"] == "SUCCESS"
    assert finished["steps"][0]["build_number"] == 41
    assert finished["result"] == "SUCCESS"


def submits(jenkins: FakeJenkins) -> int:
    return sum(1 for call in jenkins.calls if call[1].endswith("/buildWithParameters"))


def frozen(services, flow_id: str) -> list[bool]:
    _, meta = services.flows.get(flow_id)
    return [step.frozen for _, step in sorted(meta.steps.items())]


async def test_a_step_moved_while_start_reads_jenkins_stops_the_start(
    client, services, jenkins
) -> None:
    first, second = await make_preset(client), await make_cypress(client)
    flow = (
        await client.post(
            "/api/flows", json={"steps": [{"preset_id": first["id"]}, {"preset_id": second["id"]}]}
        )
    ).json()
    run_values = {flow["steps"][0]["id"]: {"FOLIO_BRANCH": "example-feature"}}
    token = (await client.post(f"/api/flows/{flow['id']}/review", json={})).json()["review_token"]
    jenkins.on_definitions = lambda: services.flows.move_step(flow["id"], 1, 0)

    refused = await client.post(
        f"/api/flows/{flow['id']}/start", json={"run_values": run_values, "review_token": token}
    )

    assert refused.status_code == 409, refused.json()
    assert refused.json()["error"]["code"] == "flow_changed", refused.json()
    assert submits(jenkins) == 0
    assert frozen(services, flow["id"]) == [False, False]


async def test_a_step_moved_while_confirm_reads_jenkins_releases_nothing(
    client, services, jenkins
) -> None:
    jenkins.building = True
    first, second = await make_cypress(client), await make_preset(client)
    flow = (await client.post("/api/flows", json={"steps": [{"preset_id": first["id"]}]})).json()
    await start_reviewed(client, flow["id"])
    for preset in (first, second):
        added = await client.post(
            f"/api/flows/{flow['id']}/steps", json={"preset_id": preset["id"]}
        )
    asked = {added.json()["steps"][2]["id"]: {"FOLIO_BRANCH": "example-feature"}}
    review = await client.post(f"/api/flows/{flow['id']}/review", json={"scope": "held"})
    jenkins.on_definitions = lambda: services.flows.move_step(flow["id"], 2, 1)

    refused = await client.post(
        f"/api/flows/{flow['id']}/confirm",
        json={"run_values": asked, "review_token": review.json()["review_token"]},
    )

    assert refused.status_code == 409, refused.json()
    assert refused.json()["error"]["code"] == "flow_changed", refused.json()
    assert frozen(services, flow["id"])[1:] == [False, False]
    jenkins.building = False
    await client.post(f"/api/flows/{flow['id']}/stop", json={"abort_current": False})
    await services.supervisor.wait(flow["id"])
    steps = (await listed(client, "flows", flow["id"]))["steps"]
    assert [step["state"] for step in steps[1:]] == ["planned", "planned"]


async def test_a_step_moved_while_resume_reads_jenkins_resumes_nothing(
    client, services, jenkins
) -> None:
    first, second = await make_cypress(client), await make_preset(client)
    jenkins.result = "FAILURE"
    flow = (
        await client.post(
            "/api/flows",
            json={"steps": [{"preset_id": first["id"]}] * 2 + [{"preset_id": second["id"]}]},
        )
    ).json()
    await start_reviewed(
        client, flow["id"], {flow["steps"][2]["id"]: {"FOLIO_BRANCH": "example-feature"}}
    )
    await services.supervisor.wait(flow["id"])
    assert (await listed(client, "flows", flow["id"]))["failed_at_position"] == 1
    review = await client.post(
        f"/api/flows/{flow['id']}/review", json={"scope": "resume", "from_position": 1}
    )
    jenkins.on_definitions = lambda: services.flows.move_step(flow["id"], 2, 1)

    refused = await client.post(
        f"/api/flows/{flow['id']}/resume",
        json={"from_position": 1, "review_token": review.json()["review_token"]},
    )

    assert refused.status_code == 409, refused.json()
    assert refused.json()["error"]["code"] == "flow_changed", refused.json()
    assert submits(jenkins) == 1


async def test_a_started_flow_cannot_be_started_again(client, services) -> None:
    preset = await make_cypress(client)
    flow = (await client.post("/api/flows", json={"steps": [{"preset_id": preset["id"]}]})).json()
    await start_reviewed(client, flow["id"])
    await services.supervisor.wait(flow["id"])

    response = await start_reviewed(client, flow["id"])

    assert response.status_code == 409


async def test_a_failure_stops_the_flow_and_offers_a_resume(client, services, jenkins) -> None:
    preset = await make_cypress(client)
    jenkins.result = "FAILURE"
    flow = (
        await client.post(
            "/api/flows",
            json={"steps": [{"preset_id": preset["id"]}, {"preset_id": preset["id"]}]},
        )
    ).json()

    await start_reviewed(client, flow["id"])
    await services.supervisor.wait(flow["id"])

    failed = await listed(client, "flows", flow["id"])
    assert failed["status"] == "failed"
    assert failed["failed_at_position"] == 1
    assert failed["steps"][1]["state"] == "planned"

    jenkins.result = "SUCCESS"
    resumed = await resume_reviewed(client, flow["id"], 1)
    await services.supervisor.wait(flow["id"])

    assert resumed.status_code == 200
    assert (await listed(client, "flows", flow["id"]))["status"] == "finished"


async def test_a_finished_flow_can_be_cleared_from_the_board_but_stays_in_history(
    client, services
) -> None:
    preset = await make_cypress(client)
    flow = (await client.post("/api/flows", json={"steps": [{"preset_id": preset["id"]}]})).json()
    await start_reviewed(client, flow["id"])
    await services.supervisor.wait(flow["id"])

    cleared = await client.patch(f"/api/flows/{flow['id']}", json={"cleared": True})

    assert cleared.json()["cleared"] is True
    history = (await client.get("/api/flows")).json()
    assert [(item["id"], item["cleared"]) for item in history] == [(flow["id"], True)]


async def test_run_again_gives_a_draft_copy_each_time(client, services) -> None:
    preset = await make_cypress(client)
    flow = (await client.post("/api/flows", json={"steps": [{"preset_id": preset["id"]}]})).json()
    await start_reviewed(client, flow["id"])
    await services.supervisor.wait(flow["id"])

    ready = (await client.post(f"/api/flows/{flow['id']}/rerun")).json()
    # The same ended run again: what History still shows after Run again.
    open_again = (await client.post(f"/api/flows/{flow['id']}/rerun")).json()

    assert (ready["status"], open_again["status"]) == ("draft", "draft")
    assert open_again["name"] != ready["name"]


async def test_run_again_takes_the_place_of_the_flow_that_ended(client, services) -> None:
    preset = await make_cypress(client)
    flow = (
        await client.post(
            "/api/flows", json={"name": "Nightly", "steps": [{"preset_id": preset["id"]}]}
        )
    ).json()
    await client.patch(f"/api/flows/{flow['id']}", json={"pinned": True})
    kept = (await client.post(f"/api/flows/{flow['id']}/save")).json()["saved_flow_id"]
    await start_reviewed(client, flow["id"])
    await services.supervisor.wait(flow["id"])

    heard = services.bus.subscribe()
    again = (await client.post(f"/api/flows/{flow['id']}/rerun")).json()

    assert again["id"] != flow["id"]
    assert again["status"] == "draft"
    assert [step["preset_id"] for step in again["steps"]] == [preset["id"]]
    assert (again["name"], again["pinned"], again["saved_flow_id"]) == ("Nightly", True, kept)
    assert again["created_at"] == flow["created_at"]
    assert [step["state"] for step in again["steps"]] == ["planned"]
    assert [step["run_values"] for step in again["steps"]] == [
        step["run_values"] for step in flow["steps"]
    ]

    # The hand-over that takes the original off is said out loud, so an open
    # panel hears it instead of showing a card that is no longer there.
    while True:
        name, data = await asyncio.wait_for(heard.get(), 3)
        if data["id"] == flow["id"]:
            break
    assert (name, data["cleared"]) == ("flow.updated", True)
    assert (await listed(client, "flows", flow["id"]))["cleared"] is True


async def test_a_flow_that_ended_keeps_its_name(client, services) -> None:
    preset = await make_cypress(client)
    flow = (await client.post("/api/flows", json={"steps": [{"preset_id": preset["id"]}]})).json()
    await start_reviewed(client, flow["id"])
    await services.supervisor.wait(flow["id"])

    renamed = await client.patch(f"/api/flows/{flow['id']}", json={"name": "Other"})

    assert renamed.status_code == 409
    assert renamed.json()["error"]["code"] == "flow_finished"


async def test_run_again_takes_a_saved_job_that_changed_or_is_gone(client, services) -> None:
    """A copy of a flow that ended is how such a step is replaced, so it never refuses."""
    changed = await make_preset(
        client,
        name="edev rancher",
        destructive=False,
        params={"CLUSTER": {"mode": "fixed", "value": "example-cluster"}},
    )
    gone = await make_cypress(client)
    flow = (
        await client.post(
            "/api/flows",
            json={"steps": [{"preset_id": changed["id"]}, {"preset_id": gone["id"]}]},
        )
    ).json()
    await start_reviewed(client, flow["id"])
    await services.supervisor.wait(flow["id"])
    services.presets.set_drift(
        changed["id"], Drift(added=(DriftEntry("ENTITLEMENT_MODE"),), seen_at=1)
    )
    assert (await client.delete(f"/api/presets/{gone['id']}")).status_code == 204

    again = await client.post(f"/api/flows/{flow['id']}/rerun")

    assert again.status_code == 201
    assert [step["preset_name"] for step in again.json()["steps"]] == [
        changed["name"],
        gone["name"],
    ]
    review = await client.post(f"/api/flows/{again.json()['id']}/review", json={})
    assert [issue["failure"] for issue in review.json()["issues"]] == [
        "Jenkins changed this saved job",
        "the saved job is gone",
    ]
    # The changed one leads to its saved job in Library; the one that is gone has none.
    assert [(issue["action"], issue["preset_id"]) for issue in review.json()["issues"]] == [
        ("Review it in Library", changed["id"]),
        ("Update the saved job in Library.", None),
    ]


async def test_a_flow_adds_up_what_jenkins_expects_of_the_steps_left(client, services) -> None:
    preset = await make_cypress(client)
    flow = (
        await client.post(
            "/api/flows", json={"steps": [{"preset_id": preset["id"]}, {"preset_id": preset["id"]}]}
        )
    ).json()
    assert flow["estimate_ms"] is None

    services.jenkins_jobs.replace_index(
        [
            JenkinsJobRecord(
                job_path=preset["job_path"],
                name="x",
                folder="",
                url="",
                param_count=1,
                typical_ms=600_000,
            )
        ]
    )

    again = await listed(client, "flows", flow["id"])
    assert [step["estimate_ms"] for step in again["steps"]] == [600_000, 600_000]
    assert again["estimate_ms"] == 1_200_000


async def test_the_board_hears_a_running_build_s_time_before_it_ends(
    client, services, jenkins
) -> None:
    jenkins.building = True
    preset = await make_cypress(client)
    flow = (await client.post("/api/flows", json={"steps": [{"preset_id": preset["id"]}]})).json()
    heard = services.bus.subscribe()
    await start_reviewed(client, flow["id"])

    async def timed() -> dict:
        while True:
            name, data = await heard.get()
            step = data["steps"][0] if name == "flow.updated" else {}
            if step.get("state") == "running" and step["elapsed_ms"] is not None:
                return step

    try:
        step = await asyncio.wait_for(timed(), 3)
    finally:
        jenkins.building = False
        await services.supervisor.wait(flow["id"])

    assert step["estimate_ms"] == 1_200_000


async def test_a_run_that_ended_long_ago_stays_on_the_board(client, services) -> None:
    """Nothing takes a finished run off the board by itself."""
    preset = await make_cypress(client)
    flow = (
        await client.post(
            "/api/flows", json={"name": "Nightly", "steps": [{"preset_id": preset["id"]}]}
        )
    ).json()
    await start_reviewed(client, flow["id"])
    await services.supervisor.wait(flow["id"])
    services.store.connection.execute(
        "UPDATE flow_meta SET finished_at = ? WHERE run_id = ?",
        (int(time.time()) - 13 * 60 * 60, flow["id"]),
    )
    services.store.connection.commit()

    # Serving starts every background task; an ended run, however old, is
    # still on the board after them.
    app = web_app.create_app(services, serve_static=False, background=True)
    async with app.router.lifespan_context(app):
        await asyncio.sleep(0.1)

    assert (await listed(client, "flows", flow["id"]))["cleared"] is False


async def test_serving_closes_even_after_a_background_task_failed(services, monkeypatch) -> None:
    """A background task that broke does not stop the server shutting down."""
    started = asyncio.Event()

    async def first_look_that_breaks(_services: object) -> None:
        started.set()
        raise RuntimeError("the first look broke")

    async def nothing(*_args: object, **_kwargs: object) -> None:
        return None

    closed: list[str] = []

    async def shutdown() -> None:
        closed.append("supervisor")

    monkeypatch.setattr(web_app, "_first_look", first_look_that_breaks)
    monkeypatch.setattr(services.supervisor, "start", nothing)
    monkeypatch.setattr(services.supervisor, "shutdown", shutdown)
    monkeypatch.setattr(services.drift, "run_forever", nothing)
    app = web_app.create_app(services, serve_static=False, background=True)

    async with app.router.lifespan_context(app):
        await asyncio.wait_for(started.wait(), 3)
        await asyncio.sleep(0)

    assert closed == ["supervisor"]


async def test_run_again_keeps_the_original_until_the_copy_is_reviewed(
    client, services, jenkins
) -> None:
    preset = await make_cypress(client)
    flow = (
        await client.post(
            "/api/flows", json={"name": "Nightly", "steps": [{"preset_id": preset["id"]}]}
        )
    ).json()
    await start_reviewed(client, flow["id"])
    await services.supervisor.wait(flow["id"])

    copy = (await client.post(f"/api/flows/{flow['id']}/rerun", json={"keep_source": True})).json()

    assert copy["name"] == "Nightly copy"
    assert copy["status"] == "draft"
    assert (await listed(client, "flows", flow["id"]))["cleared"] is False
    # A failed review leaves a cancellable draft, with its original visible.
    jenkins.unreachable = True
    review = await client.post(f"/api/flows/{copy['id']}/review", json={})
    assert review.status_code == 200
    assert review.json()["ok"] is False
    assert (await listed(client, "flows", flow["id"]))["cleared"] is False
    cancelled = await client.delete(f"/api/flows/{copy['id']}")
    assert cancelled.status_code == 204
    assert (await listed(client, "flows", flow["id"]))["cleared"] is False
