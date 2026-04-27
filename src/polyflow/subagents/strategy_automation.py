"""24/7 strategy automation loop.

The automation loop does not invent trades. It evaluates scanner-approved
quickfire markets against public evidence sources, persists analysis, and only
routes signals through the runtime's existing risk/order gauntlet.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from ..adapters.anchors import AnchorAdapter
from ..adapters.btc_feed import BtcPriceFeed, build_snapshot, fetch_perp_snapshot, summarize
from ..adapters.news import NewsAdapter
from ..adapters.polymarket_user import PolymarketUserAdapter
from ..circuit_breakers import CircuitBreakers
from ..logger import ImmutableLogger
from ..persistence import SQLiteStore
from ..strategies.btc_market_parser import parse_btc_threshold, seconds_to_close
from ..strategies.btc_threshold import BtcThresholdStrategy
from ..strategies.crypto_momentum import CryptoMomentumInputs, CryptoMomentumStrategy
from ..strategies.external_odds_divergence import ExternalOddsDivergence
from ..strategies.intra_market_arbitrage import detect as detect_arbitrage
from ..strategies.near_expiry_certainty import (
    CertaintyScalpInputs,
    evaluate as evaluate_near_expiry,
)
from ..strategies.news_repricing import NewsRepricingStrategy
from ..types import Market, Mode, ProbabilityEstimate, Signal, Strategy


@dataclass
class CandidateResult:
    strategy: Strategy
    estimate: ProbabilityEstimate
    signal: Signal


class StrategyAutomation:
    """Analyze approved quickfire markets and run real signals through gates."""

    def __init__(
        self,
        *,
        runtime,
        store: SQLiteStore,
        logger: ImmutableLogger,
        anchor_adapter: AnchorAdapter | None = None,
        news_adapter: NewsAdapter | None = None,
        btc_feed: BtcPriceFeed | None = None,
        commodities_feed=None,            # type: CommoditiesFeed | None
        macro_calendar=None,               # type: MacroCalendar | None
        circuit_breakers: CircuitBreakers | None = None,
        max_markets: int = 12,
        allow_order_placement: bool = False,
    ) -> None:
        self.runtime = runtime
        self.store = store
        self.logger = logger
        self.anchor_adapter = anchor_adapter
        self.news_adapter = news_adapter
        self.btc_feed = btc_feed
        self.commodities_feed = commodities_feed
        self.macro_calendar = macro_calendar
        self.circuit_breakers = circuit_breakers or CircuitBreakers()
        self.max_markets = max_markets
        self.allow_order_placement = allow_order_placement

    async def tick(self) -> None:
        rows = [
            row for row in self.store.get_markets_by_status("watching")
            if row.get("quickfire_eligible")
        ]
        rows.sort(key=lambda row: float(row.get("quickfire_score") or 0.0), reverse=True)
        analyzed = 0
        emitted = 0
        placed = 0

        for row in rows[: self.max_markets]:
            market = self.store.get_market(str(row["id"]))
            if market is None:
                continue
            analyzed += 1
            candidates = await self._evaluate_market(market)
            emitted += len(candidates)
            self.logger.log(
                actor="strategy_automation",
                action="analyze_market",
                market_id=market.id,
                event_id=market.event_id,
                input_obj={
                    "question": market.question,
                    "quickfire_score": row.get("quickfire_score"),
                    "strategy_candidates": row.get("strategy_candidates", []),
                },
                output_obj={
                    "candidate_signals": len(candidates),
                    "order_placement_allowed": self.allow_order_placement,
                },
                payload={
                    "candidate_signals": len(candidates),
                    "strategies": [c.strategy.value for c in candidates],
                    "quickfire_score": row.get("quickfire_score"),
                },
            )
            for candidate in candidates:
                result = await self._submit_candidate(market, candidate)
                if result.get("placed"):
                    placed += 1

        self.logger.log(
            actor="strategy_automation",
            action="cycle",
            payload={
                "analyzed_markets": analyzed,
                "candidate_signals": emitted,
                "placed_orders": placed,
                "order_placement_allowed": self.allow_order_placement,
            },
        )

    async def _evaluate_market(self, market: Market) -> list[CandidateResult]:
        out: list[CandidateResult] = []

        # Intra-market arbitrage detector — disabled for now. Detecting
        # YES+NO < 0.995 requires reading the *NO* token's order book; we
        # only have the YES book on Market.best_bid/best_ask. The previous
        # implementation used (1 - YES_bid) as a proxy for NO_ask, which
        # mathematically always returns combined_ask = 1 + spread > 1, so
        # the detector never fired. Proper detection needs an extra CLOB
        # call for market.no_token_id; tracked as follow-up.
        _ = detect_arbitrage  # keep import live for the eventual wiring

        # Near-expiry certainty scalper — only valid in the final 15min
        # window when raw external data already implies the outcome.
        if (
            market.best_bid is not None
            and market.best_ask is not None
            and market.close_time is not None
        ):
            ttc = seconds_to_close(market.close_time)
            mid = (market.best_bid + market.best_ask) / 2.0
            # Use the market's own price as a noisy certainty proxy when
            # we have no raw truth-source for this market — only fires on
            # already-near-resolved markets at 95-99c.
            if 0 < ttc <= 15 * 60 and 0.95 <= mid <= 0.99:
                cert = evaluate_near_expiry(
                    CertaintyScalpInputs(
                        market_id=market.id,
                        side="YES" if market.best_ask >= 0.5 else "NO",
                        p_executable=market.best_ask if market.best_ask >= 0.5 else market.best_bid,
                        # The market's own price is a weak certainty proxy.
                        # The strategy's volatility-spike refusal is bypassed
                        # here; for true certainty signals we'd need a raw
                        # truth-source feed (ASOS / spot / oracle).
                        certainty=max(market.best_bid, market.best_ask),
                        seconds_to_resolution=ttc,
                        fee_rate_bps=market.fee_rate_bps or 0,
                        resolution_rules_clear=bool(market.resolution_rules),
                    )
                )
                if cert.fire:
                    self.logger.log(
                        actor="near_expiry_certainty",
                        action="signal",
                        market_id=market.id,
                        payload={
                            "ev_per_dollar": cert.ev_per_dollar,
                            "p_executable": market.best_ask,
                            "ttc_seconds": ttc,
                        },
                    )

        if self.anchor_adapter is not None:
            anchors = await self.anchor_adapter.fetch(market)
            signal = ExternalOddsDivergence(policy=self.runtime.policy).evaluate(
                market=market,
                anchors=anchors,
            )
            if signal is not None:
                est, sig = signal
                out.append(CandidateResult(Strategy.EXTERNAL_ODDS_DIVERGENCE, est, sig))

        # BTC / ETH / SOL threshold strategy — only fires for short-horizon
        # crypto threshold markets. Two evaluators run in series: the
        # baseline lognormal threshold (btc_threshold) and the momentum /
        # wick-fade strategy (crypto_momentum). Both produce candidates;
        # the signal_arbiter scoring picks the best.
        if self.btc_feed is not None:
            btc_signal = await self._evaluate_btc_threshold(market)
            if btc_signal is not None:
                est, sig = btc_signal
                out.append(CandidateResult(Strategy.BTC_THRESHOLD, est, sig))

            momentum_signal = await self._evaluate_crypto_momentum(market)
            if momentum_signal is not None:
                est, sig = momentum_signal
                out.append(CandidateResult(Strategy.BTC_THRESHOLD, est, sig))

        if self.news_adapter is not None and market.best_bid is not None and market.best_ask is not None:
            events = await self.news_adapter.events_for_market(market)
            prior = (market.best_bid + market.best_ask) / 2.0
            signal = NewsRepricingStrategy(policy=self.runtime.policy).evaluate(
                market=market,
                prior_probability=prior,
                events=events,
            )
            self.logger.log(
                actor="news_analyzer",
                action="market_news",
                market_id=market.id,
                event_id=market.event_id,
                payload={
                    "events": len(events),
                    "signal": signal is not None,
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            if signal is not None:
                est, sig = signal
                out.append(CandidateResult(Strategy.NEWS_REPRICING, est, sig))
        return out

    async def _evaluate_btc_threshold(
        self, market: Market
    ) -> tuple[ProbabilityEstimate, Signal] | None:
        """Build a snapshot from the right feed (crypto vs commodity) and run the
        threshold strategy. Pre-release blackout from the macro calendar
        refuses outright."""
        parsed = parse_btc_threshold(market.question)
        if parsed is None:
            return None
        ttc = seconds_to_close(market.close_time)
        if ttc <= 0:
            return None

        # Macro pre-release blackout: refuse during the configured window.
        if self.macro_calendar is not None:
            blackout = self.macro_calendar.is_in_pre_release_window()
            if blackout is not None:
                self.logger.log(
                    actor="macro_calendar",
                    action="blackout_refusal",
                    market_id=market.id,
                    payload={
                        "event_kind": blackout.kind,
                        "event_title": blackout.title,
                        "event_at": blackout.timestamp_utc.isoformat(),
                    },
                )
                return None

        is_commodity = parsed.asset in {"WTI", "OIL", "BRENT", "GOLD", "XAU", "SILVER", "XAG", "COPPER"}

        if is_commodity:
            return await self._evaluate_commodity_threshold(market, parsed, ttc)

        # Crypto path
        try:
            quotes = await self.btc_feed.fetch(asset=parsed.asset)
        except Exception as exc:  # noqa: BLE001
            self.logger.log(
                actor="btc_feed",
                action="fetch_failed",
                market_id=market.id,
                payload={"error": str(exc)[:200], "asset": parsed.asset},
            )
            return None

        # Pull perp basis + funding + momentum (rolling 5min window).
        perp = await fetch_perp_snapshot(parsed.asset)
        momentum = self.btc_feed.momentum(asset=parsed.asset, window_seconds=300.0)
        feed_summary = summarize(quotes, perp=perp, momentum=momentum)
        if feed_summary is None:
            return None

        realized_vol = self.btc_feed.realized_volatility_annualized(asset=parsed.asset)
        if realized_vol is None:
            # Conservative default until samples accumulate. ETH/SOL are more
            # volatile than BTC, so seed each asset with a higher floor.
            realized_vol = {"BTC": 0.60, "ETH": 0.80, "SOL": 1.20}.get(parsed.asset, 0.80)

        snapshot = build_snapshot(
            summary=feed_summary,
            realized_vol=realized_vol,
            price_to_beat=parsed.price_to_beat,
            seconds_to_resolution=ttc,
        )
        self.logger.log(
            actor="btc_feed",
            action="snapshot",
            market_id=market.id,
            payload={
                "asset": parsed.asset,
                "spot_usd": feed_summary.median_price_usd,
                "sources": list(feed_summary.sources),
                "disagreement_bps": feed_summary.disagreement_bps,
                "realized_vol": realized_vol,
                "price_to_beat": parsed.price_to_beat,
                "seconds_to_resolution": ttc,
                "direction": parsed.direction,
                "perp_mark": perp.mark_price if perp else None,
                "perp_index": perp.index_price if perp else None,
                "perp_basis_bps": perp.basis_bps if perp else None,
                "perp_funding_rate": perp.funding_rate if perp else None,
            },
        )

        result = BtcThresholdStrategy(policy=self.runtime.policy).evaluate(
            market=market,
            snapshot=snapshot,
        )
        # Log the edge breakdown either way — when result is None we want
        # to see *why* (which buffer ate the edge); when it fires we want
        # to see the math that approved it.
        if result is None:
            self.logger.log(
                actor="btc_threshold",
                action="refused",
                market_id=market.id,
                payload={
                    "asset": parsed.asset,
                    "best_bid": market.best_bid,
                    "best_ask": market.best_ask,
                    "spot_usd": feed_summary.median_price_usd,
                    "price_to_beat": parsed.price_to_beat,
                    "min_effective_edge": self.runtime.policy.kelly.min_effective_edge,
                },
            )
        else:
            est, _ = result
            self.logger.log(
                actor="btc_threshold",
                action="emitted",
                market_id=market.id,
                payload={
                    "asset": parsed.asset,
                    "model_q": est.model_probability,
                    "market_p": est.market_price,
                    "edge_before": est.edge_before_costs,
                    "edge_after": est.edge_after_costs,
                    "outcome": est.outcome.value,
                    "reason_codes": est.reason_codes,
                },
            )
        return result

    async def _evaluate_commodity_threshold(
        self, market: Market, parsed, ttc: float
    ) -> tuple[ProbabilityEstimate, Signal] | None:
        """Commodity threshold path (WTI / GOLD / SILVER / COPPER).

        Uses Yahoo Finance front-month futures via ``CommoditiesFeed``. No
        perp basis (commodities don't have a uniform global perp). We
        synthesize a ``BtcThresholdSnapshot`` from the spot quote so we can
        reuse the lognormal threshold strategy unchanged.
        """
        if self.commodities_feed is None:
            return None
        try:
            quote = await self.commodities_feed.fetch(parsed.asset)
        except Exception as exc:  # noqa: BLE001
            self.logger.log(
                actor="commodities_feed",
                action="fetch_failed",
                market_id=market.id,
                payload={"error": str(exc)[:200], "asset": parsed.asset},
            )
            return None
        if quote is None or quote.price_usd <= 0:
            return None

        realized_vol = self.commodities_feed.realized_volatility_annualized(parsed.asset)
        if realized_vol is None:
            # Conservative defaults until enough rolling samples accumulate.
            # Annualized vol estimates: WTI ~35%, gold ~15%, silver ~25%, copper ~25%.
            realized_vol = {
                "WTI": 0.35, "OIL": 0.35, "BRENT": 0.35,
                "GOLD": 0.15, "XAU": 0.15,
                "SILVER": 0.25, "XAG": 0.25,
                "COPPER": 0.25,
            }.get(parsed.asset, 0.20)

        # Build a BtcThresholdSnapshot directly — the strategy doesn't care
        # what the asset *is*, only that the snapshot is valid + recent.
        from ..strategies.btc_threshold import BtcThresholdSnapshot
        snapshot = BtcThresholdSnapshot(
            source_name=f"yahoo:{quote.yahoo_symbol}",
            source_url="commodities_feed",
            fetched_at=quote.fetched_at,
            price_to_beat=parsed.price_to_beat,
            btc_spot=quote.price_usd,           # field name kept for back-compat
            seconds_to_resolution=ttc,
            realized_volatility_annualized=realized_vol,
            feed_disagreement_bps=0.0,          # single source — no disagreement
            oracle_latency_seconds=0.0,
            drift_adjustment=0.0,
            settlement_match=True,
        )

        self.logger.log(
            actor="commodities_feed",
            action="snapshot",
            market_id=market.id,
            payload={
                "asset": parsed.asset,
                "spot_usd": quote.price_usd,
                "yahoo_symbol": quote.yahoo_symbol,
                "realized_vol": realized_vol,
                "price_to_beat": parsed.price_to_beat,
                "seconds_to_resolution": ttc,
                "direction": parsed.direction,
            },
        )

        return BtcThresholdStrategy(policy=self.runtime.policy).evaluate(
            market=market, snapshot=snapshot,
        )

    async def _evaluate_crypto_momentum(
        self, market: Market
    ) -> tuple[ProbabilityEstimate, Signal] | None:
        """Run the momentum / wick-fade strategy against the rolling feed."""
        parsed = parse_btc_threshold(market.question)
        if parsed is None:
            return None
        ttc = seconds_to_close(market.close_time)
        if ttc <= 0:
            return None

        # Reuse the latest quotes / perp / momentum (from the same tick path
        # that btc_threshold ran). We re-fetch — strategy_automation runs
        # both evaluators inline; re-fetching keeps each evaluator
        # self-contained even though it spends one extra HTTP hop.
        try:
            quotes = await self.btc_feed.fetch(asset=parsed.asset)
        except Exception:  # noqa: BLE001
            return None
        if not quotes:
            return None

        perp = await fetch_perp_snapshot(parsed.asset)
        momentum = self.btc_feed.momentum(asset=parsed.asset, window_seconds=300.0)
        if momentum is None or perp is None:
            return None

        from statistics import median
        spot = median(q.price_usd for q in quotes)
        from .. import adapters  # noqa: F401  (importable surface)
        from ..adapters.btc_feed import disagreement_bps

        realized_vol = self.btc_feed.realized_volatility_annualized(asset=parsed.asset)
        if realized_vol is None:
            realized_vol = {"BTC": 0.60, "ETH": 0.80, "SOL": 1.20}.get(parsed.asset, 0.80)

        inputs = CryptoMomentumInputs(
            asset=parsed.asset,
            spot_usd=spot,
            perp_basis_bps=perp.basis_bps,
            feed_disagreement_bps=disagreement_bps(quotes),
            velocity_bps_per_min=momentum.velocity_bps_per_min,
            range_bps=momentum.range_bps,
            window_seconds=momentum.window_seconds,
            n_samples=momentum.n_samples,
            realized_vol_annualized=realized_vol,
        )

        result = CryptoMomentumStrategy(policy=self.runtime.policy).evaluate(
            market=market, inputs=inputs
        )
        if result is not None:
            self.logger.log(
                actor="crypto_momentum",
                action="signal",
                market_id=market.id,
                payload={
                    "asset": parsed.asset,
                    "velocity_bps_per_min": momentum.velocity_bps_per_min,
                    "range_bps": momentum.range_bps,
                    "perp_basis_bps": perp.basis_bps,
                    "edge_after_costs": result[0].edge_after_costs,
                },
            )
        return result

    async def _submit_candidate(self, market: Market, candidate: CandidateResult) -> dict:
        # Circuit breakers — refuse before the order even reaches the runtime.
        if not self.circuit_breakers.can_trade:
            self.logger.log(
                actor="circuit_breakers",
                action="frozen_consecutive_losses",
                market_id=market.id,
                payload={
                    "consecutive_losses": self.circuit_breakers.consecutive_losses,
                    "max": self.circuit_breakers.max_consecutive_losses,
                },
            )
            return {"placed": False, "reason": "CONSECUTIVE_LOSS_FREEZE"}

        if self.circuit_breakers.in_final_blackout(
            close_time=market.close_time, market_id=market.id
        ):
            self.logger.log(
                actor="circuit_breakers",
                action="final_blackout",
                market_id=market.id,
                payload={
                    "blackout_seconds": self.circuit_breakers.final_blackout_seconds,
                    "close_time": market.close_time.isoformat() if market.close_time else None,
                },
            )
            return {"placed": False, "reason": "FINAL_BLACKOUT"}

        original_mode = self.runtime.policy.mode
        if not self.allow_order_placement:
            self.runtime.policy.mode = Mode.OBSERVE
        try:
            result = await self.runtime.evaluate_candidate(
                signal=candidate.signal,
                estimate=candidate.estimate,
                market=market,
                strategy=candidate.strategy,
            )
        finally:
            self.runtime.policy.mode = original_mode
        self.logger.log(
            actor="strategy_automation",
            action="candidate_result",
            market_id=market.id,
            event_id=market.event_id,
            payload={
                "strategy": candidate.strategy.value,
                "placed": bool(result.get("placed")),
                "reason": result.get("reason"),
                "order_placement_allowed": self.allow_order_placement,
            },
        )
        return result

    def record_trade_outcome(self, *, pnl_usdc: float) -> None:
        """Hook for the runtime to feed realized trade outcomes back into the
        consecutive-loss counter. Called from the post-resolution path."""
        self.circuit_breakers.record_outcome(pnl_usdc=pnl_usdc)


class TradeActivityAnalyzer:
    """Poll wallet activity/positions and write analysis records."""

    def __init__(
        self,
        *,
        wallet_address: str | None,
        logger: ImmutableLogger,
        store: SQLiteStore | None = None,
    ) -> None:
        self.wallet_address = wallet_address
        self.logger = logger
        self.store = store

    async def tick(self) -> None:
        if not self.wallet_address:
            self.logger.log(
                actor="trade_activity_analyzer",
                action="skip",
                payload={"reason": "NO_WALLET_ADDRESS"},
            )
            return
        async with PolymarketUserAdapter(wallet_address=self.wallet_address) as adapter:
            positions = await adapter.positions()
            activity = await adapter.activity(limit=50)
        self.logger.log(
            actor="trade_activity_analyzer",
            action="wallet_snapshot",
            payload={
                "positions": len(positions),
                "activity": len(activity),
                "open_position_value": _sum_float(positions, "currentValue", "market_value"),
            },
        )


def _sum_float(rows: list[dict], *keys: str) -> float:
    total = 0.0
    for row in rows:
        for key in keys:
            try:
                total += float(row.get(key) or 0.0)
                break
            except (TypeError, ValueError):
                continue
    return total
