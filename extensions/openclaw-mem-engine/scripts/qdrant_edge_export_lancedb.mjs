#!/usr/bin/env node
import os from "node:os";
import * as lancedb from "@lancedb/lancedb";

function expandHome(path) {
  return String(path).startsWith("~/") ? `${os.homedir()}${String(path).slice(1)}` : String(path);
}

function usage() {
  console.error("Usage: qdrant_edge_export_lancedb.mjs --db <path> --table <name> [--limit N] [--created-after MS]");
}

const args = process.argv.slice(2);
let dbPath = "~/.openclaw/memory/lancedb";
let tableName = "memories_engine";
let limit = 100000;
let createdAfter = null;
for (let i = 0; i < args.length; i += 1) {
  const a = args[i];
  if (a === "--db") dbPath = args[++i];
  else if (a === "--table") tableName = args[++i];
  else if (a === "--limit") limit = Number(args[++i]);
  else if (a === "--created-after") createdAfter = Number(args[++i]);
  else if (a === "--help") { usage(); process.exit(0); }
  else { console.error(`Unknown arg: ${a}`); usage(); process.exit(2); }
}

const conn = await lancedb.connect(expandHome(dbPath));
const table = await conn.openTable(tableName);
let query = table.query();
if (typeof createdAfter === "number" && Number.isFinite(createdAfter)) {
  query = query.where(`createdAt > ${Math.floor(createdAfter)}`);
}
const rows = await query.limit(Math.max(1, Math.min(1000000, Math.floor(limit)))).toArray();
for (const r of rows) {
  if (!r || r.id === "__schema__") continue;
  const vector = Array.isArray(r.vector) ? r.vector : Array.from(r.vector ?? []);
  process.stdout.write(JSON.stringify({
    id: String(r.id ?? ""),
    text: String(r.text ?? ""),
    vector,
    createdAt: Number(r.createdAt ?? 0),
    category: String(r.category ?? "other"),
    importance: typeof r.importance === "number" ? r.importance : null,
    importance_label: String(r.importance_label ?? ""),
    scope: String(r.scope ?? ""),
    trust_tier: String(r.trust_tier ?? ""),
  }) + "\n");
}
