"""What will be sent, checked against Jenkins, before anything is sent.

The check is read-only and blocking: the primary button stays disabled until it
passes. It compares only the names JK will actually send, because a parameter
left on its Jenkins default is deliberately absent from the body.
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from jk.jenkins.models import ERROR_PLACEHOLDER, SUPPORTED_PARAMETER_TYPES
from jk.store.records import ParamMode
from jk.web import errors, presenter, schemas
from jk.web.deps import Services

UPDATE_ACTION = "Update the saved job in Library."
NOT_DEFINED = "parameter is not defined by Jenkins"
NOT_A_CHOICE = "value is not an allowed Jenkins choice"
PASSWORD_EMPTY = "password parameter has no value"
PLACEHOLDER = "value is the Active Choices error placeholder"
PLACEHOLDER_UNSENT = "not sent, and the Jenkins default is the Active Choices error placeholder"


#: Which planned steps a review covers.
#: - "all": a draft about to start, every step.
#: - "held": steps added to a started flow, or held after a restart or a change.
#: - "resume": the steps a stopped or failed flow would go on with.
Scope = Literal["all", "held", "resume"]

DRIFTED = "Jenkins changed this saved job"
DRIFT_ACTION = "Review it in Library"


def _covered(stored, web_meta, scope: Scope, from_position: int | None) -> bool:
    if web_meta.skipped or presenter.STATE_WORDS[stored.state] != "planned":
        return False
    if scope == "held":
        return web_meta.held
    if scope == "resume" and from_position is not None:
        return stored.position >= from_position
    return True


def _is_fresh(web_meta) -> bool:
    """A step whose body is taken from the saved job now, not from an earlier review."""
    return web_meta.held or not web_meta.frozen


def token_of(entries: list[tuple]) -> str:
    """What the user saw, reduced to a fingerprint the start request must repeat."""
    return hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest()[:32]


async def build(
    services: Services,
    flow_id: str,
    *,
    scope: Scope = "all",
    from_position: int | None = None,
) -> schemas.Review:
    """Read every referenced job once, then answer for the steps in scope."""
    run, meta = services.flows.get(flow_id)
    presets = services.preset_map()

    issues: list[schemas.ReviewIssue] = []
    steps: list[schemas.ReviewStep] = []
    missing: list[schemas.MissingRunValues] = []
    fingerprint: list[tuple] = [scope, from_position]
    definitions_by_path: dict[str, dict | str] = {}

    for stored in run.steps:
        web_meta = meta.steps[stored.position]
        if not _covered(stored, web_meta, scope, from_position):
            continue
        identifier = presenter.step_id(flow_id, stored.position)
        preset = presets.get(web_meta.preset_id)
        if preset is None:
            issues.append(
                schemas.ReviewIssue(
                    step_id=identifier,
                    preset_name=stored.job_name,
                    parameter=None,
                    failure="the saved job is gone",
                    action=UPDATE_ACTION,
                )
            )
            fingerprint.append((stored.position, "gone"))
            continue

        fresh = _is_fresh(web_meta)
        if fresh:
            asked = set(preset.ask_names())
            body = preset.sent_values(web_meta.run_values)
            is_destructive = preset.destructive
            unanswered = [
                name for name in asked if not (web_meta.run_values.get(name) or "").strip()
            ]
            if unanswered:
                missing.append(
                    schemas.MissingRunValues(step_id=identifier, names=sorted(unanswered))
                )
        else:
            # Frozen at an earlier review: exactly this body is sent.
            asked = set()
            body = services.store.get_step_inputs(flow_id, stored.position)
            is_destructive = stored.destructive

        if preset.drift is not None:
            issues.append(
                schemas.ReviewIssue(
                    step_id=identifier,
                    preset_name=preset.name,
                    parameter=None,
                    failure=DRIFTED,
                    action=DRIFT_ACTION,
                    preset_id=preset.id,
                )
            )

        if preset.job_path not in definitions_by_path:
            definitions_by_path[preset.job_path] = await _definitions(services, preset.job_path)
        live = definitions_by_path[preset.job_path]
        if isinstance(live, str):
            issues.append(
                schemas.ReviewIssue(
                    step_id=identifier,
                    preset_name=preset.name,
                    parameter=None,
                    failure=live,
                    action=UPDATE_ACTION,
                )
            )
        else:
            issues.extend(_issues(identifier, preset, body, live, asked))
        defaults = [] if isinstance(live, str) else _defaults(live, body, asked)

        steps.append(
            schemas.ReviewStep(
                step_id=identifier,
                position=stored.position,
                preset_name=preset.name,
                job_path=preset.job_path,
                job_url=presenter.job_url(services.base_url, preset.job_path),
                destructive=is_destructive,
                condition=web_meta.condition.value,
                # A value asked at launch and never typed is listed too, empty, so
                # the review offers its field instead of leaving Run off unexplained.
                sent=[
                    schemas.SummaryValue(name=name, value=value, per_run=name in asked)
                    for name, value in {
                        **body,
                        **{name: "" for name in sorted(asked) if name not in body},
                    }.items()
                ],
                defaults_left=len(defaults)
                if not isinstance(live, str)
                else sum(
                    1 for setting in preset.params.values() if setting.mode is ParamMode.DEFAULT
                ),
                defaults=defaults,
            )
        )
        fingerprint.append(
            (
                stored.position,
                web_meta.condition.value,
                preset.job_path,
                is_destructive,
                sorted(asked),
                sorted((name, value) for name, value in body.items() if name not in asked),
            )
        )

    return schemas.Review(
        ok=not issues,
        issues=issues,
        steps=steps,
        same_target=services.same_target(flow_id),
        missing_run_values=missing,
        review_token=token_of(fingerprint),
    )


def refusal(review: schemas.Review, token: str) -> str | None:
    """Why a reviewed start may not go ahead, in the sentence the user reads."""
    if not review.steps and not review.issues:
        return "There is nothing to send."
    if token != review.review_token:
        return "The saved values changed since you reviewed them. Review again."
    if review.issues:
        return "Review found problems. Nothing was sent."
    if review.missing_run_values:
        return "A value asked at launch is still empty. Nothing was sent."
    return None


async def _definitions(services: Services, job_path: str) -> dict | str:
    """The job's live definitions, or why they could not be read."""
    try:
        return await services.read_definitions(job_path)
    except errors.ApiError as exc:
        return f"{exc.message} Nothing was sent."


