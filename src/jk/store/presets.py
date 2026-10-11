"""Saved jobs: the user's values for one Jenkins job.

A preset is what the Library edits and what a flow step points at. Its run
count and last run come from the run history, so deleting a preset never
rewrites what already happened.
"""

from __future__ import annotations

import sqlite3
import time
import uuid

from jk.store.coding import (
    definitions_from_json,
    definitions_to_json,
    drift_from_json,
    drift_to_json,
    dump,
    params_from_json,
    params_to_json,
    string_list,
)
from jk.store.records import (
    DefinitionSnapshot,
    Drift,
    ParamSetting,
    Preset,
)
from jk.store.store import RunStore

MAX_SUMMARY_PARAMS = 4

#: A step still uses its saved job while it has not run yet, or is running, in a
#: flow that can still get to it. A step skipped in a flow that ended never will.
_STILL_USES = (
    "s.state IN ('prepared', 'submit_pending', 'queued', 'running', "
    "'needs_attention') AND f.cleared = 0 AND f.status NOT IN ('finished', 'failed')"
)


def _now() -> int:
    return int(time.time())


class PresetStore:
    def __init__(self, store: RunStore) -> None:
        self._store = store
        self._connection: sqlite3.Connection = store.connection

    def list(self) -> list[Preset]:
        rows = self._connection.execute("SELECT * FROM presets ORDER BY name COLLATE NOCASE")
        return [self._from_row(row) for row in rows.fetchall()]

    def get(self, preset_id: str) -> Preset:
        row = self._connection.execute(
            "SELECT * FROM presets WHERE id = ?", (preset_id,)
        ).fetchone()
        if row is None:
            raise KeyError(preset_id)
        return self._from_row(row)

    def find(self, preset_id: str) -> Preset | None:
        try:
            return self.get(preset_id)
        except KeyError:
            return None

    def job_paths(self) -> list[str]:
        rows = self._connection.execute(
            "SELECT DISTINCT job_path FROM presets ORDER BY job_path"
        ).fetchall()
        return [row["job_path"] for row in rows]

    def for_job_path(self, job_path: str) -> list[Preset]:
        rows = self._connection.execute(
            "SELECT * FROM presets WHERE job_path = ? ORDER BY name COLLATE NOCASE", (job_path,)
        ).fetchall()
        return [self._from_row(row) for row in rows]

    def create(
        self,
        *,
        name: str,
        operation: str,
        job_path: str,
        destructive: bool = False,
        summary_params: tuple[str, ...] = (),
        params: dict[str, ParamSetting] | None = None,
        definitions: tuple[DefinitionSnapshot, ...] = (),
        drift: Drift | None = None,
        preset_id: str | None = None,
    ) -> Preset:
        now = _now()
        identifier = preset_id or str(uuid.uuid4())
        with self._store.transaction() as connection:
            connection.execute(
                "INSERT INTO presets(id, name, operation, job_path, destructive, "
                "summary_params, params, definition_snapshot, drift, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    identifier,
                    name,
                    operation,
                    job_path,
                    1 if destructive else 0,
                    dump(list(summary_params[:MAX_SUMMARY_PARAMS])),
                    params_to_json(params or {}),
                    definitions_to_json(definitions),
                    drift_to_json(drift),
                    now,
                    now,
                ),
            )
        return self.get(identifier)

    def update(
        self,
        preset_id: str,
        *,
        name: str | None = None,
        operation: str | None = None,
        destructive: bool | None = None,
        summary_params: tuple[str, ...] | None = None,
        params: dict[str, ParamSetting] | None = None,
        definitions: tuple[DefinitionSnapshot, ...] | None = None,
    ) -> Preset:
        current = self.get(preset_id)
        with self._store.transaction() as connection:
            connection.execute(
                "UPDATE presets SET name = ?, operation = ?, destructive = ?, "
                "summary_params = ?, params = ?, definition_snapshot = ?, "
                "updated_at = ? WHERE id = ?",
                (
                    current.name if name is None else name,
                    current.operation if operation is None else operation,
                    int(current.destructive if destructive is None else destructive),
                    dump(
                        list(
                            (current.summary_params if summary_params is None else summary_params)[
                                :MAX_SUMMARY_PARAMS
                            ]
                        )
                    ),
                    params_to_json(current.params if params is None else params),
                    definitions_to_json(
                        current.definitions if definitions is None else definitions
                    ),
                    _now(),
                    preset_id,
                ),
            )
        return self.get(preset_id)

    def set_drift(self, preset_id: str, drift: Drift | None) -> None:
        with self._store.transaction() as connection:
            connection.execute(
                "UPDATE presets SET drift = ?, updated_at = ? WHERE id = ?",
                (drift_to_json(drift), _now(), preset_id),
            )

    def delete(self, preset_id: str) -> bool:
        with self._store.transaction() as connection:
            cursor = connection.execute("DELETE FROM presets WHERE id = ?", (preset_id,))
            return cursor.rowcount == 1

    def used_by(self, preset_id: str) -> list[tuple[str, str, int]]:
        """Each active step that points at this preset: its flow's id and name, and its position."""
        rows = self._connection.execute(
            "SELECT r.id AS flow_id, r.name AS flow_name, s.position AS position "
            "FROM steps s JOIN flow_meta f ON f.run_id = s.run_id JOIN runs r ON r.id = s.run_id "
            f"WHERE s.job_config_id = ? AND {_STILL_USES} "
            "ORDER BY r.created_at, r.rowid, s.position",
            (preset_id,),
        ).fetchall()
        return [(row["flow_id"], row["flow_name"], int(row["position"])) for row in rows]

    @staticmethod
    def _from_row(row: sqlite3.Row) -> Preset:
        return Preset(
            id=row["id"],
            name=row["name"],
            operation=row["operation"],
            job_path=row["job_path"],
            destructive=bool(row["destructive"]),
            summary_params=string_list(row["summary_params"]),
            params=params_from_json(row["params"]),
            definitions=definitions_from_json(row["definition_snapshot"]),
            drift=drift_from_json(row["drift"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
