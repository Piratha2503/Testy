"""Guardrail tests for core.client.

The point of these is one line in PLAN.md: a production-looking host must not
be callable. Everything else here protects that line from being weakened by a
later session.
"""

from __future__ import annotations

import pytest
import requests

from core.client import (
    ApiClient,
    ConfigError,
    GuardrailError,
    load_config,
)


def base_config(**overrides):
    """A minimal config that passes every guardrail, before overrides."""
    config = {
        "base_url": "https://api.staging.example.com",
        "require_host_substring": "staging",
        "auth": {"type": "none"},
        "timeout": 5,
        "max_response_chars": 500,
        "allowed_methods": ["GET", "HEAD"],
        "blocked_host_substrings": ["stripe", "amadeus"],
        "blocked_path_patterns": ["/payment", "/admin"],
    }
    config.update(overrides)
    return config


# --------------------------------------------------------------------------
# rule 1 — staging only
# --------------------------------------------------------------------------


def test_staging_host_is_accepted():
    client = ApiClient(base_config())
    assert client.host == "api.staging.example.com"


def test_production_host_raises_guardrail_error():
    config = base_config(base_url="https://api.example.com")
    with pytest.raises(GuardrailError, match="staging"):
        ApiClient(config)


def test_missing_require_host_substring_raises():
    config = base_config()
    del config["require_host_substring"]
    with pytest.raises(GuardrailError, match="require_host_substring"):
        ApiClient(config)


def test_empty_require_host_substring_raises():
    with pytest.raises(GuardrailError, match="require_host_substring"):
        ApiClient(base_config(require_host_substring="   "))


def test_host_check_is_case_insensitive():
    config = base_config(base_url="https://API.STAGING.example.com")
    assert ApiClient(config).host == "api.staging.example.com"


def test_missing_base_url_raises_config_error():
    with pytest.raises(ConfigError, match="base_url"):
        ApiClient(base_config(base_url=""))


# --------------------------------------------------------------------------
# rule 2 — third-party APIs
# --------------------------------------------------------------------------


def test_blocked_third_party_host_raises():
    config = base_config(
        base_url="https://api.staging.stripe.com",
        require_host_substring="staging",
    )
    with pytest.raises(GuardrailError, match="stripe"):
        ApiClient(config)


# --------------------------------------------------------------------------
# method allowlist
# --------------------------------------------------------------------------


def test_disallowed_method_raises():
    client = ApiClient(base_config())
    with pytest.raises(GuardrailError, match="allowed_methods"):
        client.request("POST", "/pets")


def test_delete_is_blocked_even_when_config_allows_it():
    client = ApiClient(base_config(allowed_methods=["GET", "DELETE"]))
    with pytest.raises(GuardrailError, match="blocked outright"):
        client.request("DELETE", "/pets/1")


# --------------------------------------------------------------------------
# url building
# --------------------------------------------------------------------------


def test_path_params_are_substituted():
    client = ApiClient(base_config())
    url = client.build_url("/pets/{petId}", {"petId": 7})
    assert url == "https://api.staging.example.com/pets/7"


def test_unfilled_path_param_raises():
    client = ApiClient(base_config())
    with pytest.raises(GuardrailError, match="unfilled"):
        client.build_url("/pets/{petId}")


def test_absolute_url_is_refused():
    client = ApiClient(base_config())
    with pytest.raises(GuardrailError, match="Absolute URL"):
        client.build_url("https://evil.example.com/pets")


def test_blocked_path_pattern_raises():
    client = ApiClient(base_config())
    with pytest.raises(GuardrailError, match="blocked pattern"):
        client.build_url("/v1/Payments/refund")


# --------------------------------------------------------------------------
# auth headers
# --------------------------------------------------------------------------


def test_bearer_token_becomes_authorization_header():
    config = base_config(auth={"type": "bearer", "token": "t0ken"})
    assert ApiClient(config).session.headers["Authorization"] == "Bearer t0ken"


def test_custom_header_auth():
    config = base_config(auth={"type": "header", "header_name": "X-API-Key", "token": "abc"})
    assert ApiClient(config).session.headers["X-API-Key"] == "abc"


def test_auth_without_token_raises_config_error():
    config = base_config(auth={"type": "bearer", "token": None})
    with pytest.raises(ConfigError, match="no token"):
        ApiClient(config)


def test_unknown_auth_type_raises():
    config = base_config(auth={"type": "oauth2", "token": "x"})
    with pytest.raises(ConfigError, match="Unknown auth.type"):
        ApiClient(config)


