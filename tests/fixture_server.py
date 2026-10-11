"""Serve the panel with fixture data, for looking at it.

Not a test: it is the harness for looking at the panel without a controller. It builds a
throwaway database in a temporary directory and answers Jenkins from
`tests.webapp.FakeJenkins`, so nothing here can reach the real controller.
All targets and working branches below are fictional demonstration values.

    uv run python -m tests.fixture_server --port 8799
"""

from __future__ import annotations

import argparse
import tempfile
import time
from pathlib import Path

import uvicorn

from jk.engine.messages import CONNECTION_FAILED_WHILE_SENDING
from jk.store.flows import FlowStore
from jk.store.presets import PresetStore
from jk.store.records import (
    Condition,
    DefinitionSnapshot,
    Drift,
    DriftEntry,
    FlowStatus,
    JenkinsJobRecord,
    ParamMode,
    ParamSetting,
    SavedFlowStep,
)
from jk.store.saved_flows import SavedFlowStore
from jk.web.app import create_app
from tests.webapp import BASE_URL, FakeJenkins, build

CREATE = "folioRancher/manageNamespace/createNamespaceFromBranch"
DELETE = "folioRancher/manageNamespace/deleteNamespace"
CYPRESS = "folioTestingTools/runCypressTests"


def string(name: str, default: str | None = None) -> dict:
    entry: dict = {"name": name, "type": "StringParameterDefinition"}
    if default is not None:
        entry["defaultParameterValue"] = {"value": default}
    return entry


DEFINITIONS = {
    CREATE: [
        string("CLUSTER", "example-default"),
        string("NAMESPACE"),
        string("FOLIO_BRANCH", "snapshot"),
        string("PLATFORM_BRANCH", "snapshot"),
        string("CONFIG_TYPE", "testing"),
        string("PLATFORM", "EUREKA"),
        string(
            "APPLICATIONS",
            "app-platform-complete,app-platform-minimal,app-acquisitions,app-agreements,"
            "app-authority-records,app-bulk-edit,app-consortia,app-dashboard",
        ),
        string("ENTITLEMENT_MODE", "STATE"),
        string("KONG_VERSION", "3.9.0"),
        string("OKAPI_VERSION", "7.2.0-SNAPSHOT.2080"),
        string("LOAD_REFERENCE", "true"),
        string("LOAD_SAMPLE", "true"),
        string("BUILD_UI", "true"),
    ],
    DELETE: [
        string("CLUSTER", "example-shared"),
        string("NAMESPACE"),
        string("POSTGRESQL", "built-in"),
        string("KAFKA", "built-in"),
        string("OPENSEARCH", "built-in"),
        string("S3", "built-in"),
    ],
    CYPRESS: [
        string("TENANT_ID", "diku"),
        string("NUMBER_OF_WORKERS", "1"),
        string("CYPRESS_BRANCH", "master"),
        {"name": "ADMIN_PASSWORD", "type": "PasswordParameterDefinition"},
    ],
}


def fixed(value: str) -> ParamSetting:
    return ParamSetting(ParamMode.FIXED, value, value)


def ask(last: str) -> ParamSetting:
    return ParamSetting(ParamMode.ASK, None, last)


def with_defaults(job_path: str, chosen: dict[str, ParamSetting]) -> dict[str, ParamSetting]:
    """What the user chose, plus every other parameter left to Jenkins."""
    params = dict(chosen)
    for definition in definitions_of(job_path):
        params.setdefault(definition.name, ParamSetting(ParamMode.DEFAULT))
    return params


def definitions_of(job_path: str) -> tuple[DefinitionSnapshot, ...]:
    return tuple(
        DefinitionSnapshot(
            item["name"],
            item["type"],
            (item.get("defaultParameterValue") or {}).get("value"),
        )
        for item in DEFINITIONS[job_path]
    )


