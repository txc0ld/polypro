import "server-only";
import fs from "node:fs";
import { policyPath } from "./paths";

export type Policy = {
  mode: string;
  bankrollUsdc: number | null;
  raw: Record<string, unknown>;
};

/**
 * Tiny, deliberately limited YAML reader that handles the shape of
 * configs/policy.yaml: top-level keys, nested 2-space maps, and `- item`
 * lists. Scalars are parsed as numbers when possible, else strings.
 * Avoiding a YAML dep keeps the dashboard's footprint minimal.
 */
function parsePolicy(text: string): Record<string, unknown> {
  const root: Record<string, unknown> = {};
  const stack: { indent: number; container: Record<string, unknown> | unknown[] }[] = [
    { indent: -1, container: root },
  ];
  const lines = text.split(/\r?\n/);
  for (const raw of lines) {
    const line = raw.replace(/#.*$/, "").replace(/\s+$/, "");
    if (!line.trim()) continue;
    const indent = line.length - line.replace(/^\s+/, "").length;
    while (stack.length > 1 && indent <= stack[stack.length - 1].indent) stack.pop();
    const top = stack[stack.length - 1].container;
    const body = line.slice(indent);

    if (body.startsWith("- ")) {
      if (!Array.isArray(top)) continue;
      top.push(parseScalar(body.slice(2).trim()));
      continue;
    }
    const m = /^([A-Za-z0-9_]+):\s*(.*)$/.exec(body);
    if (!m) continue;
    const [, key, rest] = m;
    if (rest === "") {
      const child: Record<string, unknown> = {};
      (top as Record<string, unknown>)[key] = child;
      stack.push({ indent, container: child });
    } else if (rest === "[]") {
      (top as Record<string, unknown>)[key] = [];
    } else {
      (top as Record<string, unknown>)[key] = parseScalar(rest.trim());
    }
  }
  return root;
}

function parseScalar(s: string): unknown {
  if (s === "true") return true;
  if (s === "false") return false;
  if (s === "null" || s === "~") return null;
  if (/^-?\d+(\.\d+)?$/.test(s)) return Number(s);
  if ((s.startsWith("'") && s.endsWith("'")) || (s.startsWith('"') && s.endsWith('"'))) {
    return s.slice(1, -1);
  }
  return s;
}

export function readPolicy(): Policy {
  if (!fs.existsSync(policyPath)) {
    return { mode: "unknown", bankrollUsdc: null, raw: {} };
  }
  const text = fs.readFileSync(policyPath, "utf8");
  const raw = parsePolicy(text);
  const risk = (raw["risk"] as Record<string, unknown> | undefined) ?? {};
  return {
    mode: typeof raw["mode"] === "string" ? (raw["mode"] as string) : "unknown",
    bankrollUsdc: typeof risk["bankroll_usdc"] === "number" ? (risk["bankroll_usdc"] as number) : null,
    raw,
  };
}
