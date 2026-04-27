"""Policy loader. One YAML in, one strongly-typed Policy out."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from .types import Mode, OrderType


class MarketFilters(BaseModel):
    min_liquidity_usd: float = 100_000
    min_volume_24h_usd: float = 25_000
    max_spread_pct: float = 5.0
    min_depth_within_5c_usd: float = 10_000
    min_time_to_close_minutes: int = 60
    max_time_to_close_minutes: int | None = None


class RiskLimits(BaseModel):
    bankroll_usdc: float = 1000.0
    max_single_market_position_pct: float = 1.0
    max_single_event_exposure_pct: float = 2.5
    max_category_exposure_pct: float = 5.0
    max_daily_loss_pct: float = 0.75
    max_weekly_loss_pct: float = 2.0
    max_open_markets: int = 10
    max_new_markets_per_hour: int = 4
    max_orders_per_minute: int = 10
    min_confidence: float = 0.75
    min_market_quality: float = 0.70
    max_resolution_risk: float = 0.35
    max_model_uncertainty: float = 0.12


class KellyParams(BaseModel):
    fraction: float = 0.05
    min_effective_edge: float = 0.03
    min_edge_after_uncertainty: float = 0.015
    max_model_uncertainty: float = 0.12


class OrderRules(BaseModel):
    allowed_types_live_tiny: list[OrderType] = Field(
        default_factory=lambda: [OrderType.GTC, OrderType.FAK]
    )
    allow_market_orders: bool = False
    require_tick_size: bool = True
    require_fee_rate: bool = True
    require_min_order_size: bool = True


class IntegrityRules(BaseModel):
    ban_private_information: bool = True
    ban_leaked_information: bool = True
    ban_outcome_influencer_trading: bool = True
    ban_spoofing: bool = True
    ban_wash_trading: bool = True
    ban_self_dealing: bool = True
    ban_manipulation: bool = True


class SubagentCadence(BaseModel):
    market_divergence_monitor_seconds: int = 60
    news_context_monitor_seconds: int = 60
    portfolio_sentinel_seconds: int = 30
    market_scanner_minutes: int = 5
    reference_repo_monitor_seconds: int = 3600
    strategy_automation_seconds: int = 30
    trade_activity_seconds: int = 60


class ReferenceRepoConfig(BaseModel):
    name: str
    repo_url: str
    purpose: str
    integration_mode: str
    pinned_commit: str | None = None
    expected_path: str | None = None
    local_path_env: str | None = None
    required_files: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    enabled: bool = True


class AutomationConfig(BaseModel):
    enabled: bool = True
    require_pinned_commits: bool = True
    sources: list[ReferenceRepoConfig] = Field(default_factory=list)
    allow_order_placement: bool = False
    max_markets_per_strategy_cycle: int = 12
    external_anchors_path: str | None = "configs/external_anchors.json"
    news_rss_urls: list[str] = Field(default_factory=list)
    news_max_items_per_feed: int = 20


class Policy(BaseModel):
    mode: Mode = Mode.OBSERVE
    market_filters: MarketFilters = Field(default_factory=MarketFilters)
    risk: RiskLimits = Field(default_factory=RiskLimits)
    kelly: KellyParams = Field(default_factory=KellyParams)
    orders: OrderRules = Field(default_factory=OrderRules)
    integrity: IntegrityRules = Field(default_factory=IntegrityRules)
    subagents: SubagentCadence = Field(default_factory=SubagentCadence)
    automation: AutomationConfig = Field(default_factory=AutomationConfig)

    config_hash: str = ""

    @classmethod
    def from_yaml(cls, path: str | Path) -> "Policy":
        raw_bytes = Path(path).read_bytes()
        data: dict[str, Any] = yaml.safe_load(raw_bytes) or {}
        config_hash = hashlib.sha256(raw_bytes).hexdigest()
        return cls.model_validate({**data, "config_hash": config_hash})
