"""Value types for stored runs and their steps."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class StepState(StrEnum):
    PREPARED = "prepared"
    SUBMIT_PENDING = "submit_pending"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    UNSTABLE = "UNSTABLE"
    ABORTED = "ABORTED"
    REJECTED = "rejected"
    NEEDS_ATTENTION = "needs_attention"


FINAL_STEP_STATES = frozenset(
    {
        StepState.SUCCESS,
        StepState.FAILURE,
        StepState.UNSTABLE,
        StepState.ABORTED,
        StepState.REJECTED,
        StepState.NEEDS_ATTENTION,
    }
)


RESULT_STATES = {
    "SUCCESS": StepState.SUCCESS,
    "FAILURE": StepState.FAILURE,
    "UNSTABLE": StepState.UNSTABLE,
    "ABORTED": StepState.ABORTED,
}


def state_for_result(result: object) -> StepState | None:
    """Map a Jenkins final result to a step state; None when JK does not know it."""
    if not isinstance(result, str):
        return None
    return RESULT_STATES.get(result)


@dataclass
class Step:
    run_id: str
    position: int
    job_config_id: str
    job_name: str
    job_path: str
    destructive: bool
    state: StepState
    queue_url: str | None = None
    build_number: int | None = None
    build_url: str | None = None
    jenkins_queue_id: int | None = None
    submitted_at: int | None = None
    finished_at: int | None = None
    build_started_at_ms: int | None = None
    build_duration_ms: int | None = None
    estimated_duration_ms: int | None = None
    search_from_build_number: int | None = None
    search_from_timestamp: int | None = None
    note: str | None = None


@dataclass
class Run:
    id: str
    name: str
    created_at: int
    updated_at: int
    error_kind: str | None = None
    error_message: str | None = None
    steps: list[Step] = field(default_factory=list)
