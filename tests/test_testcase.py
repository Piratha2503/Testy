"""Format tests.

Half of these check that bad input is rejected. That is the point of the
format: session 11 hands an LLM these rules, and a field it invents must
fail loudly instead of being silently dropped.
"""

from __future__ import annotations

import json

import pytest

from core.testcase import (
    CATEGORIES,
    TestCaseError,
    load_dir,
    load_file,
    parse_document,
    slug_for,
)

COMMITTED = "testcases/get_api-v1-website-slots.json"


def doc(**overrides):
    """A minimal valid document, before overrides."""
    document = {
        "endpoint": {"method": "GET", "path": "/api/v1/things"},
        "cases": [
            {
                "name": "default listing",
                "category": "happy_path",
                "query": {},
                "expected_status": 200,
                "reason": "a list endpoint with no parameters should return a page",
            }
        ],
    }
    document.update(overrides)
    return document


def case(**overrides):
    """A document whose single case carries the overrides."""
    document = doc()
    document["cases"][0].update(overrides)
    return document


# --------------------------------------------------------------------------
# the committed cases
# --------------------------------------------------------------------------


def test_committed_file_loads():
    cases = load_file(COMMITTED)
    assert len(cases) == 5
    assert {c.endpoint_key for c in cases} == {"GET /api/v1/website-slots"}


def test_committed_file_covers_more_than_the_happy_path():
    categories = {c.category for c in load_file(COMMITTED)}
    assert "happy_path" in categories
    assert "invalid_input" in categories
    assert len(categories) >= 3


def test_committed_invalid_input_cases_expect_4xx():
    """Expectations follow HTTP semantics, not this API's actual behaviour."""
    for c in load_file(COMMITTED):
        if c.category == "invalid_input":
            assert 400 <= c.expected_status < 500, c.name


def test_every_testcase_file_in_the_repo_is_valid():
    assert load_dir("testcases")


# --------------------------------------------------------------------------
# structure
# --------------------------------------------------------------------------


def test_missing_endpoint_is_rejected():
    with pytest.raises(TestCaseError, match="endpoint"):
        parse_document({"cases": []})


def test_path_must_be_absolute():
    with pytest.raises(TestCaseError, match="must start with"):
        parse_document(doc(endpoint={"method": "GET", "path": "api/v1/things"}))


def test_empty_cases_array_is_rejected():
    with pytest.raises(TestCaseError, match="non-empty array"):
        parse_document(doc(cases=[]))


def test_method_is_upper_cased():
    document = doc(endpoint={"method": "get", "path": "/api/v1/things"})
    assert parse_document(document)[0].method == "GET"


def test_duplicate_case_names_are_rejected():
    document = doc()
    document["cases"].append(dict(document["cases"][0]))
    with pytest.raises(TestCaseError, match="duplicate case name"):
        parse_document(document)


# --------------------------------------------------------------------------
# per-case validation
# --------------------------------------------------------------------------


@pytest.mark.parametrize("key", ["name", "category", "expected_status", "reason"])
def test_required_keys(key):
    document = doc()
    del document["cases"][0][key]
    with pytest.raises(TestCaseError, match="missing required"):
        parse_document(document)


def test_unknown_key_is_rejected():
    with pytest.raises(TestCaseError, match="unknown key"):
        parse_document(case(expectd_status=200))


def test_unknown_category_is_rejected():
    with pytest.raises(TestCaseError, match="not one of"):
        parse_document(case(category="smoke"))


@pytest.mark.parametrize("category", CATEGORIES)
def test_every_declared_category_is_accepted(category):
    assert parse_document(case(category=category))[0].category == category


def test_blank_reason_is_rejected():
    with pytest.raises(TestCaseError, match="non-empty string"):
        parse_document(case(reason="   "))


def test_expected_status_must_be_an_int():
    with pytest.raises(TestCaseError, match="must be an integer"):
        parse_document(case(expected_status="200"))


def test_expected_status_true_is_not_200():
    """bool is an int in Python; this slip must not sail through."""
    with pytest.raises(TestCaseError, match="must be an integer"):
        parse_document(case(expected_status=True))


def test_expected_status_out_of_range_is_rejected():
    with pytest.raises(TestCaseError, match="not an HTTP status"):
        parse_document(case(expected_status=40000))


def test_query_must_be_an_object():
    with pytest.raises(TestCaseError, match="must be an object"):
        parse_document(case(query=["page=1"]))


# --------------------------------------------------------------------------
# path params
# --------------------------------------------------------------------------


def test_path_param_must_be_supplied():
    document = doc(endpoint={"method": "GET", "path": "/api/v1/things/{id}"})
    with pytest.raises(TestCaseError, match="path needs"):
        parse_document(document)


def test_extra_path_param_is_rejected():
    with pytest.raises(TestCaseError, match="not in the path"):
        parse_document(case(path_params={"id": 1}))


def test_supplied_path_param_is_kept():
    document = doc(endpoint={"method": "GET", "path": "/api/v1/things/{id}"})
    document["cases"][0]["path_params"] = {"id": 7}
    assert parse_document(document)[0].path_params == {"id": 7}


# --------------------------------------------------------------------------
# files
# --------------------------------------------------------------------------


def test_missing_file():
    with pytest.raises(TestCaseError, match="not found"):
        load_file("testcases/no_such_file.json")


def test_invalid_json(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(TestCaseError, match="invalid JSON"):
        load_file(bad)


def test_load_dir_is_sorted(tmp_path):
    for name in ("b", "a"):
        document = doc(endpoint={"method": "GET", "path": f"/api/v1/{name}"})
        (tmp_path / f"{name}.json").write_text(json.dumps(document), encoding="utf-8")
    assert [c.path for c in load_dir(tmp_path)] == ["/api/v1/a", "/api/v1/b"]


# --------------------------------------------------------------------------
# slug
# --------------------------------------------------------------------------


def test_slug_matches_the_committed_file_name():
    assert slug_for("GET", "/api/v1/website-slots") == "get_api-v1-website-slots"


def test_slug_handles_path_params():
    assert slug_for("GET", "/api/v1/things/{id}") == "get_api-v1-things-id"


def test_slug_is_stable():
    assert slug_for("get", "/api/v1/Things/") == slug_for("GET", "/api/v1/Things")
