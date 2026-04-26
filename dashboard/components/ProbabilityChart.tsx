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
  model?: number | null;
  market?: number | null;
  bandLow?: number | null;
  bandHigh?: number | null;
};

type Props = {
  data: ProbabilityPoint[];
};

export default function ProbabilityChart({ data }: Props) {
  const chartData = data.map((p) => ({
    ts: new Date(p.ts).getTime(),
    model: p.model ?? null,
    market: p.market ?? null,
    band:
      p.bandLow !== null && p.bandLow !== undefined && p.bandHigh !== null && p.bandHigh !== undefined
        ? [p.bandLow, p.bandHigh]
        : undefined,
  }));

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={chartData} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
          <CartesianGrid stroke="#1d242d" strokeDasharray="2 4" />
          <XAxis
            dataKey="ts"
            type="number"
            domain={["dataMin", "dataMax"]}
            tickFormatter={(t: number) => new Date(t).toISOString().slice(11, 19)}
            stroke="#7d8794"
            fontSize={11}
          />
          <YAxis
            domain={[0, 1]}
            tickFormatter={(v: number) => v.toFixed(2)}
            stroke="#7d8794"
            fontSize={11}
          />
          <Tooltip
            contentStyle={{ background: "#11151b", border: "1px solid #1d242d", fontSize: 12 }}
            labelFormatter={(t) => new Date(Number(t)).toISOString()}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Area
            type="monotone"
            dataKey="band"
            name="confidence band"
            fill="#3ddc97"
            fillOpacity={0.12}
            stroke="none"
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="model"
            name="model p"
            stroke="#3ddc97"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
            connectNulls
          />
          <Line
            type="monotone"
            dataKey="market"
            name="market price"
            stroke="#f5b14a"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
            connectNulls
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
