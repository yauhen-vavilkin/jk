"""What must never leave the process, and what must never be written down."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx
import pytest

from jk.jenkins.client import JenkinsConfig
from jk.store.store import RunStore
from jk.web.app import create_app
from jk.web.deps import build_services
from tests.webapp import BASE_URL, FakeJenkins, client_for, listed, no_wait, start_reviewed

TOKEN = "s3cr3t-jenkins-api-token"
PASSWORD = "swordfish-not-a-token"
JOB_PATH = "folder/createNamespace"
DEFINITIONS = [
    {"name": "CLUSTER", "type": "StringParameterDefinition"},
    {"name": "ADMIN_PASSWORD", "type": "PasswordParameterDefinition"},
]


@pytest.fixture
def jenkins() -> FakeJenkins:
    return FakeJenkins(definitions={JOB_PATH: list(DEFINITIONS)})


async def make_flow(client) -> tuple[dict, dict]:
    preset = (
        await client.post(
            "/api/presets",
            json={
                "job_path": JOB_PATH,
                "name": "saved job",
                "operation": "Create environment",
                "params": {
                    "CLUSTER": {"mode": "fixed", "value": "example-cluster"},
                    "ADMIN_PASSWORD": {"mode": "fixed", "value": PASSWORD},
                },
            },
        )
    ).json()
    flow = (await client.post("/api/flows", json={"steps": [{"preset_id": preset["id"]}]})).json()
    return preset, flow


async def test_the_api_token_is_in_no_response_and_in_no_row(tmp_path: Path) -> None:
    jenkins = FakeJenkins(definitions={JOB_PATH: list(DEFINITIONS)})
    store = RunStore.open(tmp_path / "runs.db")
    config = JenkinsConfig(base_url=BASE_URL, user_id="someone", api_token=TOKEN)
    client_to_jenkins = httpx.AsyncClient(
        base_url=BASE_URL, auth=(config.user_id, config.api_token), transport=jenkins.transport()
    )
    services = build_services(
        store=store,
        client=client_to_jenkins,
        base_url=config.base_url,
        sleep=no_wait,
    )
    app = create_app(services, serve_static=False, background=False)

    seen: list[str] = []
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://127.0.0.1:8765",
        headers={"X-JK-Panel": "1"},
    ) as panel:
        _, flow = await make_flow(panel)
        assert (await start_reviewed(panel, flow["id"])).status_code == 200
        await services.supervisor.wait(flow["id"])
        for path in (
            "/api/presets",
            "/api/flows",
            "/api/saved-flows",
            "/api/jenkins/status",
            "/api/jenkins/jobs",
            f"/api/flows/{flow['id']}",
        ):
            seen.append((await panel.get(path)).text)

    rows = [
        str(tuple(row))
        for table in ("runs", "steps", "step_params", "presets", "flow_meta", "flow_step_meta")
        for row in store.connection.execute(f"SELECT * FROM {table}").fetchall()
    ]
    store.close()

    assert TOKEN not in " ".join(seen)
    assert TOKEN not in " ".join(rows)


async def test_a_password_parameter_is_stored_and_shown_as_written(client) -> None:
    preset, flow = await make_flow(client)

    detail = await listed(client, "presets", preset["id"])
    review = (await client.post(f"/api/flows/{flow['id']}/review")).json()

    # No masking: there is nowhere else the value could have come from.
    assert detail["params"]["ADMIN_PASSWORD"]["value"] == PASSWORD
    sent = {item["name"]: item["value"] for item in review["steps"][0]["sent"]}
    assert sent["ADMIN_PASSWORD"] == PASSWORD


async def test_no_request_body_is_written_to_the_log(client, services, caplog) -> None:
    caplog.set_level(logging.DEBUG)
    _, flow = await make_flow(client)

    assert (await start_reviewed(client, flow["id"])).status_code == 200
    await services.supervisor.wait(flow["id"])

    written = "\n".join(record.getMessage() for record in caplog.records)
    assert PASSWORD not in written
    assert "ADMIN_PASSWORD" not in written


async def test_the_error_shape_is_the_one_the_frontend_shows(client) -> None:
    response = await client.get("/api/presets/does-not-exist/usage")

    assert response.status_code == 404
    body = json.loads(response.text)
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message"}


async def test_a_page_on_another_name_is_refused_even_for_reading(services) -> None:
    """DNS rebinding: another domain pointed at 127.0.0.1 sends its own Host."""
    async with client_for(services) as client:
        response = await client.get("/api/presets", headers={"Host": "attacker.example:8765"})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_loopback"


async def test_a_change_without_the_panel_header_is_refused(services) -> None:
    """A form post or a no-cors fetch from another site cannot add a custom header."""
    app = create_app(services, serve_static=False, background=False)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8765"
    ) as bare:
        response = await bare.post(
            "/api/flows",
            content=b'{"steps": []}',
            headers={"Content-Type": "text/plain"},
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_the_panel"
    assert services.flows.list() == []
