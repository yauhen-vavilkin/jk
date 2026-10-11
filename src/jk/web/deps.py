"""Everything one `jk serve` process owns, assembled once.

FastAPI reads this off `app.state`. It exists so a route can ask for a flow
without knowing which repository, which supervisor and which cache answer
together, and so the tests can assemble the same thing over a MockTransport.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

import httpx
from fastapi import Request

from jk.engine.drift import DriftWatcher
from jk.engine.flows import FlowSupervisor
from jk.engine.jenkins_index import JenkinsIndexer
from jk.engine.runner import RunEngine, SleepFn, rest_path_of
from jk.errors import JenkinsAuthError, JenkinsUnavailable, TargetNotFound
from jk.jenkins.abort import JenkinsAborter
from jk.jenkins.read import JenkinsReader
from jk.jenkins.submit import JenkinsSubmitter
from jk.store.flows import FlowStore
from jk.store.jenkins_jobs import JenkinsJobStore
from jk.store.models import StepState
from jk.store.presets import PresetStore
from jk.store.records import ACTIVE_FLOW_STATUSES, FlowMeta, FlowStatus, Preset, SavedFlow
from jk.store.saved_flows import SavedFlowStore
from jk.store.store import RunStore
from jk.web import errors, presenter, schemas
from jk.web.events import EventBus

#: How soon a step of another flow reaches its namespace, most urgent first: a
#: build that is, or is about to be, in Jenkins; one that may be; a later step
#: of a flow that is running. A planned step counts only in a running flow.
URGENCY = {
    StepState.SUBMIT_PENDING: 0,
    StepState.QUEUED: 0,
    StepState.RUNNING: 0,
    StepState.NEEDS_ATTENTION: 1,
    StepState.PREPARED: 2,
}


@dataclass
class JenkinsHealth:
    """What the top bar says about the controller."""

    reachable: bool = True
    auth_ok: bool = True
    since: int | None = None

    def record(self, *, reachable: bool, auth_ok: bool = True) -> bool:
        """Remember the latest answer. True when the answer changed."""
        if (reachable, auth_ok) == (self.reachable, self.auth_ok):
            return False
        self.reachable, self.auth_ok = reachable, auth_ok
        self.since = int(time.time())
        return True


@dataclass
class Services:
    store: RunStore
    presets: PresetStore
    saved_flows: SavedFlowStore
    jenkins_jobs: JenkinsJobStore
    flows: FlowStore
    reader: JenkinsReader
    engine: RunEngine
    supervisor: FlowSupervisor
    drift: DriftWatcher
    indexer: JenkinsIndexer
    bus: EventBus
    base_url: str
    health: JenkinsHealth = field(default_factory=JenkinsHealth)

    def preset_map(self) -> dict[str, Preset]:
        return {item.id: item for item in self.presets.list()}

    def flow_response(self, flow_id: str) -> schemas.Flow:
        run, meta = self.flows.get(flow_id)
        presets = self.preset_map()
        frozen = {
            step.position: self.store.get_step_inputs(flow_id, step.position)
            for step in run.steps
            if meta.steps[step.position].frozen
        }
        return presenter.flow(
            run,
            meta,
            presets,
            frozen,
            base_url=self.base_url,
            saved_flow_id=self.kept_as(meta.saved_flow_id),
            typical=self.jenkins_jobs.typical_durations(),
        )

    def saved_flow_responses(self, saved_flows: list[SavedFlow]) -> list[schemas.SavedFlow]:
        """Saved flows for the side column and the library, each with its estimate."""
        presets = self.preset_map()
        typical = self.jenkins_jobs.typical_durations()
        return [presenter.saved_flow(item, presets, typical) for item in saved_flows]

    def kept_as(self, saved_flow_id: str | None) -> str | None:
        """The saved flow a flow is kept as, or nothing once that saved flow is gone."""
        if not saved_flow_id:
            return None
        try:
            return self.saved_flows.get(saved_flow_id).id
        except KeyError:
            return None

    def flow_responses(self) -> list[schemas.Flow]:
        """Flows for the board and for History.

        A flow cleared from the board is still listed: `cleared` is on each flow,
        the board leaves those out itself, and History is where they stay.
        """
        return [self.flow_response(flow_id) for flow_id in self.flows.list(include_cleared=True)]

    def targets_of(self, flow_id: str) -> dict[int, tuple[str, str]]:
        """CLUSTER and NAMESPACE per step, from what that step sends."""
        run, meta = self.flows.get(flow_id)
        presets = self.preset_map()
        found: dict[int, tuple[str, str]] = {}
        for step in run.steps:
            web_meta = meta.steps[step.position]
            values = (
                self.store.get_step_inputs(flow_id, step.position)
                if web_meta.frozen
                else _planned_values(presets.get(web_meta.preset_id), web_meta.run_values)
            )
            found[step.position] = (
                values.get("CLUSTER", "").strip(),
                values.get("NAMESPACE", "").strip(),
            )
        return found

    def same_target(self, flow_id: str) -> list[schemas.SameTarget]:
        """Other flows that are, or may be, running on a CLUSTER and NAMESPACE of this one.

        Each is named once, by its most urgent matching step. A draft is not
        running, and neither is a step a stopped flow never sent.
        """
        mine = {target for target in self.targets_of(flow_id).values() if target[0] and target[1]}
        if not mine:
            return []
        found: list[schemas.SameTarget] = []
        for other_id in self.flows.list(active=True):
            if other_id == flow_id:
                continue
            other_run, other_meta = self.flows.get(other_id)
            if other_meta.status not in ACTIVE_FLOW_STATUSES - {FlowStatus.DRAFT}:
                continue
            targets = self.targets_of(other_id)
            matching = [
                step
                for step in other_run.steps
                if _may_reach(step.state, step.position, other_meta)
                and targets[step.position] in mine
            ]
            if not matching:
                continue
            step = min(matching, key=lambda item: (URGENCY[item.state], item.position))
            found.append(
                schemas.SameTarget(
                    flow_id=other_id,
                    flow_name=other_run.name,
                    position=step.position,
                    state=presenter.STATE_WORDS[step.state],
                    cluster=targets[step.position][0],
                    namespace=targets[step.position][1],
                    build_number=step.build_number,
                )
            )
        return found

    def publish_flow(self, flow_id: str) -> None:
        if self.flows.find(flow_id) is None:
            return
        self.bus.publish_flow(flow_id, self.flow_response(flow_id).model_dump())

    def publish_preset(self, preset_id: str) -> None:
        found = self.presets.find(preset_id)
        if found is not None:
            self.bus.publish(
                "preset.updated", presenter.preset(found, base_url=self.base_url).model_dump()
            )

    def publish_saved_flow(self, saved_flow_id: str) -> schemas.SavedFlow:
        [payload] = self.saved_flow_responses([self.saved_flows.get(saved_flow_id)])
        self.bus.publish("saved_flow.updated", payload.model_dump())
        return payload

    async def read_definitions(self, job_path: str) -> dict:
        """The job's live definitions; a missing job is a 404, a refusal a recorded 502."""
        try:
            found = await self.reader.parameter_definitions(rest_path_of(job_path))
        except JenkinsAuthError as exc:
            await self.check_token()
            refused = errors.JOB_REFUSED if self.health.auth_ok else errors.JENKINS_AUTH
            raise errors.ApiError(502, "jenkins_auth", refused) from exc
        except TargetNotFound as exc:
            raise errors.ApiError(404, "not_found", f"Jenkins has no job {job_path}.") from exc
        except JenkinsUnavailable as exc:
            self.health.record(reachable=False)
            raise errors.ApiError(502, "jenkins_unreachable", errors.JENKINS_UNREACHABLE) from exc
        self.health.record(reachable=True, auth_ok=True)
        return found

    async def check_token(self) -> None:
        """Ask Jenkins whose token this is: without an accepted token nothing can run."""
        try:
            await self.reader.whoami()
        except JenkinsAuthError:
            changed = self.health.record(reachable=True, auth_ok=False)
        except JenkinsUnavailable, TargetNotFound:
            changed = self.health.record(reachable=False)
        else:
            changed = self.health.record(reachable=True, auth_ok=True)
        if changed:
            self.bus.publish("jenkins.status", self.jenkins_status().model_dump())

    def jenkins_status(self) -> schemas.JenkinsStatus:
        return schemas.JenkinsStatus(
            url=self.base_url,
            reachable=self.health.reachable,
            since=presenter.moment(self.health.since),
            auth_ok=self.health.auth_ok,
        )


