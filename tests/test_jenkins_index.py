"""Crawling the controller for the jobs the Library can search."""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from jk.engine.jenkins_index import JenkinsIndexer
from jk.jenkins.read import JenkinsReader
from jk.store.jenkins_jobs import JenkinsJobStore
from jk.store.store import RunStore

FOLDER = "com.cloudbees.hudson.plugins.folder.Folder"
JOB = "org.jenkinsci.plugins.workflow.job.WorkflowJob"


def job(name: str, params: list[str]) -> dict:
    return {
        "name": name,
        "_class": JOB,
        "url": f"https://jenkins.invalid/job/{name}/",
        "property": [{"parameterDefinitions": [{"name": item} for item in params]}],
    }


@pytest.fixture
def jobs(store) -> JenkinsJobStore:
    return JenkinsJobStore(store)


def indexer(jobs: JenkinsJobStore, payloads: dict[str, dict], calls: list[str]) -> JenkinsIndexer:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        payload = payloads.get(request.url.path)
        if payload is None:
            return httpx.Response(404, text="no")
        return httpx.Response(200, json=payload)

    client = httpx.AsyncClient(
        base_url="https://jenkins.invalid", transport=httpx.MockTransport(handler)
    )
    return JenkinsIndexer(jobs, JenkinsReader(client))


async def test_only_parameterised_jobs_are_indexed(jobs: JenkinsJobStore) -> None:
    payload = {
        "jobs": [
            job("takesParameters", ["CLUSTER", "NAMESPACE"]),
            {"name": "takesNone", "_class": JOB, "url": "", "property": []},
        ]
    }
    await indexer(jobs, {"/api/json": payload}, []).refresh()

    assert [item.name for item in jobs.search()] == ["takesParameters"]
    assert jobs.search()[0].param_count == 2


async def test_folders_become_the_job_path(jobs: JenkinsJobStore) -> None:
    payload = {
        "jobs": [
            {
                "name": "folioRancher",
                "_class": FOLDER,
                "jobs": [
                    {
                        "name": "manageNamespace",
                        "_class": FOLDER,
                        "jobs": [job("deleteNamespace", ["CLUSTER"])],
                    }
                ],
            }
        ]
    }
    await indexer(jobs, {"/api/json": payload}, []).refresh()

    found = jobs.search()[0]
    assert found.job_path == "folioRancher/manageNamespace/deleteNamespace"
    assert found.folder == "folioRancher / manageNamespace"


async def test_a_folder_deeper_than_the_tree_costs_one_more_request(
    jobs: JenkinsJobStore,
) -> None:
    calls: list[str] = []
    payloads = {
        "/api/json": {"jobs": [{"name": "outer", "_class": FOLDER}]},
        "/job/outer/api/json": {"jobs": [job("deep", ["X"])]},
    }
    await indexer(jobs, payloads, calls).refresh()

    assert calls == ["/api/json", "/job/outer/api/json"]
    assert [item.job_path for item in jobs.search()] == ["outer/deep"]


async def test_a_job_remembers_how_long_its_last_success_took(jobs: JenkinsJobStore) -> None:
    ran = {**job("ran", ["CLUSTER"]), "lastSuccessfulBuild": {"duration": 754_000}}
    never = {**job("neverWorked", ["CLUSTER"]), "lastSuccessfulBuild": None}
    await indexer(jobs, {"/api/json": {"jobs": [ran, never]}}, []).refresh()

    assert jobs.typical_durations() == {"ran": 754_000}
    assert {item.name: item.typical_ms for item in jobs.search()} == {
        "ran": 754_000,
        "neverWorked": None,
    }


async def test_refreshing_replaces_the_previous_index(jobs: JenkinsJobStore) -> None:
    first = {"/api/json": {"jobs": [job("one", ["X"])]}}
    await indexer(jobs, first, []).refresh()
    second = {"/api/json": {"jobs": [job("two", ["Y"])]}}
    await indexer(jobs, second, []).refresh()

    assert [item.name for item in jobs.search()] == ["two"]


async def test_a_crawl_that_cannot_read_everything_keeps_the_index_there_was(
    jobs: JenkinsJobStore,
) -> None:
    await indexer(jobs, {"/api/json": {"jobs": [job("one", ["X"])]}}, []).refresh()

    await indexer(jobs, {}, []).refresh()

    assert [item.name for item in jobs.search()] == ["one"]


async def test_two_crawls_at_once_never_land_the_incomplete_one(tmp_path: Path) -> None:
    folder = "com.cloudbees.hudson.plugins.folder.Folder"
    tree = {
        "jobs": [
            job("j", ["A"]),
            {"name": "f1", "_class": folder},
            {"name": "f2", "_class": folder},
        ]
    }
    inner = {"jobs": [job("k", ["A"])]}
    failed_once = {"f1": False}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/json":
            return httpx.Response(200, json=tree)
        if request.url.path == "/job/f1/api/json" and not failed_once["f1"]:
            failed_once["f1"] = True
            return httpx.Response(503)
        if request.url.path == "/job/f2/api/json":
            await asyncio.sleep(0.05)
        return httpx.Response(200, json=inner)

    store = RunStore.open(tmp_path / "crawl.db")
    jobs = JenkinsJobStore(store)
    client = httpx.AsyncClient(
        base_url="https://jenkins.invalid", transport=httpx.MockTransport(handler)
    )
    crawler = JenkinsIndexer(jobs, JenkinsReader(client))

    first = asyncio.create_task(crawler.refresh())
    await asyncio.sleep(0.01)
    second = asyncio.create_task(crawler.refresh())
    await first
    after_first = sorted(item.job_path for item in jobs.search())
    await second
    after_second = sorted(item.job_path for item in jobs.search())
    store.close()

    assert after_first == []
    assert after_second == ["f1/k", "f2/k", "j"]
