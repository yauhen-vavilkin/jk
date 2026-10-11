"""The Library's API: the Jenkins index, saved jobs, saved flows, and repair."""

from __future__ import annotations

from dataclasses import replace

import pytest

from jk.store.records import Drift, DriftEntry, JenkinsJobRecord, SavedFlowStep
from jk.web import presenter
from jk.web.app import _first_look
from tests.webapp import FakeJenkins, listed

FOLDER = "com.cloudbees.hudson.plugins.folder.Folder"
JOB = "org.jenkinsci.plugins.workflow.job.WorkflowJob"
JOB_PATH = "folioRancher/manageNamespace/deleteNamespace"

DEFINITIONS = [
    {"name": "CLUSTER", "type": "StringParameterDefinition"},
    {"name": "NAMESPACE", "type": "StringParameterDefinition"},
]

TREE = {
    "jobs": [
        {
            "name": "folioRancher",
            "_class": FOLDER,
            "jobs": [
                {
                    "name": "manageNamespace",
                    "_class": FOLDER,
                    "jobs": [
                        {
                            "name": "deleteNamespace",
                            "_class": JOB,
                            "url": "https://jenkins.invalid/job/x/",
                            "property": [
                                {
                                    "parameterDefinitions": [
                                        {"name": item["name"]} for item in DEFINITIONS
                                    ]
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    ]
}


@pytest.fixture
def jenkins() -> FakeJenkins:
    return FakeJenkins(definitions={JOB_PATH: list(DEFINITIONS)}, jobs_tree=dict(TREE))


async def save_from_library(client) -> str:
    """The only way a saved job is born: from a Jenkins job, in the Library."""
    created = await client.post(
        "/api/presets",
        json={
            "job_path": JOB_PATH,
            "name": "Delete EDEV environment",
            "operation": "Delete environment",
            "destructive": True,
            "params": {
                "CLUSTER": {"mode": "fixed", "value": "example-cluster"},
                "NAMESPACE": {"mode": "fixed", "value": "example-ns"},
            },
        },
    )
    assert created.status_code == 201
    return created.json()["id"]


def save_a_flow(services, *preset_ids: str, name: str = "Rebuild EDEV") -> str:
    """A saved flow made through the store, so a test starts from one without the panel."""
    steps = tuple(SavedFlowStep(preset_id=preset_id) for preset_id in preset_ids)
    return services.saved_flows.save(name=name, steps=steps).id


async def test_refreshing_fills_the_index_and_search_filters_it(client) -> None:
    refreshed = await client.post("/api/jenkins/jobs/refresh")

    assert refreshed.status_code == 204
    assert [job["job_path"] for job in (await client.get("/api/jenkins/jobs")).json()] == [JOB_PATH]
    assert (await client.get("/api/jenkins/jobs?q=nothing-like-this")).json() == []
    assert len((await client.get("/api/jenkins/jobs?q=namespace")).json()) == 1


async def test_the_first_crawl_tells_an_open_library_to_list_again(services) -> None:
    """A Library opened while the first crawl ran is not left empty after it."""
    heard = services.bus.subscribe()

    await _first_look(services)

    assert ("index.refreshed", {}) in [heard.get_nowait() for _ in range(heard.qsize())]


async def test_the_index_row_carries_the_folder_and_the_parameter_count(client) -> None:
    await client.post("/api/jenkins/jobs/refresh")

    job = (await client.get("/api/jenkins/jobs")).json()[0]

    assert job["folder"] == "folioRancher / manageNamespace"
    assert job["param_count"] == 2


async def test_the_definitions_of_a_job_can_be_read_live(client) -> None:
    definitions = (await client.get(f"/api/jenkins/jobs/{JOB_PATH}/definitions")).json()

    assert [item["name"] for item in definitions] == ["CLUSTER", "NAMESPACE"]


async def test_a_job_saved_in_the_library_is_listed_with_its_values(client) -> None:
    preset_id = await save_from_library(client)

    preset = (await client.get("/api/presets")).json()[0]
    assert preset["id"] == preset_id
    assert preset["params"]["CLUSTER"]["mode"] == "fixed"


async def test_a_saved_flow_becomes_a_draft_with_all_its_steps(client, services) -> None:
    preset_id = await save_from_library(client)
    save_a_flow(services, preset_id)
    saved = (await client.get("/api/saved-flows")).json()[0]

    flow = (await client.post(f"/api/saved-flows/{saved['id']}/instantiate", json={})).json()

    assert flow["status"] == "draft"
    # It was built once already, so it lands ready to run, not open to change.
    assert flow["editing"] is False
    assert [step["preset_id"] for step in flow["steps"]] == [preset_id]
    assert flow["name"] == saved["name"]


async def test_a_saved_flow_is_duplicated_with_a_free_name(client, services) -> None:
    preset_id = await save_from_library(client)
    save_a_flow(services, preset_id)
    saved = (await client.get("/api/saved-flows")).json()[0]

    copy = (await client.post(f"/api/saved-flows/{saved['id']}/duplicate")).json()
    again = (await client.post(f"/api/saved-flows/{saved['id']}/duplicate")).json()

    assert copy["name"] == f"{saved['name']} copy"
    assert again["name"] == f"{saved['name']} copy 2"
    assert [step["preset_id"] for step in copy["steps"]] == [
        step["preset_id"] for step in saved["steps"]
    ]


async def test_a_saved_flow_is_renamed_and_deleted_on_its_own(client, services) -> None:
    preset_id = await save_from_library(client)
    save_a_flow(services, preset_id)
    saved = (await client.get("/api/saved-flows")).json()[0]

    renamed = await client.patch(f"/api/saved-flows/{saved['id']}", json={"name": "Nightly EDEV"})
    assert renamed.json()["name"] == "Nightly EDEV"

    assert (await client.delete(f"/api/saved-flows/{saved['id']}")).status_code == 204
    assert (await client.get("/api/saved-flows")).json() == []


async def test_a_saved_flow_adds_up_how_long_its_jobs_last_took(client, services) -> None:
    preset_id = await save_from_library(client)
    saved_id = save_a_flow(services, preset_id, preset_id, name="Twice")

    def index(typical_ms: int | None) -> None:
        job = JenkinsJobRecord(JOB_PATH, "deleteNamespace", "", "", 2, typical_ms=typical_ms)
        services.jenkins_jobs.replace_index([job])

    index(None)
    assert (await client.get("/api/saved-flows")).json()[0]["estimate_ms"] is None

    index(600_000)
    assert (await client.get("/api/saved-flows")).json()[0]["estimate_ms"] == 1_200_000

    # One step whose saved job is gone makes the whole guess unknown, as on the board.
    stored = services.saved_flows.get(saved_id)
    gone = replace(stored, steps=(*stored.steps, SavedFlowStep(preset_id="gone")))
    typical = services.jenkins_jobs.typical_durations()
    assert presenter.saved_flow_estimate(gone, services.preset_map(), typical) is None


async def test_deleting_the_flow_on_the_board_keeps_its_saved_flow(client, services) -> None:
    preset_id = await save_from_library(client)
    save_a_flow(services, preset_id)
    saved = (await client.get("/api/saved-flows")).json()[0]
    flow = (await client.post(f"/api/saved-flows/{saved['id']}/instantiate", json={})).json()

    assert (await client.delete(f"/api/flows/{flow['id']}")).status_code == 204
    assert [item["id"] for item in (await client.get("/api/saved-flows")).json()] == [saved["id"]]


async def test_a_rename_keeps_the_steps_the_server_holds(client, services) -> None:
    """A tab that missed the latest save renames without writing old steps back."""
    preset_id = await save_from_library(client)
    # The server holds two steps; the tab that renames never heard of the second.
    saved_id = save_a_flow(services, preset_id, preset_id, name="Nightly")

    renamed = await client.patch(f"/api/saved-flows/{saved_id}", json={"name": "Nightly EDEV"})

    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Nightly EDEV"
    assert len(renamed.json()["steps"]) == 2


async def test_a_rename_of_a_saved_flow_is_refused_when_empty_taken_or_gone(
    client, services
) -> None:
    preset_id = await save_from_library(client)
    save_a_flow(services, preset_id, name="Nightly")
    other_id = save_a_flow(services, preset_id, name="Daily")

    empty = await client.patch(f"/api/saved-flows/{other_id}", json={"name": "   "})
    taken = await client.patch(f"/api/saved-flows/{other_id}", json={"name": " NIGHTLY "})
    gone = await client.patch("/api/saved-flows/no-such-flow", json={"name": "Weekly"})

    assert [empty.status_code, taken.status_code, gone.status_code] == [400, 409, 404]
    assert empty.json()["error"]["code"] == "name_empty"
    assert taken.json()["error"]["code"] == "name_taken"
    names = {item["id"]: item["name"] for item in (await client.get("/api/saved-flows")).json()}
    assert names[other_id] == "Daily"


async def test_a_saved_flow_keeping_its_own_name_is_not_a_clash_with_itself(
    client, services
) -> None:
    preset_id = await save_from_library(client)
    saved_id = save_a_flow(services, preset_id, name="Nightly")

    kept = await client.patch(f"/api/saved-flows/{saved_id}", json={"name": "Nightly"})

    assert kept.status_code == 200


async def test_saving_a_flow_under_a_taken_name_makes_its_own_template(client, services) -> None:
    preset_id = await save_from_library(client)
    save_a_flow(services, preset_id, name="Nightly")
    flow = (
        await client.post(
            "/api/flows", json={"name": "Nightly", "steps": [{"preset_id": preset_id}]}
        )
    ).json()

    # The user named the flow, not the template, so Save takes a free name
    # instead of refusing and leaving them nowhere to put it.
    kept = (await client.post(f"/api/flows/{flow['id']}/save")).json()

    assert kept["saved_flow_id"] is not None
    assert sorted(item["name"] for item in (await client.get("/api/saved-flows")).json()) == [
        "Nightly",
        "Nightly copy",
    ]


async def test_saving_a_flow_again_never_renames_the_template(client, services) -> None:
    preset_id = await save_from_library(client)
    save_a_flow(services, preset_id)
    saved = (await client.get("/api/saved-flows")).json()[0]
    first = (await client.post(f"/api/saved-flows/{saved['id']}/instantiate", json={})).json()
    second = (await client.post(f"/api/saved-flows/{saved['id']}/instantiate", json={})).json()
    assert second["name"] == f"{saved['name']} copy"

    # The second card was named by the board; saving it must not carry that name
    # onto the template both cards came from.
    await client.post(f"/api/flows/{second['id']}/save")
    await client.patch(f"/api/flows/{first['id']}", json={"editing": True})
    await client.patch(f"/api/flows/{first['id']}", json={"name": "Renamed for this run"})
    await client.post(f"/api/flows/{first['id']}/save")

    assert [item["name"] for item in (await client.get("/api/saved-flows")).json()] == [
        saved["name"]
    ]


async def test_a_saved_flow_is_not_appended_to_a_flow_that_is_not_being_edited(
    client, services
) -> None:
    preset_id = await save_from_library(client)
    save_a_flow(services, preset_id)
    saved = (await client.get("/api/saved-flows")).json()[0]
    ready = (await client.post(f"/api/saved-flows/{saved['id']}/instantiate", json={})).json()

    refused = await client.post(
        f"/api/saved-flows/{saved['id']}/instantiate", json={"flow_id": ready["id"]}
    )

    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "flow_not_editing"


async def test_a_saved_flow_can_be_appended_to_an_existing_flow(client, services) -> None:
    preset_id = await save_from_library(client)
    save_a_flow(services, preset_id)
    saved = (await client.get("/api/saved-flows")).json()[0]
    first = (await client.post(f"/api/saved-flows/{saved['id']}/instantiate", json={})).json()
    await client.patch(f"/api/flows/{first['id']}", json={"editing": True})

    appended = (
        await client.post(
            f"/api/saved-flows/{saved['id']}/instantiate", json={"flow_id": first["id"]}
        )
    ).json()

    assert len(appended["steps"]) == 2


async def test_save_as_flow_writes_a_template(client) -> None:
    preset_id = await save_from_library(client)

    flow = (
        await client.post(
            "/api/flows",
            json={"name": "My flow", "steps": [{"preset_id": preset_id, "condition": "always"}]},
        )
    ).json()

    assert (await client.post(f"/api/flows/{flow['id']}/save")).status_code == 200

    [saved] = (await client.get("/api/saved-flows")).json()
    assert saved["steps"][0]["condition"] == "always"


async def test_saving_a_flow_twice_keeps_one_saved_flow(client) -> None:
    preset_id = await save_from_library(client)
    flow = (
        await client.post(
            "/api/flows", json={"name": "Nightly", "steps": [{"preset_id": preset_id}]}
        )
    ).json()

    first = (await client.post(f"/api/flows/{flow['id']}/save")).json()
    await client.post(f"/api/flows/{flow['id']}/steps", json={"preset_id": preset_id})
    second = (await client.post(f"/api/flows/{flow['id']}/save")).json()

    saved = (await client.get("/api/saved-flows")).json()
    assert first["saved_flow_id"] == second["saved_flow_id"] == saved[0]["id"]
    assert [(item["name"], len(item["steps"])) for item in saved] == [("Nightly", 2)]


async def test_renaming_a_flow_leaves_the_saved_flow_alone(client, services) -> None:
    preset_id = await save_from_library(client)
    save_a_flow(services, preset_id)
    saved = (await client.get("/api/saved-flows")).json()[0]
    flow = (await client.post(f"/api/saved-flows/{saved['id']}/instantiate", json={})).json()
    assert flow["saved_flow_id"] == saved["id"]
    await client.patch(f"/api/flows/{flow['id']}", json={"editing": True})

    await client.patch(f"/api/flows/{flow['id']}", json={"name": "Renamed for this run"})

    # The copy on the board is named for this run; the template keeps its own name.
    assert (await listed(client, "flows", flow["id"]))["name"] == "Renamed for this run"
    assert [item["name"] for item in (await client.get("/api/saved-flows")).json()] == [
        saved["name"]
    ]


async def test_a_flow_whose_saved_flow_is_gone_is_saved_as_a_new_one(client, services) -> None:
    preset_id = await save_from_library(client)
    save_a_flow(services, preset_id)
    saved = (await client.get("/api/saved-flows")).json()[0]
    flow = (await client.post(f"/api/saved-flows/{saved['id']}/instantiate", json={})).json()
    await client.delete(f"/api/saved-flows/{saved['id']}")

    assert (await listed(client, "flows", flow["id"]))["saved_flow_id"] is None
    kept = (await client.post(f"/api/flows/{flow['id']}/save")).json()

    assert kept["saved_flow_id"] is not None
    assert len((await client.get("/api/saved-flows")).json()) == 1


async def test_accepting_a_drift_drops_what_jenkins_removed_and_clears_the_flag(
    client, services, jenkins
) -> None:
    preset_id = await save_from_library(client)
    jenkins.definitions[JOB_PATH] = [
        {"name": "CLUSTER", "type": "StringParameterDefinition"},
        {"name": "ENTITLEMENT_MODE", "type": "StringParameterDefinition"},
    ]
    moved = await services.drift.refresh_all()
    assert moved == [preset_id]
    assert (await listed(client, "presets", preset_id))["drift"] is not None

    repaired = (await client.post(f"/api/presets/{preset_id}/repair", json={})).json()

    assert repaired["drift"] is None
    assert "NAMESPACE" not in repaired["params"]
    assert repaired["params"]["ENTITLEMENT_MODE"]["mode"] == "default"


async def test_repairing_per_parameter_keeps_the_value_the_user_chose(
    client, services, jenkins
) -> None:
    preset_id = await save_from_library(client)
    jenkins.definitions[JOB_PATH] = [
        {"name": "CLUSTER", "type": "StringParameterDefinition"},
        {"name": "NAMESPACE", "type": "StringParameterDefinition"},
        {"name": "ENTITLEMENT_MODE", "type": "StringParameterDefinition"},
    ]
    await services.drift.refresh_all()

    repaired = (
        await client.post(
            f"/api/presets/{preset_id}/repair",
            json={
                "decisions": {"ENTITLEMENT_MODE": "fixed"},
                "values": {"ENTITLEMENT_MODE": "STATE"},
            },
        )
    ).json()

    assert repaired["drift"] is None
    assert repaired["params"]["ENTITLEMENT_MODE"] == {
        "mode": "fixed",
        "value": "STATE",
        "last_value": "STATE",
    }
    assert repaired["params"]["CLUSTER"]["value"] == "example-cluster"


async def test_repairing_to_ask_does_not_call_the_jenkins_default_a_last_value(
    client, services, jenkins
) -> None:
    preset_id = await save_from_library(client)
    jenkins.definitions[JOB_PATH] = [
        {"name": "CLUSTER", "type": "StringParameterDefinition"},
        {"name": "NAMESPACE", "type": "StringParameterDefinition"},
        {
            "name": "KONG_VERSION",
            "type": "StringParameterDefinition",
            "defaultParameterValue": {"value": "3.9.0"},
        },
    ]
    await services.drift.refresh_all()

    repaired = (
        await client.post(
            f"/api/presets/{preset_id}/repair",
            json={"decisions": {"KONG_VERSION": "ask"}, "values": {}},
        )
    ).json()

    assert repaired["params"]["KONG_VERSION"] == {"mode": "ask", "value": None, "last_value": None}


async def test_repair_never_keeps_the_active_choices_placeholder_as_the_last_value(
    client, services, jenkins
) -> None:
    preset_id = await save_from_library(client)
    jenkins.definitions[JOB_PATH] = [
        *jenkins.definitions[JOB_PATH],
        {
            "name": "APPLICATIONS",
            "type": "CascadeChoiceParameter",
            "defaultParameterValue": {"value": "error"},
        },
    ]
    await services.drift.refresh_all()

    repaired = (
        await client.post(
            f"/api/presets/{preset_id}/repair", json={"decisions": {"APPLICATIONS": "ask"}}
        )
    ).json()

    assert repaired["params"]["APPLICATIONS"] == {"mode": "ask", "value": None, "last_value": None}


async def test_a_saved_job_never_stores_the_placeholder_as_the_last_value(
    client, services, jenkins
) -> None:
    jenkins.definitions[JOB_PATH] = [
        *jenkins.definitions[JOB_PATH],
        {"name": "APPLICATIONS", "type": "CascadeChoiceParameter"},
    ]
    created = (
        await client.post(
            "/api/presets",
            json={
                "job_path": JOB_PATH,
                "name": "with choices",
                "operation": "Delete environment",
                "params": {"APPLICATIONS": {"mode": "ask", "last_value": "error"}},
            },
        )
    ).json()

    assert created["params"]["APPLICATIONS"]["last_value"] is None


async def test_a_repaired_preset_can_be_dropped_into_a_flow_again(client, services) -> None:
    preset_id = await save_from_library(client)
    services.presets.set_drift(preset_id, Drift(added=(DriftEntry("X"),), seen_at=1))
    assert (
        await client.post("/api/flows", json={"steps": [{"preset_id": preset_id}]})
    ).status_code == 409

    await client.post(f"/api/presets/{preset_id}/repair", json={})

    assert (
        await client.post("/api/flows", json={"steps": [{"preset_id": preset_id}]})
    ).status_code == 201
