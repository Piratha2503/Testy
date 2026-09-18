"""Real path parameter values, kept out of git.

A test case that hard-codes ``/website-slots/3`` is wrong the moment someone
reseeds staging, and it puts a fact about a private environment into a
committed file. So committed cases write a placeholder instead::

    "path_params": {"id": "{{seed}}"}

and the value comes from ``seed_data.yaml``, which is gitignored.

A case that deliberately wants a specific value still writes it literally --
``{"id": 99999999}`` for a not-found case is the point of that case, not a
gap in the seed file.

When no seed value exists, the case is skipped rather than sent. Running
``/reviews/{id}`` against an empty table produces a 404 that says nothing
about the API, and a report full of those teaches people to ignore it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

DEFAULT_SEED_PATH = "seed_data.yaml"

# Anything else in path_params is used as written.
PLACEHOLDER = "{{seed}}"


class SeedError(Exception):
    """No seed value for a parameter the case asked to have filled in."""


def load_seed(path: str | Path = DEFAULT_SEED_PATH) -> dict[str, Any]:
    """Read seed_data.yaml. A missing file is not an error.

    Most endpoints take no path parameters, so a run without a seed file is
    perfectly normal -- it just cannot fill placeholders.
    """
    path = Path(path)
    if not path.is_file():
        return {}

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise SeedError(f"Could not read {path}: {exc}") from exc

    if data is None:
        return {}
    if not isinstance(data, dict):
        raise SeedError(f"{path}: top level is {type(data).__name__}, expected a mapping")

    for section in ("endpoints", "defaults"):
        if section in data and not isinstance(data[section], dict):
            raise SeedError(f"{path}: '{section}' must be a mapping")
    return data


def lookup(seed: dict[str, Any], endpoint_key: str, param: str) -> Any:
    """The seed value for one parameter: endpoint-specific first, then a
    default shared by every endpoint using that parameter name."""
    endpoints = seed.get("endpoints") or {}
    specific = endpoints.get(endpoint_key)
    if isinstance(specific, dict) and param in specific:
        return specific[param]

    defaults = seed.get("defaults") or {}
    if param in defaults:
        return defaults[param]

    raise SeedError(
        f"no seed value for {param!r} on {endpoint_key}. "
        f"Add it under endpoints['{endpoint_key}'] or defaults in seed_data.yaml."
    )


def resolve_path_params(case, seed: dict[str, Any]) -> dict[str, Any]:
    """Return the case's path params with every placeholder filled in."""
    resolved = {}
    for name, value in case.path_params.items():
        if value == PLACEHOLDER:
            resolved[name] = lookup(seed, case.endpoint_key, name)
        else:
            resolved[name] = value
    return resolved
