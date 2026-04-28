"use client";

import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export type ProbabilityPoint = {
  ts: string;
  modelProbability: number | null;
  marketPrice: number | null;
  upper: number | null;
  lower: number | null;
};

export function ProbabilityChart({ data }: { data: ProbabilityPoint[] }) {
  if (data.length === 0) {
    return (
      <div className="flex h-72 items-center justify-center rounded border border-border bg-panel text-xs text-subtle">
        no probability estimates yet
      </div>
    );
  }
  const enriched = data.map((p) => ({
    ...p,
    bandBase: p.lower ?? 0,
    bandRange:
      p.upper !== null && p.lower !== null ? p.upper - p.lower : 0,
  }));
  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart
          data={enriched}
          margin={{ top: 10, right: 16, bottom: 4, left: 0 }}
        >
          <CartesianGrid stroke="#1f1f23" strokeDasharray="2 4" />
          <XAxis
            dataKey="ts"
            stroke="#52525b"
            tick={{ fontSize: 10, fill: "#71717a" }}
            tickFormatter={(v: string) =>
              new Date(v).toISOString().slice(11, 16)
            }
          />
          <YAxis
            stroke="#52525b"
            tick={{ fontSize: 10, fill: "#71717a" }}
            domain={[0, 1]}
            tickFormatter={(v: number) => `${(v * 100).toFixed(0)}c`}
            width={40}
          />
          <Tooltip
            contentStyle={{
              background: "#0c0c0f",
              border: "1px solid #1f1f23",
              fontSize: 11,
              borderRadius: 6,
              color: "#fafafa",
            }}
            labelFormatter={(v: string) =>
              new Date(v).toISOString().replace("T", " ").slice(0, 19)
            }
            formatter={(value: number, name: string) => [
              `${(value * 100).toFixed(1)}c`,
              name,
            ]}
          />
          <Legend
            wrapperStyle={{ fontSize: 10, paddingTop: 4, color: "#a1a1aa" }}
            iconType="line"
          />
          <Area
            type="monotone"
            dataKey="bandBase"
            stackId="band"
            stroke="none"
            fill="transparent"
            legendType="none"
            isAnimationActive={false}
          />
          <Area
            type="monotone"
            dataKey="bandRange"
            stackId="band"
            stroke="none"
            fill="#8b5cf6"
            fillOpacity={0.1}
            legendType="none"
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="modelProbability"
            name="model"
            stroke="#8b5cf6"
            dot={false}
            strokeWidth={1.75}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="marketPrice"
            name="market"
            stroke="#a1a1aa"
            dot={false}
            strokeWidth={1.5}
            strokeDasharray="4 3"
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
