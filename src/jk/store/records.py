"""Stored records the web panel adds beside runs and steps.

These are plain values. Every JSON column is parsed here once, so no caller
above the store ever sees a string where a mapping is meant.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ParamMode(StrEnum):
    FIXED = "fixed"
    ASK = "ask"
    DEFAULT = "default"


class Condition(StrEnum):
    UNLESS_FAILURE = "unless_failure"
    AFTER_SUCCESS = "after_success"
    ALWAYS = "always"
    AFTER_FAILURE = "after_failure"


class FlowStatus(StrEnum):
    DRAFT = "draft"
    RUNNING = "running"
    NEEDS_ATTENTION = "needs_attention"
    STOPPED = "stopped"
    FINISHED = "finished"
    FAILED = "failed"


#: Statuses that accept a new step. A finished or failed flow does not.
ACTIVE_FLOW_STATUSES = frozenset(
    {
        FlowStatus.DRAFT,
        FlowStatus.RUNNING,
        FlowStatus.NEEDS_ATTENTION,
        FlowStatus.STOPPED,
    }
)

#: How long a run that ended stays on the board before it leaves for History.
#: Pinned flows stay until the user takes them off.
KEEP_FINISHED_SECONDS = 12 * 60 * 60


@dataclass(frozen=True)
class ParamSetting:
    """What the user decided about one Jenkins parameter of a preset."""

    mode: ParamMode = ParamMode.DEFAULT
    value: str | None = None
    last_value: str | None = None


@dataclass(frozen=True)
class DefinitionSnapshot:
    """A Jenkins parameter definition as it was when the preset was saved."""

    name: str
    type: str
    default: str | None = None
    choices: list[str] | None = None


@dataclass(frozen=True)
class DriftEntry:
    name: str
    detail: str | None = None


@dataclass(frozen=True)
class Drift:
    """How the Jenkins definition moved away from the stored snapshot."""

    added: tuple[DriftEntry, ...] = ()
    removed: tuple[DriftEntry, ...] = ()
    changed: tuple[DriftEntry, ...] = ()
    seen_at: int = 0

    @property
    def is_empty(self) -> bool:
        return not (self.added or self.removed or self.changed)


@dataclass(frozen=True)
class Preset:
    id: str
    name: str
    operation: str
    job_path: str
    destructive: bool
    summary_params: tuple[str, ...]
    params: dict[str, ParamSetting]
    definitions: tuple[DefinitionSnapshot, ...]
    drift: Drift | None
    created_at: int
    updated_at: int

    def sent_values(self, run_values: dict[str, str] | None = None) -> dict[str, str]:
        """Exactly what a submission body would contain.

        ``default`` parameters are absent, so Jenkins applies its own default;
        an ``ask`` parameter takes the value entered for this run.
        """
        given = run_values or {}
        body: dict[str, str] = {}
        for name, setting in self.params.items():
            if setting.mode is ParamMode.FIXED:
                body[name] = setting.value or ""
            elif setting.mode is ParamMode.ASK and name in given:
                body[name] = given[name]
        return body

    def ask_names(self) -> tuple[str, ...]:
        return tuple(name for name, setting in self.params.items() if setting.mode is ParamMode.ASK)


@dataclass(frozen=True)
class SavedFlowStep:
    preset_id: str
    condition: Condition = Condition.UNLESS_FAILURE
    # The values typed for the parameters its saved job asks at launch.
    run_values: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SavedFlow:
    id: str
    name: str
    steps: tuple[SavedFlowStep, ...]
    created_at: int
    updated_at: int


@dataclass(frozen=True)
class JenkinsJobRecord:
    job_path: str
    name: str
    folder: str
    url: str
    param_count: int
    run_count: int = 0
    #: How long the job's last successful build took, as Jenkins reported it.
    typical_ms: int | None = None


@dataclass(frozen=True)
class FlowStepMeta:
    """The web half of a step; the engine half stays in ``steps``."""

    run_id: str
    position: int
    preset_id: str
    condition: Condition
    run_values: dict[str, str]
    summary_params: tuple[str, ...]
    frozen: bool
    skipped: bool
    added_at: int
    added_while_running: bool
    abort_state: str | None = None
    #: Added to a flow that had already started, and not reviewed yet. The flow
    #: waits at a held step; nothing is sent for it until the user confirms it.
    held: bool = False


@dataclass(frozen=True)
class FlowMeta:
    run_id: str
    status: FlowStatus
    failed_at_position: int | None
    resume_from: int | None
    cleared: bool
    started_at: int | None
    finished_at: int | None
    saved_flow_id: str | None
    steps: dict[int, FlowStepMeta] = field(default_factory=dict)
    #: Kept at the top of the board, and on it, until the user takes it off.
    pinned: bool = False
    #: The user is still building this flow: it can be changed but not run. Only
    #: a draft is ever being edited; every other status means it has started.
    editing: bool = False