def seed(services) -> None:
    presets: PresetStore = services.presets
    flows: FlowStore = services.flows
    saved_flows: SavedFlowStore = services.saved_flows
    store = services.store
    now = int(time.time())

    snapshot = presets.create(
        preset_id="example-development",
        name="Example development environment",
        operation="Create environment",
        job_path=CREATE,
        destructive=True,
        summary_params=("CLUSTER", "NAMESPACE", "FOLIO_BRANCH", "PLATFORM_BRANCH"),
        params=with_defaults(
            CREATE,
            {
                "CLUSTER": fixed("example-cluster"),
                "NAMESPACE": fixed("example-ns"),
                "FOLIO_BRANCH": ask("example-feature"),
                "PLATFORM_BRANCH": fixed("example-feature"),
                "CONFIG_TYPE": fixed("development"),
            },
        ),
        definitions=definitions_of(CREATE),
    )
    trillium = presets.create(
        preset_id="example-release",
        name="Example release environment",
        operation="Create environment",
        job_path=CREATE,
        destructive=True,
        summary_params=("CLUSTER", "NAMESPACE", "PLATFORM_BRANCH"),
        params=with_defaults(
            CREATE,
            {
                "CLUSTER": fixed("example-cluster"),
                "NAMESPACE": fixed("example-ns"),
                "PLATFORM_BRANCH": fixed("example-release"),
                "CONFIG_TYPE": fixed("development"),
                "FOLIO_BRANCH": ask("example-feature"),
            },
        ),
        definitions=definitions_of(CREATE),
    )
    presets.set_drift(
        trillium.id,
        Drift(
            added=(DriftEntry("ENTITLEMENT_MODE", "STATE"), DriftEntry("KONG_VERSION", "3.9.0")),
            removed=(DriftEntry("SKIP_REINDEX", "false"),),
            seen_at=now,
        ),
    )
    remove = presets.create(
        preset_id="delete-example-environment",
        name="Delete Example environment",
        operation="Delete environment",
        job_path=DELETE,
        destructive=True,
        summary_params=("CLUSTER", "NAMESPACE"),
        params=with_defaults(
            DELETE, {"CLUSTER": fixed("example-cluster"), "NAMESPACE": fixed("example-ns")}
        ),
        definitions=definitions_of(DELETE),
    )
    four = presets.create(
        preset_id="cypress-4-workers",
        name="Example Cypress / 4 workers",
        operation="Run Cypress tests",
        job_path=CYPRESS,
        summary_params=("TENANT_ID", "NUMBER_OF_WORKERS"),
        params=with_defaults(
            CYPRESS, {"TENANT_ID": fixed("consortium"), "NUMBER_OF_WORKERS": fixed("4")}
        ),
        definitions=definitions_of(CYPRESS),
    )
    diku = presets.create(
        preset_id="cypress-diku-trillium",
        name="Example Cypress / diku trillium",
        operation="Run Cypress tests",
        job_path=CYPRESS,
        summary_params=("TENANT_ID", "NUMBER_OF_WORKERS", "CYPRESS_BRANCH"),
        params=with_defaults(
            CYPRESS,
            {
                "TENANT_ID": fixed("diku"),
                "NUMBER_OF_WORKERS": fixed("1"),
                "CYPRESS_BRANCH": fixed("trillium"),
            },
        ),
        definitions=definitions_of(CYPRESS),
    )
    two = presets.create(
        preset_id="cypress-example-snapshot",
        name="example-snapshot Cypress / 2 worker",
        operation="Run Cypress tests",
        job_path=CYPRESS,
        summary_params=("TENANT_ID", "NUMBER_OF_WORKERS"),
        params=with_defaults(
            CYPRESS, {"TENANT_ID": fixed("diku"), "NUMBER_OF_WORKERS": fixed("2")}
        ),
        definitions=definitions_of(CYPRESS),
    )

    saved_flows.save(
        flow_id="rebuild-trillium",
        name="Rebuild example to Trillium and run Cypress",
        steps=(SavedFlowStep(remove.id), SavedFlowStep(trillium.id), SavedFlowStep(diku.id)),
    )
    saved_flows.save(
        flow_id="rebuild-branch",
        name="Rebuild Example from a branch",
        steps=(SavedFlowStep(remove.id), SavedFlowStep(snapshot.id), SavedFlowStep(two.id)),
    )

    def add(flow_id: str, preset, condition: Condition = Condition.UNLESS_FAILURE, **extra) -> int:
        return flows.append_step(
            flow_id,
            preset_id=preset.id,
            preset_name=preset.name,
            job_path=preset.job_path,
            destructive=preset.destructive,
            summary_params=preset.summary_params,
            condition=condition,
            **extra,
        )

    # The board shows flows in the order they were made, so each one is made in
    # its own hour: the oldest at the top, the draft last.
    made = iter(now - hours * 3600 for hours in (5, 4, 3, 2, 1))

    # A flow that is going: one SUCCESS, one UNSTABLE, one running, two waiting.
    running = flows.create(name="Rebuild Example from a branch", created_at=next(made))
    add(running, remove)
    add(running, snapshot, Condition.AFTER_SUCCESS, run_values={"FOLIO_BRANCH": "example-feature"})
    add(running, two)
    add(running, four, Condition.AFTER_SUCCESS)
    add(running, remove, added_while_running=True)
    flows.set_status(running, FlowStatus.RUNNING, started=True)
    _finish(
        store,
        flows,
        running,
        0,
        "SUCCESS",
        102,
        2_472_000,
        {"CLUSTER": "example-cluster", "NAMESPACE": "example-ns"},
    )
    _finish(
        store,
        flows,
        running,
        1,
        "UNSTABLE",
        204,
        3_483_000,
        {
            "CLUSTER": "example-cluster",
            "NAMESPACE": "example-ns",
            "FOLIO_BRANCH": "example-feature",
            "PLATFORM_BRANCH": "example-feature",
        },
    )
    _start(
        store,
        flows,
        running,
        2,
        205,
        1_320_000,
        2_760_000,
        {"TENANT_ID": "diku", "NUMBER_OF_WORKERS": "2"},
    )

    # A flow that ended well: it takes nothing more, and can be run again.
    done = flows.create(name="Nightly Cypress on diku", created_at=next(made))
    add(done, snapshot, run_values={"FOLIO_BRANCH": "example-feature"})
    add(done, two, Condition.AFTER_SUCCESS)
    flows.set_status(done, FlowStatus.RUNNING, started=True)
    _finish(
        store,
        flows,
        done,
        0,
        "SUCCESS",
        202,
        3_120_000,
        {
            "CLUSTER": "example-cluster",
            "NAMESPACE": "example-ns",
            "FOLIO_BRANCH": "example-feature",
        },
    )
    _finish(
        store,
        flows,
        done,
        1,
        "SUCCESS",
        203,
        2_640_000,
        {"TENANT_ID": "diku", "NUMBER_OF_WORKERS": "2"},
    )
    flows.set_status(done, FlowStatus.FINISHED, finished=True)

    # A flow JK cannot speak for: the connection dropped while the request was
    # going out, so it waits for a human.
    attention = flows.create(name="Rebuild Example from a branch", created_at=next(made))
    add(attention, remove)
    add(attention, snapshot, run_values={"FOLIO_BRANCH": "example-feature"})
    add(attention, two)
    # A step is claimed only while its flow runs; the flow waits for a human after.
    flows.set_status(attention, FlowStatus.RUNNING, started=True)
    _finish(
        store,
        flows,
        attention,
        0,
        "SUCCESS",
        101,
        2_472_000,
        {"CLUSTER": "example-cluster", "NAMESPACE": "example-ns"},
    )
    flows.freeze_step_params(
        attention,
        1,
        {
            "CLUSTER": "example-cluster",
            "NAMESPACE": "example-ns",
            "FOLIO_BRANCH": "example-feature",
        },
    )
    store.claim_submit_pending(attention, 1, next_build_number=102)
    store.mark_needs_attention(
        attention,
        1,
        kind="ambiguous_submission",
        message=f"{CONNECTION_FAILED_WHILE_SENDING} (ReadTimeout: timed out).",
    )
    flows.set_status(attention, FlowStatus.NEEDS_ATTENTION)

    # A draft being built, with a destructive step and a value asked at launch.
    draft = flows.create(name="Rebuild from an example branch and test", created_at=next(made))
    add(draft, snapshot, run_values={"FOLIO_BRANCH": "example-feature"})
    add(draft, diku, Condition.AFTER_SUCCESS)

    # One that is built and waiting, so the board shows both sides of the pencil.
    ready = flows.create(name="Nightly Cypress on trillium", created_at=next(made), editing=False)
    add(ready, trillium)
    add(ready, four, Condition.AFTER_SUCCESS)

    jobs = [
        JenkinsJobRecord(
            job_path=path,
            name=path.rsplit("/", maxsplit=1)[-1],
            folder=" / ".join(path.split("/")[:-1]),
            url=f"{BASE_URL}/job/x/",
            param_count=len(DEFINITIONS[path]),
            # A made-up last success, so the board has an estimate to show.
            typical_ms=(7 + 11 * index) * 60_000,
        )
        for index, path in enumerate(DEFINITIONS)
    ]
    services.jenkins_jobs.replace_index(jobs)


