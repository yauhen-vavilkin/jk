"""The JSON shapes of the web API, and nothing else.

`web/src/api/types.ts` lists the fields of them that the panel reads. The
Jenkins API token is not a field of anything: it never leaves the process.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Condition = Literal["unless_failure", "after_success", "always", "after_failure"]
ParamMode = Literal["fixed", "ask", "default"]
FlowStatus = Literal["draft", "running", "needs_attention", "stopped", "finished", "failed"]
StepState = Literal[
    "planned",
    "submit_pending",
    "queued",
    "running",
    "SUCCESS",
    "UNSTABLE",
    "FAILURE",
    "ABORTED",
    "rejected",
    "needs_attention",
    "skipped",
    # Needed attention, and the user ended the flow without linking a build.
    "closed",
]
Result = Literal["SUCCESS", "UNSTABLE", "FAILURE", "ABORTED"]


class ParamSetting(BaseModel):
    mode: ParamMode
    value: str | None = None
    last_value: str | None = None


class ParamDefinition(BaseModel):
    name: str
    type: str
    default: str | None = None
    choices: list[str] | None = None


class DriftItem(BaseModel):
    name: str
    default: str | None = None
    had: str | None = None
    reason: str | None = None


class Drift(BaseModel):
    added: list[DriftItem] = []
    removed: list[DriftItem] = []
    changed: list[DriftItem] = []
    seen_at: str


class Preset(BaseModel):
    id: str
    name: str
    operation: str
    job_path: str
    job_url: str
    destructive: bool
    summary_params: list[str]
    params: dict[str, ParamSetting]
    definitions: list[ParamDefinition]
    drift: Drift | None


class PresetCreate(BaseModel):
    job_path: str
    name: str
    operation: str
    destructive: bool = False
    params: dict[str, ParamSetting] = {}


class PresetUpdate(BaseModel):
    name: str | None = None
    operation: str | None = None
    destructive: bool | None = None
    params: dict[str, ParamSetting] | None = None


class RepairRequest(BaseModel):
    decisions: dict[str, Literal["default", "fixed", "ask", "drop"]] = {}
    values: dict[str, str] = {}


class PresetUse(BaseModel):
    """One step that still uses a saved job: the flow it is in, and where."""

    flow_id: str
    flow_name: str
    position: int


class PresetUsage(BaseModel):
    #: Each step that still uses the saved job, in the order the flows were made.
    steps: list[PresetUse] = []


class SavedFlowStep(BaseModel):
    preset_id: str
    condition: Condition = "unless_failure"
    run_values: dict[str, str] = {}


class SavedFlow(BaseModel):
    id: str
    name: str
    steps: list[SavedFlowStep]
    # Jenkins' guess for the whole flow, from how long each job last took; none
    # unless every step's job has one.
    estimate_ms: int | None = None


class SavedFlowPatch(BaseModel):
    """What a rename sends: a field left out keeps the value the server holds."""

    name: str | None = None


class Instantiate(BaseModel):
    flow_id: str | None = None


class JenkinsJob(BaseModel):
    job_path: str
    name: str
    folder: str
    param_count: int
    run_count: int
    url: str


class JenkinsStatus(BaseModel):
    url: str
    reachable: bool
    since: str | None
    auth_ok: bool


class SummaryValue(BaseModel):
    name: str
    value: str
    per_run: bool = False


class Step(BaseModel):
    id: str
    position: int
    preset_id: str
    preset_name: str
    job_url: str
    destructive: bool
    condition: Condition
    summary: list[SummaryValue]
    run_values: dict[str, str]
    frozen_params: dict[str, str] | None
    state: StepState
    build_number: int | None
    build_url: str | None
    sent_at: str | None
    started_at: str | None
    finished_at: str | None
    elapsed_ms: int | None
    estimate_ms: int | None
    estimate_remaining_ms: int | None
    added_at: str
    added_while_running: bool
    abort_state: Literal["requested", "accepted", "failed"] | None
    note: str | None = None
    #: Added after the start (or held after a restart or a Jenkins change) and
    #: not reviewed yet; the flow waits here and sends nothing for it.
    held: bool = False


class SameTarget(BaseModel):
    """The one step of another flow that reaches the same CLUSTER and NAMESPACE soonest."""

    flow_id: str
    flow_name: str
    position: int
    #: submit_pending, queued or running: a build is, or is about to be, in
    #: Jenkins; needs_attention: one may be; planned: a later step of a flow
    #: that is running.
    state: StepState
    cluster: str
    namespace: str
    build_number: int | None = None


class Flow(BaseModel):
    id: str
    name: str
    status: FlowStatus
    steps: list[Step]
    current_position: int | None
    created_at: str
    started_at: str | None
    finished_at: str | None
    updated_at: str
    cleared: bool
    failed_at_position: int | None
    result: Result | None
    # The saved flow this flow is kept as, while that saved flow exists.
    saved_flow_id: str | None = None
    pinned: bool = False
    # The user is still building this flow: it can be changed, but not run. Only
    # a draft is ever being edited.
    editing: bool = False
    # What is left to run, from Jenkins' estimates; null unless every step left has one.
    estimate_ms: int | None = None


class StepCreate(BaseModel):
    preset_id: str
    condition: Condition = "unless_failure"
    run_values: dict[str, str] = {}


class StepAdd(StepCreate):
    #: Where the card was dropped. Without one the step goes at the end, and only
    #: a draft takes a step anywhere else.
    position: int | None = None


class FlowCreate(BaseModel):
    name: str | None = None
    steps: list[StepCreate] = []


class FlowPatch(BaseModel):
    name: str | None = None
    cleared: bool | None = None
    pinned: bool | None = None
    #: Turns editing on or off. Only a draft takes it.
    editing: bool | None = None


class FlowRerun(BaseModel):
    #: Keep the original visible until the user successfully starts the reviewed copy.
    keep_source: bool = False
    #: `Run again` wants the copy ready to run; the pencil wants it open to change.
    editing: bool = False


class StepPatch(BaseModel):
    condition: Condition | None = None
    run_values: dict[str, str] | None = None
    position: int | None = None


class FlowStart(BaseModel):
    run_values: dict[str, dict[str, str]] = {}
    #: The token of the review the user read; a start without one is refused.
    review_token: str


class FlowConfirm(BaseModel):
    """Release the held steps of a started flow after reviewing them."""

    run_values: dict[str, dict[str, str]] = {}
    review_token: str


class FlowStop(BaseModel):
    abort_current: bool = False


class FlowClose(BaseModel):
    #: The builds the window listed as matching, written into the step's note.
    build_numbers: list[int] = []


class FlowResume(BaseModel):
    from_position: int | None = None
    #: Values asked at launch for held steps the resume review covers.
    run_values: dict[str, dict[str, str]] = {}
    review_token: str


class ReviewRequest(BaseModel):
    scope: Literal["all", "held", "resume"] = "all"
    from_position: int | None = None


class LinkBuild(BaseModel):
    build_number: int


class ReviewIssue(BaseModel):
    step_id: str
    preset_name: str
    parameter: str | None
    failure: str
    action: str
    #: The saved job to review in Library; set when Jenkins changed it.
    preset_id: str | None = None


class JenkinsDefault(BaseModel):
    name: str
    #: What Jenkins will use; None when it has no default.
    default: str | None = None


class ReviewStep(BaseModel):
    step_id: str
    position: int
    preset_name: str
    job_path: str
    job_url: str
    destructive: bool
    condition: Condition
    sent: list[SummaryValue]
    defaults_left: int
    #: Every parameter Jenkins defines that this step neither sends nor asks.
    defaults: list[JenkinsDefault] = []


class MissingRunValues(BaseModel):
    step_id: str
    names: list[str]


class Review(BaseModel):
    ok: bool
    issues: list[ReviewIssue] = []
    steps: list[ReviewStep] = []
    same_target: list[SameTarget] = []
    missing_run_values: list[MissingRunValues] = []
    review_token: str = ""


class AttentionCandidate(BaseModel):
    number: int
    time: str
    state: str
    detail: str
    url: str
    after_seconds: int | None


class Attention(BaseModel):
    reason: str
    never_again_text: str
    job_path: str
    sent_at: str | None
    next_build_number: int | None
    candidates: list[AttentionCandidate] = Field(default_factory=list)
    agreement_text: str | None = None
    lookup_error: str | None = None
