"""Verdict tests.

The rule is four lines long and every line has an edge someone will trip on
later, so each gets its own test with the reasoning written down.
"""

from __future__ import annotations

import pytest

from core.executor import ERROR, RAN, SKIPPED, CaseResult, RunResults
from core.swagger import Endpoint
from core.testcase import parse_document
from core.verdict import (
    FAIL,
    NEEDS_REVIEW,
    PASS,
    apply,
    codes_by_endpoint,
    counts,
    decide,
)


def make_case(expected_status=200, path="/api/v1/things", method="GET"):
    document = {
        "endpoint": {"method": method, "path": path},
        "cases": [
            {
                "name": "a case",
                "category": "happy_path",
                "expected_status": expected_status,
                "reason": "this status is the correct one for this input",
            }
        ],
    }
    return parse_document(document, source="t.json")[0]


def ran(status, expected_status=200):
    return CaseResult(
        case=make_case(expected_status), outcome=RAN, status=status, elapsed_ms=10
    )


# --------------------------------------------------------------------------
# rule 1 -- 5xx is always FAIL
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", [500, 502, 503, 599])
def test_5xx_is_always_fail(status):
    assert decide(ran(status)) == FAIL


def test_5xx_fails_even_when_the_case_expected_it():
    """A server error is never correct behaviour, so a case asserting one is
    a broken case, not a passing one."""
    assert decide(ran(500, expected_status=500)) == FAIL


def test_5xx_fails_even_when_the_spec_documents_it():
    assert decide(ran(503), documented_codes=[200, 503]) == FAIL


# --------------------------------------------------------------------------
# rule 2 -- expected match is PASS
# --------------------------------------------------------------------------


@pytest.mark.parametrize("status", [200, 201, 204, 400, 401, 404, 422])
def test_expected_match_is_pass(status):
    assert decide(ran(status, expected_status=status)) == PASS


def test_expected_4xx_that_arrives_is_a_pass():
    """Asserting an API rejects bad input is the main thing this tool does."""
    assert decide(ran(400, expected_status=400)) == PASS


# --------------------------------------------------------------------------
# rule 3 -- documented but not expected is NEEDS_REVIEW
# --------------------------------------------------------------------------


def test_documented_but_not_expected_is_needs_review():
    result = ran(404, expected_status=200)
    assert decide(result, documented_codes=[200, 404]) == NEEDS_REVIEW


def test_undocumented_mismatch_is_fail():
    result = ran(404, expected_status=200)
    assert decide(result, documented_codes=[200]) == FAIL


def test_a_404_against_an_expected_200_is_fail_when_undocumented():
    """This is how a missing seed value looks: the id did not exist. Under the
    rule it is a hard FAIL, because the spec never documented 404."""
    assert decide(ran(404, expected_status=200), documented_codes=[200]) == FAIL
    assert decide(ran(404, expected_status=200), documented_codes=[]) == FAIL


# --------------------------------------------------------------------------
# rule 4 -- anything else is FAIL
# --------------------------------------------------------------------------


def test_invalid_input_accepted_with_200_is_softened_when_200_is_documented():
    """Worth staring at. This is the finding the tool exists to produce -- bad
    input, no rejection -- and rule 3 turns it into NEEDS_REVIEW, because the
    spec lists 200 for this endpoint.

    On a spec that documents 200 and nothing else for every endpoint, that
    means every real finding lands in NEEDS_REVIEW while ambiguous 404s land
    in FAIL. Recorded as the rule's actual behaviour, not as an endorsement.
    """
    assert decide(ran(200, expected_status=400), documented_codes=[200]) == NEEDS_REVIEW
    # With nothing documented, the same result is a FAIL.
    assert decide(ran(200, expected_status=400), documented_codes=[]) == FAIL


def test_mismatch_with_nothing_documented_is_fail():
    assert decide(ran(301, expected_status=200)) == FAIL


# --------------------------------------------------------------------------
# no verdict at all
# --------------------------------------------------------------------------


def test_skipped_gets_no_verdict():
    """A call that was never made is neither a pass nor a failure."""
    result = CaseResult(case=make_case(), outcome=SKIPPED, detail="blocked")
    assert decide(result) is None


def test_error_gets_no_verdict():
    result = CaseResult(case=make_case(), outcome=ERROR, detail="timeout")
    assert decide(result) is None


def test_ran_without_a_status_gets_no_verdict():
    result = CaseResult(case=make_case(), outcome=RAN, status=None)
    assert decide(result) is None


# --------------------------------------------------------------------------
# applying across a run
# --------------------------------------------------------------------------


def build_run():
    results = RunResults()
    results.results = [
        ran(200, expected_status=200),                                  # match
        ran(200, expected_status=400),                                  # invalid accepted
        ran(404, expected_status=200),                                  # missing thing
        ran(500, expected_status=200),                                  # server error
        CaseResult(case=make_case(), outcome=SKIPPED, detail="blocked"),
        CaseResult(case=make_case(), outcome=ERROR, detail="timeout"),
    ]
    return results


def test_apply_fills_every_result():
    results = build_run()
    apply(results, {"GET /api/v1/things": [200, 404]})

    assert [r.verdict for r in results] == [
        PASS,           # expected 200, got 200
        NEEDS_REVIEW,   # expected 400, got a documented 200
        NEEDS_REVIEW,   # expected 200, got a documented 404
        FAIL,           # 5xx always
        None,           # skipped
        None,           # error
    ]


def test_apply_without_documented_codes_is_safe():
    results = build_run()
    apply(results)
    assert [r.verdict for r in results] == [PASS, FAIL, FAIL, FAIL, None, None]


def test_an_endpoint_missing_from_the_spec_map_only_costs_a_review():
    """Missing documentation can never turn a FAIL into a PASS."""
    results = build_run()
    apply(results, {"GET /somewhere/else": [404]})
    assert [r.verdict for r in results] == [PASS, FAIL, FAIL, FAIL, None, None]


def test_counts_ignores_results_with_no_verdict():
    results = build_run()
    apply(results, {"GET /api/v1/things": [200, 404]})

    assert counts(results) == {PASS: 1, FAIL: 1, NEEDS_REVIEW: 2}


def test_counts_of_an_empty_run():
    assert counts([]) == {PASS: 0, FAIL: 0, NEEDS_REVIEW: 0}


# --------------------------------------------------------------------------
# spec wiring
# --------------------------------------------------------------------------


def test_codes_by_endpoint_keys_match_case_endpoint_keys():
    endpoints = [
        Endpoint(path="/api/v1/things", method="GET", documented_codes=[200, 404]),
        Endpoint(path="/api/v1/things", method="POST", documented_codes=[201]),
    ]
    mapping = codes_by_endpoint(endpoints)

    assert mapping == {"GET /api/v1/things": [200, 404], "POST /api/v1/things": [201]}
    assert make_case().endpoint_key in mapping


def test_codes_from_the_fixture_spec_line_up():
    from core.swagger import parse_file

    mapping = codes_by_endpoint(parse_file("tests/fixtures/mini_spec.yaml"))
    assert mapping["GET /pets/{petId}"] == [200, 404]