def _finish(store, flows, flow_id, position, result, build_number, duration_ms, body) -> None:
    flows.freeze_step_params(flow_id, position, body)
    store.claim_submit_pending(flow_id, position, next_build_number=build_number)
    store.mark_queued(flow_id, position, queue_url=f"/queue/item/{build_number}/", note=None)
    store.mark_running(
        flow_id,
        position,
        build_number=build_number,
        build_url=f"{BASE_URL}/job/x/{build_number}/",
        queue_id=build_number,
    )
    store.update_build_timing(
        flow_id,
        position,
        started_at_ms=(int(time.time()) - 7200) * 1000,
        duration_ms=duration_ms,
        estimated_duration_ms=duration_ms,
    )
    store.mark_final(flow_id, position, result=result)


def _start(store, flows, flow_id, position, build_number, elapsed_ms, estimate_ms, body) -> None:
    flows.freeze_step_params(flow_id, position, body)
    store.claim_submit_pending(flow_id, position, next_build_number=build_number)
    store.mark_queued(flow_id, position, queue_url=f"/queue/item/{build_number}/", note=None)
    store.mark_running(
        flow_id,
        position,
        build_number=build_number,
        build_url=f"{BASE_URL}/job/x/{build_number}/",
        queue_id=build_number,
    )
    store.update_build_timing(
        flow_id,
        position,
        started_at_ms=int(time.time() * 1000) - elapsed_ms,
        duration_ms=0,
        estimated_duration_ms=estimate_ms,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the panel with fixture data.")
    parser.add_argument("--port", type=int, default=8799)
    parser.add_argument("--dist", default="", help="serve a built web/dist as well")
    arguments = parser.parse_args()

    directory = Path(tempfile.mkdtemp(prefix="jk-fixtures-"))
    jenkins = FakeJenkins(
        definitions=DEFINITIONS,
        recent={
            101: {
                "CLUSTER": "example-cluster",
                "NAMESPACE": "example-ns",
                "FOLIO_BRANCH": "example-feature",
            },
            102: {
                "CLUSTER": "example-cluster",
                "NAMESPACE": "example-ns",
                "FOLIO_BRANCH": "example-feature",
            },
        },
    )
    services = build(directory, jenkins)
    seed(services)
    app = create_app(
        services,
        dist=Path(arguments.dist) if arguments.dist else None,
        serve_static=bool(arguments.dist),
        background=False,
    )
    print(f"fixture panel on http://127.0.0.1:{arguments.port} (state in {directory})")
    uvicorn.run(app, host="127.0.0.1", port=arguments.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
