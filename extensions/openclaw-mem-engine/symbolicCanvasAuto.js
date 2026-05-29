import { execFile as execFileCb } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

const execFile = promisify(execFileCb);

const DEFAULT_COMMAND = "openclaw-mem";
const DEFAULT_TIMEOUT_MS = 2500;
const MAX_TIMEOUT_MS = 15000;
const DEFAULT_MAX_BUFFER_BYTES = 512 * 1024;
const MAX_BUFFER_BYTES = 2 * 1024 * 1024;
const DEFAULT_MAX_NODES = 8;
const DEFAULT_MAX_LABEL_CHARS = 120;
const DEFAULT_MIN_MESSAGES = 4;
const DEFAULT_OUTPUT_DIR = "memory/symbolic-canvas-auto";
const DEFAULT_TRIGGER_MODE = "qualified";
const VALID_TRIGGER_MODES = new Set(["qualified", "always"]);
const DEFAULT_TRIGGER_PATTERNS = [
  "handoff",
  "closeout",
  "closure",
  "checkpoint",
  "receipt",
  "verifier",
  "subagent",
  "inter-session message",
  "queued announce",
  "工程規格",
  "刀舞",
  "non-stop",
  "交接",
  "收尾",
  "驗證",
  "完成",
  "實作",
  "測試",
];

function clampNumber(raw, fallback, { min, max, integer = true } = {}) {
  const parsed = typeof raw === "number" ? raw : Number(raw);
  if (!Number.isFinite(parsed)) return fallback;
  const n = integer ? Math.floor(parsed) : parsed;
  return Math.max(min, Math.min(max, n));
}

function toStringArray(raw, fallback = []) {
  if (!Array.isArray(raw)) return [...fallback];
  return raw.map((item) => (typeof item === "string" ? item.trim() : "")).filter(Boolean).slice(0, 64);
}

function normalizeTriggerMode(raw) {
  const text = String(raw || DEFAULT_TRIGGER_MODE).trim().toLowerCase();
  return VALID_TRIGGER_MODES.has(text) ? text : DEFAULT_TRIGGER_MODE;
}

function compactText(raw, maxChars = DEFAULT_MAX_LABEL_CHARS) {
  const text = String(raw || "").replace(/\s+/g, " ").trim();
  if (!text) return "";
  return text.length > maxChars ? `${text.slice(0, Math.max(1, maxChars - 1)).trimEnd()}…` : text;
}

function sanitizePathSegment(raw, fallback = "session") {
  const text = String(raw || "").trim();
  const cleaned = text.replace(/[^A-Za-z0-9._:-]+/g, "_").replace(/^_+|_+$/g, "");
  return (cleaned || fallback).slice(0, 96);
}

function resolveTilde(input) {
  const raw = String(input || "").trim();
  if (raw === "~") return os.homedir();
  if (raw.startsWith("~/")) return path.join(os.homedir(), raw.slice(2));
  return raw;
}

export function resolveSymbolicCanvasAutoConfig(config = {}) {
  return {
    enabled: Boolean(config?.enabled),
    command: String(config?.command || DEFAULT_COMMAND).trim() || DEFAULT_COMMAND,
    commandArgs: toStringArray(config?.commandArgs),
    outputDir: String(config?.outputDir || DEFAULT_OUTPUT_DIR).trim() || DEFAULT_OUTPUT_DIR,
    baseDir: typeof config?.baseDir === "string" && config.baseDir.trim() ? config.baseDir.trim() : undefined,
    timeoutMs: clampNumber(config?.timeoutMs, DEFAULT_TIMEOUT_MS, { min: 200, max: MAX_TIMEOUT_MS }),
    maxBufferBytes: clampNumber(config?.maxBufferBytes, DEFAULT_MAX_BUFFER_BYTES, {
      min: 64 * 1024,
      max: MAX_BUFFER_BYTES,
    }),
    maxNodes: clampNumber(config?.maxNodes, DEFAULT_MAX_NODES, { min: 2, max: 24 }),
    maxLabelChars: clampNumber(config?.maxLabelChars, DEFAULT_MAX_LABEL_CHARS, { min: 40, max: 300 }),
    minMessages: clampNumber(config?.minMessages, DEFAULT_MIN_MESSAGES, { min: 1, max: 64 }),
    triggerMode: normalizeTriggerMode(config?.triggerMode),
    triggerPatterns: toStringArray(config?.triggerPatterns, DEFAULT_TRIGGER_PATTERNS),
  };
}

function extractMessageText(message) {
  if (!message || typeof message !== "object") return "";
  const content = message.content;
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  const parts = [];
  for (const block of content) {
    if (block && typeof block === "object" && block.type === "text" && typeof block.text === "string") {
      parts.push(block.text);
    }
  }
  return parts.join("\n");
}

