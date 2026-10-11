"""One assembled `jk serve` worth of services, over a mocked Jenkins.

The TCP boundary the suite installs stays intact: the app is driven through
`httpx.ASGITransport`, and Jenkins is an `httpx.MockTransport`.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from jk.store.store import RunStore
from jk.web.app import create_app
from jk.web.deps import Services, build_services

BASE_URL = "https://jenkins.invalid"
BUILD_URL = f"{BASE_URL}/job/folder/job/job/41/"


@dataclass
class FakeJenkins:
    """Answers the handful of reads and the two writes JK can make."""

    definitions: dict[str, list[dict]] = field(default_factory=dict)
    jobs_tree: dict = field(default_factory=dict)
    calls: list[tuple[str, str]] = field(default_factory=list)
    bodies: list[bytes] = field(default_factory=list)
    #: Status answered to the POSTs that are not a build submission: /stop, /queue/cancelItem.
    stop_status: int = 200
    result: str = "SUCCESS"
    unreachable: bool = False
    unauthorised: bool = False
    #: Paths refused although the token itself is accepted: a job this user may not read.
    forbidden: tuple[str, ...] = ()
    #: Paths answered 404: a job deleted or renamed in Jenkins.
    missing: tuple[str, ...] = ()
    #: While True, build 41 reports that it is still building.
    building: bool = False
    #: Builds a reconciliation search may find, as {number: {parameter: value}}.
    recent: dict[int, dict[str, str]] = field(default_factory=dict)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.calls.append((request.method, path))
        if self.unreachable:
            raise httpx.ConnectError("down")
        if self.unauthorised or path.startswith(self.forbidden):
            return httpx.Response(403, text="no")
        if path.startswith(self.missing):
            return httpx.Response(404, text="no")
        if request.method == "POST":
            self.bodies.append(request.content)
            if path.endswith("/buildWithParameters"):
                return httpx.Response(201, headers={"Location": f"{BASE_URL}/queue/item/7/"})
            return httpx.Response(self.stop_status)
        tree = request.url.params.get("tree") or ""
        if self.recent and tree.startswith("builds["):
            return httpx.Response(
                200, json={"builds": [self._recent(number) for number in self.recent]}
            )
        if self.recent and tree.startswith("actions["):
            number = int(path.rsplit("/", maxsplit=3)[-3])
            return httpx.Response(
                200,
                json={
                    "actions": [
                        {
                            "parameters": [
                                {"name": name, "value": value}
                                for name, value in self.recent.get(number, {}).items()
                            ]
                        }
                    ]
                },
            )
        if path == "/queue/item/7/api/json":
            return httpx.Response(
                200,
                json={"id": 7, "cancelled": False, "executable": {"number": 41, "url": BUILD_URL}},
            )
        if path.endswith("/41/api/json"):
            return httpx.Response(
                200,
                json={
                    "number": 41,
                    "queueId": 7,
                    "building": self.building,
                    "result": None if self.building else self.result,
                    "timestamp": 1_700_000_000_000,
                    "duration": 900_000,
                    "estimatedDuration": 1_200_000,
                    "url": BUILD_URL,
                },
            )
        if path == "/api/json" and "nextBuildNumber" not in (request.url.params.get("tree") or ""):
            return httpx.Response(200, json=self.jobs_tree)
        if path.endswith("/api/json"):
            job_path = _job_path_of(path)
            if job_path in self.definitions:
                return httpx.Response(
                    200,
                    json={
                        "nextBuildNumber": 41,
                        "property": [{"parameterDefinitions": self.definitions[job_path]}],
                    },
                )
            return httpx.Response(200, json={"nextBuildNumber": 41, "property": []})
        return httpx.Response(404, text=f"no route for {path}")

    def _recent(self, number: int) -> dict:
        return {
            "number": number,
            "queueId": number,
            "building": number == max(self.recent),
            "result": None if number == max(self.recent) else "UNSTABLE",
            "timestamp": int(time.time() * 1000),
            "duration": 0,
            "estimatedDuration": 1_200_000,
            "url": f"{BASE_URL}/job/folder/job/job/{number}/",
        }


def _job_path_of(api_path: str) -> str:
    parts = [part for part in api_path.split("/") if part]
    return "/".join(parts[index + 1] for index, part in enumerate(parts) if part == "job")


async def no_wait(_: float) -> None:
    """Monitoring backs off in production; the tests do not wait for it."""
    await asyncio.sleep(0)


def build(tmp_path: Path, jenkins: FakeJenkins) -> Services:
    store = RunStore.open(tmp_path / "runs.db")
    client = httpx.AsyncClient(base_url=BASE_URL, transport=jenkins.transport())
    return build_services(
        store=store,
        client=client,
        base_url=BASE_URL,
        sleep=no_wait,
    )


def client_for(services: Services) -> httpx.AsyncClient:
    app = create_app(services, serve_static=False, background=False)
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://127.0.0.1:8765",
        headers={"X-JK-Panel": "1"},
    )


async def listed(client: httpx.AsyncClient, kind: str, item_id: str) -> dict | None:
    """One flow ("flows") or saved job ("presets") as the panel's list gives it."""
    found = (await client.get(f"/api/{kind}")).json()
    return next((item for item in found if item["id"] == item_id), None)


async def start_reviewed(
    client: httpx.AsyncClient,
    flow_id: str,
    run_values: dict[str, dict[str, str]] | None = None,
) -> httpx.Response:
    """Start a draft the way the panel does.

    Editing is turned off first, then the review is read and its token sent.
    """
    await client.patch(f"/api/flows/{flow_id}", json={"editing": False})
    token = (await client.post(f"/api/flows/{flow_id}/review", json={})).json()["review_token"]
    return await client.post(
        f"/api/flows/{flow_id}/start",
        json={"run_values": run_values or {}, "review_token": token},
    )


async def resume_reviewed(
    client: httpx.AsyncClient, flow_id: str, from_position: int | None = None
) -> httpx.Response:
    review = await client.post(
        f"/api/flows/{flow_id}/review",
        json={"scope": "resume", "from_position": from_position},
    )
    return await client.post(
        f"/api/flows/{flow_id}/resume",
        json={"from_position": from_position, "review_token": review.json()["review_token"]},
    )


async def confirm_reviewed(
    client: httpx.AsyncClient,
    flow_id: str,
    run_values: dict[str, dict[str, str]] | None = None,
) -> httpx.Response:
    review = await client.post(f"/api/flows/{flow_id}/review", json={"scope": "held"})
    return await client.post(
        f"/api/flows/{flow_id}/confirm",
        json={"run_values": run_values or {}, "review_token": review.json()["review_token"]},
    )
