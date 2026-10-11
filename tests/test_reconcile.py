import httpx
import pytest

from jk.engine.reconcile import find_candidates, normalise
from jk.jenkins.client import JenkinsConfig, build_client
from jk.jenkins.read import JenkinsReader

REST = "job/folioRancher/job/manageNamespace/job/createNamespaceFromBranch"
CONFIG = JenkinsConfig(base_url="https://jenkins.invalid", user_id="t", api_token="t")


def reader_for(mock_transport, handler):
    client = build_client(CONFIG, transport=mock_transport(handler))
    return JenkinsReader(client), client


def test_normalise_makes_booleans_comparable():
    assert normalise("True") == normalise("true")
    assert normalise("FALSE") == normalise("false")
    assert normalise("") == normalise(" ")


@pytest.mark.parametrize(
    ("sent", "reported", "expected_matched"),
    [
        ({"PRESENT": "1", "MISSING_EMPTY": ""}, {"PRESENT": "1"}, {"PRESENT": "1"}),
        ({"MISSING_EMPTY": ""}, {}, None),
        ({"EMPTY": ""}, {"EMPTY": ""}, {"EMPTY": ""}),
        ({"EMPTY": ""}, {"EMPTY": "different"}, None),
        ({"PRESENT": "1", "MISSING": "value"}, {"PRESENT": "1"}, {"PRESENT": "1"}),
        ({"PRESENT": "1"}, {"PRESENT": "1", "EXTRA": "other"}, {"PRESENT": "1"}),
    ],
)
async def test_only_reported_values_are_match_evidence(
    mock_transport, sent, reported, expected_matched
):
    def handler(request):
        assert request.method == "GET"
        if "/1/api/json" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "actions": [
                        {
                            "parameters": [
                                {"name": name, "value": value} for name, value in reported.items()
                            ]
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "builds": [{"number": 1, "timestamp": 5000, "url": "https://jenkins.invalid/x/1/"}]
            },
        )

    reader, client = reader_for(mock_transport, handler)
    async with client:
        found = await find_candidates(
            reader,
            rest_path=REST,
            sent_params=sent,
            search_from_build_number=1,
            search_from_timestamp=1,
        )

    if expected_matched is None:
        assert found == []
    else:
        assert len(found) == 1
        assert found[0].matched == expected_matched


async def test_matches_a_build_by_the_declared_subset(mock_transport, fixture_json):
    params = {
        9929: {
            "CLUSTER": "example-cluster",
            "NAMESPACE": "example-ns",
            "FOLIO_BRANCH": "example-feature",
            "EXTRA_ONE": "ignored",
            "TESTRAIL_RUN_ID": "",
        },
        9928: {"CLUSTER": "example-cluster", "NAMESPACE": "example-ns", "FOLIO_BRANCH": "snapshot"},
        9927: {
            "CLUSTER": "folio-other",
            "NAMESPACE": "example-ns",
            "FOLIO_BRANCH": "example-feature",
        },
    }

    def handler(request):
        path = request.url.path
        for number in params:
            if f"/{number}/api/json" in path:
                return httpx.Response(
                    200,
                    json={
                        "actions": [
                            {
                                "parameters": [
                                    {
                                        "_class": "hudson.model.StringParameterValue",
                                        "name": n,
                                        "value": v,
                                    }
                                    for n, v in params[number].items()
                                ]
                            }
                        ]
                    },
                )
        return httpx.Response(200, json=fixture_json("builds_list"))

    reader, client = reader_for(mock_transport, handler)
    async with client:
        found = await find_candidates(
            reader,
            rest_path=REST,
            sent_params={
                "CLUSTER": "example-cluster",
                "NAMESPACE": "example-ns",
                "FOLIO_BRANCH": "example-feature",
            },
            search_from_build_number=9928,
            search_from_timestamp=1787849720,
        )

    assert [c.build_number for c in found] == [9929]


