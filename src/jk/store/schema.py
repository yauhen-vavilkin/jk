"""The runs, steps and step_params tables."""

from __future__ import annotations

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS runs (
    id            TEXT PRIMARY KEY,
    kind          TEXT NOT NULL,
    source_id     TEXT NOT NULL,
    name          TEXT NOT NULL,
    state         TEXT NOT NULL,
    created_at    INTEGER NOT NULL,
    updated_at    INTEGER NOT NULL,
    error_kind    TEXT,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS steps (
    run_id                   TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    position                 INTEGER NOT NULL,
    job_config_id            TEXT NOT NULL,
    job_name                 TEXT NOT NULL,
    operation                TEXT NOT NULL,
    job_path                 TEXT NOT NULL,
    destructive              INTEGER NOT NULL DEFAULT 0,
    state                    TEXT NOT NULL,
    queue_url                TEXT,
    build_number             INTEGER,
    build_url                TEXT,
    jenkins_queue_id         INTEGER,
    result                   TEXT,
    submitted_at             INTEGER,
    finished_at              INTEGER,
    search_from_build_number INTEGER,
    search_from_timestamp    INTEGER,
    note                     TEXT,
    PRIMARY KEY (run_id, position)
);

CREATE TABLE IF NOT EXISTS step_params (
    run_id    TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    position  INTEGER NOT NULL,
    name      TEXT NOT NULL,
    value     TEXT NOT NULL,
    PRIMARY KEY (run_id, position, name)
);

CREATE INDEX IF NOT EXISTS idx_runs_updated ON runs(updated_at DESC);
"""
