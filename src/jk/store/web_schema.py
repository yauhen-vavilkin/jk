"""Additive tables for the web panel, and the columns added to any table later.

These are created beside the engine tables and never replace one, so the user's
run history survives a release that only adds tables.

A flow *is* a run. ``flow_meta`` and ``flow_step_meta`` carry only what the web
adds on top of ``runs`` and ``steps``; the submission claim, the parameters that
are sent, and the monitored build stay where the engine already keeps them.
"""

from __future__ import annotations

import sqlite3

WEB_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS presets (
    id                  TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    operation           TEXT NOT NULL,
    description         TEXT NOT NULL DEFAULT '',
    job_path            TEXT NOT NULL,
    destructive         INTEGER NOT NULL DEFAULT 0,
    summary_params      TEXT NOT NULL DEFAULT '[]',
    params              TEXT NOT NULL DEFAULT '{}',
    definition_snapshot TEXT NOT NULL DEFAULT '[]',
    drift               TEXT,
    created_at          INTEGER NOT NULL,
    updated_at          INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS jenkins_jobs (
    job_path    TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    folder      TEXT NOT NULL,
    url         TEXT NOT NULL,
    param_count INTEGER NOT NULL DEFAULT 0,
    definitions TEXT NOT NULL DEFAULT '[]',
    fetched_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS saved_flows (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    steps       TEXT NOT NULL DEFAULT '[]',
    created_at  INTEGER NOT NULL,
    updated_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS flow_meta (
    run_id             TEXT PRIMARY KEY REFERENCES runs(id) ON DELETE CASCADE,
    status             TEXT NOT NULL,
    failed_at_position INTEGER,
    resume_from        INTEGER,
    cleared            INTEGER NOT NULL DEFAULT 0,
    started_at         INTEGER,
    finished_at        INTEGER,
    saved_flow_id      TEXT,
    editing            INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS flow_step_meta (
    run_id              TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    position            INTEGER NOT NULL,
    preset_id           TEXT NOT NULL,
    condition           TEXT NOT NULL DEFAULT 'unless_failure',
    run_values          TEXT NOT NULL DEFAULT '{}',
    summary_params      TEXT NOT NULL DEFAULT '[]',
    frozen              INTEGER NOT NULL DEFAULT 0,
    skipped             INTEGER NOT NULL DEFAULT 0,
    added_at            INTEGER NOT NULL,
    added_while_running INTEGER NOT NULL DEFAULT 0,
    abort_state         TEXT,
    PRIMARY KEY (run_id, position)
);

CREATE INDEX IF NOT EXISTS idx_flow_meta_status ON flow_meta(status);
CREATE INDEX IF NOT EXISTS idx_presets_job_path ON presets(job_path);
"""


#: Columns added to a table after it first shipped: the table is created once,
#: and a later column is added in place rather than by dropping anything.
_ADDED_COLUMNS = {
    "steps": {
        "build_started_at_ms": "INTEGER",
        "build_duration_ms": "INTEGER",
        "estimated_duration_ms": "INTEGER",
    },
    "flow_meta": {
        "resume_from": "INTEGER",
        "pinned": "INTEGER NOT NULL DEFAULT 0",
        "editing": "INTEGER NOT NULL DEFAULT 0",
    },
    "flow_step_meta": {"held": "INTEGER NOT NULL DEFAULT 0"},
    "jenkins_jobs": {"typical_ms": "INTEGER"},
}


def ensure_web_schema(connection: sqlite3.Connection) -> None:
    """Create every web table that is not there yet, and every later column."""
    for statement in WEB_SCHEMA_SQL.split(";"):
        if statement.strip():
            connection.execute(statement)
    for table, columns in _ADDED_COLUMNS.items():
        present = {row[1] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
        for name, declaration in columns.items():
            if name not in present:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")
