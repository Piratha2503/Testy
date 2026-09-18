"""CLI entry point.

Three commands.

``list`` parses a spec and prints the endpoints it found, saying per endpoint
whether the guardrails in core.client would let it be called at all -- that is
the column that matters when picking targets for a real run.

``health`` calls one cheap endpoint and exits non-zero if the API is not up,
so a suite is never run against a dead host.

``run`` replays test cases, judges them, writes a CSV, and exits non-zero if
anything failed.

    python main.py list --method GET --runnable
    python main.py health
    python main.py run
    python main.py run --endpoint website-slots --limit 5

Exit codes are shared across commands: 0 clean, 1 bad input, 2 guardrail,
3 API unhealthy, 4 the run finished with failures.

``generate`` arrives in session 13.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from core.client import ApiClient, ConfigError, GuardrailError, load_config
from core.executor import format_result, run_cases
from core.reporter import DEFAULT_REPORT, has_failures, summary_lines, write_csv
from core.swagger import Endpoint, SpecError, parse_file
from core.testcase import TestCaseError, load_dir
from core.verdict import apply as apply_verdicts
from core.verdict import codes_by_endpoint

DEFAULT_SPEC = "specs/openapi.json"

# Terminal here is a Windows console more often than not, and its default
# code page mangles anything outside cp1252. Keep every printed glyph ASCII.
COLUMNS = ("METHOD", "PATH", "CODES", "PARAMS", "BODY", "GUARDRAIL")


def _fmt_params(endpoint: Endpoint) -> str:
    bits = []
    if endpoint.path_params:
        bits.append(f"p:{len(endpoint.path_params)}")
    if endpoint.query_params:
        bits.append(f"q:{len(endpoint.query_params)}")
    return ",".join(bits)


def _guardrail_status(client: ApiClient | None, endpoint: Endpoint) -> str:
    """One word (or a short reason) for what the client would do with this.

    'ok' means the guardrails allow the call, not that the call will pass.
    """
    if client is None:
        return "?"
    try:
        # Placeholders are irrelevant to the path-pattern check, so fill them
        # with a dummy rather than reporting every {id} path as unfillable.
        # Path first: "this path is off limits" outranks "wrong method", and
        # POST /booking/book must not be filed under a method problem.
        dummy = {p["name"]: "1" for p in endpoint.path_params}
        client.build_url(endpoint.path, dummy)
    except GuardrailError as exc:
        return "blocked" if "blocked pattern" in str(exc) else "path"
    try:
        client._check_method(endpoint.method)
    except GuardrailError:
        return "method"
    return "ok"


def _print_table(rows: list[tuple[str, ...]]) -> None:
    widths = [
        max(len(str(row[i])) for row in ([COLUMNS] + rows)) for i in range(len(COLUMNS))
    ]
    line = "  ".join(col.ljust(w) for col, w in zip(COLUMNS, widths)).rstrip()
    print(line)
    print("-" * len(line))
    for row in rows:
        print("  ".join(str(cell).ljust(w) for cell, w in zip(row, widths)).rstrip())


def _build_client(config: dict[str, Any]) -> ApiClient | None:
    """Build a client for the guardrail column, or explain why we could not.

    A guardrail failure here is not fatal for ``list``: reading a spec file is
    not calling an API. It is still worth shouting about, because the same
    config will hard-stop ``run`` in session 07.
    """
    try:
        return ApiClient(config)
    except GuardrailError as exc:
        print(f"WARNING: guardrail column unavailable -- {exc}\n", file=sys.stderr)
    except ConfigError as exc:
        print(f"WARNING: guardrail column unavailable -- config: {exc}\n", file=sys.stderr)
    return None


def cmd_list(args: argparse.Namespace) -> int:
    config = load_config(args.config) if args.config else load_config()
    spec_path = args.spec or config.get("spec_path") or DEFAULT_SPEC

    try:
        endpoints = parse_file(spec_path)
    except SpecError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    client = _build_client(config)

    selected = endpoints
    if args.method:
        wanted = {m.upper() for m in args.method}
        selected = [e for e in selected if e.method in wanted]
    if args.grep:
        needle = args.grep.lower()
        selected = [
            e
            for e in selected
            if needle in e.path.lower() or needle in (e.operation_id or "").lower()
        ]

    rows = []
    for endpoint in selected:
        status = _guardrail_status(client, endpoint)
        if args.runnable and status != "ok":
            continue
        rows.append(
            (
                endpoint.method,
                endpoint.path,
                ",".join(str(c) for c in endpoint.documented_codes) or "-",
                _fmt_params(endpoint),
                "yes" if endpoint.request_schema else "",
                status,
            )
        )

    if not rows:
        print("No endpoints matched.")
        return 0

    _print_table(rows)

    shown = len(rows)
    print()
    print(f"{shown} shown / {len(endpoints)} in spec  ({spec_path})")
    if client is not None:
        allowed = sum(1 for r in rows if r[5] == "ok")
        print(f"guardrails would allow {allowed} of the {shown} shown")
    if client is not None and not args.runnable:
        print("GUARDRAIL: ok = callable | method = not in allowed_methods | "
              "blocked = blocked_path_patterns")
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    """Is the configured API up? Exit 0 yes, 3 no, 0 (with a note) if skipped.

    Session 05's executor calls the same check before a run. Having it as a
    command too means you can answer "is staging up?" without starting one.
    """
    config = load_config(args.config) if args.config else load_config()
    client = ApiClient(config)

    result = client.health_check()
    if result.skipped:
        print(f"SKIPPED  {result.reason}")
        print("Set health_check.path in your config to enable the pre-run check.")
        return 0

    print(f"{'HEALTHY' if result.ok else 'UNHEALTHY'}  {client.host}  {result.reason}")
    if not result.ok and result.response is not None and result.response.body:
        print(f"  body: {result.response.body[:200]}")
    return 0 if result.ok else 3


def cmd_run(args: argparse.Namespace) -> int:
    """Run test cases against the configured API and write a CSV.

    Exit codes: 0 clean, 1 bad input, 2 guardrail, 3 API unhealthy,
    4 the run finished and something FAILed. 4 is the one a CI job cares
    about -- a tool that exits 0 while tests fail is worse than no tool.
    """
    config = load_config(args.config) if args.config else load_config()
    client = ApiClient(config)

    try:
        cases = load_dir(args.testcases)
    except TestCaseError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.endpoint:
        wanted = args.endpoint.strip().lower()
        cases = [c for c in cases if wanted in c.endpoint_key.lower()]
    if args.limit is not None:
        cases = cases[: args.limit]

    if not cases:
        print("No test cases matched.")
        return 0

    # The spec is what tells a verdict which statuses the API documents. A
    # missing spec is not fatal: it only costs NEEDS_REVIEW, never a PASS.
    documented = {}
    spec_path = args.spec or config.get("spec_path")
    if spec_path:
        try:
            documented = codes_by_endpoint(parse_file(spec_path))
        except SpecError as exc:
            print(f"WARNING: no documented codes -- {exc}\n", file=sys.stderr)

    # Gate here rather than inside run_cases, so a dead host never gets as far
    # as announcing a run it is not going to do.
    if not args.no_health:
        health = client.health_check()
        if not health.ok:
            print(f"UNHEALTHY: {health.reason}", file=sys.stderr)
            print("No cases were run. Use --no-health to run anyway.", file=sys.stderr)
            return 3

    print(f"{len(cases)} cases against {client.host}\n")
    results = run_cases(
        client,
        cases,
        on_result=lambda r: print(format_result(r)),
        check_health=False,
    )

    apply_verdicts(results, documented)

    report = write_csv(results, args.out or DEFAULT_REPORT)
    print()
    for line in summary_lines(results.results):
        print(line)
    print(f"\nreport: {report}")

    return 4 if has_failures(results) else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py", description="Swagger-driven API test agent (staging only)."
    )
    parser.add_argument("--config", help=f"config file (default: config.yaml)")
    sub = parser.add_subparsers(dest="command", required=True)

    lister = sub.add_parser("list", help="print the endpoints in a spec")
    lister.add_argument("--spec", help=f"spec file (default: config spec_path)")
    lister.add_argument(
        "--method", action="append", help="filter by method, repeatable (e.g. --method GET)"
    )
    lister.add_argument("--grep", help="substring match on path or operationId")
    lister.add_argument(
        "--runnable", action="store_true", help="only endpoints the guardrails allow"
    )
    lister.set_defaults(func=cmd_list)

    health = sub.add_parser("health", help="check the API is up before running a suite")
    health.set_defaults(func=cmd_health)

    runner = sub.add_parser("run", help="run test cases and write a CSV report")
    runner.add_argument(
        "--testcases", default="testcases", help="test case directory (default: testcases)"
    )
    runner.add_argument(
        "--endpoint", help="only cases whose endpoint contains this, e.g. website-slots"
    )
    runner.add_argument("--limit", type=int, help="run at most this many cases")
    runner.add_argument("--spec", help="spec file, for documented status codes")
    runner.add_argument("--out", help=f"CSV path (default: {DEFAULT_REPORT})")
    runner.add_argument(
        "--no-health", action="store_true", help="run even if the health check fails"
    )
    # --all is the default and exists so the command reads the way PLAN
    # describes it; passing it changes nothing.
    runner.add_argument(
        "--all", action="store_true", help="run every case (the default)"
    )
    runner.set_defaults(func=cmd_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ConfigError as exc:
        print(f"ERROR: config: {exc}", file=sys.stderr)
        return 1
    except GuardrailError as exc:
        # NON-NEGOTIABLE RULE 1. Never downgrade this to a warning.
        print(f"GUARDRAIL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
