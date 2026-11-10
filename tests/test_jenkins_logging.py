"""What JK writes to its log about Jenkins' answers: enough to see what went wrong, no secrets."""

from __future__ import annotations

import logging

import httpx

from jk.jenkins.client import JenkinsConfig, build_client

CONFIG = JenkinsConfig("https://jenkins.invalid", "user", "token-value-1234")


async def test_each_answer_is_logged_with_status_and_location_but_never_its_body(caplog) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                201, headers={"Location": "https://jenkins.invalid/queue/item/7/"}, text="body-77"
            )
        return httpx.Response(404, text="proxy echoed body-secret-42")

    client = build_client(CONFIG, httpx.MockTransport(handler))
    with caplog.at_level(logging.INFO, logger="jk.jenkins"):
        async with client:
            await client.post("/job/x/buildWithParameters", data={"PASSWORD": "param-secret"})
            await client.get("/job/x/api/json", params={"tree": "query-secret"})

    assert "POST /job/x/buildWithParameters -> HTTP 201" in caplog.text
    assert "Location=https://jenkins.invalid/queue/item/7/" in caplog.text
    assert "GET /job/x/api/json -> HTTP 404" in caplog.text
    for secret in ("body-77", "body-secret-42", "param-secret", "query-secret", "token-value-1234"):
        assert secret not in caplog.text


async def test_a_queue_item_is_logged_by_field_without_its_parameters(caplog) -> None:
    from jk.jenkins.read import JenkinsReader

    item = {
        "_class": "hudson.model.Queue$WaitingItem",
        "id": 7,
        "why": "In the quiet period. Expires in 4.9 sec",
        "blocked": False,
        "stuck": False,
        "params": "\nADMIN_PASSWORD=param-secret",
    }
    client = build_client(
        CONFIG, httpx.MockTransport(lambda request: httpx.Response(200, json=item))
    )
    with caplog.at_level(logging.INFO, logger="jk.jenkins"):
        async with client:
            await JenkinsReader(client).queue_item("https://jenkins.invalid/queue/item/7/")

    assert "why='In the quiet period. Expires in 4.9 sec'" in caplog.text
    assert "kind=Queue$WaitingItem" in caplog.text
    assert "param-secret" not in caplog.text