def services_of(request: Request) -> Services:
    return request.app.state.services


def _may_reach(state: StepState, position: int, meta: FlowMeta) -> bool:
    if state not in URGENCY or meta.steps[position].skipped:
        return False
    return URGENCY[state] < 2 or meta.status is FlowStatus.RUNNING


def _planned_values(preset: Preset | None, run_values: dict[str, str]) -> dict[str, str]:
    return {} if preset is None else preset.sent_values(run_values)


def build_services(
    *,
    store: RunStore,
    client: httpx.AsyncClient,
    base_url: str,
    sleep: SleepFn = asyncio.sleep,
) -> Services:
    """Wire one process worth of JK. The client owns the credentials, nothing else does."""
    presets = PresetStore(store)
    saved_flows = SavedFlowStore(store)
    jenkins_jobs = JenkinsJobStore(store)
    flows = FlowStore(store)
    reader = JenkinsReader(client)
    engine = RunEngine(store, reader, JenkinsSubmitter(client), sleep=sleep)

    # The supervisor announces a flow it has just changed; the announcement
    # needs the assembled services, which need the supervisor.
    assembled: list[Services] = []

    async def announce(flow_id: str) -> None:
        assembled[0].publish_flow(flow_id)

    services = Services(
        store=store,
        presets=presets,
        saved_flows=saved_flows,
        jenkins_jobs=jenkins_jobs,
        flows=flows,
        reader=reader,
        engine=engine,
        supervisor=FlowSupervisor(
            store, flows, presets, engine, JenkinsAborter(client), on_change=announce
        ),
        drift=DriftWatcher(presets, reader),
        indexer=JenkinsIndexer(jenkins_jobs, reader),
        bus=EventBus(),
        base_url=base_url,
    )
    assembled.append(services)
    return services
