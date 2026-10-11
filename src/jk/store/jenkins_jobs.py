"""The cached Jenkins job index the Library searches.

A cache, not a contract: it records what the controller answered and when.
Nothing is ever launched from it without reading the live definitions first.
"""

from __future__ import annotations

import sqlite3
import time

from jk.store.records import JenkinsJobRecord
from jk.store.store import RunStore


def _now() -> int:
    return int(time.time())


class JenkinsJobStore:
    def __init__(self, store: RunStore) -> None:
        self._store = store
        self._connection: sqlite3.Connection = store.connection

    def replace_index(self, jobs: list[JenkinsJobRecord]) -> None:
        """Swap the whole index in one transaction; a partial crawl never lands."""
        with self._store.transaction() as connection:
            connection.execute("DELETE FROM jenkins_jobs")
            for job in jobs:
                connection.execute(
                    "INSERT INTO jenkins_jobs(job_path, name, folder, url, param_count, "
                    "fetched_at, typical_ms) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        job.job_path,
                        job.name,
                        job.folder,
                        job.url,
                        job.param_count,
                        _now(),
                        job.typical_ms,
                    ),
                )

    def search(self, query: str = "") -> list[JenkinsJobRecord]:
        rows = self._connection.execute("SELECT * FROM jenkins_jobs").fetchall()
        runs = self._run_counts()
        needle = query.strip().lower()
        found = [
            self._from_row(row, runs)
            for row in rows
            if not needle or needle in row["name"].lower() or needle in row["job_path"].lower()
        ]
        found.sort(key=lambda job: (-job.run_count, job.name.casefold()))
        return found

    def typical_durations(self) -> dict[str, int]:
        """Job path to how long its last successful build took, where Jenkins said."""
        rows = self._connection.execute(
            "SELECT job_path, typical_ms FROM jenkins_jobs WHERE typical_ms IS NOT NULL"
        ).fetchall()
        return {row["job_path"]: row["typical_ms"] for row in rows}

    def _run_counts(self) -> dict[str, int]:
        rows = self._connection.execute(
            "SELECT job_path, COUNT(*) AS runs FROM steps WHERE submitted_at IS NOT NULL "
            "GROUP BY job_path"
        ).fetchall()
        return {row["job_path"]: row["runs"] for row in rows}

    @staticmethod
    def _from_row(row: sqlite3.Row, runs: dict[str, int]) -> JenkinsJobRecord:
        return JenkinsJobRecord(
            job_path=row["job_path"],
            name=row["name"],
            folder=row["folder"],
            url=row["url"],
            param_count=row["param_count"],
            run_count=runs.get(row["job_path"], 0),
            typical_ms=row["typical_ms"],
        )
