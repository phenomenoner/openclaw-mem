import { execFile as execFileCb } from "node:child_process";
import { promisify } from "node:util";

const execFile = promisify(execFileCb);

const DEFAULT_COMMAND = "openclaw-mem";
const DEFAULT_TIMEOUT_MS = 1800;
const MAX_TIMEOUT_MS = 15000;
const DEFAULT_MAX_CHARS = 420;
const DEFAULT_MAX_GRAPH_CANDIDATES = 2;
const DEFAULT_MAX_TRANSCRIPT_SESSIONS = 2;

function parseJsonLoose(raw) {
  const text = String(raw || "").trim();
  if (!text) return null;

  try {
    return JSON.parse(text);
  } catch {
    // Continue.
  }

  const firstBrace = text.indexOf("{");
  const lastBrace = text.lastIndexOf("}");
  if (firstBrace >= 0 && lastBrace > firstBrace) {
    try {
      return JSON.parse(text.slice(firstBrace, lastBrace + 1));
    } catch {
      // Continue.
    }
  }

  return null;
}

function toStringArray(raw) {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item) => (typeof item === "string" ? item.trim() : ""))
    .filter(Boolean)
    .slice(0, 64);
}

function clampTimeout(raw) {
  const parsed = typeof raw === "number" ? raw : Number(raw);
  if (!Number.isFinite(parsed)) return DEFAULT_TIMEOUT_MS;
  return Math.max(200, Math.min(MAX_TIMEOUT_MS, Math.floor(parsed)));
}

function clampCount(raw, fallback, max = 5) {
  const parsed = typeof raw === "number" ? raw : Number(raw);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(1, Math.min(max, Math.floor(parsed)));
}

function clampChars(raw, fallback = DEFAULT_MAX_CHARS) {
  const parsed = typeof raw === "number" ? raw : Number(raw);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(120, Math.min(2400, Math.floor(parsed)));
}

function compactText(raw, maxChars = 160) {
  const text = String(raw || "").replace(/\s+/g, " ").trim();
  if (!text) return "";
  return text.length > maxChars ? `${text.slice(0, maxChars).trimEnd()}…` : text;
}

function compactSessionId(raw) {
  const text = String(raw || "").trim();
  if (!text) return "session";
  return text.length > 18 ? `${text.slice(0, 18)}…` : text;
}

async function defaultRunner({ command, args, timeoutMs }) {
  try {
    const { stdout, stderr } = await execFile(command, args, {
      timeout: timeoutMs,
      maxBuffer: 2 * 1024 * 1024,
    });
    return {
      ok: true,
      exitCode: 0,
      stdout: String(stdout || ""),
      stderr: String(stderr || ""),
      errorCode: null,
      errorMessage: null,
    };
  } catch (err) {
    return {
      ok: false,
      exitCode: typeof err?.code === "number" ? err.code : null,
      stdout: String(err?.stdout || ""),
      stderr: String(err?.stderr || ""),
      errorCode: typeof err?.code === "string" ? err.code : null,
      errorMessage: String(err?.message || err),
      timedOut: err?.killed === true || err?.signal === "SIGTERM" || String(err?.message || "").includes("timed out"),
      signal: typeof err?.signal === "string" ? err.signal : null,
      killed: Boolean(err?.killed),
    };
  }
}

function receiptBase(config) {
  const command = String(config?.command || DEFAULT_COMMAND).trim() || DEFAULT_COMMAND;
  const commandArgs = toStringArray(config?.commandArgs);
  const timeoutMs = clampTimeout(config?.timeoutMs);
  const dbPath = typeof config?.dbPath === "string" && config.dbPath.trim() ? config.dbPath.trim() : null;
  const maxChars = clampChars(config?.maxChars, DEFAULT_MAX_CHARS);
  const maxGraphCandidates = clampCount(config?.maxGraphCandidates, DEFAULT_MAX_GRAPH_CANDIDATES, 5);
  const maxTranscriptSessions = clampCount(config?.maxTranscriptSessions, DEFAULT_MAX_TRANSCRIPT_SESSIONS, 5);

  return {
    command,
    commandArgs,
    timeoutMs,
    dbPath,
    maxChars,
    maxGraphCandidates,
    maxTranscriptSessions,
  };
}

function buildArgs({ query, scope, base }) {
  const args = [...base.commandArgs];
  if (base.dbPath) args.push("--db", base.dbPath);
  args.push("--json", "route", "auto", String(query || "").trim());
  if (scope && scope !== "global") {
    args.push("--scope", scope);
  } else {
    args.push("--global");
  }
  args.push("--compact");
  return args;
}

function buildGraphConsumptionSuffix(candidate) {
  const consumption = candidate?.graph_consumption;
  const preferredRefs = toStringArray(consumption?.preferredCardRefs);
  const coveredRefs = toStringArray(consumption?.coveredRawRefs);
  const cards = Array.isArray(consumption?.cards) ? consumption.cards : [];
  if (preferredRefs.length === 0 || coveredRefs.length === 0) return "";

  const card = cards[0] || {};
  const cardLabel = compactText(card?.title || card?.recordRef || preferredRefs[0] || "synthesis card", 72);
  const why = compactText(card?.whyItMatters || "", 100);
  const coveredCount = coveredRefs.length;
  const coveredLabel = `${coveredCount} covered raw ref${coveredCount === 1 ? "" : "s"}`;
  return why
    ? `prefer synthesis ${cardLabel} over ${coveredLabel} (${why})`
    : `prefer synthesis ${cardLabel} over ${coveredLabel}`;
}

