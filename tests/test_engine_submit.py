from __future__ import annotations

import logging

import httpx
import pytest

from jk.engine.runner import RunEngine
from jk.errors import AmbiguousSubmission, SubmissionPreflightFailed, SubmissionRejected
from jk.jenkins.client import JenkinsConfig, build_client
from jk.jenkins.read import JenkinsReader
from jk.jenkins.submit import JenkinsSubmitter, SubmitOutcome
from jk.store.models import StepState
from jk.store.store import RunStore
from tests.seed import SeedStep, seed_run, step

JENKINS = JenkinsConfig(base_url="https://jenkins.invalid", user_id="t", api_token="t")


class Reader:
    async def next_build_number(self, _rest_path: str) -> int:
        return 9930


class Submitter:
    def __init__(self, result: SubmitOutcome | Exception | None = None) -> None:
        self.post_count = 0
        self.last_body: dict[str, str] | None = None
        self.result = result or SubmitOutcome(
            queue_url="https://jenkins.invalid/queue/item/183759/",
            pre_existing=False,
        )

    async def submit(self, _rest_path: str, body: dict[str, str]) -> SubmitOutcome:
        self.post_count += 1
        self.last_body = body
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def make_job() -> SeedStep:
    return step("create", {"BRANCH": "snapshot", "LOAD_SAMPLE": "true"})


def make_engine(store: RunStore, submitter: Submitter) -> RunEngine:
    return RunEngine(store, Reader(), submitter)


async def test_submit_uses_complete_persisted_map_once(store) -> None:
    submitter = Submitter()
    engine = make_engine(store, submitter)
    run_id = seed_run(store, make_job())

    state = await engine.submit_step(run_id, 0)

    assert state is StepState.QUEUED
    assert submitter.post_count == 1
    assert submitter.last_body == {"BRANCH": "snapshot", "LOAD_SAMPLE": "true"}


async def test_a_second_submit_observes_the_existing_state_without_posting(store) -> None:
    submitter = Submitter()
    engine = make_engine(store, submitter)
    run_id = seed_run(store, make_job())

    first = await engine.submit_step(run_id, 0)
    second = await engine.submit_step(run_id, 0)

    assert first is StepState.QUEUED
    assert second is StepState.QUEUED
    assert submitter.post_count == 1


@pytest.mark.parametrize("failure", ["connection", 401, 403, 404, 503])
async def test_a_failed_preflight_leaves_no_submission_evidence_or_rejection(store, failure):
    def handler(request: httpx.Request) -> httpx.Response:
        if failure == "connection":
            raise httpx.ConnectError("offline", request=request)
        return httpx.Response(failure, text="response content is not an error message")

    submitter = Submitter()
    client = build_client(JENKINS, httpx.MockTransport(handler))
    run_id = seed_run(store, make_job())
    engine = RunEngine(store, JenkinsReader(client), submitter)

    async with client:
        with pytest.raises(SubmissionPreflightFailed, match="Nothing was sent"):
            await engine.submit_step(run_id, 0)

    run = store.get_run(run_id)
    unsent = run.steps[0]
    assert unsent.state is StepState.PREPARED
    assert unsent.submitted_at is None
    assert unsent.search_from_build_number is None
    assert unsent.search_from_timestamp is None
    assert unsent.queue_url is None
    assert unsent.build_number is None
    assert run.error_kind is None
    assert submitter.post_count == 0


@pytest.mark.parametrize(
    ("error", "state"),
    [
        (SubmissionRejected("not buildable"), StepState.REJECTED),
        (AmbiguousSubmission("unknown result"), StepState.NEEDS_ATTENTION),
    ],
)
async def test_submission_outcomes_are_persisted_without_retry(store, error, state) -> None:
    submitter = Submitter(error)
    engine = make_engine(store, submitter)
    run_id = seed_run(store, make_job())

    result = await engine.submit_step(run_id, 0)

    assert result is state
    assert store.get_run(run_id).steps[0].state is state
    assert submitter.post_count == 1


async def test_rejected_response_body_never_leaks_into_exception_storage_or_logs(
    store, caplog
) -> None:
    sentinel = "UNIQUE_REJECTED_RESPONSE_SECRET_7f2d"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(400, text=f"proxy echoed {sentinel}")
        return httpx.Response(200, json={"nextBuildNumber": 1})

    client = build_client(JENKINS, httpx.MockTransport(handler))
    run_id = seed_run(store, step("rejected", {"P": "value"}))
    submitter = JenkinsSubmitter(client)
    engine = RunEngine(store, JenkinsReader(client), submitter)

    async with client:
        with pytest.raises(SubmissionRejected) as raised:
            await submitter.submit("job/folder/job/rejected", {"P": "value"})
        with caplog.at_level(logging.INFO):
            state = await engine.submit_step(run_id, 0)

    run = store.get_run(run_id)

    assert state is StepState.REJECTED
    assert sentinel not in str(raised.value)
    assert sentinel not in repr(run)
    assert sentinel not in (run.steps[0].note or "")
    assert sentinel not in (run.error_message or "")
    assert sentinel not in caplog.text


async def test_a_password_parameter_reaches_the_post_body_unmasked(store) -> None:
    """A password is a configured value: submitted and stored like any other."""
    literal = "literal-password-9f3a"
    job = step("literal-password", {"BRANCH": "snapshot", "ADMIN_PASSWORD": literal})
    posted: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            posted.append(request.content.decode())
            return httpx.Response(
                201, headers={"Location": "https://jenkins.invalid/queue/item/1/"}
            )
        return httpx.Response(200, json={"nextBuildNumber": 1})

    client = build_client(JENKINS, httpx.MockTransport(handler))
    run_id = seed_run(store, job)
    engine = RunEngine(store, JenkinsReader(client), JenkinsSubmitter(client))

    async with client:
        state = await engine.submit_step(run_id, 0)

    stored = store.get_step_inputs(run_id, 0)

    assert state is StepState.QUEUED
    assert len(posted) == 1
    assert literal in posted[0]
    assert stored["ADMIN_PASSWORD"] == literal
