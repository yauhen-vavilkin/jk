"""Drift: when Jenkins changes a job a saved job depends on."""

from __future__ import annotations

import asyncio
import sqlite3

import httpx
import pytest

from jk.engine.drift import DriftWatcher, diff, snapshot_of
from jk.jenkins.models import ParameterDefinition
from jk.jenkins.read import JenkinsReader
from jk.store.presets import PresetStore
from jk.store.records import DefinitionSnapshot, ParamMode, ParamSetting

JOB_PATH = "folder/createNamespaceFromBranch"


@pytest.fixture
def presets(store) -> PresetStore:
    return PresetStore(store)


def make_preset(presets: PresetStore, **overrides):
    fields = {
        "name": "saved job",
        "operation": "Create environment",
        "job_path": JOB_PATH,
        "params": {
            "CLUSTER": ParamSetting(ParamMode.FIXED, "example-cluster"),
            "SKIP_REINDEX": ParamSetting(ParamMode.FIXED, "false"),
            "PLATFORM": ParamSetting(ParamMode.DEFAULT),
        },
        "definitions": (
            DefinitionSnapshot("CLUSTER", "StringParameterDefinition", "example-default"),
            DefinitionSnapshot("SKIP_REINDEX", "BooleanParameterDefinition", "false"),
            DefinitionSnapshot("PLATFORM", "StringParameterDefinition", "EUREKA"),
        ),
    }
    fields.update(overrides)
    return presets.create(**fields)


def live(*definitions: DefinitionSnapshot) -> tuple[DefinitionSnapshot, ...]:
    return definitions


def test_an_unchanged_job_has_no_drift(presets: PresetStore) -> None:
    preset = make_preset(presets)
    assert diff(preset, preset.definitions) is None


def test_a_new_parameter_is_added_with_its_jenkins_default(presets: PresetStore) -> None:
    preset = make_preset(presets)
    found = diff(
        preset,
        live(
            *preset.definitions,
            DefinitionSnapshot("ENTITLEMENT_MODE", "ChoiceParameterDefinition", "STATE"),
        ),
    )
    assert found is not None
    assert [(entry.name, entry.detail) for entry in found.added] == [("ENTITLEMENT_MODE", "STATE")]
    assert found.removed == ()


def test_a_removed_parameter_remembers_the_value_the_user_had(presets: PresetStore) -> None:
    preset = make_preset(presets)
    found = diff(preset, live(preset.definitions[0], preset.definitions[2]))
    assert found is not None
    assert [(entry.name, entry.detail) for entry in found.removed] == [("SKIP_REINDEX", "false")]


def test_a_fixed_value_that_is_no_longer_an_allowed_choice_is_a_change(
    presets: PresetStore,
) -> None:
    preset = make_preset(
        presets,
        params={"CLUSTER": ParamSetting(ParamMode.FIXED, "example-cluster")},
        definitions=(
            DefinitionSnapshot(
                "CLUSTER",
                "ChoiceParameterDefinition",
                "example-default",
                ["example-default", "example-cluster"],
            ),
        ),
    )
    found = diff(
        preset,
        live(
            DefinitionSnapshot(
                "CLUSTER",
                "ChoiceParameterDefinition",
                "example-default",
                ["example-default", "example-performance"],
            )
        ),
    )
    assert found is not None
    assert found.changed[0].name == "CLUSTER"


def test_a_narrowed_choice_list_does_not_disturb_a_default_mode_parameter(
    presets: PresetStore,
) -> None:
    preset = make_preset(
        presets,
        params={"CLUSTER": ParamSetting(ParamMode.DEFAULT)},
        definitions=(
            DefinitionSnapshot(
                "CLUSTER", "ChoiceParameterDefinition", "example-default", ["example-default"]
            ),
        ),
    )
    found = diff(
        preset,
        live(
            DefinitionSnapshot("CLUSTER", "ChoiceParameterDefinition", "example-performance", ["x"])
        ),
    )
    assert found is None


def test_a_changed_type_is_a_change(presets: PresetStore) -> None:
    preset = make_preset(
        presets,
        params={"CLUSTER": ParamSetting(ParamMode.FIXED, "example-cluster")},
        definitions=(DefinitionSnapshot("CLUSTER", "StringParameterDefinition", None),),
    )
    found = diff(preset, live(DefinitionSnapshot("CLUSTER", "ChoiceParameterDefinition", None)))
    assert found is not None
    assert "type changed" in (found.changed[0].detail or "")


