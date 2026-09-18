"""CSV output and the run summary.

The CSV is the deliverable. Someone who was not in the room opens it and has
to understand what was tried, what came back, and whether that is a problem --
without reading any of this code.

Two rules shape it:

* Every row is self-contained. The input that produced a result sits in the
  same row as the result, so a finding can be reproduced from one line.
* Two runs differ only where reality did. Rows keep their file order, dicts
  are serialised with sorted keys, and the file name is fixed rather than
  timestamped -- so a diff of two reports shows what the API changed.

  Two columns still move on their own. ``ms`` is the measurement. ``response``
  mirrors the server byte for byte, so if the API puts a timestamp in its
  error body, that timestamp lands here -- and it should. Stripping it would
  be editing the evidence. Diff on verdict and actual, not on response.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable

from core.executor import ERROR, OUTCOMES, RAN, SKIPPED, CaseResult
from core.verdict import FAIL, NEEDS_REVIEW, PASS, VERDICTS

DEFAULT_REPORT = "reports/run.csv"

COLUMNS = (
    "endpoint",
    "case",
    "category",
    "input",
    "expected",
    "actual",
    "verdict",
    "outcome",
    "ms",
    "bytes",
    "reason",
    "detail",
    "response",
)

# Long enough to see an error message, short enough to keep a row readable.
SNIPPET_CHARS = 200


def _compact(value: Any) -> str:
    """JSON without spaces, so a cell stays narrow and diffs stay stable."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def format_input(case) -> str:
    """Everything that made this request different from the bare endpoint.

    Empty when the case sends nothing extra, which is the honest answer for
    'GET /things with no parameters'.
    """
    parts = []
    if case.path_params:
        parts.append(f"path={_compact(case.path_params)}")
    if case.query:
        parts.append(f"query={_compact(case.query)}")
    if case.body is not None:
        parts.append(f"body={_compact(case.body)}")
    return " ".join(parts)


def _one_line(text: str, limit: int = SNIPPET_CHARS) -> str:
    """Collapse whitespace so a body cannot break the shape of the sheet."""
    flattened = " ".join(text.split())
    if len(flattened) > limit:
        return flattened[: limit - 3] + "..."
    return flattened


def row_for(result: CaseResult) -> dict[str, Any]:
    case = result.case
    return {
        "endpoint": result.endpoint_key,
        "case": case.name,
        "category": case.category,
        "input": format_input(case),
        "expected": case.expected_status,
        "actual": result.status if result.status is not None else "",
        "verdict": result.verdict or "",
        "outcome": result.outcome,
        "ms": result.elapsed_ms,
        "bytes": result.response_bytes,
        "reason": case.reason,
        "detail": result.detail,
        "response": _one_line(result.body),
    }


def write_csv(results: Iterable[CaseResult], path: str | Path = DEFAULT_REPORT) -> Path:
    """Write one row per result. Returns the path written."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # newline="" is required on Windows, or every row gets a blank line
    # between it and the next one.
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for result in results:
            writer.writerow(row_for(result))
    return path


def summary_lines(results: list[CaseResult]) -> list[str]:
    """The three or four lines worth reading after a run.

    Verdicts and outcomes are counted separately on purpose. A case that was
    never sent has no verdict, and folding it into the pass/fail line would
    make the totals lie.
    """
    total = len(results)
    judged = [r for r in results if r.verdict]

    verdict_counts = {v: sum(1 for r in judged if r.verdict == v) for v in VERDICTS}
    outcome_counts = {o: sum(1 for r in results if r.outcome == o) for o in OUTCOMES}

    lines = [
        f"{total} cases: "
        + "  ".join(f"{name}={count}" for name, count in verdict_counts.items()),
    ]

    not_judged = outcome_counts[SKIPPED] + outcome_counts[ERROR]
    if not_judged:
        # Do not name a cause here. A case is skipped by a guardrail or by a
        # missing seed value, and guessing wrong in the summary sends the
        # reader looking in the wrong config file. The detail column says why.
        lines.append(
            f"{not_judged} not judged: "
            f"SKIPPED={outcome_counts[SKIPPED]} (not sent) "
            f"ERROR={outcome_counts[ERROR]} (no response)"
        )

    # The live lines during a run already showed every case. Repeating all of
    # them here would bury the few that need a person; list only those.
    for verdict in (FAIL, NEEDS_REVIEW):
        flagged = [r for r in results if r.verdict == verdict]
        if not flagged:
            continue
        lines.append("")
        lines.append(f"{verdict}:")
        for result in flagged:
            lines.append(
                f"  {result.endpoint_key}  {result.case.name}"
            )
            lines.append(
                f"    expected {result.case.expected_status}, got {result.status}"
                f"  ({result.case.category})"
            )
    return lines


def has_failures(results: Iterable[CaseResult]) -> bool:
    """Whether the run should end in a non-zero exit."""
    return any(r.verdict == FAIL for r in results)
