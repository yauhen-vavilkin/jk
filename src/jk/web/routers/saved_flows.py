"""Saved flows: named templates of steps, conditions and launch values."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from jk.store.records import ACTIVE_FLOW_STATUSES, FlowStatus
from jk.web import errors, naming, schemas
from jk.web.deps import Services, services_of

router = APIRouter(prefix="/api/saved-flows", tags=["saved flows"])


@router.get("", response_model=list[schemas.SavedFlow])
async def list_saved_flows(request: Request) -> list[schemas.SavedFlow]:
    services = services_of(request)
    return services.saved_flow_responses(services.saved_flows.list())


def _names(services: Services, *, excluding: str | None = None) -> list[str]:
    return [item.name for item in services.saved_flows.list() if item.id != excluding]


def _own_name(services: Services, wanted: str, *, excluding: str | None = None) -> str:
    """The user typed this name, so a clash is refused rather than worked around."""
    name = naming.tidy(wanted)
    if not name:
        raise errors.name_empty()
    if naming.is_taken(name, _names(services, excluding=excluding)):
        raise errors.conflict("name_taken", "A saved flow is already called that.")
    return name


@router.patch("/{saved_flow_id}", response_model=schemas.SavedFlow)
async def patch_saved_flow(
    request: Request, saved_flow_id: str, body: schemas.SavedFlowPatch
) -> schemas.SavedFlow:
    """Change the name, and keep the steps the server holds.

    The steps are read here rather than sent back: a panel that missed the
    latest save would otherwise write the steps it last saw over it.
    """
    services = services_of(request)
    existing = _existing(services, saved_flow_id)
    name = (
        existing.name
        if body.name is None
        else _own_name(services, body.name, excluding=saved_flow_id)
    )
    services.saved_flows.save(
        flow_id=saved_flow_id,
        name=name,
        steps=existing.steps,
    )
    return services.publish_saved_flow(saved_flow_id)


@router.post("/{saved_flow_id}/duplicate", response_model=schemas.SavedFlow, status_code=201)
async def duplicate_saved_flow(request: Request, saved_flow_id: str) -> schemas.SavedFlow:
    """A second template with the same steps, under a free name."""
    services = services_of(request)
    original = _existing(services, saved_flow_id)
    copy = services.saved_flows.save(
        name=naming.copy_name(original.name, _names(services)),
        steps=original.steps,
    )
    return services.publish_saved_flow(copy.id)


@router.delete("/{saved_flow_id}", status_code=204)
async def delete_saved_flow(request: Request, saved_flow_id: str) -> Response:
    services = services_of(request)
    _existing(services, saved_flow_id)
    services.saved_flows.delete(saved_flow_id)
    return Response(status_code=204)


@router.post("/{saved_flow_id}/instantiate", response_model=schemas.Flow, status_code=201)
async def instantiate(
    request: Request, saved_flow_id: str, body: schemas.Instantiate
) -> schemas.Flow:
    """A new draft, or the same steps appended to a flow that is already there."""
    services = services_of(request)
    template = _existing(services, saved_flow_id)

    if body.flow_id:
        found = services.flows.find(body.flow_id)
        if found is None:
            raise errors.not_found(f"flow {body.flow_id}")
        _, meta = found
        if meta.status not in ACTIVE_FLOW_STATUSES:
            raise errors.conflict("flow_finished", "This flow has finished; start a new one.")
        if meta.status is FlowStatus.DRAFT and not meta.editing:
            raise errors.conflict("flow_not_editing", "Turn editing on to change this flow.")
        flow_id = body.flow_id
        started = meta.status is not FlowStatus.DRAFT
        running = meta.status is FlowStatus.RUNNING
    else:
        flow_id = ""
        started = running = False

    # Every saved job is checked before anything is added, so a refusal leaves
    # neither a half-filled flow nor an empty draft behind.
    presets = []
    for step in template.steps:
        preset = services.presets.find(step.preset_id)
        if preset is None:
            raise errors.not_found(f"saved job {step.preset_id}")
        if preset.drift is not None:
            raise errors.preset_drifted()
        presets.append(preset)

    if body.flow_id:
        if services.supervisor.is_sending(flow_id):
            raise errors.flow_sending()
    else:
        # It was built once already, so it lands ready to run, not open to change.
        # The board named it, so a second copy takes the next free name.
        flow_id = services.flows.create(
            name=naming.free_name(template.name, services.flows.board_names()),
            saved_flow_id=template.id,
            editing=False,
        )

    for step, preset in zip(template.steps, presets, strict=True):
        services.flows.append_step(
            flow_id,
            preset_id=preset.id,
            preset_name=preset.name,
            job_path=preset.job_path,
            destructive=preset.destructive,
            summary_params=preset.summary_params,
            condition=step.condition,
            run_values=dict(step.run_values),
            added_while_running=running,
            held=started,
        )
    await services.supervisor.appended(flow_id)
    return services.flow_response(flow_id)


def _existing(services: Services, saved_flow_id: str):
    try:
        return services.saved_flows.get(saved_flow_id)
    except KeyError as exc:
        raise errors.not_found(f"saved flow {saved_flow_id}") from exc
