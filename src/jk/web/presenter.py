"""Turn stored records into the JSON shapes of `schemas.py`.

Nothing here decides anything: the engine decides, the store remembers, and this
module spells the answer. It is also the boundary that keeps the API token out
of every response, by never reading it.
"""

from __future__ import annotations

import time
from datetime import datetime

from jk.engine.flows import flow_result
from jk.engine.runner import rest_path_of
from jk.store import models, records
from jk.store.models import StepState
from jk.store.store import CLOSED_KIND
from jk.web import schemas

#: The engine's step states, in the words the board uses.
STATE_WORDS: dict[StepState, schemas.StepState] = {
    StepState.PREPARED: "planned",
    StepState.SUBMIT_PENDING: "submit_pending",
    StepState.QUEUED: "queued",
    StepState.RUNNING: "running",
    StepState.SUCCESS: "SUCCESS",
    StepState.FAILURE: "FAILURE",
    StepState.UNSTABLE: "UNSTABLE",
    StepState.ABORTED: "ABORTED",
    StepState.REJECTED: "rejected",
    StepState.NEEDS_ATTENTION: "needs_attention",
}

IN_FLIGHT: frozenset[schemas.StepState] = frozenset({"submit_pending", "queued", "running"})


def moment(seconds: int | None) -> str | None:
    """One stored second as an ISO 8601 stamp with this machine's offset."""
    if seconds is None:
        return None
    return datetime.fromtimestamp(seconds).astimezone().isoformat()


def moment_ms(milliseconds: int | None) -> str | None:
    if not milliseconds:
        return None
    return datetime.fromtimestamp(milliseconds / 1000).astimezone().isoformat()


def step_id(flow_id: str, position: int) -> str:
    return f"{flow_id}:{position}"


def split_step_id(value: str) -> tuple[str, int]:
    flow_id, _, position = value.rpartition(":")
    return flow_id, int(position)


def job_url(base_url: str, job_path: str) -> str:
    return f"{base_url.rstrip('/')}/{rest_path_of(job_path)}/"


def drift(stored: records.Drift | None) -> schemas.Drift | None:
    if stored is None:
        return None
    return schemas.Drift(
        added=[schemas.DriftItem(name=item.name, default=item.detail) for item in stored.added],
        removed=[schemas.DriftItem(name=item.name, had=item.detail) for item in stored.removed],
        changed=[schemas.DriftItem(name=item.name, reason=item.detail) for item in stored.changed],
        seen_at=moment(stored.seen_at) or moment(int(time.time())) or "",
    )


def preset(stored: records.Preset, *, base_url: str) -> schemas.Preset:
    return schemas.Preset(
        id=stored.id,
        name=stored.name,
        operation=stored.operation,
        job_path=stored.job_path,
        job_url=job_url(base_url, stored.job_path),
        destructive=stored.destructive,
        summary_params=list(stored.summary_params),
        params={
            name: schemas.ParamSetting(
                mode=setting.mode.value, value=setting.value, last_value=setting.last_value
            )
            for name, setting in stored.params.items()
        },
        definitions=[
            schemas.ParamDefinition(
                name=item.name,
                type=item.type,
                default=item.default,
                choices=item.choices,
            )
            for item in stored.definitions
        ],
        drift=drift(stored.drift),
    )


def saved_flow(
    stored: records.SavedFlow, presets: dict[str, records.Preset], typical: dict[str, int]
) -> schemas.SavedFlow:
    return schemas.SavedFlow(
        id=stored.id,
        name=stored.name,
        steps=[
            schemas.SavedFlowStep(
                preset_id=step.preset_id,
                condition=step.condition.value,
                run_values=dict(step.run_values),
            )
            for step in stored.steps
        ],
        estimate_ms=saved_flow_estimate(stored, presets, typical),
    )


def sent_values(
    stored: models.Step,
    meta: records.FlowMeta,
    source: records.Preset | None,
    frozen: dict[str, str],
) -> dict[str, str]:
    """What this step sends, or sent: the frozen body once there is one."""
    if frozen:
        return frozen
    if source is None:
        return {}
    return source.sent_values(meta.steps[stored.position].run_values)


def summary(
    stored: models.Step,
    meta: records.FlowMeta,
    source: records.Preset | None,
    values: dict[str, str],
) -> list[schemas.SummaryValue]:
    names = meta.steps[stored.position].summary_params or tuple(values)
    per_run = set(source.ask_names()) if source is not None else set()
    return [
        schemas.SummaryValue(name=name, value=values.get(name, ""), per_run=name in per_run)
        for name in names
        if name in values or name in per_run
    ]


