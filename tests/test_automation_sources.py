"""Automation source manifest and monitor tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from polyflow.automation_sources import check_source, check_sources, default_reference_sources
from polyflow.config import Policy, ReferenceRepoConfig
from polyflow.logger import ImmutableLogger
from polyflow.persistence import SQLiteStore
from polyflow.subagents.reference_repo_monitor import ReferenceRepoMonitor


def test_default_reference_sources_are_pinned() -> None:
    sources = default_reference_sources()

    assert [source.name for source in sources] == [
        "poly_data",
        "polymarket-cli",
        "polymarket-agents",
        "polymarket-trade-engine",
    ]
    assert all(source.repo_url.startswith("https://github.com/") for source in sources)
    assert all(source.pinned_commit and len(source.pinned_commit) == 40 for source in sources)


def test_missing_source_reports_actionable_reason(tmp_path: Path) -> None:
    source = ReferenceRepoConfig(
        name="poly_data",
        repo_url="https://github.com/warproxxx/poly_data",
        purpose="Historical backtest data",
        integration_mode="historical_backtest_data",
        pinned_commit="a" * 40,
        expected_path="external/poly_data",
        required_files=["processed/trades.csv"],
    )

    status = check_source(source, root=tmp_path)

    assert status.status == "not_ready"
    assert status.local_path == str(tmp_path / "external/poly_data")
    assert "LOCAL_SOURCE_NOT_FOUND" in status.reason_codes


def test_materialized_source_can_be_ready_without_git_pin_requirement(tmp_path: Path) -> None:
    source_dir = tmp_path / "external/poly_data"
    source_dir.mkdir(parents=True)
    (source_dir / "update_all.py").write_text("# fixture\n", encoding="utf-8")

    source = ReferenceRepoConfig(
        name="poly_data",
        repo_url="https://github.com/warproxxx/poly_data",
        purpose="Historical backtest data",
        integration_mode="historical_backtest_data",
        expected_path="external/poly_data",
        required_files=["update_all.py"],
    )

    status = check_source(source, root=tmp_path, require_pinned_commit=False)

    assert status.ok is True
    assert status.reason_codes == ()


def test_missing_optional_command_warns_without_blocking_ready_source(tmp_path: Path) -> None:
    source_dir = tmp_path / "external/polymarket-cli"
    (source_dir / "src/commands").mkdir(parents=True)
    (source_dir / "Cargo.toml").write_text("[package]\nname = \"polymarket\"\n", encoding="utf-8")
    (source_dir / "src/commands/clob.rs").write_text("// fixture\n", encoding="utf-8")

    source = ReferenceRepoConfig(
        name="polymarket-cli",
        repo_url="https://github.com/Polymarket/polymarket-cli",
        purpose="CLI source",
        integration_mode="external_cli_surface",
        expected_path="external/polymarket-cli",
        required_files=["Cargo.toml", "src/commands/clob.rs"],
        commands=["definitely-not-installed-polymarket-fixture"],
    )

    status = check_source(source, root=tmp_path, require_pinned_commit=False)

    assert status.ok is True
    assert status.reason_codes == ()
    assert status.warning_codes == ("COMMAND_NOT_FOUND:definitely-not-installed-polymarket-fixture",)


def test_policy_yaml_wires_reference_sources() -> None:
    policy = Policy.from_yaml("configs/policy.yaml")

    statuses = check_sources(
        policy.automation.sources,
        root=Path("."),
        require_pinned_commit=policy.automation.require_pinned_commits,
    )

    assert len(statuses) == 4
    assert {status.name for status in statuses} == {
        "poly_data",
        "polymarket-cli",
        "polymarket-agents",
        "polymarket-trade-engine",
    }


@pytest.mark.asyncio
async def test_reference_repo_monitor_persists_and_logs(tmp_path: Path) -> None:
    source_dir = tmp_path / "external/poly_data"
    source_dir.mkdir(parents=True)
    (source_dir / "update_all.py").write_text("# fixture\n", encoding="utf-8")

    policy = Policy(
        automation={
            "require_pinned_commits": False,
            "sources": [
                {
                    "name": "poly_data",
                    "repo_url": "https://github.com/warproxxx/poly_data",
                    "purpose": "Historical backtest data",
                    "integration_mode": "historical_backtest_data",
                    "expected_path": "external/poly_data",
                    "required_files": ["update_all.py"],
                }
            ],
        }
    )
    log_path = tmp_path / "immutable.jsonl"
    store = SQLiteStore(tmp_path / "polyflow.db")
    monitor = ReferenceRepoMonitor(
        policy=policy,
        logger=ImmutableLogger(log_path),
        store=store,
        root=tmp_path,
    )

    await monitor.tick()

    rows = store.list_automation_sources()
    store.close()
    assert rows[0]["name"] == "poly_data"
    assert rows[0]["status"] == "ready"

    record = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
    assert record["actor"] == "reference_repo_monitor"
    assert record["payload"]["ready"] == 1
