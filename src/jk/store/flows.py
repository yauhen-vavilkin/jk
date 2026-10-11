"""Flows, stored as runs.

A flow *is* a run: ``flow_meta.run_id`` is ``runs.id`` and a flow step is the
``steps`` row at the same position. That keeps the submission claim, the stored
body and the monitored build exactly where ``engine/runner.py`` already puts
them, and adds only what the board needs: a status, a condition per step, and
the values entered for this run.
"""

from __future__ import annotations

import sqlite3
import time
import uuid

from jk.store.coding import dump, string_list, string_map
from jk.store.models import Run, StepState
from jk.store.records import (
    ACTIVE_FLOW_STATUSES,
    KEEP_FINISHED_SECONDS,
    Condition,
    FlowMeta,
    FlowStatus,
    FlowStepMeta,
)
from jk.store.store import RunStore

#: Used while renumbering, so a moved row never collides with a row not moved yet.
_SHIFT = 1_000_000


def _now() -> int:
    return int(time.time())


class FlowStore:
    def __init__(self, store: RunStore) -> None:
        self._store = store
        self._connection: sqlite3.Connection = store.connection

    def get(self, flow_id: str) -> tuple[Run, FlowMeta]:
        run = self._store.get_run(flow_id)
        row = self._connection.execute(
            "SELECT * FROM flow_meta WHERE run_id = ?", (flow_id,)
        ).fetchone()
        if row is None:
            raise KeyError(flow_id)
        return run, self._meta_from_row(row)

    def find(self, flow_id: str) -> tuple[Run, FlowMeta] | None:
        try:
            return self.get(flow_id)
        except KeyError:
            return None

    def list(self, *, active: bool | None = None, include_cleared: bool = False) -> list[str]:
        """Flow ids, newest first; the caller loads the ones it needs."""
        clauses: list[str] = []
        params: list[object] = []
        if active is not None:
            placeholders = ", ".join("?" * len(ACTIVE_FLOW_STATUSES))
            keyword = "IN" if active else "NOT IN"
            clauses.append(f"f.status {keyword} ({placeholders})")
            params.extend(sorted(status.value for status in ACTIVE_FLOW_STATUSES))
        if not include_cleared:
            clauses.append("f.cleared = 0")
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = self._connection.execute(
            f"SELECT f.run_id FROM flow_meta f JOIN runs r ON r.id = f.run_id {where} "
            "ORDER BY r.created_at DESC",
            params,
        ).fetchall()
        return [row["run_id"] for row in rows]

    def stale_finished(self) -> list[str]:
        """Runs that ended long enough ago to leave the board.

        Reading only: the caller clears them one at a time and says so, so every
        open panel hears it. A pinned flow stays until the user takes it off.
        """
        rows = self._connection.execute(
            "SELECT run_id FROM flow_meta WHERE cleared = 0 AND pinned = 0 "
            "AND status IN (?, ?) AND finished_at IS NOT NULL AND finished_at < ?",
            (
                FlowStatus.FINISHED.value,
                FlowStatus.FAILED.value,
                _now() - KEEP_FINISHED_SECONDS,
            ),
        ).fetchall()
        return [row["run_id"] for row in rows]

    def board_names(self, *, excluding: str | None = None) -> list[str]:
        """The names on the board: every flow that has not been cleared off it.

        A run that ended is on the board until it is cleared, by the trash or by
        the server's own tidy of `stale_finished`, so a name is held exactly while
        it can be seen.
        What is cleared is History, and History may hold a name twice -- two runs
        of one flow always do.
        """
        params: list[object] = []
        clause = ""
        if excluding is not None:
            clause = " AND f.run_id != ?"
            params.append(excluding)
        rows = self._connection.execute(
            "SELECT r.name FROM flow_meta f JOIN runs r ON r.id = f.run_id "
            f"WHERE f.cleared = 0{clause}",
            params,
        ).fetchall()
        return [row["name"] for row in rows]

    def create(
        self,
        *,
        name: str,
        saved_flow_id: str | None = None,
        pinned: bool = False,
        created_at: int | None = None,
        editing: bool = True,
    ) -> str:
        """A new draft. `created_at` lets a flow that is run again keep its place on the board.

        A flow is being built unless the caller says otherwise: what comes from a
        saved flow is ready to run, because it was built once already.
        """
        flow_id = str(uuid.uuid4())
        now = _now()
        with self._store.transaction() as connection:
            connection.execute(
                "INSERT INTO runs(id, kind, source_id, name, state, created_at, updated_at) "
                "VALUES (?, 'flow', '', ?, '', ?, ?)",
                (flow_id, name, created_at if created_at is not None else now, now),
            )
            connection.execute(
                "INSERT INTO flow_meta(run_id, status, cleared, saved_flow_id, pinned, editing) "
                "VALUES (?, ?, 0, ?, ?, ?)",
                (flow_id, FlowStatus.DRAFT.value, saved_flow_id, int(pinned), int(editing)),
            )
        return flow_id

    def append_step(
        self,
        flow_id: str,
        *,
        preset_id: str,
        preset_name: str,
        job_path: str,
        destructive: bool,
        summary_params: tuple[str, ...],
        condition: Condition = Condition.UNLESS_FAILURE,
        run_values: dict[str, str] | None = None,
        added_while_running: bool = False,
        held: bool = False,
    ) -> int:
        """Add one step at the end. Returns its position."""
        now = _now()
        with self._store.transaction() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(position) + 1, 0) AS next FROM steps WHERE run_id = ?",
                (flow_id,),
            ).fetchone()
            position = int(row["next"])
            connection.execute(
                "INSERT INTO steps(run_id, position, job_config_id, job_name, operation, "
                "job_path, destructive, state) VALUES (?, ?, ?, ?, '', ?, ?, ?)",
                (
                    flow_id,
                    position,
                    preset_id,
                    preset_name,
                    job_path,
                    1 if destructive else 0,
                    StepState.PREPARED.value,
                ),
            )
            connection.execute(
                "INSERT INTO flow_step_meta(run_id, position, preset_id, condition, run_values, "
                "summary_params, frozen, skipped, added_at, added_while_running, held) "
                "VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?)",
                (
                    flow_id,
                    position,
                    preset_id,
                    condition.value,
                    dump(run_values or {}),
                    dump(list(summary_params)),
                    now,
                    1 if added_while_running else 0,
                    1 if held else 0,
                ),
            )
            connection.execute("UPDATE runs SET updated_at = ? WHERE id = ?", (now, flow_id))
        return position

    def update_step(
        self,
        flow_id: str,
        position: int,
        *,
        condition: Condition | None = None,
        run_values: dict[str, str] | None = None,
    ) -> bool:
        """Change a planned step. False when it is no longer planned."""
        with self._store.transaction() as connection:
            if not self._is_planned(connection, flow_id, position):
                return False
            if condition is not None:
                connection.execute(
                    "UPDATE flow_step_meta SET condition = ? WHERE run_id = ? AND position = ?",
                    (condition.value, flow_id, position),
                )
            if run_values is not None:
                connection.execute(
                    "UPDATE flow_step_meta SET run_values = ? WHERE run_id = ? AND position = ?",
                    (dump(run_values), flow_id, position),
                )
            connection.execute("UPDATE runs SET updated_at = ? WHERE id = ?", (_now(), flow_id))
            return True

    def remove_step(self, flow_id: str, position: int) -> bool:
        """Delete a planned step and close the gap it leaves."""
        with self._store.transaction() as connection:
            if not self._may_renumber_from(connection, flow_id, position):
                return False
            for table in ("step_params", "flow_step_meta", "steps"):
                connection.execute(
                    f"DELETE FROM {table} WHERE run_id = ? AND position = ?", (flow_id, position)
                )
            order = [
                row["position"]
                for row in connection.execute(
                    "SELECT position FROM steps WHERE run_id = ? ORDER BY position", (flow_id,)
                )
            ]
            self._apply_order(connection, flow_id, order)
            connection.execute("UPDATE runs SET updated_at = ? WHERE id = ?", (_now(), flow_id))
            return True

    def move_step(self, flow_id: str, position: int, target: int) -> bool:
        """Move a planned step to another planned position; it ends up at `target`."""
        with self._store.transaction() as connection:
            if not self._is_planned(connection, flow_id, target):
                return False
            if not self._may_renumber_from(connection, flow_id, min(position, target)):
                return False
            order = [
                row["position"]
                for row in connection.execute(
                    "SELECT position FROM steps WHERE run_id = ? ORDER BY position", (flow_id,)
                ).fetchall()
            ]
            index = order.index(target) if target in order else len(order) - 1
            order.remove(position)
            order.insert(index, position)
            self._apply_order(connection, flow_id, order)
            connection.execute("UPDATE runs SET updated_at = ? WHERE id = ?", (_now(), flow_id))
            return True

    def freeze_step_params(
        self,
        flow_id: str,
        position: int,
        body: dict[str, str],
        *,
        destructive: bool | None = None,
    ) -> bool:
        """Write the exact body a step will send, when the user reviews it.

        Planned steps only. `destructive` brings the step's flag in line with
        what Review showed.
        """
        with self._store.transaction() as connection:
            if not self._is_planned(connection, flow_id, position):
                return False
            if destructive is not None:
                connection.execute(
                    "UPDATE steps SET destructive = ? WHERE run_id = ? AND position = ?",
                    (1 if destructive else 0, flow_id, position),
                )
            connection.execute(
                "DELETE FROM step_params WHERE run_id = ? AND position = ?", (flow_id, position)
            )
            for name, value in body.items():
                connection.execute(
                    "INSERT INTO step_params(run_id, position, name, value) VALUES (?, ?, ?, ?)",
                    (flow_id, position, name, value),
                )
            connection.execute(
                "UPDATE flow_step_meta SET frozen = 1 WHERE run_id = ? AND position = ?",
                (flow_id, position),
            )
            return True

    def set_held(self, flow_id: str, position: int, held: bool) -> bool:
        """Hold a planned step for review, or release it. False when it is not planned."""
        with self._store.transaction() as connection:
            if not self._is_planned(connection, flow_id, position):
                return False
            connection.execute(
                "UPDATE flow_step_meta SET held = ? WHERE run_id = ? AND position = ?",
                (1 if held else 0, flow_id, position),
            )
            connection.execute("UPDATE runs SET updated_at = ? WHERE id = ?", (_now(), flow_id))
            return True

    def mark_skipped(self, flow_id: str, position: int) -> bool:
        with self._store.transaction() as connection:
            if not self._is_planned(connection, flow_id, position):
                return False
            connection.execute(
                "UPDATE flow_step_meta SET skipped = 1 WHERE run_id = ? AND position = ?",
                (flow_id, position),
            )
            connection.execute("UPDATE runs SET updated_at = ? WHERE id = ?", (_now(), flow_id))
            return True

    def set_abort_state(self, flow_id: str, position: int, abort_state: str | None) -> None:
        with self._store.transaction() as connection:
            connection.execute(
                "UPDATE flow_step_meta SET abort_state = ? WHERE run_id = ? AND position = ?",
                (abort_state, flow_id, position),
            )
            connection.execute("UPDATE runs SET updated_at = ? WHERE id = ?", (_now(), flow_id))

    def stop_before_submit(self, flow_id: str, position: int, *, message: str) -> bool:
        """Keep an unsent step resumable without overwriting a later Stop or claim."""
        with self._store.transaction() as connection:
            cursor = connection.execute(
                "UPDATE flow_meta SET status = ?, editing = 0 WHERE run_id = ? AND status = ? "
                "AND EXISTS (SELECT 1 FROM steps s WHERE s.run_id = flow_meta.run_id "
                "AND s.position = ? AND s.state = ?)",
                (
                    FlowStatus.STOPPED.value,
                    flow_id,
                    FlowStatus.RUNNING.value,
                    position,
                    StepState.PREPARED.value,
                ),
            )
            if not cursor.rowcount:
                return False
            connection.execute(
                "UPDATE steps SET note = ? WHERE run_id = ? AND position = ?",
                (message, flow_id, position),
            )
            connection.execute("UPDATE runs SET updated_at = ? WHERE id = ?", (_now(), flow_id))
            return True

    def set_status(
        self,
        flow_id: str,
        status: FlowStatus,
        *,
        failed_at_position: int | None = None,
        clear_failed: bool = False,
        resume_from: int | None = None,
        started: bool = False,
        finished: bool = False,
    ) -> None:
        now = _now()
        with self._store.transaction() as connection:
            connection.execute(
                "UPDATE flow_meta SET status = ? WHERE run_id = ?", (status.value, flow_id)
            )
            # Only a draft is ever being edited: a flow that has started is past
            # being built, whatever it was marked as a moment before.
            if status is not FlowStatus.DRAFT:
                connection.execute("UPDATE flow_meta SET editing = 0 WHERE run_id = ?", (flow_id,))
            if failed_at_position is not None or clear_failed:
                connection.execute(
                    "UPDATE flow_meta SET failed_at_position = ? WHERE run_id = ?",
                    (None if clear_failed else failed_at_position, flow_id),
                )
            if resume_from is not None or clear_failed:
                connection.execute(
                    "UPDATE flow_meta SET resume_from = ? WHERE run_id = ?",
                    (resume_from, flow_id),
                )
            if started:
                connection.execute(
                    "UPDATE flow_meta SET started_at = COALESCE(started_at, ?) WHERE run_id = ?",
                    (now, flow_id),
                )
            if finished:
                connection.execute(
                    "UPDATE flow_meta SET finished_at = ? WHERE run_id = ?", (now, flow_id)
                )
            connection.execute("UPDATE runs SET updated_at = ? WHERE id = ?", (now, flow_id))

    def clear_resume_from(self, flow_id: str) -> None:
        """Consume the one step the user asked to start regardless of its condition."""
        with self._store.transaction() as connection:
            connection.execute(
                "UPDATE flow_meta SET resume_from = NULL WHERE run_id = ?", (flow_id,)
            )

    def rename(self, flow_id: str, name: str) -> None:
        with self._store.transaction() as connection:
            connection.execute(
                "UPDATE runs SET name = ?, updated_at = ? WHERE id = ?", (name, _now(), flow_id)
            )

    def link_saved_flow(self, flow_id: str, saved_flow_id: str) -> None:
        """Record which saved flow this flow is kept as."""
        with self._store.transaction() as connection:
            connection.execute(
                "UPDATE flow_meta SET saved_flow_id = ? WHERE run_id = ?", (saved_flow_id, flow_id)
            )

    def set_pinned(self, flow_id: str, pinned: bool) -> None:
        with self._store.transaction() as connection:
            connection.execute(
                "UPDATE flow_meta SET pinned = ? WHERE run_id = ?", (int(pinned), flow_id)
            )

    def set_editing(self, flow_id: str, editing: bool) -> None:
        """Only a draft is ever being edited; the caller holds that rule."""
        with self._store.transaction() as connection:
            connection.execute(
                "UPDATE flow_meta SET editing = ? WHERE run_id = ?", (int(editing), flow_id)
            )

    def set_cleared(self, flow_id: str, cleared: bool) -> None:
        with self._store.transaction() as connection:
            connection.execute(
                "UPDATE flow_meta SET cleared = ? WHERE run_id = ?",
                (1 if cleared else 0, flow_id),
            )

    def delete(self, flow_id: str) -> bool:
        with self._store.transaction() as connection:
            cursor = connection.execute("DELETE FROM runs WHERE id = ?", (flow_id,))
            return cursor.rowcount == 1

    @staticmethod
    def _is_planned(connection: sqlite3.Connection, flow_id: str, position: int) -> bool:
        row = connection.execute(
            "SELECT state FROM steps WHERE run_id = ? AND position = ?", (flow_id, position)
        ).fetchone()
        return row is not None and StepState(row["state"]) is StepState.PREPARED

    @staticmethod
    def _may_renumber_from(connection: sqlite3.Connection, flow_id: str, low: int) -> bool:
        """Positions from `low` on may change only if every step there is still planned.

        The engine claims and monitors a step by its position. A renumbering that
        moved a sent, running or skipped step would point it at another row.
        """
        rows = connection.execute(
            "SELECT s.state, COALESCE(m.skipped, 0) AS skipped FROM steps s "
            "LEFT JOIN flow_step_meta m ON m.run_id = s.run_id AND m.position = s.position "
            "WHERE s.run_id = ? AND s.position >= ?",
            (flow_id, low),
        ).fetchall()
        return bool(rows) and all(
            StepState(row["state"]) is StepState.PREPARED and not row["skipped"] for row in rows
        )

    @staticmethod
    def _apply_order(connection: sqlite3.Connection, flow_id: str, order: list[int]) -> None:
        """Rewrite positions so they read 0..n-1 in the order given."""
        tables = ("steps", "step_params", "flow_step_meta")
        for table in tables:
            connection.execute(
                f"UPDATE {table} SET position = position + ? WHERE run_id = ?", (_SHIFT, flow_id)
            )
        for index, old in enumerate(order):
            if index == old:
                continue
            for table in tables:
                connection.execute(
                    f"UPDATE {table} SET position = ? WHERE run_id = ? AND position = ?",
                    (index, flow_id, old + _SHIFT),
                )
        for table in tables:
            connection.execute(
                f"UPDATE {table} SET position = position - ? WHERE run_id = ? AND position >= ?",
                (_SHIFT, flow_id, _SHIFT),
            )

    def _meta_from_row(self, row: sqlite3.Row) -> FlowMeta:
        steps = {
            step["position"]: FlowStepMeta(
                run_id=step["run_id"],
                position=step["position"],
                preset_id=step["preset_id"],
                condition=Condition(step["condition"]),
                run_values=string_map(step["run_values"]),
                summary_params=string_list(step["summary_params"]),
                frozen=bool(step["frozen"]),
                skipped=bool(step["skipped"]),
                added_at=step["added_at"],
                added_while_running=bool(step["added_while_running"]),
                abort_state=step["abort_state"],
                held=bool(step["held"]),
            )
            for step in self._connection.execute(
                "SELECT * FROM flow_step_meta WHERE run_id = ? ORDER BY position",
                (row["run_id"],),
            ).fetchall()
        }
        return FlowMeta(
            run_id=row["run_id"],
            status=FlowStatus(row["status"]),
            failed_at_position=row["failed_at_position"],
            resume_from=row["resume_from"],
            cleared=bool(row["cleared"]),
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            saved_flow_id=row["saved_flow_id"],
            steps=steps,
            pinned=bool(row["pinned"]),
            editing=bool(row["editing"]),
        )
