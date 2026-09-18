"""Executor tests.

Most of these check that the loop keeps going. A run that dies on case 3 of
60 is worse than useless: it looks like a result and is not one.
"""

from __future__ import annotations

import pytest

from core.client import ApiClient, GuardrailError, HealthResult, Response
from core.executor import (
    ERROR,
    RAN,
    SKIPPED,
    CaseResult,
    UnhealthyApiError,
    format_result,
    run_case,
    run_cases,
)
from core.testcase import parse_document

COMMITTED = "testcases/get_api-v1-website-slots.json"


def make_cases(count=1, path="/api/v1/things"):
    document = {
        "endpoint": {"method": "GET", "path": path},
        "cases": [
            {
                "name": f"case {i}",
                "category": "happy_path",
                "expected_status": 200,
                "reason": "a list endpoint should return a page",
            }
            for i in range(count)
        ],
    }
    return parse_document(document, source="test.json")


class FakeClient:
    """Stands in for ApiClient: scripted replies, one per call."""

    def __init__(self, replies, healthy=True, health_reason="ok"):
        self.replies = list(replies)
        self.calls = []
        self._healthy = healthy
        self._health_reason = health_reason

    def health_check(self):
        return HealthResult(ok=self._healthy, reason=self._health_reason)

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def response(status=200, elapsed_ms=12, body="{}", nbytes=2, error=None, truncated=False):
    return Response(
        method="GET",
        url="https://api.staging.example.com/api/v1/things",
        status=status,
        elapsed_ms=elapsed_ms,
        body=body,
        truncated=truncated,
        error=error,
        response_bytes=nbytes,
    )


# --------------------------------------------------------------------------
# one case
# --------------------------------------------------------------------------


def test_successful_call_is_recorded_as_ran():
    client = FakeClient([response(status=200, elapsed_ms=34, nbytes=618)])
    result = run_case(client, make_cases()[0])

    assert result.outcome == RAN
    assert result.status == 200
    assert result.elapsed_ms == 34
    assert result.response_bytes == 618
    assert result.detail == ""


def test_a_4xx_still_counts_as_ran():
    """RAN says a reply came back, not that the API behaved. Verdict is S06."""
    result = run_case(FakeClient([response(status=404)]), make_cases()[0])
    assert result.outcome == RAN
    assert result.status == 404


def test_guardrail_refusal_is_skipped_not_an_error():
    client = FakeClient([GuardrailError("Method POST not in allowed_methods: GET")])
    result = run_case(client, make_cases()[0])

    assert result.outcome == SKIPPED
    assert result.status is None
    assert "allowed_methods" in result.detail


def test_no_reply_is_error_not_skipped():
    client = FakeClient([response(status=None, error="timeout after 10.0s")])
    result = run_case(client, make_cases()[0])

    assert result.outcome == ERROR
    assert result.status is None
    assert "timeout" in result.detail


def test_skipped_and_error_are_not_the_same_bucket():
    """'We declined to call' must never read as 'staging was down'."""
    skipped = run_case(FakeClient([GuardrailError("blocked")]), make_cases()[0])
    errored = run_case(
        FakeClient([response(status=None, error="ConnectionError")]), make_cases()[0]
    )
    assert skipped.outcome != errored.outcome


def test_case_inputs_are_passed_to_the_client():
    document = {
        "endpoint": {"method": "GET", "path": "/api/v1/things/{id}"},
        "cases": [
            {
                "name": "one thing",
                "category": "happy_path",
                "path_params": {"id": 7},
                "query": {"size": 1},
                "expected_status": 200,
                "reason": "fetching an existing thing should succeed",
            }
        ],
    }
    client = FakeClient([response()])
    run_case(client, parse_document(document, source="t.json")[0])

    method, path, kwargs = client.calls[0]
    assert (method, path) == ("GET", "/api/v1/things/{id}")
    assert kwargs["path_params"] == {"id": 7}
    assert kwargs["query"] == {"size": 1}


# --------------------------------------------------------------------------
# the loop
# --------------------------------------------------------------------------


def test_every_case_runs_in_order():
    cases = make_cases(3)
    client = FakeClient([response(status=200), response(status=404), response(status=500)])

    results = run_cases(client, cases)
    assert [r.name for r in results] == ["case 0", "case 1", "case 2"]
    assert [r.status for r in results] == [200, 404, 500]


