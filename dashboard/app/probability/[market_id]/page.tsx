import { notFound } from "next/navigation";
import { Card, EmptyState, KeyRow } from "@/components/Card";
import { Pill } from "@/components/Pill";
import { StrategyBadge } from "@/components/StrategyBadge";
import {
  ProbabilityChart,
  type ProbabilityPoint,
} from "@/components/ProbabilityChart";
import {
  calibrationBuckets,
  getMarket,
  listSignalsForMarket,
} from "@/lib/db";
import { tailLog, type LogRecord } from "@/lib/log";
import { fmtNum, fmtPct, fmtUsd, shortId, timeAgo } from "@/lib/format";

type SignalPayload = {
  model_probability?: number;
  market_price?: number;
  uncertainty?: number;
};

function pointsFromLog(records: LogRecord[]): ProbabilityPoint[] {
  const pts: ProbabilityPoint[] = [];
  for (const r of records) {
    const payload = r.payload as Record<string, unknown>;
    const inputObj = (payload.input_obj ?? payload) as SignalPayload;
    const mp = inputObj.model_probability ?? (payload as SignalPayload).model_probability;
    const px = inputObj.market_price ?? (payload as SignalPayload).market_price;
    const unc =
      inputObj.uncertainty ?? (payload as SignalPayload).uncertainty ?? 0;
    if (typeof mp === "number" && typeof px === "number") {
      pts.push({
        ts: r.ts,
        modelProbability: mp,
        marketPrice: px,
        upper: Math.min(1, mp + unc),
        lower: Math.max(0, mp - unc),
      });
    }
  }
  return pts;
}

function calibrationBucketLabel(p: number | null): string {
  if (p === null || Number.isNaN(p)) return "—";
  return (Math.round(p * 10) / 10).toFixed(1);
}