# --------------------------------------------------------------------------
# request behaviour
# --------------------------------------------------------------------------


class _FakeElapsed:
    def total_seconds(self):
        return 0.123


class _FakeResponse:
    def __init__(self, text, status=200):
        self.text = text
        self.content = text.encode()
        self.status_code = status
        self.headers = {"Content-Type": "application/json"}
        self.elapsed = _FakeElapsed()


def test_long_response_body_is_truncated(monkeypatch):
    client = ApiClient(base_config(max_response_chars=50))
    monkeypatch.setattr(
        client.session, "request", lambda *a, **kw: _FakeResponse("x" * 500)
    )

    response = client.request("GET", "/pets")
    assert len(response.body) == 50
    assert response.truncated is True
    assert response.elapsed_ms == 123


def test_response_bytes_is_measured_before_truncation(monkeypatch):
    """The whole point: len(body) cannot tell 2 MB from 501 bytes."""
    client = ApiClient(base_config(max_response_chars=50))
    monkeypatch.setattr(
        client.session, "request", lambda *a, **kw: _FakeResponse("x" * 5000)
    )

    response = client.request("GET", "/pets")
    assert len(response.body) == 50
    assert response.response_bytes == 5000


def test_response_bytes_counts_bytes_not_characters(monkeypatch):
    """raw.text is decoded, so it under-counts anything multi-byte."""
    client = ApiClient(base_config())
    payload = '{"city":"சென்னை"}'
    monkeypatch.setattr(
        client.session, "request", lambda *a, **kw: _FakeResponse(payload)
    )

    response = client.request("GET", "/pets")
    assert response.response_bytes == len(payload.encode()) > len(payload)


def test_short_response_body_is_not_truncated(monkeypatch):
    client = ApiClient(base_config())
    monkeypatch.setattr(client.session, "request", lambda *a, **kw: _FakeResponse("{}"))

    response = client.request("GET", "/pets")
    assert response.body == "{}"
    assert response.truncated is False
    assert response.ok is True


def test_timeout_returns_response_instead_of_raising(monkeypatch):
    client = ApiClient(base_config())

    def blow_up(*args, **kwargs):
        raise requests.Timeout("too slow")

    monkeypatch.setattr(client.session, "request", blow_up)

    response = client.request("GET", "/pets")
    assert response.status is None
    assert response.ok is False
    assert "timeout" in response.error


def test_connection_error_returns_response(monkeypatch):
    client = ApiClient(base_config())

    def blow_up(*args, **kwargs):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(client.session, "request", blow_up)

    response = client.request("GET", "/pets")
    assert response.status is None
    assert "ConnectionError" in response.error


# --------------------------------------------------------------------------
# health check
# --------------------------------------------------------------------------


def health_client(monkeypatch, status=None, error=None, **config_overrides):
    client = ApiClient(base_config(**config_overrides))

    def fake_request(method, url, **kwargs):
        if error is not None:
            raise error
        return _FakeResponse("{}", status=status)

    monkeypatch.setattr(client.session, "request", fake_request)
    return client


def test_health_is_skipped_when_no_path_configured(monkeypatch):
    result = health_client(monkeypatch, status=200).health_check()
    assert result.skipped is True
    assert result.ok is True
    assert result.response is None


def test_health_ok_on_200(monkeypatch):
    client = health_client(monkeypatch, status=200, health_check={"path": "/ping"})
    result = client.health_check()
    assert result.ok is True
    assert result.skipped is False
    assert "/ping" in result.reason


@pytest.mark.parametrize("status", [200, 204, 301, 399])
def test_health_ok_below_400(monkeypatch, status):
    client = health_client(monkeypatch, status=status, health_check={"path": "/ping"})
    assert client.health_check().ok is True


@pytest.mark.parametrize("status", [400, 401, 404, 500, 503])
def test_health_not_ok_at_400_and_above(monkeypatch, status):
    """404 and 401 count as unhealthy: the path is one you know returns 200,
    so anything else means it is misconfigured or auth is broken."""
    client = health_client(monkeypatch, status=status, health_check={"path": "/ping"})
    result = client.health_check()
    assert result.ok is False
    assert str(status) in result.reason


def test_health_not_ok_when_nothing_responds(monkeypatch):
    client = health_client(
        monkeypatch, error=requests.Timeout("slow"), health_check={"path": "/ping"}
    )
    result = client.health_check()
    assert result.ok is False
    assert "no response" in result.reason
    assert result.response is not None