def reader_for(definitions: dict, *, status: int = 200) -> JenkinsReader:
    def handler(request: httpx.Request) -> httpx.Response:
        if status != 200:
            return httpx.Response(status, text="no")
        return httpx.Response(
            200,
            json={"property": [{"parameterDefinitions": definitions}]},
        )

    return JenkinsReader(
        httpx.AsyncClient(
            base_url="https://jenkins.invalid", transport=httpx.MockTransport(handler)
        )
    )


async def test_the_watcher_marks_and_then_clears_drift(presets: PresetStore) -> None:
    preset = make_preset(presets)

    changed = reader_for(
        [
            {"name": "CLUSTER", "type": "StringParameterDefinition"},
            {"name": "PLATFORM", "type": "StringParameterDefinition"},
        ]
    )
    assert await DriftWatcher(presets, changed).refresh_all() == [preset.id]
    assert presets.get(preset.id).drift is not None

    unchanged = reader_for(
        [
            {
                "name": "CLUSTER",
                "type": "StringParameterDefinition",
                "defaultParameterValue": {"value": "example-default"},
            },
            {
                "name": "SKIP_REINDEX",
                "type": "BooleanParameterDefinition",
                "defaultParameterValue": {"value": False},
            },
            {
                "name": "PLATFORM",
                "type": "StringParameterDefinition",
                "defaultParameterValue": {"value": "EUREKA"},
            },
        ]
    )
    assert await DriftWatcher(presets, unchanged).refresh_all() == [preset.id]
    assert presets.get(preset.id).drift is None


async def test_an_unreachable_jenkins_changes_nothing(presets: PresetStore) -> None:
    preset = make_preset(presets)
    assert await DriftWatcher(presets, reader_for([], status=503)).refresh_all() == []
    assert presets.get(preset.id).drift is None


async def test_a_preset_with_no_snapshot_is_left_for_the_user_to_read(
    presets: PresetStore,
) -> None:
    preset = make_preset(presets, definitions=())
    watcher = DriftWatcher(presets, reader_for([{"name": "CLUSTER", "type": "String"}]))
    assert await watcher.refresh_all() == []
    assert presets.get(preset.id).definitions == ()


def test_the_snapshot_keeps_what_jenkins_answered() -> None:
    taken = snapshot_of(
        {
            "CLUSTER": ParameterDefinition(
                "CLUSTER", "ChoiceParameterDefinition", "example-default", ["example-default"]
            )
        }
    )
    assert taken == (
        DefinitionSnapshot(
            "CLUSTER", "ChoiceParameterDefinition", "example-default", ["example-default"]
        ),
    )


async def test_the_background_check_reports_each_saved_job_it_marked(presets) -> None:
    """An open panel hears that Jenkins changed a saved job without asking."""
    preset = make_preset(presets)
    watcher = DriftWatcher(presets, reader_for([{"name": "CLUSTER", "type": "String"}]))
    moved: asyncio.Queue[str] = asyncio.Queue()

    loop = asyncio.create_task(watcher.run_forever(moved.put_nowait, interval=3600))
    heard = await asyncio.wait_for(moved.get(), 3)
    loop.cancel()
    with pytest.raises(asyncio.CancelledError):
        await loop

    assert heard == preset.id


async def test_the_background_checks_outlive_a_turn_that_fails(presets, monkeypatch) -> None:
    """A database still busy after its wait costs one turn, not the checks."""
    watcher = DriftWatcher(presets, reader_for({}))
    turns: list[int] = []
    second = asyncio.Event()

    async def busy_the_first_time() -> list[str]:
        turns.append(len(turns))
        if len(turns) == 1:
            raise sqlite3.OperationalError("database is locked")
        second.set()
        return []

    monkeypatch.setattr(watcher, "refresh_all", busy_the_first_time)

    loop = asyncio.create_task(watcher.run_forever(lambda _preset_id: None, interval=0.01))
    await asyncio.wait_for(second.wait(), 3)
    loop.cancel()
    with pytest.raises(asyncio.CancelledError):
        await loop

    assert len(turns) >= 2
