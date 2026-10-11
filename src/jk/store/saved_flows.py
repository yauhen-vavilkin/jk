"""Saved flows: a named template of steps and conditions.

A template holds preset ids, conditions, and the values typed for what each
saved job asks at launch. Everything else a step sends is resolved when the flow
runs, never here.
"""

from __future__ import annotations

import sqlite3
import time
import uuid

from jk.store.coding import saved_flow_steps_from_json, saved_flow_steps_to_json
from jk.store.records import SavedFlow, SavedFlowStep
from jk.store.store import RunStore


def _now() -> int:
    return int(time.time())


class SavedFlowStore:
    def __init__(self, store: RunStore) -> None:
        self._store = store
        self._connection: sqlite3.Connection = store.connection

    def list(self) -> list[SavedFlow]:
        rows = self._connection.execute(
            "SELECT * FROM saved_flows ORDER BY name COLLATE NOCASE"
        ).fetchall()
        return [self._from_row(row) for row in rows]

    def get(self, flow_id: str) -> SavedFlow:
        row = self._connection.execute(
            "SELECT * FROM saved_flows WHERE id = ?", (flow_id,)
        ).fetchone()
        if row is None:
            raise KeyError(flow_id)
        return self._from_row(row)

    def save(
        self,
        *,
        name: str,
        steps: tuple[SavedFlowStep, ...],
        flow_id: str | None = None,
    ) -> SavedFlow:
        """Insert, or update in place when the id already exists."""
        identifier = flow_id or str(uuid.uuid4())
        now = _now()
        with self._store.transaction() as connection:
            existing = connection.execute(
                "SELECT created_at FROM saved_flows WHERE id = ?", (identifier,)
            ).fetchone()
            created_at = existing["created_at"] if existing is not None else now
            connection.execute(
                "INSERT OR REPLACE INTO saved_flows(id, name, steps, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    identifier,
                    name,
                    saved_flow_steps_to_json(steps),
                    created_at,
                    now,
                ),
            )
        return self.get(identifier)

    def delete(self, flow_id: str) -> bool:
        with self._store.transaction() as connection:
            cursor = connection.execute("DELETE FROM saved_flows WHERE id = ?", (flow_id,))
            return cursor.rowcount == 1

    @staticmethod
    def _from_row(row: sqlite3.Row) -> SavedFlow:
        return SavedFlow(
            id=row["id"],
            name=row["name"],
            steps=saved_flow_steps_from_json(row["steps"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