async def test_a_boolean_returned_as_json_true_still_matches(mock_transport):
    def handler(request):
        if "/9929/api/json" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "actions": [
                        {
                            "parameters": [
                                {
                                    "_class": "hudson.model.BooleanParameterValue",
                                    "name": "RUN_SANITY_CHECK",
                                    "value": True,
                                },
                                {
                                    "_class": "hudson.model.StringParameterValue",
                                    "name": "TESTRAIL_RUN_ID",
                                    "value": "",
                                },
                            ]
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "builds": [
                    {
                        "number": 9929,
                        "queueId": 1,
                        "building": True,
                        "result": None,
                        "timestamp": 1787849729605,
                        "duration": 0,
                        "url": "https://jenkins.invalid/x/9929/",
                    },
                ]
            },
        )

    reader, client = reader_for(mock_transport, handler)
    async with client:
        found = await find_candidates(
            reader,
            rest_path=REST,
            # JK sends the STRING "true"; Jenkins returns the BOOLEAN true.
            sent_params={"RUN_SANITY_CHECK": "true", "TESTRAIL_RUN_ID": ""},
            search_from_build_number=9929,
            search_from_timestamp=1,
        )

    assert [c.build_number for c in found] == [9929]


async def test_builds_before_the_search_window_are_ignored(mock_transport, fixture_json):
    def handler(request):
        if "/api/json" in request.url.path and "builds" in str(request.url.params):
            return httpx.Response(200, json=fixture_json("builds_list"))
        return httpx.Response(
            200,
            json={"actions": [{"parameters": [{"name": "A", "value": "1"}]}]},
        )

    reader, client = reader_for(mock_transport, handler)
    async with client:
        found = await find_candidates(
            reader,
            rest_path=REST,
            sent_params={"A": "1"},
            search_from_build_number=9929,
            search_from_timestamp=1,
        )

    assert [c.build_number for c in found] == [9929]


async def test_seconds_after_submit_is_reported(mock_transport):
    def handler(request):
        if "/9929/api/json" in request.url.path:
            return httpx.Response(
                200,
                json={"actions": [{"parameters": [{"name": "P", "value": "v"}]}]},
            )
        return httpx.Response(
            200,
            json={
                "builds": [
                    {
                        "number": 9929,
                        "queueId": 1,
                        "building": True,
                        "result": None,
                        "timestamp": 1787849729605,
                        "duration": 0,
                        "url": "https://jenkins.invalid/x/9929/",
                    },
                ]
            },
        )

    reader, client = reader_for(mock_transport, handler)
    async with client:
        found = await find_candidates(
            reader,
            rest_path=REST,
            sent_params={"P": "v"},
            search_from_build_number=9929,
            search_from_timestamp=1787849727,
        )

    assert found[0].seconds_after_submit == 2


async def test_empty_sent_parameters_never_match_an_arbitrary_build(mock_transport):
    def handler(_request):
        raise AssertionError("Jenkins must not be queried without comparison parameters")

    reader, client = reader_for(mock_transport, handler)
    async with client:
        found = await find_candidates(
            reader,
            rest_path=REST,
            sent_params={},
            search_from_build_number=9929,
            search_from_timestamp=1,
        )

    assert found == []