def _elapsed_ms(stored: models.Step, state: schemas.StepState, now_ms: int) -> int | None:
    if stored.build_duration_ms:
        return stored.build_duration_ms
    if state == "running" and stored.build_started_at_ms:
        return max(0, now_ms - stored.build_started_at_ms)
    return None


def step(
    stored: models.Step,
    meta: records.FlowMeta,
    source: records.Preset | None,
    frozen: dict[str, str],
    *,
    base_url: str,
    now_ms: int,
    typical_ms: int | None = None,
    closed: bool = False,
) -> schemas.Step:
    """One step. `closed`: the user ended its flow while this step needed attention."""
    web_meta = meta.steps[stored.position]
    state: schemas.StepState = STATE_WORDS[stored.state]
    if web_meta.skipped and state == "planned":
        state = "skipped"
    if closed and state == "rejected":
        state = "closed"
    values = sent_values(stored, meta, source, frozen)
    elapsed = _elapsed_ms(stored, state, now_ms)
    remaining = None
    if state == "running" and stored.estimated_duration_ms and elapsed is not None:
        remaining = max(0, stored.estimated_duration_ms - elapsed)
    return schemas.Step(
        id=step_id(stored.run_id, stored.position),
        position=stored.position,
        preset_id=web_meta.preset_id,
        # Until its body is fixed, a step is its saved job as it is now, name included.
        preset_name=source.name if source is not None and not web_meta.frozen else stored.job_name,
        job_url=job_url(base_url, stored.job_path),
        destructive=stored.destructive,
        condition=web_meta.condition.value,
        summary=summary(stored, meta, source, values),
        run_values=dict(web_meta.run_values),
        frozen_params=frozen or None,
        state=state,
        build_number=stored.build_number,
        build_url=stored.build_url,
        sent_at=moment(stored.submitted_at),
        started_at=moment_ms(stored.build_started_at_ms),
        finished_at=moment(stored.finished_at),
        elapsed_ms=elapsed,
        # The build's own estimate once there is a build; before that, the job's last success.
        estimate_ms=stored.estimated_duration_ms or typical_ms,
        estimate_remaining_ms=remaining,
        added_at=moment(web_meta.added_at) or "",
        added_while_running=web_meta.added_while_running,
        abort_state=web_meta.abort_state,
        held=web_meta.held,
        note=stored.note,
    )


def saved_flow_estimate(
    stored: records.SavedFlow, presets: dict[str, records.Preset], typical: dict[str, int]
) -> int | None:
    """How long a saved flow takes. As for a flow: nothing unless every step is known."""
    total = 0
    for step in stored.steps:
        preset = presets.get(step.preset_id)
        known = typical.get(preset.job_path) if preset else None
        if known is None:
            return None
        total += known
    return total or None


def remaining_estimate(steps: list[schemas.Step]) -> int | None:
    """What is left of a flow, from Jenkins' estimates. Nothing unless every step left has one."""
    total = 0
    for item in steps:
        if item.state == "running":
            left = item.estimate_remaining_ms
        elif item.state in ("planned", "submit_pending", "queued"):
            left = item.estimate_ms
        else:
            continue
        if left is None:
            return None
        total += left
    return total or None


def flow(
    run: models.Run,
    meta: records.FlowMeta,
    presets: dict[str, records.Preset],
    frozen: dict[int, dict[str, str]],
    *,
    base_url: str,
    saved_flow_id: str | None = None,
    typical: dict[str, int] | None = None,
) -> schemas.Flow:
    stamp = int(time.time() * 1000)
    steps = [
        step(
            stored,
            meta,
            presets.get(meta.steps[stored.position].preset_id),
            frozen.get(stored.position, {}),
            base_url=base_url,
            now_ms=stamp,
            typical_ms=(typical or {}).get(stored.job_path),
            closed=run.error_kind == CLOSED_KIND,
        )
        for stored in run.steps
    ]
    current = next((item.position for item in steps if item.state in IN_FLIGHT), None)
    return schemas.Flow(
        id=run.id,
        name=run.name,
        status=meta.status.value,
        steps=steps,
        current_position=current,
        created_at=moment(run.created_at) or "",
        started_at=moment(meta.started_at),
        finished_at=moment(meta.finished_at),
        updated_at=moment(run.updated_at) or "",
        cleared=meta.cleared,
        failed_at_position=meta.failed_at_position,
        result=flow_result(run),
        saved_flow_id=saved_flow_id,
        pinned=meta.pinned,
        editing=meta.editing,
        estimate_ms=remaining_estimate(steps),
    )
