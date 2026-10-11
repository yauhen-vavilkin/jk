"""Turn the JSON columns of the web tables into records and back.

One place decides how a stored shape is spelled, so what the editor writes is
what the panel reads.
"""

from __future__ import annotations

import json
from typing import Any

from jk.store.records import (
    Condition,
    DefinitionSnapshot,
    Drift,
    DriftEntry,
    ParamMode,
    ParamSetting,
    SavedFlowStep,
)


def dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _load(raw: str | None, fallback: Any) -> Any:
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except ValueError:
        return fallback


def string_list(raw: str | None) -> tuple[str, ...]:
    loaded = _load(raw, [])
    return tuple(str(item) for item in loaded if isinstance(item, str))


def string_map(raw: str | None) -> dict[str, str]:
    loaded = _load(raw, {})
    if not isinstance(loaded, dict):
        return {}
    return {str(key): str(item) for key, item in loaded.items()}


def params_from_json(raw: str | None) -> dict[str, ParamSetting]:
    loaded = _load(raw, {})
    if not isinstance(loaded, dict):
        return {}
    settings: dict[str, ParamSetting] = {}
    for name, entry in loaded.items():
        if not isinstance(entry, dict):
            continue
        mode = entry.get("mode", ParamMode.DEFAULT.value)
        if mode not in tuple(ParamMode):
            mode = ParamMode.DEFAULT.value
        settings[str(name)] = ParamSetting(
            mode=ParamMode(mode),
            value=_optional_str(entry.get("value")),
            last_value=_optional_str(entry.get("last_value")),
        )
    return settings


def params_to_json(params: dict[str, ParamSetting]) -> str:
    return dump(
        {
            name: {
                "mode": setting.mode.value,
                "value": setting.value,
                "last_value": setting.last_value,
            }
            for name, setting in params.items()
        }
    )


def definitions_from_json(raw: str | None) -> tuple[DefinitionSnapshot, ...]:
    loaded = _load(raw, [])
    if not isinstance(loaded, list):
        return ()
    found: list[DefinitionSnapshot] = []
    for entry in loaded:
        if not isinstance(entry, dict) or not entry.get("name"):
            continue
        choices = entry.get("choices")
        found.append(
            DefinitionSnapshot(
                name=str(entry["name"]),
                type=str(entry.get("type", "")),
                default=_optional_str(entry.get("default")),
                choices=[str(item) for item in choices] if isinstance(choices, list) else None,
            )
        )
    return tuple(found)


def definitions_to_json(definitions: tuple[DefinitionSnapshot, ...]) -> str:
    return dump(
        [
            {
                "name": item.name,
                "type": item.type,
                "default": item.default,
                "choices": item.choices,
            }
            for item in definitions
        ]
    )


def drift_from_json(raw: str | None) -> Drift | None:
    loaded = _load(raw, None)
    if not isinstance(loaded, dict):
        return None
    drift = Drift(
        added=_entries(loaded.get("added")),
        removed=_entries(loaded.get("removed")),
        changed=_entries(loaded.get("changed")),
        seen_at=int(loaded.get("seen_at") or 0),
    )
    return None if drift.is_empty else drift


def drift_to_json(drift: Drift | None) -> str | None:
    if drift is None or drift.is_empty:
        return None
    return dump(
        {
            "added": [{"name": item.name, "detail": item.detail} for item in drift.added],
            "removed": [{"name": item.name, "detail": item.detail} for item in drift.removed],
            "changed": [{"name": item.name, "detail": item.detail} for item in drift.changed],
            "seen_at": drift.seen_at,
        }
    )


def saved_flow_steps_from_json(raw: str | None) -> tuple[SavedFlowStep, ...]:
    loaded = _load(raw, [])
    if not isinstance(loaded, list):
        return ()
    steps: list[SavedFlowStep] = []
    for entry in loaded:
        if not isinstance(entry, dict) or not entry.get("preset_id"):
            continue
        condition = entry.get("condition", Condition.UNLESS_FAILURE.value)
        if condition not in tuple(Condition):
            condition = Condition.UNLESS_FAILURE.value
        values = entry.get("run_values")
        steps.append(
            SavedFlowStep(
                preset_id=str(entry["preset_id"]),
                condition=Condition(condition),
                run_values=(
                    {str(key): str(item) for key, item in values.items()}
                    if isinstance(values, dict)
                    else {}
                ),
            )
        )
    return tuple(steps)


def saved_flow_steps_to_json(steps: tuple[SavedFlowStep, ...]) -> str:
    return dump(
        [
            {
                "preset_id": step.preset_id,
                "condition": step.condition.value,
                "run_values": dict(step.run_values),
            }
            for step in steps
        ]
    )


def _entries(raw: Any) -> tuple[DriftEntry, ...]:
    if not isinstance(raw, list):
        return ()
    return tuple(
        DriftEntry(name=str(item["name"]), detail=_optional_str(item.get("detail")))
        for item in raw
        if isinstance(item, dict) and item.get("name")
    )


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)
