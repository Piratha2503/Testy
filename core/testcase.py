"""Test case file format: load and validate.

Session 04 scope: fix the on-disk format and make it enforceable. A format
that only exists in a README drifts the moment an LLM starts writing files
against it, so the rules live here and the committed files are tested.

One file per endpoint::

    {
      "endpoint": {"method": "GET", "path": "/api/v1/website-slots"},
      "cases": [
        {
          "name": "...",            required, unique within the file
          "category": "...",        required, one of CATEGORIES
          "path_params": {...},     optional, {} when the path has none
          "query": {...},           optional
          "body": ...,              optional, null for GET
          "expected_status": 400,   required, the HTTP status that *should*
                                    come back per HTTP semantics -- not
                                    whatever this API happens to return
          "reason": "..."           required, why that status is right
        }
      ]
    }

Unknown keys are rejected rather than ignored. When session 11 points an LLM
at this format, a hallucinated field must fail loudly instead of being
silently dropped.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Deliberately small. A category exists to group findings in the report, not
# to describe every thought the author had.
CATEGORIES = (
    "happy_path",      # valid input, should succeed
    "boundary",        # the edge of a documented range, still valid
    "invalid_input",   # malformed or out-of-range input, should be rejected
    "not_found",       # well-formed request for something that does not exist
    "auth",            # missing or bad credentials
)

CASE_REQUIRED = ("name", "category", "expected_status", "reason")
CASE_OPTIONAL = ("path_params", "query", "body")
CASE_KEYS = CASE_REQUIRED + CASE_OPTIONAL


class TestCaseError(Exception):
    """A test case file is malformed. Never raised for a failing test."""

    # These names start with "Test", so pytest tries to collect them as test
    # classes and warns. They are our domain objects, not test classes.
    __test__ = False


@dataclass
class TestCase:
    """One request to make, and the status it ought to come back with."""

    __test__ = False  # see TestCaseError

    name: str
    category: str
    method: str
    path: str
    expected_status: int
    reason: str
    path_params: dict[str, Any] = field(default_factory=dict)
    query: dict[str, Any] = field(default_factory=dict)
    body: Any = None
    source_file: str = ""

    @property
    def endpoint_key(self) -> str:
        return f"{self.method} {self.path}"


def slug_for(method: str, path: str) -> str:
    """Stable file name for an endpoint: GET /api/v1/pets -> get_api-v1-pets.

    Session 13 writes one file per endpoint in a loop, so this has to be a
    pure function of the endpoint -- rerunning must overwrite, not accumulate.
    """
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", path).strip("-").lower()
    return f"{method.lower()}_{cleaned}"


def _require_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TestCaseError(f"{label} must be an object, got {type(value).__name__}")
    return value


def _validate_case(raw: Any, label: str, method: str, path: str, source: str) -> TestCase:
    case = _require_mapping(raw, label)

    unknown = sorted(set(case) - set(CASE_KEYS))
    if unknown:
        raise TestCaseError(f"{label}: unknown key(s) {unknown}; allowed: {list(CASE_KEYS)}")

    missing = [k for k in CASE_REQUIRED if k not in case]
    if missing:
        raise TestCaseError(f"{label}: missing required key(s) {missing}")

    for key in ("name", "reason"):
        if not isinstance(case[key], str) or not case[key].strip():
            raise TestCaseError(f"{label}: '{key}' must be a non-empty string")

    if case["category"] not in CATEGORIES:
        raise TestCaseError(
            f"{label}: category {case['category']!r} is not one of {list(CATEGORIES)}"
        )

    status = case["expected_status"]
    # bool is an int in Python, and "expected_status": true is a real LLM slip.
    if isinstance(status, bool) or not isinstance(status, int):
        raise TestCaseError(f"{label}: 'expected_status' must be an integer, got {status!r}")
    if not 100 <= status <= 599:
        raise TestCaseError(f"{label}: 'expected_status' {status} is not an HTTP status")

    path_params = _require_mapping(case.get("path_params") or {}, f"{label}: 'path_params'")
    query = _require_mapping(case.get("query") or {}, f"{label}: 'query'")

    declared = set(re.findall(r"\{([^}]+)\}", path))
    supplied = set(path_params)
    if declared - supplied:
        raise TestCaseError(
            f"{label}: path needs {sorted(declared)} but path_params has {sorted(supplied)}"
        )
    if supplied - declared:
        raise TestCaseError(
            f"{label}: path_params has {sorted(supplied - declared)}, not in the path"
        )

    return TestCase(
        name=case["name"].strip(),
        category=case["category"],
        method=method,
        path=path,
        expected_status=status,
        reason=case["reason"].strip(),
        path_params=path_params,
        query=query,
        body=case.get("body"),
        source_file=source,
    )


def parse_document(document: Any, source: str = "") -> list[TestCase]:
    """Validate a loaded test case document and return its cases."""
    document = _require_mapping(document, f"{source or 'document'}: top level")

    endpoint = _require_mapping(document.get("endpoint"), f"{source}: 'endpoint'")
    method = endpoint.get("method")
    path = endpoint.get("path")
    if not isinstance(method, str) or not method.strip():
        raise TestCaseError(f"{source}: endpoint.method is missing")
    if not isinstance(path, str) or not path.startswith("/"):
        raise TestCaseError(f"{source}: endpoint.path must start with '/'")
    method = method.upper()

    cases = document.get("cases")
    if not isinstance(cases, list) or not cases:
        raise TestCaseError(f"{source}: 'cases' must be a non-empty array")

    parsed = []
    seen: set[str] = set()
    for index, raw in enumerate(cases):
        case = _validate_case(raw, f"{source}[{index}]", method, path, source)
        if case.name in seen:
            # Duplicate names make a CSV report unreadable and, worse, make a
            # failure impossible to trace back to a line in the file.
            raise TestCaseError(f"{source}: duplicate case name {case.name!r}")
        seen.add(case.name)
        parsed.append(case)
    return parsed


def load_file(path: str | Path) -> list[TestCase]:
    """Read one test case JSON file."""
    path = Path(path)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TestCaseError(f"Test case file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise TestCaseError(f"{path}: invalid JSON: {exc}") from exc
    return parse_document(document, source=path.name)


def load_dir(directory: str | Path) -> list[TestCase]:
    """Read every .json file in a directory, sorted by name for determinism."""
    directory = Path(directory)
    cases: list[TestCase] = []
    for path in sorted(directory.glob("*.json")):
        cases.extend(load_file(path))
    return cases
