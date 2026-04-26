import path from "node:path";

const projectRoot = path.resolve(process.cwd(), "..");

export const dbPath = process.env.POLYFLOW_DB
  ? path.resolve(process.env.POLYFLOW_DB)
  : path.join(projectRoot, "logs", "polyflow.db");

export const logPath = process.env.POLYFLOW_LOG
  ? path.resolve(process.env.POLYFLOW_LOG)
  : path.join(projectRoot, "logs", "immutable.jsonl");

export const heartbeatPath = process.env.POLYFLOW_HEARTBEAT
  ? path.resolve(process.env.POLYFLOW_HEARTBEAT)
  : path.join(projectRoot, "logs", "heartbeat.json");

export const policyPath = process.env.POLYFLOW_POLICY
  ? path.resolve(process.env.POLYFLOW_POLICY)
  : path.join(projectRoot, "configs", "policy.yaml");
