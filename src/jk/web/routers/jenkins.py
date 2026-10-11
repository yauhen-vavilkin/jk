"""The Jenkins index the Library searches, and what the top bar says."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from jk.engine.drift import snapshot_of
from jk.web import schemas
from jk.web.deps import services_of

router = APIRouter(prefix="/api/jenkins", tags=["jenkins"])


@router.get("/jobs", response_model=list[schemas.JenkinsJob])
async def list_jobs(request: Request, q: str = "") -> list[schemas.JenkinsJob]:
    services = services_of(request)
    return [
        schemas.JenkinsJob(
            job_path=job.job_path,
            name=job.name,
            folder=job.folder,
            param_count=job.param_count,
            run_count=job.run_count,
            url=job.url,
        )
        for job in services.jenkins_jobs.search(q)
    ]


@router.post("/jobs/refresh", status_code=204)
async def refresh_jobs(request: Request) -> Response:
    services = services_of(request)
    await services.indexer.refresh()
    services.bus.publish("index.refreshed", {})
    return Response(status_code=204)


@router.get("/jobs/{job_path:path}/definitions", response_model=list[schemas.ParamDefinition])
async def job_definitions(request: Request, job_path: str) -> list[schemas.ParamDefinition]:
    definitions = await services_of(request).read_definitions(job_path)
    return [
        schemas.ParamDefinition(
            name=item.name, type=item.type, default=item.default, choices=item.choices
        )
        for item in snapshot_of(definitions)
    ]


@router.post("/check", response_model=schemas.JenkinsStatus)
async def check(request: Request) -> schemas.JenkinsStatus:
    """Ask Jenkins again whether it accepts the token; the panel does this on every open."""
    services = services_of(request)
    await services.check_token()
    return services.jenkins_status()


@router.get("/status", response_model=schemas.JenkinsStatus)
async def status(request: Request) -> schemas.JenkinsStatus:
    """While Jenkins is unreachable, each read asks it again: the top bar says it retries."""
    services = services_of(request)
    if not services.health.reachable:
        await services.check_token()
    return services.jenkins_status()
