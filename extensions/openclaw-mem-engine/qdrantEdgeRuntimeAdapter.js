import { spawn } from "node:child_process";

const DEFAULT_TIMEOUT_MS = 1500;

export function resolveQdrantEdgeRuntimeAdapterConfig(input = {}) {
  const raw = input && typeof input === "object" && !Array.isArray(input) ? input : {};
  const searchCommand = typeof raw.searchCommand === "string" && raw.searchCommand.trim() ? raw.searchCommand.trim() : "python3";
  const searchCommandArgs = Array.isArray(raw.searchCommandArgs)
    ? raw.searchCommandArgs.filter((item) => typeof item === "string")
    : [];
  const timeoutMs = typeof raw.timeoutMs === "number" && Number.isFinite(raw.timeoutMs)
    ? Math.max(100, Math.min(30000, Math.floor(raw.timeoutMs)))
    : DEFAULT_TIMEOUT_MS;
  return { searchCommand, searchCommandArgs, timeoutMs };
}

function defaultRunner({ command, args, stdin, timeoutMs }) {
  return new Promise((resolve) => {
    const child = spawn(command, args, { stdio: ["pipe", "pipe", "pipe"] });
    let stdout = "";
    let stderr = "";
    let settled = false;
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      child.kill("SIGKILL");
      resolve({ ok: false, exitCode: null, stdout, stderr, errorCode: "timeout", errorMessage: `qdrant-edge search timed out after ${timeoutMs}ms` });
    }, timeoutMs);
    child.stdout.on("data", (chunk) => { stdout += chunk.toString("utf8"); });
    child.stderr.on("data", (chunk) => { stderr += chunk.toString("utf8"); });
    child.on("error", (err) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve({ ok: false, exitCode: null, stdout, stderr, errorCode: err.code || "spawn_error", errorMessage: err.message });
    });
    child.on("close", (code) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve({ ok: code === 0, exitCode: code, stdout, stderr, errorCode: code === 0 ? null : "nonzero_exit", errorMessage: code === 0 ? null : `qdrant-edge search exited ${code}` });
    });
    child.stdin.end(stdin);
  });
}

function normalizeHit(raw) {
  const row = raw && typeof raw === "object" ? raw.row || raw : {};
  const id = String(row.id ?? raw?.id ?? "");
  if (!id) return null;
  return {
    row: {
      id,
      text: String(row.text ?? raw?.text ?? ""),
      createdAt: Number(row.createdAt ?? 0),
      category: String(row.category ?? "other"),
      importance: typeof row.importance === "number" ? row.importance : null,
      importance_label: String(row.importance_label ?? ""),
      scope: String(row.scope ?? ""),
      trust_tier: String(row.trust_tier ?? ""),
    },
    distance: typeof raw.distance === "number" ? raw.distance : 0,
    score: typeof raw.score === "number" ? raw.score : 0,
  };
}

export async function runQdrantEdgeSearch({ config, request, runner = defaultRunner }) {
  const cfg = resolveQdrantEdgeRuntimeAdapterConfig(config);
  const payload = JSON.stringify({ schema: "openclaw-mem-engine.qdrant-edge.search.request.v1", ...request });
  const result = await runner({
    command: cfg.searchCommand,
    args: cfg.searchCommandArgs,
    stdin: payload,
    timeoutMs: cfg.timeoutMs,
  });

  if (!result.ok) {
    const err = new Error(result.errorMessage || "qdrant-edge search failed");
    err.code = result.errorCode || "qdrant_edge_search_failed";
    err.exitCode = result.exitCode ?? null;
    throw err;
  }

  let parsed;
  try {
    parsed = JSON.parse(result.stdout || "{}");
  } catch (cause) {
    const err = new Error("qdrant-edge search returned invalid JSON");
    err.code = "invalid_json";
    err.cause = cause;
    throw err;
  }
  if (parsed.ok === false) {
    const err = new Error(String(parsed.error || "qdrant-edge search failed"));
    err.code = String(parsed.errorCode || "qdrant_edge_search_failed");
    throw err;
  }
  const hits = Array.isArray(parsed.hits) ? parsed.hits.map(normalizeHit).filter(Boolean) : [];
  return hits;
}
