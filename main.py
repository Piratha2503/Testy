"""CLI entry point.

Two commands so far.

``list`` parses a spec and prints the endpoints it found, saying per endpoint
whether the guardrails in core.client would let it be called at all -- that is
the column that matters when picking targets for a real run.

``health`` calls one cheap endpoint and exits non-zero if the API is not up,
so a suite is never run against a dead host.

    python main.py list
    python main.py list --method GET --runnable
    python main.py list --grep booking
    python main.py health

``run`` and ``generate`` arrive in sessions 07 and 13.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from core.client import ApiClient, ConfigError, GuardrailError, load_config
from core.swagger import Endpoint, SpecError, parse_file

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