function eventTextForTrigger(event = {}, cfg = {}) {
  const messages = Array.isArray(event?.messages) ? event.messages : [];
  const parts = [];
  for (const message of messages.slice(-Math.max(cfg.maxNodes || DEFAULT_MAX_NODES, cfg.minMessages || DEFAULT_MIN_MESSAGES, 8))) {
    if (!message || typeof message !== "object") continue;
    const role = String(message.role || "unknown").toLowerCase();
    if (role !== "user" && role !== "assistant") continue;
    const text = extractMessageText(message);
    if (text) parts.push(text);
  }
  return parts.join("\n").toLowerCase();
}

export function shouldRunSymbolicCanvasAutoBuild(event = {}, ctx = {}, config = {}) {
  const cfg = resolveSymbolicCanvasAutoConfig(config);
  if (!cfg.enabled) return { ok: false, reason: "disabled" };
  if (event?.success === false) return { ok: false, reason: "agent_not_successful" };
  if (cfg.triggerMode === "always") return { ok: true, reason: "trigger_mode_always" };

  const text = eventTextForTrigger(event, cfg);
  const matchedPattern = cfg.triggerPatterns.find((pattern) => text.includes(String(pattern).toLowerCase()));
  if (matchedPattern) return { ok: true, reason: "qualified_pattern", matchedPattern };

  return { ok: false, reason: "not_qualified" };
}

export function buildTraceFromAgentEvent(event = {}, ctx = {}, config = {}) {
  const cfg = resolveSymbolicCanvasAutoConfig(config);
  const messages = Array.isArray(event?.messages) ? event.messages : [];
  const eligible = [];

  for (const message of messages) {
    if (!message || typeof message !== "object") continue;
    const role = String(message.role || "unknown").toLowerCase();
    if (role !== "user" && role !== "assistant") continue;
    const label = compactText(extractMessageText(message), cfg.maxLabelChars);
    if (!label) continue;
    eligible.push({ role, label });
  }

  const selected = eligible.slice(-cfg.maxNodes);
  const nodes = selected.map((item, idx) => {
    const index = idx + 1;
    return {
      id: `m${String(index).padStart(3, "0")}_${item.role}`,
      label: `${item.role}: ${item.label}`,
      state: "done",
      refs: [`artifact:openclaw-session-message:${index}:${item.role}`],
    };
  });

  const edges = [];
  for (let i = 0; i < nodes.length - 1; i += 1) {
    edges.push([nodes[i].id, nodes[i + 1].id, "next"]);
  }

  const rawTaskId = event?.taskId || event?.task_id || ctx?.sessionKey || ctx?.sessionId || event?.sessionId || "session";
  return {
    task_id: `auto-${sanitizePathSegment(rawTaskId)}`,
    nodes,
    edges,
    meta: {
      source: "openclaw-mem-engine.symbolicCanvas.autoBuild",
      sessionKey: ctx?.sessionKey || null,
      sessionId: ctx?.sessionId || event?.sessionId || null,
      agentId: ctx?.agentId || null,
      totalMessages: messages.length,
      eligibleMessages: eligible.length,
      selectedMessages: selected.length,
      triggerMode: cfg.triggerMode,
    },
  };
}

async function defaultRunner({ command, args, input, timeoutMs, maxBufferBytes }) {
  try {
    const { stdout, stderr } = await execFile(command, args, {
      input,
      timeout: timeoutMs,
      maxBuffer: maxBufferBytes,
    });
    return { ok: true, exitCode: 0, stdout: String(stdout || ""), stderr: String(stderr || "") };
  } catch (err) {
    return {
      ok: false,
      exitCode: typeof err?.code === "number" ? err.code : null,
      stdout: String(err?.stdout || ""),
      stderr: String(err?.stderr || ""),
      errorCode: typeof err?.code === "string" ? err.code : null,
      errorMessage: String(err?.message || err),
      timedOut: err?.killed === true || String(err?.message || "").includes("timed out"),
    };
  }
}

function parseJsonLoose(raw) {
  const text = String(raw || "").trim();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {}
  const first = text.indexOf("{");
  const last = text.lastIndexOf("}");
  if (first >= 0 && last > first) {
    try {
      return JSON.parse(text.slice(first, last + 1));
    } catch {}
  }
  return null;
}

function openclawMemProjectRoot() {
  return path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
}

function fallbackCommandForOpenclawMem(args) {
  return {
    command: "uv",
    args: [
      "run",
      "--project",
      openclawMemProjectRoot(),
      "--python",
      "3.13",
      "--frozen",
      "python",
      "-m",
      "openclaw_mem",
      ...args,
    ],
  };
}

function isMissingCommandResult(proc) {
  return proc?.errorCode === "ENOENT";
}

function summarizeAttempt({ label, command, args, proc, elapsedMs }) {
  return {
    label,
    command,
    args,
    ok: Boolean(proc?.ok),
    exitCode: proc?.exitCode ?? null,
    errorCode: proc?.errorCode ?? null,
    errorMessage: proc?.errorMessage ? String(proc.errorMessage).slice(0, 300) : null,
    timedOut: Boolean(proc?.timedOut),
    elapsedMs,
  };
}

