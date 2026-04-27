import path from "node:path";

const repoRoot = path.resolve(process.cwd(), "..");

export const dbPath = process.env.POLYFLOW_DB
  ? path.resolve(process.env.POLYFLOW_DB)
  : path.join(repoRoot, "logs", "polyflow.db");

export const logPath = process.env.POLYFLOW_LOG
  ? path.resolve(process.env.POLYFLOW_LOG)
  : path.join(repoRoot, "logs", "immutable.jsonl");

export const heartbeatPath = process.env.POLYFLOW_HEARTBEAT
  ? path.resolve(process.env.POLYFLOW_HEARTBEAT)
  : path.join(repoRoot, "logs", "heartbeat.json");

export const policyPath = process.env.POLYFLOW_POLICY
  ? path.resolve(process.env.POLYFLOW_POLICY)
  : path.join(repoRoot, "configs", "policy.yaml");
