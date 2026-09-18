"""HTTP client + guardrails.

Session 02 scope: load ``config.yaml`` (overlaid with a gitignored
``config.local.yaml``), refuse to talk to anything that is not the configured
staging host, and make one request at a time with a truncated response.

The guardrails here are not advisory. Every refusal raises ``GuardrailError``
*before* a socket is opened. Nothing in this module retries, and nothing in
this module writes files.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests
import yaml

DEFAULT_CONFIG_PATH = "config.yaml"

# load_config(local_path=...) default: derive the overlay from the config file
# being loaded, rather than always reaching for the repo's config.local.yaml.
# Passing an explicit --config must not pick up an unrelated local file.
DERIVE_LOCAL = object()

# Substituted from os.environ, e.g. "${API_TEST_TOKEN}".
_ENV_PATTERN = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")

# Whatever the config says, these can never be called. Session 10 may widen
# allowed_methods to POST; it must not widen it to DELETE by accident.
HARD_BLOCKED_METHODS = frozenset({"DELETE"})


class ConfigError(Exception):
    """config.yaml is missing, unreadable, or has a nonsense value."""


class GuardrailError(Exception):
    """A request was refused before it left the process."""


# --------------------------------------------------------------------------
# config
# --------------------------------------------------------------------------


def _expand_env(node: Any) -> Any:
    """Replace exact ``${VAR}`` strings with their environment value.

    An unset variable becomes ``None`` rather than the literal ``${VAR}``, so
    a missing token fails the auth check instead of being sent as a header.
    """
    if isinstance(node, str):
        match = _ENV_PATTERN.match(node.strip())
        if match:
            return os.environ.get(match.group(1))
        return node
    if isinstance(node, dict):
        return {k: _expand_env(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_expand_env(item) for item in node]
    return node


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Overlay wins, but nested mappings merge key by key."""
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"Could not read {path}: {exc}") from exc
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: top level is {type(raw).__name__}, expected a mapping")
    return raw


def local_config_path(path: str | Path) -> Path:
    """The overlay that belongs to ``path``: config.yaml -> config.local.yaml."""
    path = Path(path)
    return path.with_name(f"{path.stem}.local{path.suffix}")


def load_config(
    path: str | Path = DEFAULT_CONFIG_PATH,
    local_path: str | Path | None | Any = DERIVE_LOCAL,
) -> dict[str, Any]:
    """Load a config file, merge its ``.local`` overlay over it, expand ``${VAR}``.

    The overlay is the sibling of ``path``, so ``--config other.yaml`` picks up
    ``other.local.yaml`` and nothing else. Pass ``local_path=None`` to skip the
    overlay entirely, or an explicit path to point somewhere else.
    """
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"Config file not found: {path}")

    if local_path is DERIVE_LOCAL:
        local_path = local_config_path(path)

    config = _read_yaml(path)
    if local_path is not None:
        local = Path(local_path)
        if local.is_file():
            config = _deep_merge(config, _read_yaml(local))
    return _expand_env(config)


# --------------------------------------------------------------------------
# response
# --------------------------------------------------------------------------


@dataclass
class Response:
    """What one call produced. A transport failure is a Response, not a raise.

    ``status`` is None when nothing came back (timeout, DNS failure, refused
    connection); ``error`` then says why. Guardrail refusals never reach here.
    """

    method: str
    url: str
    status: int | None
    elapsed_ms: int
    body: str = ""
    truncated: bool = False
    error: str | None = None
    headers: dict[str, str] = field(default_factory=dict)

    # Size of what the server actually sent, measured before truncation.
    # len(body) answers a different question once max_response_chars bites:
    # a 2 MB payload and a 501-byte one both leave 500 characters behind.
    response_bytes: int = 0

    @property
    def ok(self) -> bool:
        return self.status is not None and 200 <= self.status < 300