export default async function ProbabilityLab({
  params,
}: {
  params: { market_id: string };
}) {
  const marketId = decodeURIComponent(params.market_id);
  const market = getMarket(marketId);
  if (!market) notFound();

  const signalRecords = await tailLog(4000, { marketId });
  const points = pointsFromLog(
    signalRecords.filter((r) => r.actor === "signal_arbiter"),
  );
  const signals = listSignalsForMarket(marketId);
  const buckets = calibrationBuckets();
  const latest = points[points.length - 1];
  const bucketLabel = calibrationBucketLabel(latest?.modelProbability ?? null);
  const bucketStat = buckets.find((b) => b.bucket.toFixed(1) === bucketLabel);

  const gap =
    latest && latest.modelProbability !== null && latest.marketPrice !== null
      ? latest.modelProbability - latest.marketPrice
      : null;

  // Group source-evidence signals by strategy so each strategy's most recent
  // probability sits side-by-side with the others.
  const byStrategy = new Map<string, typeof signals>();
  for (const s of signals) {
    const arr = byStrategy.get(s.strategy) ?? [];
    arr.push(s);
    byStrategy.set(s.strategy, arr);
  }

  const closeIso = market.close_time;
  const closeMs = closeIso ? new Date(closeIso).getTime() - Date.now() : null;

  return (
    <div className="space-y-6">
      <header className="space-y-3">
        <div className="flex items-baseline justify-between gap-4">
          <h1 className="text-display font-semibold tracking-tight">
            {market.question}
          </h1>
          <Pill tone="muted">PRD §19.3</Pill>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <Pill tone="info">{market.category ?? "uncategorised"}</Pill>
          <Pill tone={market.status === "watching" ? "good" : "muted"}>
            {market.status}
          </Pill>
          <span className="font-mono text-subtle">{shortId(market.id, 18)}</span>
          {closeMs !== null ? (
            <span className="text-subtle">
              ·{" "}
              {closeMs <= 0
                ? "closed"
                : `closes in ${Math.floor(closeMs / 3600000)}h ${Math.floor(
                    (closeMs % 3600000) / 60000,
                  )}m`}
            </span>
          ) : null}
        </div>
      </header>

      {/* Hero: chart + big-number panel */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_320px]">
        <Card title="model probability vs market price">
          <ProbabilityChart data={points} />
          <p className="mt-3 text-xs text-subtle">
            {points.length} estimate{points.length === 1 ? "" : "s"} · band shows ±1σ
            uncertainty.
          </p>
        </Card>

        <Card title="latest">
          {!latest ? (
            <EmptyState
              title="no estimates yet"
              hint="Strategies have not produced a probability for this market in the recent log window."
            />
          ) : (
            <div className="space-y-4">
              <div>
                <div className="text-caption uppercase tracking-wider text-subtle">
                  model probability
                </div>
                <div className="tabular text-3xl font-medium text-accent">
                  {fmtPct(latest.modelProbability, 1)}
                </div>
              </div>
              <div>
                <div className="text-caption uppercase tracking-wider text-subtle">
                  market price
                </div>
                <div className="tabular text-3xl font-medium text-warn">
                  {fmtPct(latest.marketPrice, 1)}
                </div>
              </div>
              <div className="border-t border-hairline pt-3">
                <div className="text-caption uppercase tracking-wider text-subtle">
                  gap (model − market)
                </div>
                <div
                  className={`tabular text-2xl font-medium ${
                    gap === null
                      ? "text-ink"
                      : gap > 0
                        ? "text-accent"
                        : "text-bad"
                  }`}
                >
                  {gap === null
                    ? "—"
                    : `${gap > 0 ? "+" : ""}${(gap * 100).toFixed(1)}¢`}
                </div>
              </div>
              {bucketStat ? (
                <div className="space-y-1 border-t border-hairline pt-3">
                  <KeyRow
                    k="calibration bucket"
                    v={
                      <span className="text-accent">
                        {bucketLabel}
                      </span>
                    }
                  />
                  <KeyRow
                    k="empirical"
                    v={fmtPct(bucketStat.empirical, 1)}
                  />
                  <KeyRow k="n" v={bucketStat.n} />
                </div>
              ) : null}
            </div>
          )}
        </Card>
      </div>

      {/* Source evidence grid — one card per strategy */}
      <Card title="sources" action={<span>{byStrategy.size} strategies</span>}>
        {byStrategy.size === 0 ? (
          <EmptyState
            title="no strategy emissions"
            hint="No strategy has emitted a candidate for this market yet."
          />
        ) : (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
            {[...byStrategy.entries()].map(([strategy, list]) => {
              const newest = list[0];
              let refs: string[] = [];
              try {
                refs = JSON.parse(newest.evidence_refs) as string[];
              } catch {
                /* noop */
              }
              return (
                <div
                  key={strategy}
                  className="rounded border border-hairline bg-surface p-3"
                >
                  <div className="mb-2 flex items-center justify-between">
                    <StrategyBadge strategy={strategy} size="sm" />
                    <span className="text-[10px] text-subtle">
                      {timeAgo(newest.created_at)}
                    </span>
                  </div>
                  <KeyRow
                    k="side"
                    v={<span className="font-medium">{newest.side}</span>}
                  />
                  <KeyRow k="score" v={fmtNum(newest.score, 2)} />
                  <KeyRow
                    k="status"
                    v={
                      <span
                        className={
                          newest.status === "PLACE"
                            ? "text-accent"
                            : newest.status === "REJECT"
                              ? "text-bad"
                              : "text-muted"
                        }
                      >
                        {newest.status}
                      </span>
                    }
                  />
                  {refs.length > 0 ? (
                    <div className="mt-2 text-[10px] text-subtle">
                      evidence: {refs.slice(0, 2).join(", ")}
                      {refs.length > 2 ? ` +${refs.length - 2}` : ""}
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        )}
      </Card>

      {/* Market metadata + resolution rules in a clean grid */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <Card title="metadata">
          <div className="space-y-1">
            <KeyRow k="liquidity" v={fmtUsd(market.liquidity_usd, 0)} />
            <KeyRow k="volume 24h" v={fmtUsd(market.volume_24h_usd, 0)} />
            <KeyRow
              k="spread"
              v={
                market.spread_pct === null
                  ? "—"
                  : `${market.spread_pct.toFixed(2)}c`
              }
            />
            <KeyRow
              k="best bid/ask"
              v={
                market.best_bid !== null && market.best_ask !== null
                  ? `${(market.best_bid * 100).toFixed(1)}/${(market.best_ask * 100).toFixed(1)}c`
                  : "—"
              }
            />
            <KeyRow k="quality" v={fmtNum(market.market_quality, 2)} />
            <KeyRow k="resolution risk" v={fmtNum(market.resolution_risk, 2)} />
            <KeyRow
              k="quickfire"
              v={
                market.quickfire_eligible
                  ? `eligible · ${fmtNum(market.quickfire_score, 2)}`
                  : `no · ${fmtNum(market.quickfire_score, 2)}`
              }
            />
            <KeyRow k="neg risk" v={market.neg_risk ? "yes" : "no"} />
          </div>
        </Card>

        <Card title="market identifiers">
          <div className="space-y-1 font-mono text-xs">
            <KeyRow k="market id" v={shortId(market.id, 24)} mono />
            <KeyRow k="event id" v={shortId(market.event_id, 24)} mono />
            <KeyRow k="created" v={timeAgo(market.created_at)} />
            <KeyRow
              k="closes"
              v={market.close_time ? timeAgo(market.close_time) : "—"}
            />
          </div>
        </Card>

        <Card title="resolution rules">
          {market.resolution_rules ? (
            <details className="text-xs">
              <summary className="cursor-pointer text-subtle hover:text-ink">
                {market.resolution_rules.slice(0, 80)}
                {market.resolution_rules.length > 80 ? "…" : ""}
              </summary>
              <p className="mt-2 whitespace-pre-wrap leading-relaxed text-muted">
                {market.resolution_rules}
              </p>
            </details>
          ) : (
            <EmptyState title="no rules captured" />
          )}
        </Card>
      </div>
    </div>
  );
}
