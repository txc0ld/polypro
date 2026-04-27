"use client";

import {
  CartesianGrid,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";

export type CalibrationPoint = {
  bucket: number;
  meanPredicted: number;
  empirical: number;
  n: number;
};

/**
 * Reliability diagram: predicted probability (x) vs empirical realized rate (y).
 * Perfect calibration sits on y = x. Bubble size encodes sample count.
 */
export function CalibrationDiagram({ data }: { data: CalibrationPoint[] }) {
  if (data.length === 0) {
    return (
      <p className="text-sm text-muted">
        No calibration observations recorded yet.
      </p>
    );
  }
  const totalN = data.reduce((a, b) => a + b.n, 0);
  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 10, right: 16, bottom: 10, left: 0 }}>
          <CartesianGrid stroke="#1f262e" strokeDasharray="3 3" />
          <XAxis
            type="number"
            dataKey="meanPredicted"
            name="predicted"
            domain={[0, 1]}
            stroke="#8a95a4"
            tick={{ fontSize: 10 }}
            tickFormatter={(v: number) => v.toFixed(1)}
            label={{
              value: "predicted",
              position: "insideBottom",
              offset: -2,
              fill: "#8a95a4",
              fontSize: 11,
            }}
          />
          <YAxis
            type="number"
            dataKey="empirical"
            name="empirical"
            domain={[0, 1]}
            stroke="#8a95a4"
            tick={{ fontSize: 10 }}
            tickFormatter={(v: number) => v.toFixed(1)}
            label={{
              value: "empirical",
              angle: -90,
              position: "insideLeft",
              fill: "#8a95a4",
              fontSize: 11,
            }}
          />
          <ZAxis
            type="number"
            dataKey="n"
            range={[40, 400]}
            name="n"
            domain={[1, Math.max(1, totalN)]}
          />
          <Tooltip
            contentStyle={{
              background: "#13171c",
              border: "1px solid #1f262e",
              fontSize: 12,
            }}
            formatter={(v: number, name: string) =>
              name === "n" ? `${v}` : (v as number).toFixed(3)
            }
          />
          <ReferenceLine
            segment={[
              { x: 0, y: 0 },
              { x: 1, y: 1 },
            ]}
            stroke="#8a95a4"
            strokeDasharray="3 3"
            ifOverflow="extendDomain"
          />
          <Scatter data={data} fill="#6ee7b7" />
          <Line
            data={data}
            dataKey="empirical"
            stroke="#6ee7b7"
            dot={false}
            type="linear"
          />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}