@dataclass
class HealthResult:
    """Is the API worth running a suite against at all?

    Answered before the run, not after: 60 cases against a dead host produce
    60 failures that say nothing about the API, and cost ten minutes to read.
    """

    ok: bool
    reason: str
    skipped: bool = False
    response: Response | None = None


# --------------------------------------------------------------------------
# client
# --------------------------------------------------------------------------


class ApiClient:
    """Calls exactly one configured host, and only in ways config allows.

    The staging check runs in ``__init__``, so constructing a client against a
    production base_url fails immediately — before any caller gets the chance
    to make a request.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = load_config() if config is None else config

        self.base_url = str(self.config.get("base_url") or "").strip().rstrip("/")
        if not self.base_url:
            raise ConfigError("base_url is missing from config")

        self.timeout = float(self.config.get("timeout", 10))
        self.verify_tls = bool(self.config.get("verify_tls", True))
        self.max_response_chars = int(self.config.get("max_response_chars", 500))

        self.allowed_methods = {
            str(m).upper() for m in (self.config.get("allowed_methods") or [])
        }
        self.blocked_host_substrings = [
            str(s).lower() for s in (self.config.get("blocked_host_substrings") or [])
        ]
        self.blocked_path_patterns = [
            re.compile(str(p), re.IGNORECASE)
            for p in (self.config.get("blocked_path_patterns") or [])
        ]

        self.host = self._check_base_url()

        self.session = requests.Session()
        self.session.headers.update(self._build_headers())

    # -- guardrails --------------------------------------------------------

    def _check_base_url(self) -> str:
        """NON-NEGOTIABLE RULE 1 + 2, enforced at construction time."""
        required = self.config.get("require_host_substring")
        if not isinstance(required, str) or not required.strip():
            raise GuardrailError(
                "require_host_substring is missing or empty in config. "
                "Refusing to run - this is the only thing stopping a production run."
            )
        required = required.strip().lower()

        host = urlsplit(self.base_url).hostname
        if not host:
            raise ConfigError(f"base_url has no host: {self.base_url!r}")
        host = host.lower()

        if required not in host:
            raise GuardrailError(
                f"Host {host!r} does not contain required substring {required!r}. "
                "Staging only - refusing to run."
            )
        self._check_blocked_host(host)
        return host

    def _check_blocked_host(self, host: str) -> None:
        """NON-NEGOTIABLE RULE 2 — third-party APIs are off limits."""
        for blocked in self.blocked_host_substrings:
            if blocked in host:
                raise GuardrailError(
                    f"Host {host!r} matches blocked substring {blocked!r} - "
                    "third-party APIs must not be touched."
                )

    def _check_method(self, method: str) -> None:
        if method in HARD_BLOCKED_METHODS:
            raise GuardrailError(f"{method} is blocked outright, config cannot enable it.")
        if method not in self.allowed_methods:
            allowed = ", ".join(sorted(self.allowed_methods)) or "(none)"
            raise GuardrailError(f"Method {method} not in allowed_methods: {allowed}")

    def _check_path(self, path: str) -> None:
        for pattern in self.blocked_path_patterns:
            if pattern.search(path):
                raise GuardrailError(
                    f"Path {path!r} matches blocked pattern {pattern.pattern!r}"
                )

    def build_url(self, path: str, path_params: dict[str, Any] | None = None) -> str:
        """Fill ``{id}`` placeholders and join onto base_url, checking as we go.

        An absolute URL is rejected rather than followed — a test case must not
        be able to point the run at a different host.
        """
        if "://" in path:
            raise GuardrailError(
                f"Absolute URL {path!r} not allowed; paths must be relative to base_url."
            )

        for name, value in (path_params or {}).items():
            path = path.replace("{" + str(name) + "}", str(value))

        leftover = re.findall(r"\{([^}]+)\}", path)
        if leftover:
            raise GuardrailError(f"Path {path!r} still has unfilled params: {leftover}")

        self._check_path(path)
        return f"{self.base_url}/{path.lstrip('/')}"

    # -- auth --------------------------------------------------------------

    def _build_headers(self) -> dict[str, str]:
        headers = {
            str(k): str(v) for k, v in (self.config.get("default_headers") or {}).items()
        }

        auth = self.config.get("auth") or {}
        auth_type = str(auth.get("type") or "none").lower()
        if auth_type == "none":
            return headers

        token = auth.get("token")
        if not token:
            raise ConfigError(
                f"auth.type is {auth_type!r} but no token is set "
                "(check config.local.yaml or the environment variable)."
            )

        if auth_type == "bearer":
            headers["Authorization"] = f"Bearer {token}"
        elif auth_type == "header":
            name = auth.get("header_name")
            if not name:
                raise ConfigError("auth.type is 'header' but auth.header_name is not set")
            headers[str(name)] = str(token)
        else:
            raise ConfigError(f"Unknown auth.type {auth_type!r} - use none, bearer, or header")
        return headers

    # -- request -----------------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        *,
        path_params: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
        body: Any = None,
        headers: dict[str, str] | None = None,
    ) -> Response:
        """Make one call. Guardrail failures raise; transport failures don't."""
        method = str(method).upper()
        self._check_method(method)
        url = self.build_url(path, path_params)

        # Redirects are not followed: a 302 could land on a host that never
        # passed the staging check.
        kwargs: dict[str, Any] = {
            "params": query or None,
            "headers": headers or None,
            "timeout": self.timeout,
            "verify": self.verify_tls,
            "allow_redirects": False,
        }
        if body is not None:
            kwargs["json"] = body

        try:
            raw = self.session.request(method, url, **kwargs)
        except requests.Timeout:
            return Response(
                method=method,
                url=url,
                status=None,
                elapsed_ms=int(self.timeout * 1000),
                error=f"timeout after {self.timeout}s",
            )
        except requests.RequestException as exc:
            return Response(
                method=method,
                url=url,
                status=None,
                elapsed_ms=0,
                error=f"{type(exc).__name__}: {exc}",
            )

        text = raw.text or ""
        truncated = len(text) > self.max_response_chars
        return Response(
            method=method,
            url=url,
            status=raw.status_code,
            elapsed_ms=int(raw.elapsed.total_seconds() * 1000),
            body=text[: self.max_response_chars],
            truncated=truncated,
            headers=dict(raw.headers),
            # raw.content is the bytes off the wire; raw.text is decoded, so
            # it under-counts anything multi-byte.
            response_bytes=len(raw.content or b""),
        )

    # -- health -----------------------------------------------------------

    def health_check(self) -> HealthResult:
        """Call one cheap endpoint to decide whether a run should start.

        Healthy means a response came back with a status below 400. A 404 or
        401 here is treated as unhealthy on purpose: the configured path is
        one you know returns 200, so anything else means the path is wrong,
        auth is broken, or the service is not the one you think it is -- all
        reasons to stop before running a suite.

        Guardrail failures are not caught. A health path the guardrails refuse
        is a config mistake, and it must be as loud as any other.
        """
        settings = self.config.get("health_check") or {}
        if not isinstance(settings, dict):
            raise ConfigError("health_check must be a mapping with a 'path' key")

        path = settings.get("path")
        if not path:
            return HealthResult(
                ok=True, skipped=True, reason="no health_check.path configured"
            )

        query = settings.get("query") or None
        response = self.request("GET", str(path), query=query)

        if response.status is None:
            return HealthResult(
                ok=False, reason=f"no response from {self.host}: {response.error}",
                response=response,
            )
        if response.status >= 400:
            return HealthResult(
                ok=False,
                reason=f"{path} returned {response.status}, expected below 400",
                response=response,
            )
        return HealthResult(
            ok=True,
            reason=f"{path} returned {response.status} in {response.elapsed_ms}ms",
            response=response,
        )

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> "ApiClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
