from __future__ import annotations

import asyncio

import pytest

from jk.engine.runner import RunEngine
from jk.jenkins.models import BuildInfo, QueueInfo
from jk.jenkins.submit import SubmitOutcome
from jk.store.models import StepState
from jk.store.store import RunStore
from tests.seed import SeedStep, seed_run, step


class Reader:
    def __init__(self, results: list[str]) -> None:
        self.results = iter(results)
        self.next_number = 1

    async def next_build_number(self, _rest_path: str) -> int:
        number = self.next_number
        self.next_number += 1
        return number

    async def queue_item(self, queue_url: str) -> QueueInfo:
        queue_id = int(queue_url.rstrip("/").split("/")[-1])
        return QueueInfo(queue_id, False, 1, f"https://jenkins.invalid/job/{queue_id}/1/")

    async def build_by_url(self, url: str) -> BuildInfo:
        result = next(self.results)
        number = int(url.rstrip("/").split("/")[-2])
        return BuildInfo(number, number, False, result, 1, 10, 10, url)


class Submitter:
    def __init__(self) -> None:
        self.posts: list[str] = []

    async def submit(self, rest_path: str, _body: dict[str, str]) -> SubmitOutcome:
        self.posts.append(rest_path)
        queue_id = 100 + len(self.posts)
        return SubmitOutcome(f"https://jenkins.invalid/queue/item/{queue_id}/", False)


def make_job(job_id: str, *, destructive: bool = False) -> SeedStep:
    body = (
        {"CLUSTER": "example-cluster", "NAMESPACE": "example-ns"} if destructive else {"P": job_id}
    )
    return step(job_id, body, destructive=destructive)


def make_engine(store, results: list[str]) -> tuple[RunEngine, Submitter]:
    submitter = Submitter()
    engine = RunEngine(store, Reader(results), submitter, sleep=lambda _seconds: _no_sleep())
    return engine, submitter


async def _no_sleep() -> None:
    return None


async def test_concurrent_submissions_produce_one_post(tmp_path) -> None:
    path = tmp_path / "runs.db"
    first_store = RunStore.open(path)
    second_store = RunStore.open(path)
    run_id = seed_run(first_store, make_job("first", destructive=True))
    first_engine, first_submitter = make_engine(first_store, ["SUCCESS", "SUCCESS"])
    second_engine, second_submitter = make_engine(second_store, ["SUCCESS", "SUCCESS"])
    post_started = asyncio.Event()
    release_post = asyncio.Event()
    original_submit = first_submitter.submit

    async def blocked_submit(rest_path: str, _body: dict[str, str]) -> SubmitOutcome:
        post_started.set()
        await release_post.wait()
        return await original_submit(rest_path, _body)

    first_submitter.submit = blocked_submit
    first_task = asyncio.create_task(first_engine.submit_step(run_id, 0))
    await post_started.wait()

    second_result = await second_engine.submit_step(run_id, 0)
    release_post.set()
    results = [
        await first_task,
        second_result,
    ]

    assert results == [StepState.QUEUED, StepState.SUBMIT_PENDING]
    assert first_submitter.posts + second_submitter.posts == [
        "job/folder/job/first",
    ]
    first_store.close()
    second_store.close()


async def test_interruption_after_claim_recovers_to_attention_without_retry(tmp_path) -> None:
    path = tmp_path / "runs.db"
    store = RunStore.open(path)
    run_id = seed_run(store, make_job("delete", destructive=True))
    engine, submitter = make_engine(store, ["SUCCESS"])
    post_started = asyncio.Event()
    release_post = asyncio.Event()
    original_submit = submitter.submit

    async def blocked_submit(rest_path: str, _body: dict[str, str]) -> SubmitOutcome:
        post_started.set()
        await release_post.wait()
        return await original_submit(rest_path, _body)

    submitter.submit = blocked_submit
    task = asyncio.create_task(engine.submit_step(run_id, 0))
    await post_started.wait()
    assert store.get_run(run_id).steps[0].state is StepState.SUBMIT_PENDING
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    store.close()

    recovered = RunStore.open(path)
    assert recovered.recover_pending_submissions() == [run_id]
    assert recovered.get_run(run_id).steps[0].state is StepState.NEEDS_ATTENTION
    recovered.close()
