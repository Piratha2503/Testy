"""Replay loop: take test cases, call the API, record what came back.

Session 05 scope: run cases and record outcomes. No verdicts here -- whether
a result is PASS or FAIL is session 06's job, and keeping the two apart means
the verdict rule can change without touching the code that makes requests.

The loop never raises for a bad endpoint. A case the guardrails refuse is
recorded as SKIPPED, a case that never got a reply is ERROR, and the run
carries on. One dead endpoint must not cost you the other fifty-nine results.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable

from core.client import ApiClient, GuardrailError, Response
from core.seed import SeedError, resolve_path_params
from core.testcase import TestCase

# What happened to the request, not whether the API behaved.
RAN = "RAN"          # a reply came back, whatever it said
SKIPPED = "SKIPPED"  # we did not send it: guardrails, or no seed value
ERROR = "ERROR"      # we sent it and got nothing: timeout, refused, DNS

OUTCOMES = (RAN, SKIPPED, ERROR)


class UnhealthyApiError(Exception):
    """The pre-run health check failed, so no cases were run."""


@dataclass
class CaseResult:
    """One case, and what the API did with it.

    SKIPPED and ERROR are deliberately separate. SKIPPED means the tool
    worked: it declined to make a call it was told not to make. ERROR means
    the call went out and nothing came back. Collapsing them into one bucket
    would let "staging was down" read as "those were blocked on purpose".
    """

    case: TestCase
    outcome: str
    status: int | None = None
    elapsed_ms: int = 0
    response_bytes: int = 0
    body: str = ""
    truncated: bool = False
    detail: str = ""  # why it was skipped, or what the transport said

    # Filled in by core.verdict.apply(). None means there was nothing to
    # judge: a call that was never made, or never answered.
    verdict: str | None = None

    @property
    def name(self) -> str:
        return self.case.name

    @property
    def endpoint_key(self) -> str:
        return self.case.endpoint_key


@dataclass
class RunResults:
    """Everything one run produced, in the order the cases were written."""

    results: list[CaseResult] = field(default_factory=list)

    def __iter__(self):
        return iter(self.results)

    def __len__(self) -> int:
        return len(self.results)

    def counts(self) -> dict[str, int]:
        tally = Counter(r.outcome for r in self.results)
        return {outcome: tally.get(outcome, 0) for outcome in OUTCOMES}

    def of(self, outcome: str) -> list[CaseResult]:
        return [r for r in self.results if r.outcome == outcome]


def run_case(
    client: ApiClient, case: TestCase, seed: dict[str, Any] | None = None
) -> CaseResult:
    """Run one case. Returns a result for every outcome, raises for none."""
    try:
        path_params = resolve_path_params(case, seed or {})
    except SeedError as exc:
        # No value to put in the URL, so nothing is sent. Sending a made-up id
        # instead would produce a 404 that says nothing about the API.
        return CaseResult(case=case, outcome=SKIPPED, detail=str(exc))

    try:
        response: Response = client.request(
            case.method,
            case.path,
            path_params=path_params,
            query=case.query,
            body=case.body,
        )
    except GuardrailError as exc:
        # Not a failure of the API, and not a failure of the case. The tool
        # was told not to make this call and did not make it.
        return CaseResult(case=case, outcome=SKIPPED, detail=str(exc))

    if response.status is None:
        return CaseResult(
            case=case,
            outcome=ERROR,
            elapsed_ms=response.elapsed_ms,
            detail=response.error or "no response",
        )

    return CaseResult(
        case=case,
        outcome=RAN,
        status=response.status,
        elapsed_ms=response.elapsed_ms,
        response_bytes=response.response_bytes,
        body=response.body,
        truncated=response.truncated,
    )


def run_cases(
    client: ApiClient,
    cases: list[TestCase],
    on_result: Callable[[CaseResult], Any] | None = None,
    check_health: bool = True,
    seed: dict[str, Any] | None = None,
) -> RunResults:
    """Run every case in order, optionally reporting each as it finishes.

    The health check runs first by default: sixty failures against a host
    that is simply down tell you nothing, and take ten minutes to read.
    """
    if check_health:
        health = client.health_check()
        if not health.ok:
            raise UnhealthyApiError(health.reason)

    results = RunResults()
    for case in cases:
        result = run_case(client, case, seed)
        results.results.append(result)
        if on_result is not None:
            on_result(result)
    return results


def format_result(result: CaseResult) -> str:
    """One ASCII line per case, for a terminal that may be a Windows console."""
    status = str(result.status) if result.status is not None else "-"
    # Before verdicts are applied, and for skipped or errored cases, the
    # outcome is all there is to show.
    label = result.verdict or result.outcome
    line = (
        f"{label:12} {status:>4} {result.elapsed_ms:>6}ms "
        f"{result.response_bytes:>7}b  {result.case.name}"
    )
    if result.detail:
        line += f"\n{'':>9}{result.detail}"
    return line
