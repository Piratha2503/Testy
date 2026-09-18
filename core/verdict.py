"""Did the API behave? One verdict per case.

Kept apart from core.executor on purpose. The executor says what happened to
the request; this says whether that was acceptable. The rule below will be
argued about and changed; the code that makes HTTP calls should not have to
move when it is.

The rule, in order (PLAN session 06):

    1. 5xx                          -> FAIL
    2. status == expected_status    -> PASS
    3. status is documented in spec -> NEEDS_REVIEW
    4. anything else                -> FAIL

Order matters at step 1. A case that expects 500 and gets 500 is still a
FAIL: a server error is never correct behaviour, so a test asserting one is
a broken test, not a passing one.

Step 3 is the precision valve. A status the spec documents, but this case did
not ask for, is a disagreement between spec and case -- someone should look,
rather than the tool declaring the API broken.

One refinement to step 3, decided in session 10 against 58 real cases. A spec
that documents exactly one status for an endpoint is not claiming that status
is the only valid one; generators emit a single 200 when the author wrote
nothing. Treating that as evidence let the finding this tool exists to produce
-- invalid input accepted with 200 -- be softened to NEEDS_REVIEW on every
endpoint, while ambiguous 404s stayed FAIL. So a documented set of one is
treated as no information at all. A spec that documents 200 and 404 still
gets the valve, because there the author said something.
"""

from __future__ import annotations

from collections import Counter
from typing import Iterable, Sequence

from core.executor import RAN, CaseResult, RunResults
from core.swagger import Endpoint

PASS = "PASS"
FAIL = "FAIL"
NEEDS_REVIEW = "NEEDS_REVIEW"

VERDICTS = (PASS, FAIL, NEEDS_REVIEW)

# Below this, a documented set says nothing a generator would not have written
# on its own. See the note on step 3 above.
MIN_DOCUMENTED_CODES = 2


def is_informative(documented_codes: Sequence[int]) -> bool:
    """Whether the spec's documented codes are worth believing for an endpoint."""
    return len(set(documented_codes)) >= MIN_DOCUMENTED_CODES


def decide(result: CaseResult, documented_codes: Sequence[int] = ()) -> str | None:
    """The verdict for one result, or None when there is nothing to judge.

    SKIPPED and ERROR get no verdict at all. A call that was never made, or
    never answered, is neither a pass nor a failure of the API -- calling it
    either would put a number in the report that nobody can act on.
    """
    if result.outcome != RAN or result.status is None:
        return None

    status = result.status
    if status >= 500:
        return FAIL
    if status == result.case.expected_status:
        return PASS
    if is_informative(documented_codes) and status in documented_codes:
        return NEEDS_REVIEW
    return FAIL


def codes_by_endpoint(endpoints: Iterable[Endpoint]) -> dict[str, list[int]]:
    """Map 'GET /pets' -> the codes the spec documents for it."""
    return {endpoint.key: list(endpoint.documented_codes) for endpoint in endpoints}


def apply(
    results: RunResults | list[CaseResult],
    documented: dict[str, list[int]] | None = None,
) -> None:
    """Fill in result.verdict for every result, in place.

    ``documented`` comes from the spec, keyed by 'METHOD /path'. An endpoint
    missing from it is treated as documenting nothing, which only ever costs a
    NEEDS_REVIEW -- it can never turn a FAIL into a PASS.
    """
    documented = documented or {}
    for result in results:
        result.verdict = decide(result, documented.get(result.endpoint_key, ()))


def counts(results: RunResults | list[CaseResult]) -> dict[str, int]:
    """Verdict tally. Results with no verdict are not counted here; their
    outcome (SKIPPED / ERROR) is what describes them."""
    tally = Counter(r.verdict for r in results if r.verdict)
    return {verdict: tally.get(verdict, 0) for verdict in VERDICTS}
