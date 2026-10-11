"""Flows: the board's verbs.

Nothing here talks to Jenkins directly. A route writes what the user decided and
hands the flow to the supervisor, which owns every request that leaves.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from jk.engine.messages import ended_without_link
from jk.store.models import StepState
from jk.store.records import (
    ACTIVE_FLOW_STATUSES,
    Condition,
    FlowMeta,
    FlowStatus,
    Preset,
    SavedFlowStep,
)
from jk.web import attention, errors, naming, presenter, review, schemas
from jk.web.deps import Services, services_of

router = APIRouter(prefix="/api/flows", tags=["flows"])

DEFAULT_FLOW_NAME = "New flow"


def _flow(services: Services, flow_id: str):
    found = services.flows.find(flow_id)
    if found is None:
        raise errors.not_found(f"flow {flow_id}")
    return found


def _require_editable(meta: FlowMeta) -> None:
    """A draft is changed only while it is being edited.

    Every other status keeps the rules it always had: what a running flow allows
    is decided by the step, not by this.
    """
    if meta.status is FlowStatus.DRAFT and not meta.editing:
        raise errors.conflict("flow_not_editing", "Turn editing on to change this flow.")


def _refuse_unless_ready(meta: FlowMeta) -> None:
    """Nothing is sent for a flow the user is still building.

    Asked on both sides of the review, because the review awaits Jenkins and
    editing can be turned back on while it does.
    """
    if meta.status is not FlowStatus.DRAFT:
        raise errors.conflict("flow_started", "This flow has already started.")
    if meta.editing:
        raise errors.conflict("flow_editing", "Press Done before running this flow.")


def _preset(services: Services, preset_id: str) -> Preset:
    found = services.presets.find(preset_id)
    if found is None:
        raise errors.not_found(f"saved job {preset_id}")
    if found.drift is not None:
        raise errors.preset_drifted()
    return found


def _presets(services: Services, steps: list[schemas.StepCreate]) -> list[Preset]:
    """Check every saved job first, so a refusal adds nothing at all."""
    return [_preset(services, step.preset_id) for step in steps]


def _append(
    services: Services,
    flow_id: str,
    step: schemas.StepCreate,
    preset: Preset,
    *,
    running: bool,
    started: bool | None = None,
) -> int:
    """Add one step at the end, and say where it landed.

    A step added to a flow that has started is held for review.
    """
    held = running if started is None else started
    return services.flows.append_step(
        flow_id,
        preset_id=preset.id,
        preset_name=preset.name,
        job_path=preset.job_path,
        destructive=preset.destructive,
        summary_params=preset.summary_params,
        condition=Condition(step.condition),
        run_values=step.run_values,
        added_while_running=running,
        held=held,
    )


@router.get("", response_model=list[schemas.Flow])
async def list_flows(request: Request) -> list[schemas.Flow]:
    return services_of(request).flow_responses()


@router.post("", response_model=schemas.Flow, status_code=201)
async def create_flow(request: Request, body: schemas.FlowCreate) -> schemas.Flow:
    services = services_of(request)
    presets = _presets(services, body.steps)
    name = naming.tidy(body.name or "") or (presets[0].name if presets else "")
    # The board named this itself, after the job that was dropped: it takes the
    # next free name rather than refusing a drop.
    flow_id = services.flows.create(
        name=naming.free_name(name or DEFAULT_FLOW_NAME, services.flows.board_names())
    )
    for step, preset in zip(body.steps, presets, strict=True):
        _append(services, flow_id, step, preset, running=False)
    services.publish_flow(flow_id)
    return services.flow_response(flow_id)


def _copy_steps(services: Services, run, meta: FlowMeta, target_id: str) -> None:
    """Every step as a planned one again: no build, no frozen body, no hold.

    A saved job Jenkins changed, and one that is gone, come along as they were
    stored, to be replaced on the board. Review says so before anything is sent.
    """
    for stored in run.steps:
        web_meta = meta.steps[stored.position]
        preset = services.presets.find(web_meta.preset_id)
        services.flows.append_step(
            target_id,
            preset_id=web_meta.preset_id,
            preset_name=preset.name if preset else stored.job_name,
            job_path=preset.job_path if preset else stored.job_path,
            destructive=preset.destructive if preset else stored.destructive,
            summary_params=preset.summary_params if preset else web_meta.summary_params,
            condition=web_meta.condition,
            run_values=dict(web_meta.run_values),
        )


@router.post("/{flow_id}/save", response_model=schemas.Flow)
async def save_flow(request: Request, flow_id: str) -> schemas.Flow:
    """Keep this flow as a saved flow: the one it already is, or a new one."""
    services = services_of(request)
    run, meta = _flow(services, flow_id)
    # Each step's job, its condition, and the values typed for it: a flow taken
    # from the saved flow later starts with them filled in.
    steps = tuple(
        SavedFlowStep(
            preset_id=step.preset_id,
            condition=Condition(step.condition),
            run_values={name: value for name, value in step.run_values.items() if value.strip()},
        )
        for step in services.flow_response(flow_id).steps
    )
    kept = services.kept_as(meta.saved_flow_id)
    existing = services.saved_flows.get(kept) if kept else None
    # A saved flow keeps the name its own row gives it: saving writes the steps.
    # Only the first save names it, after the board, and takes a free name --
    # the user typed that name for the flow, not for the template.
    name = (
        existing.name
        if existing
        else naming.free_name(run.name, [item.name for item in services.saved_flows.list()])
    )
    saved = services.saved_flows.save(flow_id=kept, name=name, steps=steps)
    services.flows.link_saved_flow(flow_id, saved.id)
    services.publish_saved_flow(saved.id)
    services.publish_flow(flow_id)
    return services.flow_response(flow_id)


@router.patch("/{flow_id}", response_model=schemas.Flow)
async def patch_flow(request: Request, flow_id: str, body: schemas.FlowPatch) -> schemas.Flow:
    services = services_of(request)
    run, meta = _flow(services, flow_id)
    if body.name is not None:
        # A flow is named while it is built, and keeps that name from then on:
        # what ran is a record of the name it ran under.
        if meta.status not in ACTIVE_FLOW_STATUSES:
            raise errors.conflict(
                "flow_finished", "This flow has finished; run it again to change it."
            )
        if meta.status is not FlowStatus.DRAFT:
            raise errors.conflict("flow_started", "This flow has already started.")
        _require_editable(meta)
        wanted = naming.tidy(body.name)
        if not wanted:
            raise errors.name_empty()
        if naming.is_taken(wanted, services.flows.board_names(excluding=flow_id)):
            raise errors.conflict("name_taken", "A flow on the board is already called that.")
        # The saved flow this one is kept as keeps its own name: a copy on the
        # board is renamed for this run, not for every run to come.
        services.flows.rename(flow_id, wanted)
    if body.editing is not None:
        if meta.status is not FlowStatus.DRAFT:
            raise errors.conflict("flow_started", "This flow has already started.")
        services.flows.set_editing(flow_id, body.editing)
    if body.cleared is not None:
        if body.cleared and meta.status in ACTIVE_FLOW_STATUSES:
            _refuse_unless_settled(run, meta)
        services.flows.set_cleared(flow_id, body.cleared)
    if body.pinned is not None:
        services.flows.set_pinned(flow_id, body.pinned)
    services.publish_flow(flow_id)
    return services.flow_response(flow_id)


@router.delete("/{flow_id}", status_code=204)
async def delete_flow(request: Request, flow_id: str) -> Response:
    services = services_of(request)
    _, meta = _flow(services, flow_id)
    if meta.status is not FlowStatus.DRAFT:
        raise errors.conflict("flow_started", "This flow has already started.")
    services.flows.delete(flow_id)
    return Response(status_code=204)


@router.post("/{flow_id}/steps", response_model=schemas.Flow)
async def add_step(request: Request, flow_id: str, body: schemas.StepAdd) -> schemas.Flow:
    services = services_of(request)
    _, meta = _flow(services, flow_id)
    if meta.status not in ACTIVE_FLOW_STATUSES:
        raise errors.conflict("flow_finished", "This flow has finished; start a new one.")
    _require_editable(meta)
    # A step takes a place of its own only in a draft: once a flow has started,
    # the order it is running in is the order it was reviewed in.
    if body.position is not None and meta.status is not FlowStatus.DRAFT:
        raise errors.conflict("flow_started", "This flow has started; a step goes at the end.")
    preset = _preset(services, body.preset_id)
    landed = _append(
        services,
        flow_id,
        body,
        preset,
        started=meta.status is not FlowStatus.DRAFT,
        running=meta.status is FlowStatus.RUNNING,
    )
    if body.position is not None and 0 <= body.position < landed:
        services.flows.move_step(flow_id, landed, body.position)
    await services.supervisor.appended(flow_id)
    return services.flow_response(flow_id)


@router.patch("/{flow_id}/steps/{step_id}", response_model=schemas.Flow)
async def patch_step(
    request: Request, flow_id: str, step_id: str, body: schemas.StepPatch
) -> schemas.Flow:
    services = services_of(request)
    _, meta = _flow(services, flow_id)
    # A value asked at launch belongs to this run, not to the shape of the flow,
    # so a flow that is built and waiting still takes one.
    if body.condition is not None or body.position is not None:
        _require_editable(meta)
    position = _position(flow_id, step_id)
    if services.supervisor.is_sending(flow_id):
        raise errors.flow_sending()
    web_meta = meta.steps.get(position)
    if (
        (body.run_values is not None or body.condition is not None)
        and web_meta is not None
        and _reviewed(web_meta)
    ):
        # The body and the condition were fixed when the user reviewed them; a
        # change needs a new review.
        raise errors.flow_running()
    changed = True
    if body.condition is not None or body.run_values is not None:
        changed = services.flows.update_step(
            flow_id,
            position,
            condition=None if body.condition is None else Condition(body.condition),
            run_values=body.run_values,
        )
    if changed and body.position is not None:
        changed = services.flows.move_step(flow_id, position, body.position)
    if not changed:
        raise errors.flow_running()
    await services.supervisor.appended(flow_id)
    return services.flow_response(flow_id)


@router.delete("/{flow_id}/steps/{step_id}", response_model=schemas.Flow)
async def delete_step(request: Request, flow_id: str, step_id: str) -> schemas.Flow:
    services = services_of(request)
    _, meta = _flow(services, flow_id)
    _require_editable(meta)
    if services.supervisor.is_sending(flow_id):
        raise errors.flow_sending()
    if not services.flows.remove_step(flow_id, _position(flow_id, step_id)):
        raise errors.flow_running()
    await services.supervisor.appended(flow_id)
    return services.flow_response(flow_id)


@router.post("/{flow_id}/review", response_model=schemas.Review)
async def review_flow(
    request: Request, flow_id: str, body: schemas.ReviewRequest | None = None
) -> schemas.Review:
    services = services_of(request)
    _flow(services, flow_id)
    asked = body or schemas.ReviewRequest()
    return await review.build(
        services, flow_id, scope=asked.scope, from_position=asked.from_position
    )


@router.post("/{flow_id}/start", response_model=schemas.Flow)
async def start_flow(request: Request, flow_id: str, body: schemas.FlowStart) -> schemas.Flow:
    """Start a draft with exactly the bodies the user reviewed, or nothing."""
    services = services_of(request)
    _, meta = _flow(services, flow_id)
    _refuse_unless_ready(meta)
    _apply_run_values(services, flow_id, body.run_values)
    checked = await review.build(services, flow_id, scope="all")
    _refuse_unless_reviewed(checked, body.review_token)

    # The review awaited Jenkins; decide again on what is true now.
    _, meta = _flow(services, flow_id)
    _refuse_unless_ready(meta)
    _freeze(services, flow_id, checked)
    await services.supervisor.run(flow_id)
    return services.flow_response(flow_id)


@router.post("/{flow_id}/confirm", response_model=schemas.Flow)
async def confirm_held(request: Request, flow_id: str, body: schemas.FlowConfirm) -> schemas.Flow:
    """Release the held steps of a started flow after the user reviewed them."""
    services = services_of(request)
    _, meta = _flow(services, flow_id)
    if meta.status is FlowStatus.DRAFT or meta.status not in ACTIVE_FLOW_STATUSES:
        raise errors.conflict("flow_not_started", "This flow has not started.")
    if services.supervisor.is_sending(flow_id):
        raise errors.flow_sending()
    _apply_run_values(services, flow_id, body.run_values)
    checked = await review.build(services, flow_id, scope="held")
    _refuse_unless_reviewed(checked, body.review_token)

    if services.supervisor.is_sending(flow_id):
        raise errors.flow_sending()
    _freeze(services, flow_id, checked)
    await services.supervisor.confirmed(flow_id)
    return services.flow_response(flow_id)


@router.post("/{flow_id}/stop", response_model=schemas.Flow)
async def stop_flow(request: Request, flow_id: str, body: schemas.FlowStop) -> schemas.Flow:
    services = services_of(request)
    _, meta = _flow(services, flow_id)
    if meta.status not in (FlowStatus.RUNNING, FlowStatus.NEEDS_ATTENTION):
        raise errors.conflict("flow_not_running", "This flow is not running.")
    await services.supervisor.stop(flow_id, abort_current=body.abort_current)
    return services.flow_response(flow_id)


@router.post("/{flow_id}/resume", response_model=schemas.Flow)
async def resume_flow(request: Request, flow_id: str, body: schemas.FlowResume) -> schemas.Flow:
    """Go on with a stopped or failed flow, after reviewing what it would send."""
    services = services_of(request)
    run, meta = _flow(services, flow_id)
    _check_resumable(services, run, meta)
    _apply_run_values(services, flow_id, body.run_values)
    checked = await review.build(
        services, flow_id, scope="resume", from_position=body.from_position
    )
    _refuse_unless_reviewed(checked, body.review_token)

    run, meta = _flow(services, flow_id)
    _check_resumable(services, run, meta)
    _freeze(services, flow_id, checked)
    await services.supervisor.resume(flow_id, from_position=body.from_position)
    return services.flow_response(flow_id)


def _check_resumable(services: Services, run, meta) -> None:
    if meta.status not in (FlowStatus.STOPPED, FlowStatus.FAILED):
        raise errors.conflict("flow_not_resumable", "This flow is not stopped.")
    if any(step.state.value == "rejected" for step in run.steps):
        raise errors.conflict(
            "flow_not_resumable",
            "Jenkins refused a step of this flow. Run it again as a new flow.",
        )
    if services.supervisor.is_sending(run.id):
        raise errors.flow_sending()


def _undecided(run):
    """The step that waits for the user to link its build or end the flow, if one does."""
    return next((step for step in run.steps if step.state is StepState.NEEDS_ATTENTION), None)


def _refuse_unless_settled(run, meta) -> None:
    """A stopped flow with no build still in Jenkins, and nothing left undecided,
    can be cleared from the board."""
    undecided = _undecided(run)
    if undecided is not None:
        raise errors.conflict("flow_active", f"Resolve step {undecided.position + 1} first.")
    if meta.status is not FlowStatus.STOPPED or any(
        step.state.value in presenter.IN_FLIGHT for step in run.steps
    ):
        raise errors.conflict("flow_active", "This flow is still active.")


def _reviewed(web_meta) -> bool:
    return web_meta.frozen and not web_meta.held


def _apply_run_values(
    services: Services, flow_id: str, run_values: dict[str, dict[str, str]]
) -> None:
    _, meta = services.flows.get(flow_id)
    for step_id, values in run_values.items():
        position = _position(flow_id, step_id)
        web_meta = meta.steps.get(position)
        if web_meta is None or _reviewed(web_meta):
            raise errors.flow_running()
        services.flows.update_step(flow_id, position, run_values=values)


def _refuse_unless_reviewed(checked: schemas.Review, token: str) -> None:
    reason = review.refusal(checked, token)
    if reason is not None:
        raise errors.review_refused(reason)


def _freeze(services: Services, flow_id: str, checked: schemas.Review) -> None:
    """Write each reviewed body as the one that will be sent, and release holds."""
    for step in checked.steps:
        body = {item.name: item.value for item in step.sent}
        if not services.flows.freeze_step_params(
            flow_id, step.position, body, destructive=step.destructive
        ):
            raise errors.flow_running()
        services.flows.set_held(flow_id, step.position, False)


@router.post("/{flow_id}/rerun", response_model=schemas.Flow, status_code=201)
async def rerun_flow(
    request: Request, flow_id: str, body: schemas.FlowRerun | None = None
) -> schemas.Flow:
    """The same flow as a fresh copy, optionally retaining the original on the Board.

    `Run again` asks for a copy that is ready, and reviews it at once. The pencil
    asks for one that is open to change, and stops there. Either way it never
    refuses: a saved job Jenkins changed, and one that is gone, come along as they
    are, to be replaced here. Review says so before anything is sent.
    """
    services = services_of(request)
    run, meta = _flow(services, flow_id)
    asked = body or schemas.FlowRerun()
    # Unless keep_source is requested, an ended flow leaves the Board to its
    # copy, which takes the name it is giving up. One still going stays, and the
    # copy is named beside it. A flow already cleared hands nothing over: it is not on the board to
    # begin with. Either way the name is decided before anything is written.
    leaving = meta.status not in ACTIVE_FLOW_STATUSES and not asked.keep_source
    name = naming.free_name(
        run.name, services.flows.board_names(excluding=flow_id if leaving else None)
    )
    new_id = services.flows.create(
        name=name,
        saved_flow_id=services.kept_as(meta.saved_flow_id),
        pinned=meta.pinned,
        created_at=run.created_at,
        editing=asked.editing,
    )
    _copy_steps(services, run, meta, new_id)
    if leaving:
        services.flows.set_cleared(flow_id, True)
        services.publish_flow(flow_id)
    services.publish_flow(new_id)
    return services.flow_response(new_id)


@router.post("/{flow_id}/duplicate", response_model=schemas.Flow, status_code=201)
async def duplicate_flow(request: Request, flow_id: str) -> schemas.Flow:
    """A second flow with the same steps, under a free name, open to change.

    It is a thing of its own: it is not kept as the saved flow the original is,
    so saving it later cannot overwrite that template.
    """
    services = services_of(request)
    run, meta = _flow(services, flow_id)
    copy_id = services.flows.create(
        name=naming.copy_name(run.name, services.flows.board_names()),
        editing=True,
    )
    _copy_steps(services, run, meta, copy_id)
    services.publish_flow(copy_id)
    return services.flow_response(copy_id)


@router.get("/{flow_id}/steps/{step_id}/attention", response_model=schemas.Attention)
async def step_attention(request: Request, flow_id: str, step_id: str) -> schemas.Attention:
    services = services_of(request)
    _flow(services, flow_id)
    position = _position(flow_id, step_id)
    if not attention.is_attention_step(services, flow_id, position):
        raise errors.conflict("step_not_attention", "This step is not waiting for a decision.")
    return await attention.build(services, flow_id, position)


@router.post("/{flow_id}/steps/{step_id}/link", response_model=schemas.Flow)
async def link_build(
    request: Request, flow_id: str, step_id: str, body: schemas.LinkBuild
) -> schemas.Flow:
    """Attach the build the user recognised. Nothing is sent."""
    services = services_of(request)
    _flow(services, flow_id)
    position = _position(flow_id, step_id)
    if not attention.is_attention_step(services, flow_id, position):
        raise errors.conflict("step_not_attention", "This step is not waiting for a decision.")
    found = await attention.build(services, flow_id, position)
    candidate = next((item for item in found.candidates if item.number == body.build_number), None)
    if candidate is None:
        raise errors.conflict("build_not_found", "That build no longer matches what JK sent.")
    linked = services.store.link_build_if_attention(
        flow_id, position, build_number=candidate.number, build_url=candidate.url
    )
    if not linked:
        raise errors.conflict("step_not_attention", "This step is not waiting for a decision.")
    await services.supervisor.linked(flow_id)
    return services.flow_response(flow_id)


@router.post("/{flow_id}/close", response_model=schemas.Flow)
async def close_flow(
    request: Request, flow_id: str, body: schemas.FlowClose | None = None
) -> schemas.Flow:
    """End a flow whose step waits for a decision, stopped or not. Nothing is sent."""
    services = services_of(request)
    run, meta = _flow(services, flow_id)
    waiting = meta.status is FlowStatus.NEEDS_ATTENTION or (
        meta.status is FlowStatus.STOPPED and _undecided(run) is not None
    )
    if not waiting:
        raise errors.conflict("flow_not_attention", "This flow is not waiting for a decision.")
    note = ended_without_link((body or schemas.FlowClose()).build_numbers)
    for step in run.steps:
        services.store.mark_rejected_if_attention(flow_id, step.position, message=note)
    await services.supervisor.close(flow_id)
    return services.flow_response(flow_id)


def _position(flow_id: str, step_id: str) -> int:
    try:
        owner, position = presenter.split_step_id(step_id)
    except ValueError as exc:
        raise errors.not_found(f"step {step_id}") from exc
    if owner and owner != flow_id:
        raise errors.not_found(f"step {step_id}")
    return position