function buildGraphText(payload, base) {
  const candidates = payload?.inputs?.graph_match?.result?.candidates;
  if (!Array.isArray(candidates) || candidates.length === 0) return "";

  const lines = [
    `route-hint: graph-semantic (${compactText(payload?.selection?.reason || "graph_ready_with_candidates", 80)})`,
  ];

  for (const candidate of candidates.slice(0, base.maxGraphCandidates)) {
    const title = compactText(candidate?.title || candidate?.candidateRef || "candidate", 72);
    const why = compactText(candidate?.why_relevant || candidate?.explanation_path || "matched graph evidence", 140);
    const consumptionSuffix = buildGraphConsumptionSuffix(candidate);
    lines.push(`- ${title}: ${why}${consumptionSuffix ? ` | ${consumptionSuffix}` : ""}`);
  }

  return lines.join("\n");
}

function buildTranscriptText(payload, base) {
  const sessions = payload?.inputs?.episodes_search?.result?.sessions;
  if (!Array.isArray(sessions) || sessions.length === 0) return "";

  const lines = [
    `route-hint: transcript recall (${compactText(payload?.selection?.reason || "episodes_search", 80)})`,
  ];

  for (const session of sessions.slice(0, base.maxTranscriptSessions)) {
    const sid = compactSessionId(session?.session_id);
    const summary = compactText(session?.summary || session?.matched_items?.[0]?.match?.snippet || "matched prior session", 140);
    lines.push(`- ${sid}: ${summary}`);
  }

  return lines.join("\n");
}

export function renderRouteAutoText(payload, config = {}) {
  const base = receiptBase(config);
  const lane = String(payload?.selection?.selected_lane || "none").trim();

  let text = "";
  if (lane === "graph_match") {
    text = buildGraphText(payload, base);
  } else if (lane === "episodes_search") {
    text = buildTranscriptText(payload, base);
  }

  const compact = compactText(text, base.maxChars);
  return compact || "";
}

export async function runRouteAuto({ query, scope, config, runner = defaultRunner }) {
  const started = Date.now();
  const base = receiptBase(config);
  const enabled = Boolean(config?.enabled);
  const trimmedQuery = String(query || "").trim();

  if (!enabled) {
    return {
      text: "",
      payload: null,
      receipt: {
        enabled: false,
        attempted: false,
        selectedLane: null,
        graphCandidates: 0,
        transcriptSessions: 0,
        injected: false,
        latencyMs: Date.now() - started,
      },
    };
  }

  if (!trimmedQuery) {
    return {
      text: "",
      payload: null,
      receipt: {
        enabled: true,
        attempted: false,
        selectedLane: null,
        graphCandidates: 0,
        transcriptSessions: 0,
        injected: false,
        skipReason: "no_query",
        latencyMs: Date.now() - started,
      },
    };
  }

  const result = await runner({
    command: base.command,
    args: buildArgs({ query: trimmedQuery, scope, base }),
    timeoutMs: base.timeoutMs,
  });

  const payload = parseJsonLoose(result.stdout) ?? parseJsonLoose(result.stderr);
  const selectedLane = String(payload?.selection?.selected_lane || "none").trim() || "none";
  const graphCandidates = Array.isArray(payload?.inputs?.graph_match?.result?.candidates)
    ? payload.inputs.graph_match.result.candidates.length
    : 0;
  const transcriptSessions = Array.isArray(payload?.inputs?.episodes_search?.result?.sessions)
    ? payload.inputs.episodes_search.result.sessions.length
    : 0;
  const preferredCardRefs = toStringArray(payload?.selection?.graph_consumption?.preferredCardRefs);
  const coveredRawRefs = toStringArray(payload?.selection?.graph_consumption?.coveredRawRefs);
  const text = payload ? renderRouteAutoText(payload, base) : "";

  return {
    text,
    payload,
    receipt: {
      enabled: true,
      attempted: true,
      ok: Boolean(result.ok && payload),
      selectedLane,
      graphCandidates,
      transcriptSessions,
      preferredCardRefs,
      coveredRawRefs,
      preferredCardCount: preferredCardRefs.length,
      coveredRawRefCount: coveredRawRefs.length,
      injected: Boolean(text),
      reason: payload?.selection?.reason ? compactText(payload.selection.reason, 120) : null,
      errorCode: result.errorCode,
      errorMessage: result.ok ? null : compactText(result.errorMessage, 180),
      timeoutHit: Boolean(result.timedOut),
      signal: result.signal || null,
      killed: Boolean(result.killed),
      latencyMs: Date.now() - started,
      timeoutMs: base.timeoutMs,
      command: base.command,
    },
  };
}
