import httpx
import pytest

from jk.errors import JenkinsAuthError, TargetNotFound
from jk.jenkins.client import JenkinsConfig, build_client
from jk.jenkins.read import JenkinsReader

REST = "job/folioRancher/job/manageNamespace/job/createNamespaceFromBranch"
CONFIG = JenkinsConfig(base_url="https://jenkins.invalid", user_id="tester", api_token="token")


def reader_for(mock_transport, routes) -> tuple[JenkinsReader, httpx.AsyncClient]:
    client = build_client(CONFIG, transport=mock_transport(routes))
    return JenkinsReader(client), client


async def test_parameter_definitions_drop_unnamed_entries(mock_transport, fixture_json):
    routes = {f"/{REST}/api/json": httpx.Response(200, json=fixture_json("job_defs_cnfb"))}
    reader, client = reader_for(mock_transport, routes)
    async with client:
        defs = await reader.parameter_definitions(REST)
    assert "CLUSTER" in defs
    assert all(name for name in defs)
    assert len(defs) == 40


async def test_cascade_and_secret_flags(mock_transport, fixture_json):
    routes = {f"/{REST}/api/json": httpx.Response(200, json=fixture_json("job_defs_cnfb"))}
    reader, client = reader_for(mock_transport, routes)
    async with client:
        defs = await reader.parameter_definitions(REST)
    assert defs["CLUSTER"].is_cascade is True
    assert defs["CLUSTER"].default == "error"
    assert defs["NAMESPACE"].default == "error"
    assert defs["PLATFORM"].is_cascade is False
    assert defs["PLATFORM"].choices == ["EUREKA", "OKAPI"]
    assert defs["LOAD_SAMPLE"].default == "true"


async def test_build_reads_a_finished_build(mock_transport, fixture_json):
    routes = {f"/{REST}/9928/api/json": httpx.Response(200, json=fixture_json("build_finished"))}
    reader, client = reader_for(mock_transport, routes)
    async with client:
        info = await reader.build_by_url(f"https://jenkins.invalid/{REST}/9928/")
    assert info.number == 9928
    assert info.queue_id == 183738
    assert info.result == "SUCCESS"
    assert info.is_final is True


async def test_running_build_is_not_final(mock_transport, fixture_json):
    routes = {f"/{REST}/9929/api/json": httpx.Response(200, json=fixture_json("build_running"))}
    reader, client = reader_for(mock_transport, routes)
    async with client:
        info = await reader.build_by_url(f"https://jenkins.invalid/{REST}/9929/")
    assert info.result is None
    assert info.building is True
    assert info.is_final is False
    assert info.estimated_ms == 2619692


async def test_queue_item_404_raises_target_not_found(mock_transport):
    routes = {"/queue/item/183738/api/json": httpx.Response(404, text="Not Found")}
    reader, client = reader_for(mock_transport, routes)
    async with client:
        with pytest.raises(TargetNotFound):
            await reader.queue_item("https://jenkins.invalid/queue/item/183738/")


async def test_queue_item_reports_the_build_once_started(mock_transport):
    payload = {
        "id": 183759,
        "cancelled": False,
        "why": None,
        "executable": {"number": 9929, "url": "https://jenkins.invalid/x/9929/"},
    }
    routes = {"/queue/item/183759/api/json": httpx.Response(200, json=payload)}
    reader, client = reader_for(mock_transport, routes)
    async with client:
        item = await reader.queue_item("https://jenkins.invalid/queue/item/183759/")
    assert item.build_number == 9929
    assert item.cancelled is False


async def test_queue_item_still_waiting_has_no_build(mock_transport, fixture_json):
    routes = {
        "/queue/item/183759/api/json": httpx.Response(200, json=fixture_json("queue_item_waiting"))
    }
    reader, client = reader_for(mock_transport, routes)
    async with client:
        item = await reader.queue_item("https://jenkins.invalid/queue/item/183759/")
    assert item.build_number is None


async def test_recent_builds_are_ordered_newest_first(mock_transport, fixture_json):
    routes = {f"/{REST}/api/json": httpx.Response(200, json=fixture_json("builds_list"))}
    reader, client = reader_for(mock_transport, routes)
    async with client:
        builds = await reader.recent_builds(REST)
    assert [b.number for b in builds] == [9929, 9928, 9927]
    assert builds[1].queue_id == 183738


async def test_build_parameters_exclude_secrets_and_lowercase_booleans(
    mock_transport, fixture_json
):
    routes = {
        f"/{REST}/10050/api/json": httpx.Response(200, json=fixture_json("build_params_cypress"))
    }
    reader, client = reader_for(mock_transport, routes)
    async with client:
        params = await reader.build_parameters(REST, 10050)
    assert "ADMIN_PASSWORD" not in params
    assert "ABSENT" not in params
    assert params["RUN_SANITY_CHECK"] == "true"
    assert params["PREPARE"] == "false"
    assert params["TESTRAIL_RUN_ID"] == ""


async def test_401_becomes_an_auth_error(mock_transport):
    routes = {f"/{REST}/api/json": httpx.Response(401, text="bad credentials")}
    reader, client = reader_for(mock_transport, routes)
    async with client:
        with pytest.raises(JenkinsAuthError):
            await reader.parameter_definitions(REST)


async def test_the_reader_never_sends_anything_but_get(mock_transport, fixture_json, call_log):
    routes = {f"/{REST}/api/json": httpx.Response(200, json=fixture_json("job_defs_cnfb"))}
    reader, client = reader_for(mock_transport, routes)
    async with client:
        await reader.parameter_definitions(REST)
    assert {method for method, _ in call_log} == {"GET"}
