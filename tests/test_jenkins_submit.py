import httpx
import pytest

from jk.errors import AmbiguousSubmission, JenkinsAuthError, SubmissionRejected
from jk.jenkins.client import JenkinsConfig, build_client
from jk.jenkins.submit import JenkinsSubmitter

REST = "job/folioRancher/job/manageNamespace/job/createNamespaceFromBranch"
PATH = f"/{REST}/buildWithParameters"
QUEUE = "https://jenkins.invalid/queue/item/183759/"
CONFIG = JenkinsConfig(base_url="https://jenkins.invalid", user_id="t", api_token="t")
BODY = {"CLUSTER": "example-cluster", "NAMESPACE": "example-ns"}


def submitter_for(mock_transport, handler):
    client = build_client(CONFIG, transport=mock_transport(handler))
    return JenkinsSubmitter(client), client


async def test_201_with_location_is_a_new_queue_item(mock_transport):
    def handler(request):
        return httpx.Response(201, headers={"Location": QUEUE})

    submitter, client = submitter_for(mock_transport, handler)
    async with client:
        outcome = await submitter.submit(REST, BODY)
    assert outcome.queue_url == QUEUE
    assert outcome.pre_existing is False


async def test_303_means_jenkins_merged_an_identical_request(mock_transport):
    def handler(request):
        return httpx.Response(303, headers={"Location": QUEUE})

    submitter, client = submitter_for(mock_transport, handler)
    async with client:
        outcome = await submitter.submit(REST, BODY)
    assert outcome.queue_url == QUEUE
    assert outcome.pre_existing is True


async def test_the_body_is_form_encoded(mock_transport):
    seen = {}

    def handler(request):
        seen["content_type"] = request.headers.get("content-type")
        seen["body"] = request.content.decode()
        return httpx.Response(201, headers={"Location": QUEUE})

    submitter, client = submitter_for(mock_transport, handler)
    async with client:
        await submitter.submit(REST, BODY)
    assert "application/x-www-form-urlencoded" in seen["content_type"]
    assert "CLUSTER=example-cluster" in seen["body"]


async def test_exactly_one_post_is_issued(mock_transport, call_log):
    def handler(request):
        return httpx.Response(201, headers={"Location": QUEUE})

    submitter, client = submitter_for(mock_transport, handler)
    async with client:
        await submitter.submit(REST, BODY)
    posts = [entry for entry in call_log if entry[0] == "POST"]
    assert len(posts) == 1


async def test_409_is_a_clear_rejection(mock_transport):
    def handler(request):
        return httpx.Response(409, text="job is not buildable")

    submitter, client = submitter_for(mock_transport, handler)
    async with client:
        with pytest.raises(SubmissionRejected):
            await submitter.submit(REST, BODY)


async def test_400_is_a_clear_rejection(mock_transport):
    def handler(request):
        return httpx.Response(400, text="bad parameter")

    submitter, client = submitter_for(mock_transport, handler)
    async with client:
        with pytest.raises(SubmissionRejected):
            await submitter.submit(REST, BODY)


async def test_403_is_an_auth_error_and_is_never_sent_again(mock_transport, call_log):
    def handler(request):
        return httpx.Response(403, text="missing the Job/Build permission")

    submitter, client = submitter_for(mock_transport, handler)
    async with client:
        with pytest.raises(JenkinsAuthError):
            await submitter.submit(REST, BODY)
    assert call_log == [("POST", PATH)]


async def test_success_without_a_location_header_is_ambiguous(mock_transport):
    def handler(request):
        return httpx.Response(201)

    submitter, client = submitter_for(mock_transport, handler)
    async with client:
        with pytest.raises(AmbiguousSubmission):
            await submitter.submit(REST, BODY)


async def test_a_timeout_is_ambiguous_and_is_never_retried(mock_transport, call_log):
    def handler(request):
        raise httpx.ReadTimeout("timed out", request=request)

    submitter, client = submitter_for(mock_transport, handler)
    async with client:
        with pytest.raises(AmbiguousSubmission):
            await submitter.submit(REST, BODY)
    assert len([entry for entry in call_log if entry[0] == "POST"]) == 1


async def test_a_server_error_is_ambiguous_not_rejected(mock_transport):
    # Jenkins may have accepted the request before failing to answer.
    def handler(request):
        return httpx.Response(502, text="bad gateway")

    submitter, client = submitter_for(mock_transport, handler)
    async with client:
        with pytest.raises(AmbiguousSubmission):
            await submitter.submit(REST, BODY)