async def test_builds_before_the_submission_timestamp_are_ignored(mock_transport):
    def handler(request):
        if "builds" in str(request.url.params):
            return httpx.Response(
                200,
                json={
                    "builds": [
                        {
                            "number": 9930,
                            "queueId": 1,
                            "building": True,
                            "result": None,
                            "timestamp": 1787849700000,
                            "duration": 0,
                            "url": "https://jenkins.invalid/x/9930/",
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={"actions": [{"parameters": [{"name": "A", "value": "1"}]}]},
        )

    reader, client = reader_for(mock_transport, handler)
    async with client:
        found = await find_candidates(
            reader,
            rest_path=REST,
            sent_params={"A": "1"},
            search_from_build_number=9929,
            search_from_timestamp=1787849720,
        )

    assert found == []


async def test_builds_without_a_timestamp_are_not_safe_candidates(mock_transport):
    def handler(request):
        if "builds" in str(request.url.params):
            return httpx.Response(
                200,
                json={
                    "builds": [
                        {
                            "number": 9930,
                            "queueId": 1,
                            "building": True,
                            "result": None,
                            "timestamp": 0,
                            "duration": 0,
                            "url": "https://jenkins.invalid/x/9930/",
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={"actions": [{"parameters": [{"name": "A", "value": "1"}]}]},
        )

    reader, client = reader_for(mock_transport, handler)
    async with client:
        found = await find_candidates(
            reader,
            rest_path=REST,
            sent_params={"A": "1"},
            search_from_build_number=9929,
            search_from_timestamp=1,
        )

    assert found == []


async def test_reconciliation_only_reads(mock_transport, fixture_json, call_log):
    def handler(request):
        if "builds" in str(request.url.params):
            return httpx.Response(200, json=fixture_json("builds_list"))
        return httpx.Response(200, json={"actions": [{"parameters": []}]})

    reader, client = reader_for(mock_transport, handler)
    async with client:
        await find_candidates(
            reader,
            rest_path=REST,
            sent_params={"A": "1"},
            search_from_build_number=9927,
            search_from_timestamp=1,
        )

    assert {method for method, _ in call_log} == {"GET"}


async def test_builds_with_unreadable_parameters_are_skipped(mock_transport, fixture_json):
    def handler(request):
        if "/9929/api/json" in request.url.path:
            return httpx.Response(404, text="Not Found")
        if "/9928/api/json" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "actions": [
                        {
                            "parameters": [
                                {"name": "CLUSTER", "value": "example-cluster"},
                                {"name": "NAMESPACE", "value": "example-ns"},
                            ]
                        }
                    ]
                },
            )
        return httpx.Response(200, json=fixture_json("builds_list"))

    reader, client = reader_for(mock_transport, handler)
    async with client:
        found = await find_candidates(
            reader,
            rest_path=REST,
            sent_params={"CLUSTER": "example-cluster", "NAMESPACE": "example-ns"},
            search_from_build_number=9928,
            search_from_timestamp=1,
        )

    assert [candidate.build_number for candidate in found] == [9928]


async def test_a_literal_password_is_unverifiable_and_never_blocks_a_match(mock_transport):
    """Jenkins omits a password value, so it cannot decide a match."""

    def handler(request):
        if "/9929/api/json" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "actions": [
                        {
                            "parameters": [
                                {
                                    "_class": "hudson.model.StringParameterValue",
                                    "name": "A",
                                    "value": "1",
                                },
                                {
                                    "_class": "hudson.model.PasswordParameterValue",
                                    "name": "ADMIN_PASSWORD",
                                },
                            ]
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "builds": [
                    {
                        "number": 9929,
                        "queueId": 1,
                        "building": True,
                        "result": None,
                        "timestamp": 5_000,
                        "duration": 0,
                        "url": "https://jenkins.invalid/x/9929/",
                    },
                ]
            },
        )

    reader, client = reader_for(mock_transport, handler)
    async with client:
        found = await find_candidates(
            reader,
            rest_path=REST,
            sent_params={"A": "1", "ADMIN_PASSWORD": "literal-password-9f3a"},
            search_from_build_number=9929,
            search_from_timestamp=1,
        )

    assert [c.build_number for c in found] == [9929]
    assert found[0].matched == {"A": "1"}


async def test_a_build_with_nothing_comparable_is_not_a_candidate(mock_transport):
    def handler(request):
        if "/9929/api/json" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "actions": [
                        {
                            "parameters": [
                                {
                                    "_class": "hudson.model.PasswordParameterValue",
                                    "name": "ADMIN_PASSWORD",
                                },
                            ]
                        }
                    ]
                },
            )
        return httpx.Response(
            200,
            json={
                "builds": [
                    {
                        "number": 9929,
                        "queueId": 1,
                        "building": True,
                        "result": None,
                        "timestamp": 5_000,
                        "duration": 0,
                        "url": "https://jenkins.invalid/x/9929/",
                    },
                ]
            },
        )

    reader, client = reader_for(mock_transport, handler)
    async with client:
        found = await find_candidates(
            reader,
            rest_path=REST,
            sent_params={"ADMIN_PASSWORD": "literal-password-9f3a"},
            search_from_build_number=9929,
            search_from_timestamp=1,
        )

    assert found == []
