"""Saved jobs: read, write, repair."""

from __future__ import annotations

from dataclasses import replace

from fastapi import APIRouter, Request, Response

from jk.engine.drift import diff, snapshot_of
from jk.jenkins.models import ERROR_PLACEHOLDER
from jk.store.records import DefinitionSnapshot, ParamMode, ParamSetting, Preset
from jk.web import errors, naming, presenter, schemas
from jk.web.deps import Services, services_of

router = APIRouter(prefix="/api/presets", tags=["presets"])


def _settings(params: dict[str, schemas.ParamSetting]) -> dict[str, ParamSetting]:
    return {
        name: ParamSetting(
            mode=ParamMode(setting.mode), value=setting.value, last_value=setting.last_value
        )
        for name, setting in params.items()
    }


def _placeholder(definition: DefinitionSnapshot | None, value: str | None) -> bool:
    """Jenkins' Active Choices `error`: never a value, and never kept as the last one."""
    return (
        definition is not None
        and definition.type == "CascadeChoiceParameter"
        and (value or "").strip() == ERROR_PLACEHOLDER
    )


def _without_placeholders(
    params: dict[str, ParamSetting], definitions: tuple[DefinitionSnapshot, ...]
) -> dict[str, ParamSetting]:
    known = {item.name: item for item in definitions}
    return {
        name: replace(setting, last_value=None)
        if _placeholder(known.get(name), setting.last_value)
        else setting
        for name, setting in params.items()
    }


def _check_values(
    params: dict[str, ParamSetting], definitions: tuple[DefinitionSnapshot, ...]
) -> None:
    """A saved job may only name parameters Jenkins defines, with no empty password
    and no Active Choices placeholder (spec.md section 6)."""
    known = {item.name: item for item in definitions}
    for name, setting in params.items():
        if known and name not in known:
            raise errors.param_not_defined(name)
        definition = known.get(name)
        if (
            definition is not None
            and definition.type == "PasswordParameterDefinition"
            and setting.mode is ParamMode.FIXED
            and not (setting.value or "").strip()
        ):
            raise errors.password_empty()
        if setting.mode is ParamMode.FIXED and _placeholder(definition, setting.value):
            raise errors.placeholder_value(name)


def _summary(
    params: dict[str, ParamSetting], definitions: tuple[DefinitionSnapshot, ...]
) -> tuple[str, ...]:
    """What a card shows is derived, never configured: the first four sent values,
    in the order Jenkins declares them."""
    sent = (ParamMode.FIXED, ParamMode.ASK)
    names = [item.name for item in definitions if item.name in params]
    return tuple(name for name in names if params[name].mode in sent)[:4]


def _found(services: Services, preset_id: str) -> Preset:
    found = services.presets.find(preset_id)
    if found is None:
        raise errors.not_found(f"saved job {preset_id}")
    return found


@router.get("", response_model=list[schemas.Preset])
async def list_presets(request: Request) -> list[schemas.Preset]:
    services = services_of(request)
    return [presenter.preset(item, base_url=services.base_url) for item in services.presets.list()]


@router.post("", response_model=schemas.Preset, status_code=201)
async def create_preset(request: Request, body: schemas.PresetCreate) -> schemas.Preset:
    services = services_of(request)
    definitions = snapshot_of(await services.read_definitions(body.job_path))
    params = _without_placeholders(_settings(body.params), definitions)
    _check_values(params, definitions)
    for definition in definitions:
        params.setdefault(definition.name, ParamSetting(mode=ParamMode.DEFAULT))
    created = services.presets.create(
        name=body.name,
        operation=body.operation,
        job_path=body.job_path,
        destructive=body.destructive,
        summary_params=_summary(params, definitions),
        params=params,
        definitions=definitions,
    )
    services.publish_preset(created.id)
    return presenter.preset(created, base_url=services.base_url)


