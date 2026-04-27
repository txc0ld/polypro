"""Reference repository automation checks.

The runtime treats upstream repositories as pinned inputs, not as trusted code
to import blindly. This module verifies whether each source is materialized
locally and whether the checked-out commit still matches policy.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import ReferenceRepoConfig


@dataclass(frozen=True)
class AutomationSourceStatus:
    name: str
    repo_url: str
    purpose: str
    integration_mode: str
    enabled: bool
    pinned_commit: str | None
    local_path: str | None
    detected_commit: str | None
    status: str
    reason_codes: tuple[str, ...]
    required_files: tuple[str, ...]
    commands: tuple[str, ...]
    checked_at: str

    @property
    def ok(self) -> bool:
        return self.status == "ready"

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "repo_url": self.repo_url,
            "purpose": self.purpose,
            "integration_mode": self.integration_mode,
            "enabled": self.enabled,
            "pinned_commit": self.pinned_commit,
            "local_path": self.local_path,
            "detected_commit": self.detected_commit,
            "status": self.status,
            "reason_codes": list(self.reason_codes),
            "required_files": list(self.required_files),
            "commands": list(self.commands),
            "checked_at": self.checked_at,
            "ok": self.ok,
        }


def default_reference_sources() -> list[ReferenceRepoConfig]:
    """Pinned public sources used by the POLYFLOW automation doctrine."""
    return [
        ReferenceRepoConfig(
            name="poly_data",
            repo_url="https://github.com/warproxxx/poly_data",
            purpose="Historical trade data for backtesting and wallet replay.",
            integration_mode="historical_backtest_data",
            pinned_commit="b7c1d1703d6a3d1dfaa5f49c9ef7b4b899775392",
            expected_path="external/poly_data",
            local_path_env="POLYFLOW_POLY_DATA_PATH",
            required_files=[
                "update_all.py",
                "update_utils/process_live.py",
                "poly_utils/utils.py",
            ],
        ),
        ReferenceRepoConfig(
            name="polymarket-cli",
            repo_url="https://github.com/Polymarket/polymarket-cli",
            purpose="Official command surface for market scanning, order inspection, and guarded order workflows.",
            integration_mode="external_cli_surface",
            pinned_commit="4b5a749d5bf04f23611544a059e2a15c7281ae83",
            expected_path="external/polymarket-cli",
            local_path_env="POLYFLOW_POLYMARKET_CLI_PATH",
            required_files=["Cargo.toml", "src/commands/clob.rs", "src/commands/markets.rs"],
            commands=["polymarket"],
        ),
        ReferenceRepoConfig(
            name="polymarket-agents",
            repo_url="https://github.com/Polymarket/agents",
            purpose="Agent/RAG framework reference for public-source reasoning and LLM tool contracts.",
            integration_mode="agent_framework_reference",
            pinned_commit="081f2b5594c37edeb9d3780a778c084d5b6f2743",
            expected_path="external/agents",
            local_path_env="POLYFLOW_POLYMARKET_AGENTS_PATH",
            required_files=[
                "agents/application/trade.py",
                "agents/polymarket/gamma.py",
                "agents/utils/objects.py",
            ],
        ),
        ReferenceRepoConfig(
            name="polymarket-trade-engine",
            repo_url="https://github.com/KaustubhPatange/polymarket-trade-engine",
            purpose="5-minute market engine architecture reference for lifecycle, ticker, and simulation patterns.",
            integration_mode="five_minute_engine_reference",
            pinned_commit="b941451fb2a65cfc721c73bdc92e0a3e4b7c9a4f",
            expected_path="external/polymarket-trade-engine",
            local_path_env="POLYFLOW_TRADE_ENGINE_PATH",
            required_files=[
                "engine/market-lifecycle.ts",
                "engine/strategy/simulation.ts",
                "tracker/orderbook.ts",
            ],
        ),
    ]


def resolve_sources(sources: list[ReferenceRepoConfig]) -> list[ReferenceRepoConfig]:
    """Use policy sources when present; otherwise fall back to pinned defaults."""
    return sources or default_reference_sources()


def check_source(
    source: ReferenceRepoConfig,
    *,
    root: str | Path = ".",
    require_pinned_commit: bool = True,
) -> AutomationSourceStatus:
    checked_at = datetime.now(timezone.utc).isoformat()
    reason_codes: list[str] = []
    local_path = _resolve_local_path(source, root=root)
    detected_commit: str | None = None

    if not source.enabled:
        reason_codes.append("DISABLED")
    if require_pinned_commit and not source.pinned_commit:
        reason_codes.append("PINNED_COMMIT_MISSING")

    if local_path is None:
        reason_codes.append("LOCAL_PATH_UNCONFIGURED")
    elif not local_path.exists():
        reason_codes.append("LOCAL_SOURCE_NOT_FOUND")
    elif not local_path.is_dir():
        reason_codes.append("LOCAL_SOURCE_NOT_DIRECTORY")
    else:
        for required in source.required_files:
            if not (local_path / required).exists():
                reason_codes.append(f"REQUIRED_FILE_MISSING:{required}")
        detected_commit = _git_commit(local_path)
        if require_pinned_commit and source.pinned_commit and detected_commit:
            if detected_commit.lower() != source.pinned_commit.lower():
                reason_codes.append("PIN_MISMATCH")
        elif require_pinned_commit and source.pinned_commit and detected_commit is None:
            reason_codes.append("GIT_COMMIT_UNAVAILABLE")

    for command in source.commands:
        if shutil.which(command) is None:
            reason_codes.append(f"COMMAND_NOT_FOUND:{command}")

    status = "ready" if source.enabled and not reason_codes else "not_ready"
    return AutomationSourceStatus(
        name=source.name,
        repo_url=source.repo_url,
        purpose=source.purpose,
        integration_mode=source.integration_mode,
        enabled=source.enabled,
        pinned_commit=source.pinned_commit,
        local_path=str(local_path) if local_path is not None else None,
        detected_commit=detected_commit,
        status=status,
        reason_codes=tuple(reason_codes),
        required_files=tuple(source.required_files),
        commands=tuple(source.commands),
        checked_at=checked_at,
    )


def check_sources(
    sources: list[ReferenceRepoConfig],
    *,
    root: str | Path = ".",
    require_pinned_commit: bool = True,
) -> list[AutomationSourceStatus]:
    return [
        check_source(source, root=root, require_pinned_commit=require_pinned_commit)
        for source in resolve_sources(sources)
    ]


def _resolve_local_path(source: ReferenceRepoConfig, *, root: str | Path) -> Path | None:
    if source.local_path_env:
        env_value = os.environ.get(source.local_path_env)
        if env_value:
            return Path(env_value).expanduser()
    if source.expected_path:
        return Path(root) / source.expected_path
    return None


def _git_commit(path: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=3.0,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    commit = result.stdout.strip()
    return commit or None
