"""Seed data tests.

The rule worth protecting: a parameter with no seed value must stop the case,
not invent an id. A made-up id produces a 404 that says nothing about the API
and everything about our test data.
"""

from __future__ import annotations

import pytest

from core.client import ApiClient, Response
from core.executor import RAN, SKIPPED, run_case, run_cases
from core.seed import PLACEHOLDER, SeedError, load_seed, lookup, resolve_path_params
from core.testcase import parse_document

SEED = {
    "defaults": {"countryCode": "ME", "id": 1},
    "endpoints": {"GET /api/v1/things/{id}": {"id": 42}},
}


def make_case(path="/api/v1/things/{id}", path_params=None):
    document = {
        "endpoint": {"method": "GET", "path": path},
        "cases": [
            {
                "name": "a case",
                "category": "happy_path",
                "path_params": path_params if path_params is not None else {"id": PLACEHOLDER},
                "expected_status": 200,
                "reason": "fetching a record that exists should return it",
            }
        ],
    }
    return parse_document(document, source="t.json")[0]


# --------------------------------------------------------------------------
# lookup
# --------------------------------------------------------------------------


def test_endpoint_value_wins_over_the_default():
    assert lookup(SEED, "GET /api/v1/things/{id}", "id") == 42


def test_default_is_used_when_the_endpoint_is_not_listed():
    assert lookup(SEED, "GET /api/v1/other/{id}", "id") == 1


def test_default_covers_a_param_the_endpoint_entry_omits():
    assert lookup(SEED, "GET /api/v1/things/{id}", "countryCode") == "ME"


def test_missing_value_raises_with_a_usable_message():
    with pytest.raises(SeedError) as exc:
        lookup(SEED, "GET /api/v1/things/{id}", "slug")
    message = str(exc.value)
    assert "slug" in message
    assert "seed_data.yaml" in message


def test_empty_seed_raises_rather_than_guessing():
    with pytest.raises(SeedError):
        lookup({}, "GET /api/v1/things/{id}", "id")


# --------------------------------------------------------------------------
# resolution
# --------------------------------------------------------------------------


def test_placeholder_is_replaced():
    assert resolve_path_params(make_case(), SEED) == {"id": 42}


def test_a_literal_value_is_left_alone():
    """A not-found case means that id on purpose; it is not a seed gap."""
    case = make_case(path_params={"id": 99999999})
    assert resolve_path_params(case, SEED) == {"id": 99999999}


def test_a_literal_value_needs_no_seed_file_at_all():
    case = make_case(path_params={"id": 99999999})
    assert resolve_path_params(case, {}) == {"id": 99999999}


def test_case_with_no_path_params_is_unaffected():
    case = make_case(path="/api/v1/things", path_params={})
    assert resolve_path_params(case, {}) == {}


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------


def test_missing_file_is_not_an_error():
    """Most endpoints take no path params, so no seed file is normal."""
    assert load_seed("no_such_seed.yaml") == {}


def test_empty_file_is_not_an_error(tmp_path):
    path = tmp_path / "seed.yaml"
    path.write_text("", encoding="utf-8")
    assert load_seed(path) == {}


def test_loads_both_sections(tmp_path):
    path = tmp_path / "seed.yaml"
    path.write_text(
        "defaults:\n  id: 1\nendpoints:\n  \"GET /a/{id}\":\n    id: 9\n", encoding="utf-8"
    )
    seed = load_seed(path)
    assert lookup(seed, "GET /a/{id}", "id") == 9


def test_a_list_at_the_top_level_is_rejected(tmp_path):
    path = tmp_path / "seed.yaml"
    path.write_text("- 1\n- 2\n", encoding="utf-8")
    with pytest.raises(SeedError, match="expected a mapping"):
        load_seed(path)


def test_a_non_mapping_section_is_rejected(tmp_path):
    path = tmp_path / "seed.yaml"
    path.write_text("defaults: [1, 2]\n", encoding="utf-8")
    with pytest.raises(SeedError, match="'defaults' must be a mapping"):
        load_seed(path)


# --------------------------------------------------------------------------
# through the executor
# --------------------------------------------------------------------------


class FakeClient:
    def __init__(self):
        self.calls = []

    def health_check(self):
        from core.client import HealthResult

        return HealthResult(ok=True, reason="ok")

    def request(self, method, path, **kwargs):
        self.calls.append(kwargs.get("path_params"))
        return Response(method=method, url=path, status=200, elapsed_ms=5,
                        body="{}", response_bytes=2)


def test_resolved_value_reaches_the_client():
    client = FakeClient()
    run_case(client, make_case(), SEED)
    assert client.calls == [{"id": 42}]


def test_a_case_with_no_seed_value_is_skipped_and_never_sent():
    client = FakeClient()
    result = run_case(client, make_case(), {})

    assert result.outcome == SKIPPED
    assert client.calls == []
    assert "no seed value" in result.detail


def test_one_missing_seed_does_not_stop_the_others():
    client = FakeClient()
    cases = [
        make_case(path="/api/v1/things/{id}"),      # resolves to 42
        make_case(path="/api/v1/missing/{slug}", path_params={"slug": PLACEHOLDER}),
        make_case(path="/api/v1/other/{id}"),       # resolves via defaults
    ]

    results = run_cases(client, cases, seed=SEED, check_health=False)
    assert [r.outcome for r in results] == [RAN, SKIPPED, RAN]


def test_running_without_a_seed_at_all_skips_rather_than_crashing():
    client = FakeClient()
    results = run_cases(client, [make_case()], check_health=False)
    assert results.counts()[SKIPPED] == 1


def test_the_committed_cases_use_placeholders_not_real_ids():
    """Real ids belong in the gitignored seed file, never in a committed case."""
    from core.testcase import load_dir

    for case in load_dir("testcases"):
        for name, value in case.path_params.items():
            if case.category in ("happy_path", "boundary"):
                assert value == PLACEHOLDER, f"{case.source_file}: {name}={value!r}"


def test_real_apiclient_never_opens_a_socket_for_an_unseeded_case(monkeypatch):
    client = ApiClient(
        {
            "base_url": "https://api.staging.example.com",
            "require_host_substring": "staging",
            "allowed_methods": ["GET"],
        }
    )

    def explode(*args, **kwargs):
        raise AssertionError("a request was made for a case with no seed value")

    monkeypatch.setattr(client.session, "request", explode)
    assert run_case(client, make_case(), {}).outcome == SKIPPED