@router.put("/{preset_id}", response_model=schemas.Preset)
async def update_preset(
    request: Request, preset_id: str, body: schemas.PresetUpdate
) -> schemas.Preset:
    services = services_of(request)
    current = _found(services, preset_id)
    params = (
        None
        if body.params is None
        else _without_placeholders(_settings(body.params), current.definitions)
    )
    if params is not None:
        _check_values(params, current.definitions)
    updated = services.presets.update(
        preset_id,
        name=body.name,
        operation=body.operation,
        destructive=body.destructive,
        summary_params=_summary(params or current.params, current.definitions),
        params=params,
    )
    services.publish_preset(preset_id)
    return presenter.preset(updated, base_url=services.base_url)


@router.delete("/{preset_id}", status_code=204)
async def delete_preset(request: Request, preset_id: str) -> Response:
    services = services_of(request)
    _found(services, preset_id)
    used = services.presets.used_by(preset_id)
    if used:
        steps = "that step" if len(used) == 1 else "those steps"
        raise errors.conflict("preset_in_use", f"{_used_by(used)}. Remove {steps} first.")
    services.presets.delete(preset_id)
    return Response(status_code=204)


@router.post("/{preset_id}/duplicate", response_model=schemas.Preset, status_code=201)
async def duplicate_preset(request: Request, preset_id: str) -> schemas.Preset:
    services = services_of(request)
    original = _found(services, preset_id)
    copy = services.presets.create(
        name=naming.copy_name(original.name, [item.name for item in services.presets.list()]),
        operation=original.operation,
        job_path=original.job_path,
        destructive=original.destructive,
        summary_params=original.summary_params,
        params=dict(original.params),
        definitions=original.definitions,
        drift=original.drift,
    )
    services.publish_preset(copy.id)
    return presenter.preset(copy, base_url=services.base_url)


@router.post("/{preset_id}/repair", response_model=schemas.Preset)
async def repair_preset(
    request: Request, preset_id: str, body: schemas.RepairRequest
) -> schemas.Preset:
    """Read the job again and settle every difference the user decided on."""
    services = services_of(request)
    current = _found(services, preset_id)
    live = snapshot_of(await services.read_definitions(current.job_path))
    known = {item.name: item for item in live}

    params = dict(current.params)
    for name in list(params):
        if name not in known and body.decisions.get(name, "drop") == "drop":
            params.pop(name)
    for name, definition in known.items():
        decision = body.decisions.get(name)
        if decision in ("fixed", "ask"):
            # An asked value that never ran has no last value; Jenkins' default is not one.
            fallback = None if _placeholder(definition, definition.default) else definition.default
            params[name] = ParamSetting(
                mode=ParamMode(decision),
                value=body.values.get(name) if decision == "fixed" else None,
                last_value=body.values.get(name) or (fallback if decision == "fixed" else None),
            )
        elif decision == "default" or name not in params:
            params[name] = ParamSetting(mode=ParamMode.DEFAULT)

    _check_values(params, live)
    services.presets.update(preset_id, params=params, definitions=live)
    remaining = diff(services.presets.get(preset_id), live)
    services.presets.set_drift(preset_id, remaining)
    services.publish_preset(preset_id)
    return presenter.preset(services.presets.get(preset_id), base_url=services.base_url)


@router.get("/{preset_id}/usage", response_model=schemas.PresetUsage)
async def preset_usage(request: Request, preset_id: str) -> schemas.PresetUsage:
    services = services_of(request)
    _found(services, preset_id)
    return schemas.PresetUsage(
        steps=[
            schemas.PresetUse(flow_id=flow_id, flow_name=name, position=position)
            for flow_id, name, position in services.presets.used_by(preset_id)
        ],
    )


def _used_by(used: list[tuple[str, str, int]]) -> str:
    """`Used by Nightly Cypress, step 2 · Rebuild, step 1`: each flow, and the step in it."""
    return "Used by " + " · ".join(f"{name}, step {position + 1}" for _, name, position in used)
