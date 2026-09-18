"""CSV reporter tests.

The CSV is what someone who was not in the room actually reads, so these
check shape and self-containment, not just that a file appeared.
"""

from __future__ import annotations

import csv

from core.executor import ERROR, RAN, SKIPPED, CaseResult
from core.reporter import (
    COLUMNS,
    format_input,
    has_failures,
    row_for,
    summary_lines,
    write_csv,
)
from core.testcase import parse_document
from core.verdict import FAIL, NEEDS_REVIEW, PASS


def make_case(name="a case", expected_status=200, path="/api/v1/things", **extra):
    case = {
        "name": name,
        "category": "happy_path",
        "expected_status": expected_status,
        "reason": "this status is the correct one for this input",
    }
    case.update(extra)
    document = {"endpoint": {"method": "GET", "path": path}, "cases": [case]}
    return parse_document(document, source="t.json")[0]


def result(verdict=PASS, status=200, **kwargs):
    case = kwargs.pop("case", None) or make_case()
    return CaseResult(
        case=case,
        outcome=kwargs.pop("outcome", RAN),
        status=status,
        elapsed_ms=kwargs.pop("elapsed_ms", 12),
        response_bytes=kwargs.pop("response_bytes", 618),
        verdict=verdict,
        **kwargs,
    )


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


# --------------------------------------------------------------------------
# input rendering
# --------------------------------------------------------------------------


def test_input_is_empty_when_the_case_sends_nothing():
    assert format_input(make_case()) == ""


def test_input_shows_query():
    case = make_case(query={"size": 101})
    assert format_input(case) == 'query={"size":101}'


def test_input_shows_path_params_and_body():
    case = make_case(
        path="/api/v1/things/{id}", path_params={"id": 7}, body={"title": "x"}
    )
    rendered = format_input(case)
    assert 'path={"id":7}' in rendered
    assert 'body={"title":"x"}' in rendered


def test_input_keys_are_sorted_so_two_runs_match():
    case = make_case(query={"b": 2, "a": 1})
    assert format_input(case) == 'query={"a":1,"b":2}'


# --------------------------------------------------------------------------
# rows
# --------------------------------------------------------------------------


def test_row_has_every_column():
    assert set(row_for(result())) == set(COLUMNS)


def test_row_carries_the_input_that_produced_it():
    """A finding has to be reproducible from one line of the sheet."""
    row = row_for(result(case=make_case(query={"size": 101}, expected_status=400),
                         verdict=NEEDS_REVIEW))
    assert row["input"] == 'query={"size":101}'
    assert row["expected"] == 400
    assert row["actual"] == 200


def test_skipped_row_has_no_verdict_and_no_status():
    row = row_for(
        CaseResult(case=make_case(), outcome=SKIPPED, detail="blocked pattern")
    )
    assert row["verdict"] == ""
    assert row["actual"] == ""
    assert row["outcome"] == SKIPPED
    assert "blocked" in row["detail"]


def test_error_row_says_what_the_transport_said():
    row = row_for(
        CaseResult(case=make_case(), outcome=ERROR, detail="timeout after 10.0s")
    )
    assert row["outcome"] == ERROR
    assert "timeout" in row["detail"]


def test_response_snippet_is_one_line():
    """A body with newlines must not break the shape of the sheet."""
    row = row_for(result(body='{\n  "a": 1\n}'))
    assert "\n" not in row["response"]
    assert '"a": 1' in row["response"]


def test_long_response_is_cut_with_an_ellipsis():
    row = row_for(result(body="x" * 5000))
    assert len(row["response"]) <= 200
    assert row["response"].endswith("...")


# --------------------------------------------------------------------------
# the file
# --------------------------------------------------------------------------


def test_csv_has_a_header_and_one_row_per_result(tmp_path):
    path = write_csv([result(), result(verdict=FAIL, status=500)], tmp_path / "r.csv")
    rows = read_csv(path)

    assert len(rows) == 2
    assert list(rows[0]) == list(COLUMNS)


def test_csv_creates_its_directory(tmp_path):
    path = write_csv([result()], tmp_path / "nested" / "deeper" / "r.csv")
    assert path.is_file()


def test_csv_rows_keep_case_order(tmp_path):
    results = [result(case=make_case(name=n)) for n in ("first", "second", "third")]
    rows = read_csv(write_csv(results, tmp_path / "r.csv"))
    assert [r["case"] for r in rows] == ["first", "second", "third"]


def test_two_writes_of_the_same_results_are_identical(tmp_path):
    results = [result(case=make_case(query={"b": 2, "a": 1}))]
    first = write_csv(results, tmp_path / "a.csv").read_bytes()
    second = write_csv(results, tmp_path / "b.csv").read_bytes()
    assert first == second


def test_csv_has_no_blank_lines_between_rows(tmp_path):
    """Windows turns a missing newline='' into a blank line per row."""
    path = write_csv([result(), result()], tmp_path / "r.csv")
    text = path.read_text(encoding="utf-8")
    assert "\n\n" not in text.replace("\r\n", "\n")


# --------------------------------------------------------------------------
# summary
# --------------------------------------------------------------------------


def test_summary_counts_verdicts():
    results = [result(), result(), result(verdict=FAIL, status=500)]
    assert "PASS=2" in summary_lines(results)[0]
    assert "FAIL=1" in summary_lines(results)[0]


def test_summary_counts_unjudged_separately():
    """Folding skipped cases into pass/fail would make the totals lie."""
    results = [
        result(),
        CaseResult(case=make_case(), outcome=SKIPPED, verdict=None),
        CaseResult(case=make_case(), outcome=ERROR, verdict=None),
    ]
    text = "\n".join(summary_lines(results))

    assert "3 cases: PASS=1" in text
    assert "2 not judged" in text
    assert "SKIPPED=1" in text and "ERROR=1" in text
    # the summary must not guess *why* it was skipped
    assert "guardrail" not in text.lower()


def test_summary_omits_the_not_judged_line_when_everything_ran():
    assert "not judged" not in "\n".join(summary_lines([result()]))


def test_summary_lists_failures_with_what_was_expected():
    results = [result(case=make_case(name="bad size", expected_status=400), verdict=FAIL)]
    text = "\n".join(summary_lines(results))

    assert "FAIL:" in text
    assert "bad size" in text
    assert "expected 400, got 200" in text


def test_summary_lists_needs_review_too():
    results = [result(verdict=NEEDS_REVIEW, case=make_case(expected_status=400))]
    assert "NEEDS_REVIEW:" in "\n".join(summary_lines(results))


def test_summary_does_not_relist_passing_cases():
    """The live lines already showed those; repeating them buries the rest."""
    results = [result(case=make_case(name="quiet success"))]
    assert "quiet success" not in "\n".join(summary_lines(results)[1:])


def test_has_failures():
    assert has_failures([result(verdict=FAIL)]) is True
    assert has_failures([result(), result(verdict=NEEDS_REVIEW)]) is False
    assert has_failures([]) is False
