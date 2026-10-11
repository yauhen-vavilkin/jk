"""Notice when Jenkins changes a job a saved job depends on.

A saved job holds the values the user chose and a snapshot of the definitions
those values were chosen against. When the two stop agreeing, the saved job is
not run until a human has looked: that is the whole point of the check, so this
module only ever reads and never repairs anything by itself.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Mapping
from contextlib import suppress

from jk.engine.runner import rest_path_of
from jk.errors import JenkinsAuthError, JenkinsUnavailable, TargetNotFound
from jk.jenkins.models import ParameterDefinition
from jk.jenkins.read import JenkinsReader
from jk.store.presets import PresetStore
from jk.store.records import (
    DefinitionSnapshot,
    Drift,
    DriftEntry,
    ParamMode,
    Preset,
)

#: How often the watcher looks by itself.
INTERVAL_SECONDS = 600.0


def snapshot_of(definitions: Mapping[str, ParameterDefinition]) -> tuple[DefinitionSnapshot, ...]:
    """The stored shape of what Jenkins answered, in Jenkins' own order."""
    return tuple(
        DefinitionSnapshot(
            name=definition.name,
            type=definition.type,
            default=definition.default,
            choices=list(definition.choices) if definition.choices else None,
        )
        for definition in definitions.values()
    )


def diff(preset: Preset, live: tuple[DefinitionSnapshot, ...]) -> Drift | None:
    """What changed between the preset's snapshot and what Jenkins says now."""
    known = {item.name: item for item in preset.definitions}
    current = {item.name: item for item in live}

    added = tuple(
        DriftEntry(name=name, detail=current[name].default) for name in current if name not in known
    )
    removed = tuple(
        DriftEntry(name=name, detail=_value_of(preset, name))
        for name in known
        if name not in current
    )
    changed = tuple(
        entry
        for entry in (
            _changed(preset, known[name], current[name]) for name in known & current.keys()
        )
        if entry is not None
    )
    drift = Drift(added=added, removed=removed, changed=changed, seen_at=int(time.time()))
    return None if drift.is_empty else drift


def _changed(
    preset: Preset, before: DefinitionSnapshot, after: DefinitionSnapshot
) -> DriftEntry | None:
    if before.type != after.type:
        return DriftEntry(
            name=after.name, detail=f"type changed from {before.type} to {after.type}"
        )
    setting = preset.params.get(after.name)
    if setting is None or setting.mode is not ParamMode.FIXED:
        return None
    if after.choices and (setting.value or "") not in after.choices:
        return DriftEntry(name=after.name, detail="your value is no longer an allowed choice")
    return None


def _value_of(preset: Preset, name: str) -> str | None:
    setting = preset.params.get(name)
    return None if setting is None else setting.value


class DriftWatcher:
    """Re-reads the definitions of every job a saved job points at."""

    def __init__(self, presets: PresetStore, reader: JenkinsReader) -> None:
        self._presets = presets
        self._reader = reader

    async def refresh_all(self) -> list[str]:
        """Check every job used by a preset. Returns the presets whose drift moved."""
        moved: list[str] = []
        for job_path in self._presets.job_paths():
            moved.extend(await self.refresh(job_path))
        return moved

    async def refresh(self, job_path: str) -> list[str]:
        """Check one job. A Jenkins that cannot be reached changes nothing."""
        try:
            definitions = await self._reader.parameter_definitions(rest_path_of(job_path))
        except JenkinsUnavailable, JenkinsAuthError, TargetNotFound:
            return []
        live = snapshot_of(definitions)
        moved: list[str] = []
        for preset in self._presets.for_job_path(job_path):
            if not preset.definitions:
                # Nothing was ever read for this saved job, so there is nothing
                # to compare. The Library asks the user to read it.
                continue
            found = diff(preset, live)
            if found != preset.drift:
                self._presets.set_drift(preset.id, found)
                moved.append(preset.id)
        return moved

    async def run_forever(
        self, on_moved: Callable[[str], None], *, interval: float = INTERVAL_SECONDS
    ) -> None:
        """The background loop `jk serve` owns.

        A turn that fails -- the database still busy after its wait -- is tried
        again at the next one. Ending the loop instead would stop every saved job
        being checked against Jenkins until the server restarts.
        """
        while True:
            with suppress(Exception):
                for preset_id in await self.refresh_all():
                    on_moved(preset_id)
            await asyncio.sleep(interval)
