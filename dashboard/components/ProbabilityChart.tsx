"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
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
      <p className="text-sm text-muted">
        No probability estimates in the log yet.
      </p>
    );
  }
  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 10, right: 16, bottom: 10, left: 0 }}>
          <CartesianGrid stroke="#1f262e" strokeDasharray="3 3" />
          <XAxis
            dataKey="ts"
            stroke="#8a95a4"
            tick={{ fontSize: 10 }}
            tickFormatter={(v: string) =>
              new Date(v).toISOString().slice(11, 19)
            }
          />
          <YAxis
            stroke="#8a95a4"
            tick={{ fontSize: 10 }}
            domain={[0, 1]}
            tickFormatter={(v: number) => v.toFixed(1)}
          />
          <Tooltip
            contentStyle={{
              background: "#13171c",
              border: "1px solid #1f262e",
              fontSize: 12,
            }}
            labelFormatter={(v: string) => new Date(v).toISOString()}
          />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          <Line
            type="monotone"
            dataKey="modelProbability"
            name="model"
            stroke="#6ee7b7"
            dot={false}
            strokeWidth={2}
          />
          <Line
            type="monotone"
            dataKey="marketPrice"
            name="market"
            stroke="#fbbf24"
            dot={false}
            strokeWidth={2}
          />
          <Line
            type="monotone"
            dataKey="upper"
            name="+1σ"
            stroke="#6ee7b7"
            strokeOpacity={0.4}
            strokeDasharray="3 3"
            dot={false}
          />
          <Line
            type="monotone"
            dataKey="lower"
            name="−1σ"
            stroke="#6ee7b7"
            strokeOpacity={0.4}
            strokeDasharray="3 3"
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
