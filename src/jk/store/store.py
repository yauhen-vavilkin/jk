"""Durable run and step state."""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from jk.engine.messages import JK_STOPPED_WHILE_SENDING
from jk.state import open_private_file
from jk.store.models import Run, Step, StepState
from jk.store.schema import SCHEMA_SQL
from jk.store.web_schema import ensure_web_schema

#: The claim of a flow's step is only valid while that flow is running, in the
#: same statement, so a Stop that lands during the pre-claim read wins. A run
#: with no flow_meta row is unaffected.
_FLOW_IS_RUNNING = (
    "NOT EXISTS (SELECT 1 FROM flow_meta f WHERE f.run_id = steps.run_id AND f.status != 'running')"
)


#: The run's error kind once the user ended a step that needed attention.
CLOSED_KIND = "closed"


def _now() -> int:
    return int(time.time())


class RunStore:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self._connection.row_factory = sqlite3.Row

    @classmethod
    def open(cls, path: Path) -> RunStore:
        path = Path(path)
        # New state directories are private; existing generic parents are not ours
        # to chmod. The CLI separately hardens its dedicated .jk directory.
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with open_private_file(path):
            pass
        for suffix in ("-wal", "-shm", "-journal"):
            try:
                with open_private_file(Path(f"{path}{suffix}"), create=False):
                    pass
            except FileNotFoundError:
                pass
        connection = sqlite3.connect(path, isolation_level=None, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        cls._create_schema(connection)
        # A release before this one stored a destructive step as AWAITING_CONFIRMATION;
        # it is planned like any other now: PREPARED plus the destructive flag.
        connection.execute(
            "UPDATE steps SET state = 'prepared' WHERE state = 'awaiting_confirmation'"
        )
        return cls(connection)

    @staticmethod
    def _create_schema(connection: sqlite3.Connection) -> None:
        for statement in SCHEMA_SQL.split(";"):
            if statement.strip():
                connection.execute(statement)
        ensure_web_schema(connection)

    def close(self) -> None:
        self._connection.close()

    @property
    def connection(self) -> sqlite3.Connection:
        """The open connection, for the repositories that share this database."""
        return self._connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """One write transaction, shared with the web repositories."""
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            yield self._connection
        except Exception:
            self._connection.execute("ROLLBACK")
            raise
        else:
            self._connection.execute("COMMIT")

    def get_step_inputs(self, run_id: str, position: int) -> dict[str, str]:
        """The exact body to submit: every stored parameter of the step."""
        rows = self._connection.execute(
            "SELECT name, value FROM step_params WHERE run_id = ? AND position = ? ORDER BY name",
            (run_id, position),
        ).fetchall()
        return {row["name"]: row["value"] for row in rows}

    def claim_submit_pending(
        self,
        run_id: str,
        position: int,
        *,
        next_build_number: int,
        now: int | None = None,
    ) -> bool:
        stamp = _now() if now is None else now
        with self.transaction() as connection:
            cursor = connection.execute(
                "UPDATE steps SET state = ?, note = NULL, submitted_at = ?, "
                "search_from_build_number = ?, search_from_timestamp = ? "
                "WHERE run_id = ? AND position = ? AND state = ? "
                "AND " + _FLOW_IS_RUNNING,
                (
                    StepState.SUBMIT_PENDING.value,
                    stamp,
                    next_build_number,
                    stamp,
                    run_id,
                    position,
                    StepState.PREPARED.value,
                ),
            )
            if cursor.rowcount:
                self._touch(connection, run_id)
            return cursor.rowcount == 1

    def mark_queued(self, run_id: str, position: int, *, queue_url: str, note: str | None) -> bool:
        with self.transaction() as connection:
            cursor = connection.execute(
                "UPDATE steps SET state = ?, queue_url = ?, note = ? "
                "WHERE run_id = ? AND position = ? AND state = ?",
                (
                    StepState.QUEUED.value,
                    queue_url,
                    note,
                    run_id,
                    position,
                    StepState.SUBMIT_PENDING.value,
                ),
            )
            if cursor.rowcount:
                self._touch(connection, run_id)
            return cursor.rowcount == 1

    def mark_running(
        self,
        run_id: str,
        position: int,
        *,
        build_number: int,
        build_url: str,
        queue_id: int | None,
    ) -> bool:
        with self.transaction() as connection:
            cursor = connection.execute(
                "UPDATE steps SET state = ?, build_number = ?, build_url = ?, "
                "jenkins_queue_id = ? WHERE run_id = ? AND position = ? AND state = ?",
                (
                    StepState.RUNNING.value,
                    build_number,
                    build_url,
                    queue_id,
                    run_id,
                    position,
                    StepState.QUEUED.value,
                ),
            )
            if cursor.rowcount:
                self._touch(connection, run_id)
            return cursor.rowcount == 1

    def update_build_timing(
        self,
        run_id: str,
        position: int,
        *,
        started_at_ms: int,
        duration_ms: int,
        estimated_duration_ms: int | None,
    ) -> bool:
        with self.transaction() as connection:
            cursor = connection.execute(
                "UPDATE steps SET build_started_at_ms = ?, build_duration_ms = ?, "
                "estimated_duration_ms = ? WHERE run_id = ? AND position = ? AND state = ?",
                (
                    started_at_ms,
                    duration_ms,
                    estimated_duration_ms,
                    run_id,
                    position,
                    StepState.RUNNING.value,
                ),
            )
            if cursor.rowcount:
                connection.execute("UPDATE runs SET updated_at = ? WHERE id = ?", (_now(), run_id))
            return cursor.rowcount == 1

    def mark_final(self, run_id: str, position: int, result: str, now: int | None = None) -> bool:
        stamp = _now() if now is None else now
        state = StepState(result)
        with self.transaction() as connection:
            cursor = connection.execute(
                "UPDATE steps SET state = ?, finished_at = ? "
                "WHERE run_id = ? AND position = ? AND state IN (?, ?)",
                (
                    state.value,
                    stamp,
                    run_id,
                    position,
                    StepState.QUEUED.value,
                    StepState.RUNNING.value,
                ),
            )
            if not cursor.rowcount:
                return False
            # A step result only stamps the run: it never rewrites the run's error,
            # so a build already in flight cannot erase a failure it did not cause.
            connection.execute("UPDATE runs SET updated_at = ? WHERE id = ?", (stamp, run_id))
            return True

    def mark_rejected(self, run_id: str, position: int, *, message: str) -> bool:
        with self.transaction() as connection:
            cursor = connection.execute(
                "UPDATE steps SET state = ?, note = ? WHERE run_id = ? AND position = ? "
                "AND state IN (?, ?)",
                (
                    StepState.REJECTED.value,
                    message,
                    run_id,
                    position,
                    StepState.PREPARED.value,
                    StepState.SUBMIT_PENDING.value,
                ),
            )
            if cursor.rowcount:
                self._touch(connection, run_id, "rejected", message)
            return cursor.rowcount == 1

    def mark_rejected_if_attention(self, run_id: str, position: int, *, message: str) -> bool:
        """Close an attention step only if it is still awaiting user resolution.

        The run keeps why: the user ended it, which is not a Jenkins refusal.
        """
        with self.transaction() as connection:
            cursor = connection.execute(
                "UPDATE steps SET state = ?, note = ? WHERE run_id = ? AND position = ? "
                "AND state = ?",
                (
                    StepState.REJECTED.value,
                    message,
                    run_id,
                    position,
                    StepState.NEEDS_ATTENTION.value,
                ),
            )
            if cursor.rowcount:
                self._touch(connection, run_id, CLOSED_KIND, message)
            return cursor.rowcount == 1

    def mark_needs_attention(self, run_id: str, position: int, *, kind: str, message: str) -> bool:
        with self.transaction() as connection:
            cursor = connection.execute(
                "UPDATE steps SET state = ?, note = ? WHERE run_id = ? AND position = ? "
                "AND state IN (?, ?, ?, ?)",
                (
                    StepState.NEEDS_ATTENTION.value,
                    message,
                    run_id,
                    position,
                    StepState.PREPARED.value,
                    StepState.SUBMIT_PENDING.value,
                    StepState.QUEUED.value,
                    StepState.RUNNING.value,
                ),
            )
            if cursor.rowcount:
                self._touch(connection, run_id, kind, message)
            return cursor.rowcount == 1

    def link_build_if_attention(
        self, run_id: str, position: int, *, build_number: int, build_url: str
    ) -> bool:
        """Link a reconciled build only if the attention state is still current."""
        with self.transaction() as connection:
            cursor = connection.execute(
                "UPDATE steps SET state = ?, build_number = ?, build_url = ?, note = ? "
                "WHERE run_id = ? AND position = ? AND state = ?",
                (
                    StepState.RUNNING.value,
                    build_number,
                    build_url,
                    "linked by the user after an ambiguous submission",
                    run_id,
                    position,
                    StepState.NEEDS_ATTENTION.value,
                ),
            )
            if cursor.rowcount:
                self._touch(connection, run_id)
            return cursor.rowcount == 1

    def recover_pending_submissions(self) -> list[str]:
        rows = self._connection.execute(
            "SELECT run_id, position FROM steps WHERE state = ?",
            (StepState.SUBMIT_PENDING.value,),
        ).fetchall()
        affected: list[str] = []
        for row in rows:
            self.mark_needs_attention(
                row["run_id"],
                row["position"],
                kind="ambiguous_submission",
                message=JK_STOPPED_WHILE_SENDING,
            )
            affected.append(row["run_id"])
        return affected

    def get_run(self, run_id: str) -> Run:
        row = self._connection.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(f"no run {run_id}")
        return self._run_from_row(row)

    def _run_from_row(self, row: sqlite3.Row) -> Run:
        steps = self._connection.execute(
            "SELECT * FROM steps WHERE run_id = ? ORDER BY position", (row["id"],)
        ).fetchall()
        return Run(
            id=row["id"],
            name=row["name"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            error_kind=row["error_kind"],
            error_message=row["error_message"],
            steps=[
                Step(
                    run_id=step["run_id"],
                    position=step["position"],
                    job_config_id=step["job_config_id"],
                    job_name=step["job_name"],
                    job_path=step["job_path"],
                    destructive=bool(step["destructive"]),
                    state=StepState(step["state"]),
                    queue_url=step["queue_url"],
                    build_number=step["build_number"],
                    build_url=step["build_url"],
                    jenkins_queue_id=step["jenkins_queue_id"],
                    submitted_at=step["submitted_at"],
                    finished_at=step["finished_at"],
                    build_started_at_ms=step["build_started_at_ms"],
                    build_duration_ms=step["build_duration_ms"],
                    estimated_duration_ms=step["estimated_duration_ms"],
                    search_from_build_number=step["search_from_build_number"],
                    search_from_timestamp=step["search_from_timestamp"],
                    note=step["note"],
                )
                for step in steps
            ],
        )

    def _touch(
        self,
        connection: sqlite3.Connection,
        run_id: str,
        error_kind: str | None = None,
        error_message: str | None = None,
    ) -> None:
        connection.execute(
            "UPDATE runs SET updated_at = ?, error_kind = ?, error_message = ? WHERE id = ?",
            (_now(), error_kind, error_message, run_id),
        )
