"""CLI tests for main.py list.

These run against tests/fixtures/mini_spec.yaml, not the real spec -- the real
one is gitignored and would make the suite depend on a machine-local file.
"""

from __future__ import annotations

import json
import pathlib

import pytest
import yaml

import main
from core.client import HealthResult, Response

FIXTURE_SPEC = "tests/fixtures/mini_spec.yaml"


@pytest.fixture
def config_file(tmp_path):
    """A committed-safe config pointing at the fixture spec."""
    config = {
        "base_url": "https://api.staging.example.com",
        "require_host_substring": "staging",
        "spec_path": FIXTURE_SPEC,
        "auth": {"type": "none"},
        "allowed_methods": ["GET"],
        "blocked_path_patterns": ["/pets/"],
    }
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return str(path)


def run_cli(argv, config_file):
    return main.main(["--config", config_file] + argv)


def test_list_prints_every_endpoint(config_file, capsys):
    assert run_cli(["list"], config_file) == 0
    out = capsys.readouterr().out

    assert "METHOD" in out and "PATH" in out and "CODES" in out
    assert "/pets" in out
    assert "3 shown / 3 in spec" in out


def test_list_shows_documented_codes(config_file, capsys):
    run_cli(["list"], config_file)
    out = capsys.readouterr().out
    # mini_spec documents 200 and 404 on GET /pets/{petId}
    assert "200,404" in out


def test_spec_flag_overrides_config(config_file, capsys):
    assert run_cli(["list", "--spec", FIXTURE_SPEC], config_file) == 0
    assert FIXTURE_SPEC in capsys.readouterr().out


def test_method_filter(config_file, capsys):
    run_cli(["list", "--method", "GET"], config_file)
    out = capsys.readouterr().out
    assert "POST" not in out.split("GUARDRAIL")[1]


def test_grep_filter(config_file, capsys):
    run_cli(["list", "--grep", "petId"], config_file)
    out = capsys.readouterr().out
    assert "1 shown / 3 in spec" in out


def test_grep_with_no_match_is_not_an_error(config_file, capsys):
    assert run_cli(["list", "--grep", "zzzz"], config_file) == 0
    assert "No endpoints matched." in capsys.readouterr().out


def test_guardrail_column_flags_blocked_path(config_file, capsys):
    run_cli(["list", "--grep", "petId"], config_file)
    out = capsys.readouterr().out
    assert "blocked" in out


def test_guardrail_column_flags_disallowed_method(config_file, capsys):
    run_cli(["list", "--method", "POST"], config_file)
    out = capsys.readouterr().out
    assert "method" in out.lower()


def test_runnable_filter_drops_everything_not_ok(config_file, capsys):
    run_cli(["list", "--runnable"], config_file)
    out = capsys.readouterr().out
    assert "blocked" not in out
    assert "1 shown / 3 in spec" in out


def test_missing_spec_file_exits_1(config_file, capsys):
    assert run_cli(["list", "--spec", "no_such_spec.yaml"], config_file) == 1
    assert "ERROR" in capsys.readouterr().err


def health_config(tmp_path, **overrides):
    config = {
        "base_url": "https://api.staging.example.com",
        "require_host_substring": "staging",
        "spec_path": FIXTURE_SPEC,
        "allowed_methods": ["GET"],
    }
    config.update(overrides)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return str(path)


def test_health_exits_0_when_up(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(
        main.ApiClient,
        "health_check",
        lambda self: HealthResult(ok=True, reason="/ping returned 200 in 12ms"),
    )
    config = health_config(tmp_path, health_check={"path": "/ping"})

    assert main.main(["--config", config, "health"]) == 0
    assert "HEALTHY" in capsys.readouterr().out


def test_health_exits_3_when_down(tmp_path, capsys, monkeypatch):
    """A non-zero exit is what stops a CI job from running the suite anyway."""
    monkeypatch.setattr(
        main.ApiClient,
        "health_check",
        lambda self: HealthResult(ok=False, reason="/ping returned 503"),
    )
    config = health_config(tmp_path, health_check={"path": "/ping"})

    assert main.main(["--config", config, "health"]) == 3
    assert "UNHEALTHY" in capsys.readouterr().out


def test_health_exits_0_and_says_so_when_not_configured(tmp_path, capsys):
    assert main.main(["--config", health_config(tmp_path), "health"]) == 0
    out = capsys.readouterr().out
    assert "SKIPPED" in out
    assert "health_check.path" in out


def test_health_on_production_config_exits_2(tmp_path, capsys):
    """RULE 1 outranks the health check: never call a production host at all."""
    config = health_config(
        tmp_path,
        base_url="https://api.example.com",
        health_check={"path": "/ping"},
    )
    assert main.main(["--config", config, "health"]) == 2
    assert "GUARDRAIL" in capsys.readouterr().err


# --------------------------------------------------------------------------
# run
# --------------------------------------------------------------------------


@pytest.fixture
def run_setup(tmp_path):
    """A config, a testcases dir with two endpoints, and a fake transport."""
    cases_dir = tmp_path / "testcases"
    cases_dir.mkdir()
    for name, path, expected in (
        ("things", "/api/v1/things", 200),
        ("widgets", "/api/v1/widgets", 400),
    ):
        document = {
            "endpoint": {"method": "GET", "path": path},
            "cases": [
                {
                    "name": f"{name} case {i}",
                    "category": "happy_path" if expected == 200 else "invalid_input",
                    "expected_status": expected,
                    "reason": "the documented behaviour for this input",
                }
                for i in range(2)
            ],
        }
        (cases_dir / f"{name}.json").write_text(json.dumps(document), encoding="utf-8")

    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "base_url": "https://api.staging.example.com",
                "require_host_substring": "staging",
                "allowed_methods": ["GET"],
            }
        ),
        encoding="utf-8",
    )
    return str(config), str(cases_dir), tmp_path


