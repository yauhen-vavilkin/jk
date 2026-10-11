"""The ONLY place JK writes to Jenkins.

There is no retry here, and there must never be one. If the outcome of a request
is unknown, the caller marks the run NEEDS_ATTENTION and a human decides.

Response codes come from Jenkins core (ParametersDefinitionProperty):
  201 + Location -> a new queue item
  303 + Location -> Jenkins merged an identical request already queued
  409            -> the job is not buildable
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from jk.engine.messages import CONNECTION_FAILED_WHILE_SENDING
from jk.errors import AmbiguousSubmission, JenkinsAuthError, SubmissionRejected


@dataclass(frozen=True)
class SubmitOutcome:
    queue_url: str
    #: True when Jenkins attached us to a queue item that already existed. The
    #: build may have been started by somebody else, so the UI must say it
    #: already existed rather than imply JK started it.
    pre_existing: bool


class JenkinsSubmitter:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def submit(self, rest_path: str, body: dict[str, str]) -> SubmitOutcome:
        path = f"/{rest_path}/buildWithParameters"
        try:
            response = await self._client.post(path, data=body)
        except httpx.HTTPError as exc:
            # The request may or may not have reached Jenkins. Never re-send.
            raise AmbiguousSubmission(f"{CONNECTION_FAILED_WHILE_SENDING} ({exc}).") from exc
        return self._interpret(path, response)

    def _interpret(self, path: str, response: httpx.Response) -> SubmitOutcome:
        code = response.status_code

        if code in (201, 303):
            location = response.headers.get("Location")
            if not location:
                raise AmbiguousSubmission(
                    f"Jenkins answered HTTP {code} without a Location header, so JK "
                    f"cannot tell which queue item was created."
                )
            return SubmitOutcome(queue_url=location, pre_existing=(code == 303))

        if code in (401, 403):
            raise JenkinsAuthError(
                f"Jenkins refused the submission with HTTP {code}. Check your API token "
                f"and whether you may build this job."
            )

        if 400 <= code < 500:
            raise SubmissionRejected(
                f"Jenkins rejected the submission for {path} with HTTP {code}. "
                "No build was created."
            )

        # 5xx and anything else: Jenkins may have accepted the request before failing.
        raise AmbiguousSubmission(
            f"Jenkins answered HTTP {code}, which does not say whether the request was accepted."
        )