def test_a_skip_in_the_middle_does_not_stop_the_run():
    cases = make_cases(3)
    client = FakeClient([response(), GuardrailError("blocked"), response()])

    results = run_cases(client, cases)
    assert [r.outcome for r in results] == [RAN, SKIPPED, RAN]
    assert len(results) == 3


def test_an_error_in_the_middle_does_not_stop_the_run():
    cases = make_cases(3)
    client = FakeClient(
        [response(), response(status=None, error="timeout after 10.0s"), response()]
    )

    results = run_cases(client, cases)
    assert [r.outcome for r in results] == [RAN, ERROR, RAN]


def test_counts_cover_every_outcome():
    cases = make_cases(4)
    client = FakeClient(
        [
            response(),
            GuardrailError("blocked"),
            response(status=None, error="timeout"),
            response(status=404),
        ]
    )

    counts = run_cases(client, cases).counts()
    assert counts == {RAN: 2, SKIPPED: 1, ERROR: 1}


def test_of_filters_by_outcome():
    cases = make_cases(2)
    client = FakeClient([response(), GuardrailError("blocked")])

    results = run_cases(client, cases)
    assert [r.name for r in results.of(SKIPPED)] == ["case 1"]


def test_on_result_is_called_as_each_case_finishes():
    cases = make_cases(3)
    client = FakeClient([response(), response(), response()])

    seen = []
    run_cases(client, cases, on_result=seen.append)
    assert [r.name for r in seen] == ["case 0", "case 1", "case 2"]


def test_empty_case_list_is_not_an_error():
    results = run_cases(FakeClient([]), [])
    assert len(results) == 0
    assert results.counts() == {RAN: 0, SKIPPED: 0, ERROR: 0}


# --------------------------------------------------------------------------
# health gate
# --------------------------------------------------------------------------


def test_unhealthy_api_stops_the_run_before_any_case():
    client = FakeClient([response()], healthy=False, health_reason="/ping returned 503")

    with pytest.raises(UnhealthyApiError, match="503"):
        run_cases(client, make_cases(3))
    assert client.calls == []


def test_healthy_api_runs_normally():
    client = FakeClient([response()], healthy=True)
    assert len(run_cases(client, make_cases(1))) == 1


def test_health_gate_can_be_turned_off():
    client = FakeClient([response()], healthy=False)
    assert len(run_cases(client, make_cases(1), check_health=False)) == 1


# --------------------------------------------------------------------------
# display
# --------------------------------------------------------------------------


def test_format_result_is_ascii_only():
    line = format_result(
        CaseResult(case=make_cases()[0], outcome=RAN, status=200, elapsed_ms=34,
                   response_bytes=618)
    )
    assert line.isascii()
    assert "RAN" in line and "200" in line and "618" in line


def test_format_result_shows_the_detail_for_a_skip():
    line = format_result(
        CaseResult(case=make_cases()[0], outcome=SKIPPED, detail="blocked pattern '/admin'")
    )
    assert "SKIPPED" in line
    assert "/admin" in line


# --------------------------------------------------------------------------
# against the real client object, with the socket faked out
# --------------------------------------------------------------------------


class _FakeElapsed:
    def total_seconds(self):
        return 0.05


class _FakeRaw:
    def __init__(self, status=200, text="{}"):
        self.status_code = status
        self.text = text
        self.content = text.encode()
        self.headers = {}
        self.elapsed = _FakeElapsed()


def test_committed_cases_run_through_a_real_apiclient(monkeypatch):
    """The five hand-written cases reach the client with their real inputs."""
    from core.testcase import load_file

    client = ApiClient(
        {
            "base_url": "https://api.staging.example.com",
            "require_host_substring": "staging",
            "allowed_methods": ["GET"],
            "auth": {"type": "none"},
        }
    )
    sent = []

    def capture(method, url, **kwargs):
        sent.append(kwargs.get("params"))
        return _FakeRaw()

    monkeypatch.setattr(client.session, "request", capture)

    results = run_cases(client, load_file(COMMITTED), check_health=False)
    assert results.counts() == {RAN: 5, SKIPPED: 0, ERROR: 0}
    assert {"size": 101} in sent
    assert {"sortBy": "nonexistent_column"} in sent