@pytest.fixture
def always_200(monkeypatch):
    """A healthy API that answers 200 to everything, so the tests are about
    the CLI's wiring and exit codes rather than about HTTP."""
    monkeypatch.setattr(
        main.ApiClient,
        "health_check",
        lambda self: HealthResult(ok=True, reason="/ping returned 200"),
    )
    monkeypatch.setattr(
        main.ApiClient,
        "request",
        lambda self, method, path, **kwargs: Response(
            method=method, url=path, status=200, elapsed_ms=10,
            body="{}", response_bytes=2,
        ),
    )


def run_cmd(config, extra):
    return main.main(["--config", config, "run"] + extra)


def test_run_writes_a_csv_and_reports_a_summary(run_setup, always_200, capsys):
    config, cases_dir, tmp_path = run_setup
    out = tmp_path / "report.csv"

    code = run_cmd(config, ["--testcases", cases_dir, "--out", str(out)])
    captured = capsys.readouterr().out

    assert out.is_file()
    assert "4 cases" in captured
    assert str(out) in captured
    # two cases expect 200 and get it; two expect 400 and do not
    assert "PASS=2" in captured
    assert code == 4


def test_run_exits_4_when_something_failed(run_setup, always_200):
    config, cases_dir, _ = run_setup
    assert run_cmd(config, ["--testcases", cases_dir]) == 4


def test_run_exits_0_when_nothing_failed(run_setup, always_200, tmp_path):
    config, cases_dir, _ = run_setup
    assert run_cmd(config, ["--testcases", cases_dir, "--endpoint", "things"]) == 0


def test_endpoint_filter_selects_one_endpoint(run_setup, always_200, capsys):
    config, cases_dir, _ = run_setup
    run_cmd(config, ["--testcases", cases_dir, "--endpoint", "widgets"])
    out = capsys.readouterr().out

    assert "2 cases" in out
    assert "things case" not in out


def test_limit_caps_the_number_of_cases(run_setup, always_200, capsys):
    config, cases_dir, _ = run_setup
    run_cmd(config, ["--testcases", cases_dir, "--limit", "1"])
    assert "1 cases" in capsys.readouterr().out


def test_no_matching_cases_is_not_an_error(run_setup, always_200, capsys):
    config, cases_dir, _ = run_setup
    assert run_cmd(config, ["--testcases", cases_dir, "--endpoint", "zzz"]) == 0
    assert "No test cases matched." in capsys.readouterr().out


def test_unhealthy_api_exits_3_without_running(run_setup, monkeypatch, capsys):
    config, cases_dir, _ = run_setup
    monkeypatch.setattr(
        main.ApiClient,
        "health_check",
        lambda self: HealthResult(ok=False, reason="/ping returned 503"),
    )

    assert run_cmd(config, ["--testcases", cases_dir]) == 3
    err = capsys.readouterr().err
    assert "UNHEALTHY" in err
    assert "--no-health" in err


def test_no_health_flag_runs_anyway(run_setup, always_200, monkeypatch):
    config, cases_dir, _ = run_setup
    monkeypatch.setattr(
        main.ApiClient,
        "health_check",
        lambda self: HealthResult(ok=False, reason="down"),
    )
    assert run_cmd(config, ["--testcases", cases_dir, "--no-health"]) == 4


def test_malformed_testcase_file_exits_1(run_setup, always_200, capsys):
    config, cases_dir, _ = run_setup
    (pathlib.Path(cases_dir) / "broken.json").write_text("{not json", encoding="utf-8")

    assert run_cmd(config, ["--testcases", cases_dir]) == 1
    assert "ERROR" in capsys.readouterr().err


def test_run_on_production_config_exits_2(run_setup, always_200, tmp_path, capsys):
    """RULE 1 again: no request is made at all."""
    _, cases_dir, _ = run_setup
    config = tmp_path / "prod.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "base_url": "https://api.example.com",
                "require_host_substring": "staging",
                "allowed_methods": ["GET"],
            }
        ),
        encoding="utf-8",
    )

    assert run_cmd(str(config), ["--testcases", cases_dir]) == 2
    assert "GUARDRAIL" in capsys.readouterr().err


def test_missing_spec_only_warns(run_setup, always_200, capsys):
    """Documented codes are optional: their absence can only cost a review."""
    config, cases_dir, _ = run_setup
    code = run_cmd(config, ["--testcases", cases_dir, "--spec", "no_such_spec.yaml"])

    assert code == 4
    assert "WARNING" in capsys.readouterr().err


def test_production_config_exits_2_and_prints_guardrail(tmp_path, capsys):
    """RULE 1 reaches the CLI, not just the client."""
    config = tmp_path / "prod.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "base_url": "https://api.example.com",
                "require_host_substring": "staging",
                "spec_path": FIXTURE_SPEC,
                "allowed_methods": ["GET"],
            }
        ),
        encoding="utf-8",
    )

    # list still works -- reading a spec is not calling an API -- but it warns
    # loudly, and no endpoint is reported callable.
    assert main.main(["--config", str(config), "list"]) == 0
    captured = capsys.readouterr()
    assert "WARNING" in captured.err
    assert "staging" in captured.err
    assert "?" in captured.out
