"""OpenAPI 3 spec parser.

Session 01 scope: load a spec file (YAML or JSON), resolve local ``$ref``
pointers with a circular-reference guard, and return a list of ``Endpoint``
objects. No HTTP calls, no LLM, no config here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Methods we bother reading out of a path item. Whether we are *allowed* to
# call them is a client concern (session 02), not a parser concern.
HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")

# Refs nested deeper than this are almost certainly a spec bug, not a real
# schema. Stop instead of blowing the recursion limit.
MAX_REF_DEPTH = 40

CIRCULAR_KEY = "$circular_ref"
TRUNCATED_KEY = "$truncated_ref"


class SpecError(Exception):
    """Spec file is missing, unreadable, or not an OpenAPI 3 document."""


@dataclass
class Endpoint:
    """One callable operation: a path + method pair."""

    path: str
    method: str  # upper-case: GET, POST, ...
    operation_id: str | None = None
    summary: str = ""
    path_params: list[dict[str, Any]] = field(default_factory=list)
    query_params: list[dict[str, Any]] = field(default_factory=list)
    request_schema: dict[str, Any] | None = None
    documented_codes: list[int] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.method} {self.path}"

    def __str__(self) -> str:  # pragma: no cover - display only
        return self.key


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------


def load_spec(path: str | Path) -> dict[str, Any]:
    """Read a .json/.yaml/.yml spec file into a dict."""
    path = Path(path)
    if not path.is_file():
        raise SpecError(f"Spec file not found: {path}")

    raw = path.read_text(encoding="utf-8")
    try:
        if path.suffix.lower() == ".json":
            spec = json.loads(raw)
        else:
            # safe_load also parses JSON, so it is the safer default.
            spec = yaml.safe_load(raw)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise SpecError(f"Could not parse {path}: {exc}") from exc

    if not isinstance(spec, dict):
        raise SpecError(f"{path}: top level is {type(spec).__name__}, expected a mapping")
    if "openapi" not in spec and "swagger" in spec:
        raise SpecError(
            f"{path}: Swagger 2.0 spec detected. Only OpenAPI 3 is supported in the MVP."
        )
    if "paths" not in spec:
        raise SpecError(f"{path}: no 'paths' section — not an OpenAPI document?")
    return spec


# --------------------------------------------------------------------------
# $ref resolution
# --------------------------------------------------------------------------


def _lookup(ref: str, root: dict[str, Any]) -> Any:
    """Follow a local JSON pointer like '#/components/schemas/Pet'."""
    if not ref.startswith("#/"):
        raise SpecError(f"External $ref not supported: {ref!r}")

    node: Any = root
    for token in ref[2:].split("/"):
        # JSON pointer escapes, per RFC 6901.
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(node, list):
            try:
                node = node[int(token)]
            except (ValueError, IndexError) as exc:
                raise SpecError(f"Bad $ref {ref!r}: no index {token!r}") from exc
        elif isinstance(node, dict) and token in node:
            node = node[token]
        else:
            raise SpecError(f"Bad $ref {ref!r}: {token!r} not found")
    return node


def resolve_refs(
    node: Any,
    root: dict[str, Any],
    _seen: frozenset[str] = frozenset(),
    _depth: int = 0,
) -> Any:
    """Deep-copy ``node`` with every local ``$ref`` inlined.

    A ref already on the current resolution path is replaced with a marker
    instead of being followed, so self-referencing schemas (Category -> Pet ->
    Category) terminate rather than recursing forever.
    """
    if _depth > MAX_REF_DEPTH:
        return {TRUNCATED_KEY: True}

    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            if ref in _seen:
                return {CIRCULAR_KEY: ref}
            resolved = resolve_refs(_lookup(ref, root), root, _seen | {ref}, _depth + 1)
            # Sibling keys next to a $ref are legal in OpenAPI 3.1 and are
            # sometimes written (wrongly) in 3.0 specs too. Let them win.
            siblings = {k: v for k, v in node.items() if k != "$ref"}
            if siblings and isinstance(resolved, dict):
                resolved = {**resolved, **resolve_refs(siblings, root, _seen, _depth + 1)}
            return resolved
        return {k: resolve_refs(v, root, _seen, _depth + 1) for k, v in node.items()}

    if isinstance(node, list):
        return [resolve_refs(item, root, _seen, _depth + 1) for item in node]

    return node


# --------------------------------------------------------------------------
# parsing
# --------------------------------------------------------------------------


def _merge_params(
    path_level: list[Any], op_level: list[Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Combine path-item and operation parameters, then split by location.

    Operation-level parameters override path-level ones with the same
    (name, in) pair, per the OpenAPI spec.
    """
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for param in list(path_level) + list(op_level):
        if not isinstance(param, dict) or "name" not in param:
            continue
        merged[(param["name"], param.get("in", ""))] = param

    path_params = [p for (_, loc), p in merged.items() if loc == "path"]
    query_params = [p for (_, loc), p in merged.items() if loc == "query"]
    return path_params, query_params


def _request_schema(operation: dict[str, Any]) -> dict[str, Any] | None:
    """Pull the application/json request body schema, if there is one."""
    content = operation.get("requestBody", {})
    if not isinstance(content, dict):
        return None
    content = content.get("content", {})
    if not isinstance(content, dict):
        return None
    for media_type, media in content.items():
        if "json" in media_type.lower() and isinstance(media, dict):
            schema = media.get("schema")
            if isinstance(schema, dict):
                return schema
    return None


def _documented_codes(operation: dict[str, Any]) -> list[int]:
    """Numeric response codes the spec claims this operation returns.

    'default' and wildcard codes like '4XX' are dropped — we can only compare
    a concrete number against a real response.
    """
    responses = operation.get("responses", {})
    if not isinstance(responses, dict):
        return []
    codes = []
    for code in responses:
        try:
            codes.append(int(code))
        except (TypeError, ValueError):
            continue
    return sorted(codes)


def parse_spec(spec: dict[str, Any]) -> list[Endpoint]:
    """Turn a loaded spec dict into a flat list of Endpoint objects."""
    resolved = resolve_refs(spec, spec)
    paths = resolved.get("paths") or {}
    if not isinstance(paths, dict):
        raise SpecError("'paths' is not a mapping")

    endpoints: list[Endpoint] = []
    for path, item in paths.items():
        if not isinstance(item, dict):
            continue
        shared_params = item.get("parameters") or []

        for method in HTTP_METHODS:
            operation = item.get(method)
            if not isinstance(operation, dict):
                continue

            path_params, query_params = _merge_params(
                shared_params, operation.get("parameters") or []
            )
            endpoints.append(
                Endpoint(
                    path=path,
                    method=method.upper(),
                    operation_id=operation.get("operationId"),
                    summary=(operation.get("summary") or operation.get("description") or "").strip(),
                    path_params=path_params,
                    query_params=query_params,
                    request_schema=_request_schema(operation),
                    documented_codes=_documented_codes(operation),
                )
            )

    endpoints.sort(key=lambda e: (e.path, e.method))
    return endpoints


def parse_file(path: str | Path) -> list[Endpoint]:
    """Convenience: load a spec file and parse it in one call."""
    return parse_spec(load_spec(path))