def test_health_sends_the_configured_query(monkeypatch):
    client = ApiClient(base_config(health_check={"path": "/ping", "query": {"size": 1}}))
    seen = {}

    def capture(method, url, **kwargs):
        seen.update(kwargs)
        return _FakeResponse("{}", status=200)

    monkeypatch.setattr(client.session, "request", capture)
    client.health_check()
    assert seen["params"] == {"size": 1}


def test_health_path_that_guardrails_refuse_still_raises(monkeypatch):
    """A refused health path is a config mistake, not a sick API."""
    client = health_client(
        monkeypatch, status=200, health_check={"path": "/payment/ping"}
    )
    with pytest.raises(GuardrailError, match="blocked pattern"):
        client.health_check()


def test_health_check_must_be_a_mapping(monkeypatch):
    client = health_client(monkeypatch, status=200, health_check="/ping")
    with pytest.raises(ConfigError, match="must be a mapping"):
        client.health_check()


def test_redirects_are_not_followed(monkeypatch):
    client = ApiClient(base_config())
    seen = {}

    def capture(method, url, **kwargs):
        seen.update(kwargs)
        return _FakeResponse("{}")

    monkeypatch.setattr(client.session, "request", capture)
    client.request("GET", "/pets")
    assert seen["allow_redirects"] is False


# --------------------------------------------------------------------------
# config loading
# --------------------------------------------------------------------------


def test_local_config_overrides_and_merges(tmp_path):
    (tmp_path / "config.yaml").write_text(
        "base_url: http://localhost:8080\n"
        "timeout: 10\n"
        "auth:\n  type: none\n  header_name: X-API-Key\n",
        encoding="utf-8",
    )
    (tmp_path / "config.local.yaml").write_text(
        "base_url: https://staging.internal\nauth:\n  type: bearer\n", encoding="utf-8"
    )

    config = load_config(tmp_path / "config.yaml", tmp_path / "config.local.yaml")
    assert config["base_url"] == "https://staging.internal"
    assert config["timeout"] == 10
    # nested mapping merged, not replaced wholesale
    assert config["auth"] == {"type": "bearer", "header_name": "X-API-Key"}


def test_overlay_is_derived_from_the_config_being_loaded(tmp_path):
    """An explicit config must not pick up the repo's own config.local.yaml.

    This bit for real: `main.py --config <tmp>` silently merged the checked-out
    config.local.yaml over the caller's file, so a deliberately safe config
    could be overridden by whatever host happened to be on the machine.
    """
    (tmp_path / "other.yaml").write_text("base_url: http://safe.local\n", encoding="utf-8")
    (tmp_path / "other.local.yaml").write_text("timeout: 99\n", encoding="utf-8")
    # The sibling of a *different* config file must be ignored.
    (tmp_path / "config.local.yaml").write_text(
        "base_url: http://should-not-win\n", encoding="utf-8"
    )

    config = load_config(tmp_path / "other.yaml")
    assert config["base_url"] == "http://safe.local"
    assert config["timeout"] == 99


def test_overlay_can_be_skipped(tmp_path):
    (tmp_path / "config.yaml").write_text("timeout: 1\n", encoding="utf-8")
    (tmp_path / "config.local.yaml").write_text("timeout: 2\n", encoding="utf-8")

    assert load_config(tmp_path / "config.yaml")["timeout"] == 2
    assert load_config(tmp_path / "config.yaml", None)["timeout"] == 1


def test_env_var_placeholder_is_expanded(tmp_path, monkeypatch):
    monkeypatch.setenv("API_TEST_TOKEN", "secret-from-env")
    (tmp_path / "config.yaml").write_text(
        "auth:\n  token: ${API_TEST_TOKEN}\n", encoding="utf-8"
    )

    config = load_config(tmp_path / "config.yaml", None)
    assert config["auth"]["token"] == "secret-from-env"


def test_unset_env_var_becomes_none_not_literal(tmp_path, monkeypatch):
    monkeypatch.delenv("API_TEST_TOKEN", raising=False)
    (tmp_path / "config.yaml").write_text(
        "auth:\n  token: ${API_TEST_TOKEN}\n", encoding="utf-8"
    )

    config = load_config(tmp_path / "config.yaml", None)
    assert config["auth"]["token"] is None


def test_missing_config_file_raises():
    with pytest.raises(ConfigError, match="not found"):
        load_config("no_such_config.yaml", None)


def test_shipped_config_yaml_passes_its_own_guardrails():
    """The config committed to git must not itself be a production config."""
    config = load_config("config.yaml", None)
    client = ApiClient(config)
    assert config["require_host_substring"] in client.host
