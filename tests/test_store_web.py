"""The web tables: presets, saved flows, the Jenkins index, and flows as runs."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from jk.store.flows import FlowStore
from jk.store.jenkins_jobs import JenkinsJobStore
from jk.store.presets import PresetStore
from jk.store.records import (
    KEEP_FINISHED_SECONDS,
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
from jk.store.store import RunStore


def make_preset(presets: PresetStore, **overrides) -> object:
    fields = {
        "name": "snapshot edev rancher",
        "operation": "Create environment",
        "job_path": "folioRancher/manageNamespace/createNamespaceFromBranch",
        "destructive": True,
        "summary_params": ("CLUSTER", "NAMESPACE"),
        "params": {
            "CLUSTER": ParamSetting(ParamMode.FIXED, "example-cluster"),
            "NAMESPACE": ParamSetting(ParamMode.FIXED, "example-ns"),
            "FOLIO_BRANCH": ParamSetting(ParamMode.ASK, None, "example-feature"),
            "PLATFORM": ParamSetting(ParamMode.DEFAULT),
        },
        "definitions": (
            DefinitionSnapshot("CLUSTER", "StringParameterDefinition", "example-default"),
            DefinitionSnapshot("NAMESPACE", "StringParameterDefinition", None),
        ),
    }
    fields.update(overrides)
    return presets.create(**fields)


def append(flows: FlowStore, flow_id: str, preset, **overrides) -> int:
    fields = {
        "preset_id": preset.id,
        "preset_name": preset.name,
        "job_path": preset.job_path,
        "destructive": preset.destructive,
        "summary_params": preset.summary_params,
    }
    fields.update(overrides)
    return flows.append_step(flow_id, **fields)


def test_reopening_an_existing_database_keeps_its_rows(tmp_path: Path) -> None:
    path = tmp_path / "runs.db"
    first = RunStore.open(path)
    make_preset(PresetStore(first))
    first.close()

    second = RunStore.open(path)
    assert len(PresetStore(second).list()) == 1
    second.close()


def test_a_preset_round_trips_every_field(store: RunStore) -> None:
    presets = PresetStore(store)
    saved = make_preset(presets)
    loaded = presets.get(saved.id)

    assert loaded.name == "snapshot edev rancher"
    assert loaded.destructive is True
    assert loaded.params["FOLIO_BRANCH"].mode is ParamMode.ASK
    assert loaded.params["FOLIO_BRANCH"].last_value == "example-feature"
    assert loaded.definitions[0].default == "example-default"
    assert loaded.drift is None


def test_summary_params_are_capped_at_four(store: RunStore) -> None:
    presets = PresetStore(store)
    saved = make_preset(presets, summary_params=("A", "B", "C", "D", "E"))
    assert saved.summary_params == ("A", "B", "C", "D")


def test_sent_values_omit_default_mode_and_take_the_run_value(store: RunStore) -> None:
    presets = PresetStore(store)
    preset = make_preset(presets)

    body = preset.sent_values({"FOLIO_BRANCH": "example-other-feature"})

    assert body == {
        "CLUSTER": "example-cluster",
        "NAMESPACE": "example-ns",
        "FOLIO_BRANCH": "example-other-feature",
    }
    assert "PLATFORM" not in body


def test_an_unanswered_ask_parameter_is_not_sent(store: RunStore) -> None:
    preset = make_preset(PresetStore(store))
    assert "FOLIO_BRANCH" not in preset.sent_values()


def test_drift_round_trips_and_clears(store: RunStore) -> None:
    presets = PresetStore(store)
    preset = make_preset(presets)
    presets.set_drift(
        preset.id,
        Drift(
            added=(DriftEntry("ENTITLEMENT_MODE", "STATE"),),
            removed=(DriftEntry("SKIP_REINDEX", "false"),),
            seen_at=1_700_000_000,
        ),
    )

    drifted = presets.get(preset.id)
    assert drifted.drift is not None
    assert drifted.drift.added[0].name == "ENTITLEMENT_MODE"

    presets.set_drift(preset.id, None)
    assert presets.get(preset.id).drift is None


def test_an_empty_drift_is_stored_as_no_drift(store: RunStore) -> None:
    presets = PresetStore(store)
    preset = make_preset(presets)
    presets.set_drift(preset.id, Drift(seen_at=1))
    assert presets.get(preset.id).drift is None


def test_saving_a_flow_template_twice_updates_it_in_place(store: RunStore) -> None:
    saved_flows = SavedFlowStore(store)
    first = saved_flows.save(name="Rebuild", steps=(SavedFlowStep("a"),))
    again = saved_flows.save(
        name="Rebuild EDEV",
        steps=(SavedFlowStep("a"), SavedFlowStep("b", Condition.ALWAYS)),
        flow_id=first.id,
    )

    assert len(saved_flows.list()) == 1
    assert again.name == "Rebuild EDEV"
    assert again.steps[1].condition is Condition.ALWAYS
    assert again.created_at == first.created_at


def test_the_index_is_replaced_whole_and_searched_by_name_or_path(store: RunStore) -> None:
    jobs = JenkinsJobStore(store)
    jobs.replace_index(
        [
            JenkinsJobRecord(
                job_path="folioRancher/manageNamespace/deleteNamespace",
                name="deleteNamespace",
                folder="folioRancher / manageNamespace",
                url="https://example.invalid/job/x/",
                param_count=8,
            ),
            JenkinsJobRecord(
                job_path="folioTestingTools/runCypressTests",
                name="runCypressTests",
                folder="folioTestingTools",
                url="https://example.invalid/job/y/",
                param_count=21,
            ),
        ]
    )

    assert len(jobs.search()) == 2
    assert [job.name for job in jobs.search("namespace")] == ["deleteNamespace"]
    assert [job.name for job in jobs.search("TestingTools")] == ["runCypressTests"]

    jobs.replace_index([])
    assert jobs.search() == []


def test_a_new_flow_is_a_draft_run_with_no_steps(store: RunStore) -> None:
    flows = FlowStore(store)
    flow_id = flows.create(name="Rebuild from my branch")

    run, meta = flows.get(flow_id)
    assert run.name == "Rebuild from my branch"
    assert run.steps == []
    assert meta.status is FlowStatus.DRAFT
    assert meta.cleared is False


def test_a_new_flow_is_being_edited(store: RunStore) -> None:
    flows = FlowStore(store)

    _, meta = flows.get(flows.create(name="Built by hand"))

    assert meta.editing is True


def test_a_flow_that_came_ready_is_not_being_edited(store: RunStore) -> None:
    flows = FlowStore(store)

    # What comes from a saved flow was built once already.
    _, meta = flows.get(flows.create(name="From a saved flow", editing=False))

    assert meta.editing is False


def test_editing_is_turned_on_and_off_in_place(store: RunStore) -> None:
    flows = FlowStore(store)
    flow_id = flows.create(name="Flow")

    flows.set_editing(flow_id, False)
    assert flows.get(flow_id)[1].editing is False

    flows.set_editing(flow_id, True)
    assert flows.get(flow_id)[1].editing is True


def test_a_flow_that_starts_is_no_longer_being_edited(store: RunStore) -> None:
    flows = FlowStore(store)
    flow_id = flows.create(name="Flow")

    flows.set_status(flow_id, FlowStatus.RUNNING, started=True)

    # Past being built, whatever it was marked as a moment before.
    assert flows.get(flow_id)[1].editing is False


def test_a_run_that_ended_long_ago_leaves_the_board(store: RunStore) -> None:
    flows = FlowStore(store)
    stale = flows.create(name="yesterday")
    flows.set_status(stale, FlowStatus.FINISHED, finished=True)
    pinned = flows.create(name="kept")
    flows.set_status(pinned, FlowStatus.FINISHED, finished=True)
    flows.set_pinned(pinned, True)
    fresh = flows.create(name="just now")
    flows.set_status(fresh, FlowStatus.FINISHED, finished=True)
    long_ago = int(time.time()) - KEEP_FINISHED_SECONDS - 60
    store.connection.execute(
        "UPDATE flow_meta SET finished_at = ? WHERE run_id IN (?, ?)", (long_ago, stale, pinned)
    )
    store.connection.commit()

    assert flows.stale_finished() == [stale]
    flows.set_cleared(stale, True)

    # The name goes with the card: what the board no longer shows holds nothing.
    assert sorted(flows.board_names()) == ["just now", "kept"]


def test_board_names_are_the_ones_the_user_can_see(store: RunStore) -> None:
    flows = FlowStore(store)
    here = flows.create(name="on the board")
    gone = flows.create(name="cleared away")
    flows.set_status(gone, FlowStatus.FINISHED, finished=True)
    flows.set_cleared(gone, True)
    ended = flows.create(name="still showing")
    flows.set_status(ended, FlowStatus.FINISHED, finished=True)

    # A run that ended is still on the board, so its name is still taken; what
    # was cleared off it is History, and History may hold a name twice.
    assert sorted(flows.board_names()) == ["on the board", "still showing"]
    assert flows.board_names(excluding=here) == ["still showing"]


def test_the_active_flows_are_every_flow_that_has_not_ended(store: RunStore) -> None:
    flows = FlowStore(store)
    draft = flows.create(name="draft")
    running = flows.create(name="running")
    flows.set_status(running, FlowStatus.RUNNING, started=True)
    done = flows.create(name="done")
    flows.set_status(done, FlowStatus.FINISHED, finished=True)

    assert sorted(flows.list(active=True, include_cleared=True)) == sorted([draft, running])


def test_appending_steps_numbers_them_from_zero(store: RunStore) -> None:
    presets, flows = PresetStore(store), FlowStore(store)
    preset = make_preset(presets)
    flow_id = flows.create(name="Flow")

    assert append(flows, flow_id, preset) == 0
    assert append(flows, flow_id, preset, condition=Condition.ALWAYS) == 1

    run, meta = flows.get(flow_id)
    assert [step.position for step in run.steps] == [0, 1]
    assert meta.steps[1].condition is Condition.ALWAYS
    assert meta.steps[0].preset_id == preset.id


def test_a_step_snapshots_the_preset_so_history_survives_a_rename(store: RunStore) -> None:
    presets, flows = PresetStore(store), FlowStore(store)
    preset = make_preset(presets)
    flow_id = flows.create(name="Flow")
    append(flows, flow_id, preset)

    presets.update(preset.id, name="a different name")

    run, _ = flows.get(flow_id)
    assert run.steps[0].job_name == "snapshot edev rancher"


def test_removing_a_planned_step_closes_the_gap(store: RunStore) -> None:
    presets, flows = PresetStore(store), FlowStore(store)
    preset = make_preset(presets)
    flow_id = flows.create(name="Flow")
    for index in range(3):
        append(flows, flow_id, preset, preset_name=f"step {index}")

    assert flows.remove_step(flow_id, 1) is True

    run, meta = flows.get(flow_id)
    assert [step.position for step in run.steps] == [0, 1]
    assert [step.job_name for step in run.steps] == ["step 0", "step 2"]
    assert sorted(meta.steps) == [0, 1]


@pytest.mark.parametrize(
    ("position", "target", "order"),
    [
        (0, 1, ["step 1", "step 0", "step 2", "step 3"]),
        (0, 2, ["step 1", "step 2", "step 0", "step 3"]),
        (1, 3, ["step 0", "step 2", "step 3", "step 1"]),
        (3, 1, ["step 0", "step 3", "step 1", "step 2"]),
        (2, 0, ["step 2", "step 0", "step 1", "step 3"]),
    ],
)
def test_a_moved_step_lands_on_the_place_it_was_moved_to(
    store: RunStore, position: int, target: int, order: list[str]
) -> None:
    presets, flows = PresetStore(store), FlowStore(store)
    preset = make_preset(presets)
    flow_id = flows.create(name="Flow")
    for index in range(4):
        append(flows, flow_id, preset, preset_name=f"step {index}")

    assert flows.move_step(flow_id, position, target) is True

    run, _ = flows.get(flow_id)
    assert [step.job_name for step in run.steps] == order


def test_frozen_parameters_are_the_stored_submission_body(store: RunStore) -> None:
    presets, flows = PresetStore(store), FlowStore(store)
    preset = make_preset(presets)
    flow_id = flows.create(name="Flow")
    append(flows, flow_id, preset)

    body = preset.sent_values({"FOLIO_BRANCH": "example-feature"})
    assert flows.freeze_step_params(flow_id, 0, body) is True

    assert store.get_step_inputs(flow_id, 0) == body
    _, meta = flows.get(flow_id)
    assert meta.steps[0].frozen is True


def test_a_started_step_can_no_longer_be_reordered_or_refrozen(store: RunStore) -> None:
    presets, flows = PresetStore(store), FlowStore(store)
    preset = make_preset(presets, destructive=False)
    flow_id = flows.create(name="Flow")
    append(flows, flow_id, preset)
    flows.set_status(flow_id, FlowStatus.RUNNING)
    assert store.claim_submit_pending(flow_id, 0, next_build_number=10)

    assert flows.freeze_step_params(flow_id, 0, {"X": "1"}) is False
    assert flows.remove_step(flow_id, 0) is False
    assert flows.update_step(flow_id, 0, condition=Condition.ALWAYS) is False


def test_status_transitions_record_their_timestamps(store: RunStore) -> None:
    flows = FlowStore(store)
    flow_id = flows.create(name="Flow")

    flows.set_status(flow_id, FlowStatus.RUNNING, started=True)
    _, running = flows.get(flow_id)
    assert running.status is FlowStatus.RUNNING
    assert running.started_at is not None

    flows.set_status(flow_id, FlowStatus.FAILED, failed_at_position=1, finished=True)
    _, failed = flows.get(flow_id)
    assert failed.failed_at_position == 1
    assert failed.finished_at is not None

    flows.set_status(flow_id, FlowStatus.RUNNING, clear_failed=True)
    _, resumed = flows.get(flow_id)
    assert resumed.failed_at_position is None


def test_listing_separates_active_from_finished_and_hides_cleared(store: RunStore) -> None:
    flows = FlowStore(store)
    active = flows.create(name="active")
    finished = flows.create(name="finished")
    flows.set_status(finished, FlowStatus.FINISHED, finished=True)

    assert flows.list(active=True) == [active]
    assert flows.list(active=False) == [finished]

    flows.set_cleared(finished, True)
    assert flows.list(active=False) == []
    assert flows.list(active=False, include_cleared=True) == [finished]


def test_deleting_a_flow_removes_its_steps_and_meta(store: RunStore) -> None:
    presets, flows = PresetStore(store), FlowStore(store)
    preset = make_preset(presets)
    flow_id = flows.create(name="Flow")
    append(flows, flow_id, preset)

    assert flows.delete(flow_id) is True
    assert flows.find(flow_id) is None
    remaining = store.connection.execute(
        "SELECT COUNT(*) AS total FROM flow_step_meta WHERE run_id = ?", (flow_id,)
    ).fetchone()
    assert remaining["total"] == 0


def test_a_preset_reports_how_many_steps_still_point_at_it(store: RunStore) -> None:
    presets, flows = PresetStore(store), FlowStore(store)
    preset = make_preset(presets, destructive=False)
    flow_id = flows.create(name="Flow")
    append(flows, flow_id, preset)

    # A planned step is already a reference: deleting the preset under it
    # would leave the flow pointing at nothing.
    assert len(presets.used_by(preset.id)) == 1

    flows.set_status(flow_id, FlowStatus.RUNNING)
    assert store.claim_submit_pending(flow_id, 0, next_build_number=1)
    assert len(presets.used_by(preset.id)) == 1

    store.mark_queued(flow_id, 0, queue_url="/queue/item/1/", note=None)
    store.mark_running(flow_id, 0, build_number=1, build_url="/job/x/1/", queue_id=1)
    store.mark_final(flow_id, 0, result="SUCCESS")
    assert presets.used_by(preset.id) == []


def test_a_step_its_flow_will_never_reach_does_not_hold_the_preset(store: RunStore) -> None:
    presets, flows = PresetStore(store), FlowStore(store)
    preset = make_preset(presets, destructive=False)
    ended, stopped, cleared = (flows.create(name=name) for name in ("Ended", "Stopped", "Cleared"))
    for flow_id in (ended, stopped, cleared):
        append(flows, flow_id, preset)

    # A step skipped in a flow that finished is still `prepared`, but nothing will run it.
    flows.set_status(ended, FlowStatus.FINISHED, finished=True)
    flows.set_status(stopped, FlowStatus.STOPPED)
    flows.set_cleared(cleared, True)

    assert [name for _, name, _ in presets.used_by(preset.id)] == ["Stopped"]