async function runSymbolicCanvasCommand({ cfg, args, input, runner }) {
  const attempts = [];
  const primary = {
    label: "configured",
    command: cfg.command,
    args,
  };
  const startedPrimary = Date.now();
  let proc = await runner({
    command: primary.command,
    args: primary.args,
    input,
    timeoutMs: cfg.timeoutMs,
    maxBufferBytes: cfg.maxBufferBytes,
  });
  attempts.push(summarizeAttempt({ ...primary, proc, elapsedMs: Date.now() - startedPrimary }));

  if (cfg.command !== DEFAULT_COMMAND || !isMissingCommandResult(proc)) {
    return {
      proc,
      command: primary.command,
      args: primary.args,
      fallbackUsed: false,
      fallbackAvailable: cfg.command === DEFAULT_COMMAND,
      attempts,
    };
  }

  const fallback = {
    label: "uv-project-module-fallback",
    ...fallbackCommandForOpenclawMem(args),
  };
  const startedFallback = Date.now();
  proc = await runner({
    command: fallback.command,
    args: fallback.args,
    input,
    timeoutMs: cfg.timeoutMs,
    maxBufferBytes: cfg.maxBufferBytes,
  });
  attempts.push(summarizeAttempt({ ...fallback, proc, elapsedMs: Date.now() - startedFallback }));

  return {
    proc,
    command: fallback.command,
    args: fallback.args,
    fallbackUsed: true,
    fallbackAvailable: true,
    attempts,
  };
}

export async function runSymbolicCanvasAutoBuild({ event = {}, ctx = {}, config = {}, stateDir, runner = defaultRunner } = {}) {
  const cfg = resolveSymbolicCanvasAutoConfig(config);
  const started = Date.now();

  const trigger = shouldRunSymbolicCanvasAutoBuild(event, ctx, cfg);
  if (!trigger.ok) {
    return { ok: true, skipped: true, skipReason: trigger.reason, elapsedMs: Date.now() - started };
  }

  const trace = buildTraceFromAgentEvent(event, ctx, cfg);
  if (trace.nodes.length < cfg.minMessages) {
    return {
      ok: true,
      skipped: true,
      skipReason: "too_few_messages",
      nodeCount: trace.nodes.length,
      minMessages: cfg.minMessages,
      elapsedMs: Date.now() - started,
    };
  }

  const root = stateDir ? path.resolve(stateDir) : process.cwd();
  const outDirRaw = resolveTilde(cfg.outputDir);
  const outDir = path.isAbsolute(outDirRaw) ? outDirRaw : path.resolve(root, outDirRaw);
  const runId = `${new Date().toISOString().replace(/[:.]/g, "-")}-${sanitizePathSegment(trace.task_id, "task")}`;
  const runDir = path.join(outDir, runId);
  fs.mkdirSync(runDir, { recursive: true });

  const traceOut = path.join(runDir, "trace.json");
  const jsonOut = path.join(runDir, "canvas.json");
  const mermaidOut = path.join(runDir, "canvas.mmd");
  fs.writeFileSync(traceOut, `${JSON.stringify(trace, null, 2)}\n`, "utf8");
  const args = [
    ...cfg.commandArgs,
    "symbolic-canvas",
    "build",
    "--from-file",
    traceOut,
    "--json",
    "--out",
    jsonOut,
    "--mermaid-out",
    mermaidOut,
  ];
  if (cfg.baseDir) args.push("--base-dir", cfg.baseDir);

  const commandResult = await runSymbolicCanvasCommand({
    cfg,
    args,
    input: JSON.stringify(trace),
    runner,
  });
  const proc = commandResult.proc;
  const payload = parseJsonLoose(proc.stdout);
  const ok = Boolean(proc.ok && payload?.ok !== false && fs.existsSync(jsonOut) && fs.existsSync(mermaidOut));

  return {
    ok,
    skipped: false,
    elapsedMs: Date.now() - started,
    configuredCommand: cfg.command,
    command: commandResult.command,
    args,
    configuredArgs: args,
    executedArgs: commandResult.args,
    fallbackUsed: commandResult.fallbackUsed,
    fallbackAvailable: commandResult.fallbackAvailable,
    attempts: commandResult.attempts,
    runDir,
    traceOut,
    jsonOut,
    mermaidOut,
    nodeCount: trace.nodes.length,
    edgeCount: trace.edges.length,
    payloadKind: payload?.kind || null,
    payloadOk: payload?.ok ?? null,
    exitCode: proc.exitCode ?? null,
    errorCode: proc.errorCode ?? null,
    errorMessage: ok ? null : String(proc.errorMessage || proc.stderr || "symbolic-canvas build failed").slice(0, 500),
  };
}
