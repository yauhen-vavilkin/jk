"""Seed the run store with a running flow, the way the panel leaves one.

The store and engine tests need runs in a known state without going through
the web API. A seeded step is reviewed and frozen: it is PREPARED, destructive
or not, and the flow is running, so the store's claim accepts it.
"""

from __future__ import annotations

from dataclasses import dataclass

from jk.store.flows import FlowStore
from jk.store.records import FlowStatus
from jk.store.store import RunStore


@dataclass(frozen=True)
class SeedStep:
    """One saved job of a seeded run, with the exact body it will send."""

    job_id: str
    body: dict[str, str]
    destructive: bool = False
    job_path: str = ""


def step(
    job_id: str,
    body: dict[str, str],
    *,
    destructive: bool = False,
    job_path: str = "",
) -> SeedStep:
    return SeedStep(job_id, body, destructive, job_path or f"folder/{job_id}")


def seed_run(store: RunStore, *steps: SeedStep, name: str = "Test run") -> str:
    """A running flow with every step frozen. Returns its run id."""
    flows = FlowStore(store)
    flow_id = flows.create(name=name)
    for item in steps:
        position = flows.append_step(
            flow_id,
            preset_id=item.job_id,
            preset_name=f"{item.job_id} job",
            job_path=item.job_path,
            destructive=item.destructive,
            summary_params=tuple(item.body),
        )
        flows.freeze_step_params(flow_id, position, item.body, destructive=item.destructive)
    flows.set_status(flow_id, FlowStatus.RUNNING, started=True)
    return flow_id
