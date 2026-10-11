"""Opt-in checks against the real Jenkins controller.

Read-only. Never issues a POST, and never triggers a build.

Enable with:
    JK_CONTRACT=1 uv run pytest tests/contract -v -m contract
"""

from __future__ import annotations

import os

import httpx
import pytest

from jk.__main__ import checkout_root
from jk.jenkins.client import JenkinsConfig, build_client
from jk.jenkins.read import JenkinsReader
from tests.contract import ReadOnlyTransport

pytestmark = [
    pytest.mark.contract,
    pytest.mark.skipif(
        os.environ.get("JK_CONTRACT") != "1",
        reason="set JK_CONTRACT=1 to run the contract checks",
    ),
]

CNFB = "job/folioRancher/job/manageNamespace/job/createNamespaceFromBranch"
CYPRESS = "job/folioTestingTools/job/runCypressTests"


@pytest.fixture
async def reader():
    # Load credentials exactly the way `jk` does, so the documented command
    # works with the .env at the checkout root and not only with exported variables.
    config = JenkinsConfig.from_environment(checkout_root())
    client = build_client(config, transport=ReadOnlyTransport(httpx.AsyncHTTPTransport()))
    async with client:
        response = await client.get("/me/api/json")
        assert response.status_code == 200, "Jenkins identity preflight failed"
        assert isinstance(response.json(), dict), "Jenkins identity response is not JSON"
        yield JenkinsReader(client)


async def test_cascade_parameters_still_have_no_dependable_default(reader):
    definitions = await reader.parameter_definitions(CNFB)
    cluster = definitions["CLUSTER"]
    assert cluster.is_cascade, "CLUSTER is no longer an Active Choices parameter"
    assert cluster.default == "error", (
        f"CLUSTER now defaults to {cluster.default!r}. Re-read spec.md "
        f"section 6.1 before relaxing anything."
    )


async def test_password_parameters_are_still_declared(reader):
    definitions = await reader.parameter_definitions(CYPRESS)
    assert definitions["ADMIN_PASSWORD"].is_secret


async def test_builds_still_expose_queue_id(reader):
    builds = await reader.recent_builds(CNFB, limit=5)
    assert builds, "no builds returned"
    assert any(build.queue_id is not None for build in builds)


async def test_next_build_number_is_available(reader):
    assert await reader.next_build_number(CNFB) > 0


async def test_a_finished_build_reports_a_result_and_is_final(reader):
    builds = await reader.recent_builds(CNFB, limit=10)
    finished = [b for b in builds if not b.building]
    assert finished, "no finished build to check"
    assert finished[0].result is not None
    assert finished[0].is_final


async def test_password_values_are_still_omitted_from_build_parameters(reader):
    builds = await reader.recent_builds(CYPRESS, limit=5)
    finished = [b for b in builds if not b.building]
    if not finished:
        pytest.skip("no finished Cypress build available")
    params = await reader.build_parameters(CYPRESS, finished[0].number)
    assert "ADMIN_PASSWORD" not in params, (
        "Jenkins now returns a value for a password parameter. Stop and re-check "
        "the secret-handling assumptions before continuing."
    )
