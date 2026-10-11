"""The ambiguous-submission screen, assembled read-only.

There is no retry here and there is no code path to one. This module looks for
builds that match what JK sent and describes them; a human links one or closes
the run.
"""

from __future__ import annotations

from datetime import datetime

from jk.engine.messages import (
    CONNECTION_FAILED_WHILE_SENDING,
    JK_STOPPED_WHILE_SENDING,
    KEPT_LAST_KNOWN_STATE,
    UNKNOWN_SUBMISSION_REASON,
)
from jk.engine.reconcile import find_candidates
from jk.engine.runner import rest_path_of
from jk.errors import JenkinsAuthError, JenkinsUnavailable, TargetNotFound
from jk.store.models import StepState
from jk.web import presenter, schemas
from jk.web.deps import Services

LOOKUP_FAILED = "JK could not inspect Jenkins for matching builds."


async def build(services: Services, flow_id: str, position: int) -> schemas.Attention:
    run, meta = services.flows.get(flow_id)
    stored = run.steps[position]
    candidates, lookup_error = await _candidates(services, flow_id, position)

    never_again = (
        UNKNOWN_SUBMISSION_REASON
        if run.error_kind == "ambiguous_submission"
        else KEPT_LAST_KNOWN_STATE
    )
    return schemas.Attention(
        reason=_reason(stored.note or run.error_message, stored.job_name),
        never_again_text=never_again,
        job_path=stored.job_path,
        sent_at=presenter.moment(stored.submitted_at),
        next_build_number=stored.search_from_build_number,
        candidates=candidates,
        agreement_text=_agreement(candidates, services, flow_id, position),
        lookup_error=lookup_error,
    )


def _reason(note: str | None, job_name: str) -> str:
    """The note in plain words when it is a submission JK cannot speak for.

    The step keeps the raw error in its own note; the window names the saved job.
    """
    if note and note.startswith(JK_STOPPED_WHILE_SENDING):
        return f"JK stopped while sending {job_name}. Jenkins may have started it."
    if note and note.startswith(CONNECTION_FAILED_WHILE_SENDING):
        return f"Connection dropped while sending {job_name}. Jenkins may have started it."
    return note or UNKNOWN_SUBMISSION_REASON


async def _candidates(
    services: Services, flow_id: str, position: int
) -> tuple[list[schemas.AttentionCandidate], str | None]:
    stored = services.store.get_run(flow_id).steps[position]
    if stored.search_from_build_number is None or stored.search_from_timestamp is None:
        return [], None
    sent = services.store.get_step_inputs(flow_id, position)
    if not sent:
        return [], LOOKUP_FAILED
    try:
        found = await find_candidates(
            services.reader,
            rest_path=rest_path_of(stored.job_path),
            sent_params=sent,
            search_from_build_number=stored.search_from_build_number,
            search_from_timestamp=stored.search_from_timestamp,
        )
    except (JenkinsAuthError, JenkinsUnavailable, TargetNotFound) as exc:
        return [], f"{LOOKUP_FAILED} {exc}"
    return [
        schemas.AttentionCandidate(
            number=candidate.build_number,
            time=_clock(candidate.started_at_ms),
            state=_state_word(candidate),
            detail=_detail(candidate.matched),
            url=candidate.build_url,
            after_seconds=candidate.seconds_after_submit,
        )
        for candidate in found
    ], None


def _detail(matched: dict[str, str]) -> str:
    """What a build matched on, CLUSTER and NAMESPACE first: they say where it runs."""
    first = [name for name in ("CLUSTER", "NAMESPACE") if name in matched]
    names = first + [name for name in matched if name not in first]
    return " ".join(f"{name} {matched[name] or 'empty'}" for name in names)


def _state_word(candidate) -> str:
    if candidate.building:
        return "RUNNING"
    return candidate.result or "unknown"


def _clock(milliseconds: int) -> str:
    if not milliseconds:
        return ""
    return datetime.fromtimestamp(milliseconds / 1000).astimezone().strftime("%H:%M:%S")


def _agreement(
    candidates: list[schemas.AttentionCandidate],
    services: Services,
    flow_id: str,
    position: int,
) -> str | None:
    """The one sentence under the candidate list, or nothing to say."""
    if not candidates:
        return None
    parts: list[str] = []
    first = candidates[0]
    if first.after_seconds is not None:
        parts.append(f"#{first.number} started {_delay(first.after_seconds)} after sending.")
    targets = services.targets_of(flow_id).get(position)
    if targets and targets[0] and targets[1]:
        parts.append(f"Sent to: {targets[0]} / {targets[1]}.")
    return " ".join(parts) or None


def _delay(seconds: int) -> str:
    """`2 seconds`, `1 second`, and past a minute `4m 04s`, as a card writes a length."""
    if abs(seconds) < 60:
        return f"{seconds} {'second' if abs(seconds) == 1 else 'seconds'}"
    minutes, rest = divmod(abs(seconds), 60)
    return f"{minutes}m {rest:02d}s"


def is_attention_step(services: Services, flow_id: str, position: int) -> bool:
    run = services.store.get_run(flow_id)
    return 0 <= position < len(run.steps) and run.steps[position].state is StepState.NEEDS_ATTENTION
