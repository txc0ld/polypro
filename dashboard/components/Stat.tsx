type Props = {
  label: string;
  value: string;
  hint?: string;
  tone?: "neutral" | "good" | "warn" | "bad";
};

const toneClass: Record<NonNullable<Props["tone"]>, string> = {
  neutral: "text-white",
  good: "text-good",
  warn: "text-warn",
  bad: "text-bad",
};

export default function Stat({ label, value, hint, tone = "neutral" }: Props) {
  return (
    <div className="panel">
      <div className="label">{label}</div>
      <div className={`stat ${toneClass[tone]}`}>{value}</div>
      {hint ? <div className="mt-1 text-xs text-muted">{hint}</div> : null}
    </div>
  );
}
