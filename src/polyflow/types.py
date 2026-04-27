"""Core domain types. Every cross-module payload flows as one of these models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Mode(str, Enum):
    OBSERVE = "observe"
    PAPER = "paper"
    LIVE_CONFIRM = "live_confirm"
    LIVE_TINY = "live_tiny"
    LIVE_STANDARD = "live_standard"
    LOCKDOWN = "lockdown"


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class Outcome(str, Enum):
    YES = "YES"
    NO = "NO"


class OrderType(str, Enum):
    GTC = "GTC"
    FAK = "FAK"
    FOK = "FOK"


class Strategy(str, Enum):
    NEWS_REPRICING = "news_repricing"
    EXTERNAL_ODDS_DIVERGENCE = "external_odds_divergence"
    BTC_THRESHOLD = "btc_threshold"
    FOUR_LAYER_ALIGNMENT = "four_layer_alignment"
    PASSIVE_FAIR_VALUE_QUOTING = "passive_fair_value_quoting"
    NEW_MARKET_OPENING = "new_market_opening"
    SPREAD_CAPTURE = "spread_capture"
    NEGATIVE_RISK_BASKET = "negative_risk_basket"


class Market(BaseModel):
    """Market metadata — what the scanner emits after passing hard filters."""

    model_config = ConfigDict(frozen=True)

    id: str
    event_id: str | None = None
    question: str
    category: str | None = None
    close_time: datetime | None = None
    resolution_rules: str | None = None

    liquidity_usd: float = 0.0
    volume_24h_usd: float = 0.0
    spread_pct: float = 100.0
    depth_within_5c_usd: float = 0.0
    best_bid: float | None = None
    best_ask: float | None = None

    yes_token_id: str | None = None
    no_token_id: str | None = None
    tick_size: float | None = None
    min_order_size: float | None = None
    fee_rate_bps: float | None = None
    neg_risk: bool | None = None

    market_quality: float = 0.0
    resolution_risk: float = 1.0


class ProbabilityEstimate(BaseModel):
    """PRD §8.1 probability object."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    market_id: str
    token_id: str
    outcome: Outcome
    market_price: float = Field(ge=0.0, le=1.0)
    model_probability: float = Field(ge=0.0, le=1.0)
    uncertainty: float = Field(ge=0.0, le=1.0)
    fair_bid: float = Field(ge=0.0, le=1.0)
    fair_ask: float = Field(ge=0.0, le=1.0)
    edge_before_costs: float
    edge_after_costs: float
    source_confidence: float = Field(ge=0.0, le=1.0)
    resolution_risk: float = Field(ge=0.0, le=1.0)
    recommendation: str
    expires_at: datetime
    reason_codes: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)

    @field_validator("fair_ask")
    @classmethod
    def ask_above_bid(cls, v: float, info: Any) -> float:
        bid = info.data.get("fair_bid")
        if bid is not None and v < bid:
            raise ValueError("fair_ask must be >= fair_bid")
        return v


class Signal(BaseModel):
    """Candidate trading signal arbitration object (PRD §17.1)."""

    signal_id: UUID = Field(default_factory=uuid4)
    market_id: str
    event_id: str | None
    token_id: str
    outcome: Outcome
    side: Side
    strategy: Strategy
    market_price: float
    model_probability: float
    uncertainty: float
    effective_edge: float
    market_quality: float
    resolution_risk: float
    liquidity_score: float
    confidence: float
    expires_at: datetime
    evidence_refs: list[str] = Field(default_factory=list)
    score: float = 0.0
    status: str = "candidate"
    reason_codes: list[str] = Field(default_factory=list)


class OrderPayload(BaseModel):
    """The exact payload we hand to the CLOB SDK."""

    model_config = ConfigDict(frozen=True)

    tokenID: str
    side: Side
    price: str  # decimal string aligned to tick
    size: str   # decimal string >= min_order_size
    orderType: OrderType
    strategy: Strategy
    marketId: str
    eventId: str | None = None
    maxPositionAfterFill: str
    clientOrderId: str


class FormattedOrder(BaseModel):
    """Output of clob_order_formatter — strict JSON the CLOB adapter consumes."""

    ready_to_submit: bool
    order_payload: OrderPayload | None
    risk_ref: str | None = None
    evidence_ref: str | None = None
    rejected: bool = False
    reason_codes: list[str] = Field(default_factory=list)


class Position(BaseModel):
    market_id: str
    token_id: str
    outcome: Outcome
    size: float
    avg_price: float
    market_value: float = 0.0
    max_loss: float = 0.0


class RiskState(BaseModel):
    """Live exposure snapshot used by the Risk Governor and post-order hook."""

    bankroll_usdc: float
    used_market_usdc: dict[str, float] = Field(default_factory=dict)
    used_event_usdc: dict[str, float] = Field(default_factory=dict)
    used_category_usdc: dict[str, float] = Field(default_factory=dict)
    daily_loss_usdc: float = 0.0
    weekly_loss_usdc: float = 0.0
    open_markets: int = 0
    orders_in_last_minute: int = 0
    new_markets_in_last_hour: int = 0


class RiskDecision(BaseModel):
    approved: bool
    approved_size_usdc: float = 0.0
    raw_kelly: float = 0.0
    fractional_kelly: float = 0.0
    caps_applied: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
