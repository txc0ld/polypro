"use client";

/**
 * Inline sparkline. Pure SVG (no recharts) so it renders cheaply in long
 * tables. We accept an array of numbers and a colour; the line is normalised
 * to its own min/max. A trailing dot marks the latest point.
 */
export function Sparkline({
  values,
  width = 80,
  height = 20,
  stroke = "#a1a1aa",
  fill = "none",
}: {
  values: number[];
  width?: number;
  height?: number;
  stroke?: string;
  fill?: string;
}) {
  if (!values || values.length < 2) {
    return (
      <svg width={width} height={height} aria-hidden>
        <line
          x1={0}
          x2={width}
          y1={height / 2}
          y2={height / 2}
          stroke="#1f1f23"
        />
      </svg>
    );
  }
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const stepX = width / (values.length - 1);
  const points = values
    .map(
      (v, i) =>
        `${(i * stepX).toFixed(2)},${(
          height - ((v - min) / range) * height
        ).toFixed(2)}`,
    )
    .join(" ");
  const last = values[values.length - 1];
  const lastY = height - ((last - min) / range) * height;
  return (
    <svg width={width} height={height} aria-hidden>
      <polyline
        points={points}
        fill={fill}
        stroke={stroke}
        strokeWidth={1.25}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <circle cx={width} cy={lastY} r={1.75} fill={stroke} />
    </svg>
  );
}