def _issues(
    step_id: str, preset, body: dict[str, str], live: dict, asked: set[str]
) -> list[schemas.ReviewIssue]:
    """What JK will send, and the one Jenkins default that is JK's business.

    A Jenkins default is normally left alone (spec.md section 6). An Active Choices
    parameter is the exception: leaving it unsent makes Jenkins resolve it to the
    `error` placeholder, which spec.md 6.1 forbids carrying into a build.
    """
    found: list[schemas.ReviewIssue] = []
    for name in sorted(body):
        definition = live.get(name)
        if definition is None:
            found.append(_issue(step_id, preset.name, name, NOT_DEFINED))
            continue
        if definition.type not in SUPPORTED_PARAMETER_TYPES:
            found.append(
                _issue(
                    step_id,
                    preset.name,
                    name,
                    f"unsupported Jenkins parameter type {definition.type}",
                )
            )
            continue
        if definition.is_cascade and body[name].strip() == ERROR_PLACEHOLDER:
            found.append(_issue(step_id, preset.name, name, PLACEHOLDER))
            continue
        if definition.choices and body[name] not in definition.choices:
            found.append(_issue(step_id, preset.name, name, NOT_A_CHOICE))
        if definition.is_secret and not body[name]:
            found.append(_issue(step_id, preset.name, name, PASSWORD_EMPTY))
    # A value asked at launch and still empty is not left to Jenkins: it is
    # reported as missing, and the start is refused for that instead.
    for name in sorted(live.keys() - body.keys() - asked):
        definition = live[name]
        if definition.is_cascade and (definition.default or "").strip() == ERROR_PLACEHOLDER:
            found.append(_issue(step_id, preset.name, name, PLACEHOLDER_UNSENT))
    return found


def _defaults(live: dict, body: dict[str, str], asked: set[str]) -> list[schemas.JenkinsDefault]:
    """What Jenkins will use for each parameter JK leaves to it, in Jenkins' order.

    The Active Choices `error` placeholder is not a default anyone chose.
    """
    return [
        schemas.JenkinsDefault(
            name=name,
            default=None
            if definition.is_cascade and (definition.default or "").strip() == ERROR_PLACEHOLDER
            else definition.default,
        )
        for name, definition in live.items()
        if name not in body and name not in asked
    ]


def _issue(step_id: str, preset_name: str, parameter: str, failure: str) -> schemas.ReviewIssue:
    return schemas.ReviewIssue(
        step_id=step_id,
        preset_name=preset_name,
        parameter=parameter,
        failure=failure,
        action=UPDATE_ACTION,
    )
