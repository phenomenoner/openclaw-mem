import type { OpenClawPluginApi } from "openclaw/plugin-sdk";
import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";

const DEFAULT_OUTPUT = "memory/openclaw-mem-observations.jsonl";
const DEFAULT_EPISODIC_OUTPUT = "memory/openclaw-mem-episodes.jsonl";
const DEFAULT_EPISODIC_SCOPE = "global";
const MAX_MESSAGE_LENGTH = 1000; // Truncate large messages to prevent bloat
const DEFAULT_EPISODIC_SUMMARY_LENGTH = 220;
const DEFAULT_EPISODIC_PAYLOAD_BYTES = 2048;
const DEFAULT_EPISODIC_REFS_BYTES = 1024;
const DEFAULT_MEMORY_TOOLS = [
  "memory_search",
  "memory_get",
  "memory_store",
  "memory_recall",
  "memory_forget",
];

type BackendMode = "auto" | "memory-core" | "memory-lancedb";

type EpisodicConfig = {
  enabled?: boolean;
  outputPath?: string;
  scope?: string;
  captureToolCall?: boolean;
  captureToolResult?: boolean;
  captureOpsAlert?: boolean;
  payloadCapBytes?: number;
  refsCapBytes?: number;
  maxSummaryLength?: number;
};

type PluginConfig = {
  enabled?: boolean;
  outputPath?: string;
  includeTools?: string[];
  excludeTools?: string[];
  captureMessage?: boolean; // Default: false (message can be huge)
  maxMessageLength?: number;
  redactSensitive?: boolean; // Default: true
  // v0.5.9 adapter fields
  backendMode?: BackendMode;
  annotateMemoryTools?: boolean;
  memoryToolNames?: string[];
  // episodic auto mode (v0)
  episodes?: EpisodicConfig;
};

type EpisodicEventLine = {
  schema: "openclaw-mem.episodes.spool.v0";
  event_id: string;
  ts_ms: number;
  scope: string;
  session_id: string;
  agent_id: string;
  type: "tool.call" | "tool.result" | "ops.alert";
  summary: string;
  payload?: unknown;
  refs?: unknown;
};

function shouldCapture(toolName: string | undefined, cfg: PluginConfig): boolean {
  if (!cfg.enabled) return false;
  if (!toolName) return false;
  const include = cfg.includeTools;
  const exclude = cfg.excludeTools;
  if (Array.isArray(include) && include.length > 0) {
    return include.includes(toolName);
  }
  if (Array.isArray(exclude) && exclude.length > 0) {
    return !exclude.includes(toolName);
  }
  return true;
}

function redactSensitiveText(text: string): string {
  if (!text) return text;

  // Best-effort redaction (avoid persisting obvious secrets). This is intentionally conservative.
  const patterns: Array<[RegExp, string]> = [
    [/\bsk-[A-Za-z0-9]{16,}\b/g, "sk-[REDACTED]"],
    [/\bsk-proj-[A-Za-z0-9\-_]{16,}\b/g, "sk-proj-[REDACTED]"],
    [/\bBearer\s+[A-Za-z0-9\-_.=]{8,}\b/g, "Bearer [REDACTED]"],
    [/\bAuthorization:\s*Bearer\s+[A-Za-z0-9\-_.=]{8,}\b/gi, "Authorization: Bearer [REDACTED]"],
    [/\b\d{8,12}:[A-Za-z0-9_-]{20,}\b/g, "[TELEGRAM_BOT_TOKEN_REDACTED]"],
  ];

  let out = text;
  for (const [re, rep] of patterns) out = out.replace(re, rep);
  return out;
}

function extractSummary(message: any, redactSensitive: boolean): string {
  // Extract a compact summary from the message content
  if (!message || !message.content) return "";

  try {
    const content = Array.isArray(message.content) ? message.content : [message.content];
    const textParts = content
      .filter((c: any) => c.type === "text")
      .map((c: any) => c.text || "")
      .join(" ");

    const summary = textParts.slice(0, 200).trim();
    return redactSensitive ? redactSensitiveText(summary) : summary;
  } catch {
    return "";
  }
}

function truncateMessage(message: any, maxLength: number, redactSensitive: boolean): any {
  if (!message || !message.content) return message;

  try {
    const content = Array.isArray(message.content) ? message.content : [message.content];
    const truncated = content.map((c: any) => {
      if (c.type === "text" && typeof c.text === "string") {
        let text = c.text;
        if (text.length > maxLength) {
          text = text.slice(0, maxLength) + "... [truncated]";
        }
        if (redactSensitive) {
          text = redactSensitiveText(text);
        }
        return { ...c, text };
      }
      return c;
    });

    return { ...message, content: truncated };
  } catch {
    return message;
  }
}

function resolveBackendMode(input: unknown): BackendMode {
  if (input === "memory-core" || input === "memory-lancedb" || input === "auto") {
    return input;
  }
  return "auto";
}

function resolveMemoryBackend(api: OpenClawPluginApi, mode: BackendMode): string {
  if (mode !== "auto") {
    return mode;
  }

  const slot = (api.config as any)?.plugins?.slots?.memory;
  if (typeof slot === "string" && slot.trim()) {
    return slot;
  }
  return "unknown";
}

function isMemoryBackendReady(api: OpenClawPluginApi, backend: string): boolean {
  if (!backend || backend === "unknown") {
    return false;
  }
  const entry = (api.config as any)?.plugins?.entries?.[backend];
  if (!entry || typeof entry !== "object") {
    return false;
  }
  return (entry as any).enabled !== false;
}

function classifyMemoryOperation(toolName: string): string | undefined {
  switch (toolName) {
    case "memory_store":
      return "store";
    case "memory_recall":
      return "recall";
    case "memory_forget":
      return "forget";
    case "memory_search":
      return "search";
    case "memory_get":
      return "get";
    default:
      return undefined;
  }
}

function normalizedMemoryToolSet(cfg: PluginConfig): Set<string> {
  const src = Array.isArray(cfg.memoryToolNames) && cfg.memoryToolNames.length > 0
    ? cfg.memoryToolNames
    : DEFAULT_MEMORY_TOOLS;
  return new Set(src.filter((x) => typeof x === "string" && x.trim()).map((x) => x.trim()));
}

function clampNumber(input: unknown, fallback: number, min: number, max: number): number {
  if (typeof input !== "number" || !Number.isFinite(input)) return fallback;
  return Math.max(min, Math.min(max, Math.floor(input)));
}

function normalizeScopeToken(input: unknown, fallback: string): string {
  const raw = typeof input === "string" ? input.trim().toLowerCase() : "";
  if (!raw) return fallback;
  const cleaned = raw
    .replace(/\s+/g, "-")
    .replace(/[^a-z0-9._:/-]+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^[-./:_]+/, "")
    .replace(/[-./:_]+$/, "");
  return cleaned || fallback;
}

function stableEventId(parts: Array<string | number | boolean | undefined | null>): string {
  const h = createHash("sha256");
  for (const part of parts) {
    h.update(String(part ?? ""));
    h.update("\x1f");
  }
  return `ep-${h.digest("hex").slice(0, 32)}`;
}

function appendJsonlLine(filePath: string, payload: unknown): void {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.appendFileSync(filePath, JSON.stringify(payload) + "\n", "utf-8");
}

function shortText(text: string, maxLength: number): string {
  if (!text) return "";
  return text.length <= maxLength ? text : `${text.slice(0, maxLength)}…`;
}

function looksLikeFailureSignal(summary: string): boolean {
  const s = (summary || "").toLowerCase();
  if (!s) return false;
  return /(error|failed|failure|exception|traceback|timeout|rate\s*limit|429|denied)/i.test(s);
}

function buildToolResultSummary(toolName: string, message: unknown, redactSensitive: boolean, maxLength: number): string {
  const raw = extractSummary(message, redactSensitive);
  const compact = raw.replace(/\s+/g, " ").trim();
  if (!compact) return `${toolName} result captured`;
  if (compact.startsWith("{") || compact.startsWith("[")) return `${toolName} result captured`;
  if (/(stdout|stderr|traceback|stack\s*trace|command output)/i.test(compact)) {
    return `${toolName} result captured (output redacted)`;
  }
  return shortText(`${toolName}: ${compact}`, maxLength);
}

function buildAgentEndAlertSummary(maxLength: number): string {
  return shortText("agent_end reported unsuccessful turn", maxLength);
}

function withBoundedJson(value: unknown, capBytes: number): unknown {
  if (value == null) return undefined;
  const raw = JSON.stringify(value);
  if (!raw) return undefined;
  const size = Buffer.byteLength(raw, "utf-8");
  if (size <= capBytes) return value;
  return {
    _truncated: true,
    reason: "cap_bytes",
    original_bytes: size,
    preview: raw.slice(0, Math.min(220, Math.max(40, Math.floor(capBytes / 2)))),
  };
}

const plugin = {
  id: "openclaw-mem",
  name: "OpenClaw Mem",
  description: "Capture tool results + optional episodic spool for openclaw-mem ingestion",
  kind: "utility",

  register(api: OpenClawPluginApi) {
    const cfg = (api.pluginConfig ?? {}) as PluginConfig;

    const stateDir = api.runtime.state.resolveStateDir();

    const resolveOutputPath = (input: string | undefined): string => {
      const raw = (input ?? DEFAULT_OUTPUT).trim();

      // Historical config default used "~/.openclaw/..." which can diverge from
      // the gateway's effective state dir (e.g., OPENCLAW_STATE_DIR override).
      // If the user specified ~/.openclaw explicitly, treat it as an alias for the
      // resolved stateDir.
      if (raw === "~/.openclaw" || raw.startsWith("~/.openclaw/") || raw.startsWith("~\\.openclaw\\")) {
        const suffix = raw.replace(/^~[\\/]\.openclaw[\\/]?/, "");
        return path.resolve(stateDir, suffix);
      }

      // If it's a relative path, resolve it under the OpenClaw state dir.
      if (!raw.startsWith("~") && !path.isAbsolute(raw)) {
        return path.resolve(stateDir, raw);
      }

      // Otherwise, fall back to standard user-path resolution.
      return api.resolvePath(raw);
    };

    const outputPath = resolveOutputPath(cfg.outputPath);
    const captureMessage = cfg.captureMessage ?? false;
    const maxMessageLength = cfg.maxMessageLength ?? MAX_MESSAGE_LENGTH;
    const redactSensitive = cfg.redactSensitive ?? true;
    const annotateMemoryTools = cfg.annotateMemoryTools ?? true;
    const backendMode = resolveBackendMode(cfg.backendMode);
    const memoryTools = normalizedMemoryToolSet(cfg);

    const resolvedMemoryBackend = resolveMemoryBackend(api, backendMode);
    const memoryBackendReady = isMemoryBackendReady(api, resolvedMemoryBackend);

    const episodesCfg = (cfg.episodes ?? {}) as EpisodicConfig;
    const episodesEnabled = episodesCfg.enabled ?? false;
    const episodesOutputPath = resolveOutputPath(episodesCfg.outputPath ?? DEFAULT_EPISODIC_OUTPUT);
    const episodesScope = normalizeScopeToken(episodesCfg.scope, DEFAULT_EPISODIC_SCOPE);
    const episodesCaptureToolCall = episodesCfg.captureToolCall ?? true;
    const episodesCaptureToolResult = episodesCfg.captureToolResult ?? true;
    const episodesCaptureOpsAlert = episodesCfg.captureOpsAlert ?? true;
    const episodesPayloadCapBytes = clampNumber(
      episodesCfg.payloadCapBytes,
      DEFAULT_EPISODIC_PAYLOAD_BYTES,
      256,
      64 * 1024,
    );
    const episodesRefsCapBytes = clampNumber(
      episodesCfg.refsCapBytes,
      DEFAULT_EPISODIC_REFS_BYTES,
      128,
      16 * 1024,
    );
    const episodesSummaryMaxLength = clampNumber(
      episodesCfg.maxSummaryLength,
      DEFAULT_EPISODIC_SUMMARY_LENGTH,
      48,
      400,
    );

    const appendEpisode = (episode: EpisodicEventLine) => {
      if (!episodesEnabled) return;

      const line: EpisodicEventLine = {
        ...episode,
        summary: shortText(redactSensitive ? redactSensitiveText(episode.summary) : episode.summary, episodesSummaryMaxLength),
        payload: withBoundedJson(episode.payload, episodesPayloadCapBytes),
        refs: withBoundedJson(episode.refs, episodesRefsCapBytes),
      };

      try {
        appendJsonlLine(episodesOutputPath, line);
      } catch (err) {
        api.logger.warn(`openclaw-mem: failed to write episodic spool JSONL: ${String(err)}`);
      }
    };

    api.on("tool_result_persist", (event, ctx) => {
      if (!shouldCapture(event.toolName ?? ctx.toolName, cfg)) return;

      const toolName = (event.toolName ?? ctx.toolName)!;
      const summary = extractSummary(event.message, redactSensitive);
      const isMemoryTool = memoryTools.has(toolName);
      const memoryOperation = classifyMemoryOperation(toolName);

      const obs: any = {
        ts: new Date().toISOString(),
        kind: "tool",
        tool_name: toolName,
        tool_call_id: event.toolCallId ?? ctx.toolCallId,
        session_key: ctx.sessionKey,
        agent_id: ctx.agentId,
        is_synthetic: event.isSynthetic ?? false,
        summary: summary || `${toolName} called`,
      };

      const detail: any = {};
      if (annotateMemoryTools) {
        detail.memory_backend = resolvedMemoryBackend;
        detail.memory_backend_ready = memoryBackendReady;
        detail.memory_backend_mode = backendMode;
        detail.memory_tool = isMemoryTool;
        if (isMemoryTool && memoryOperation) {
          detail.memory_operation = memoryOperation;
        }
      }

      // Optionally include full message (truncated)
      if (captureMessage && event.message) {
        const msg = truncateMessage(event.message, maxMessageLength, redactSensitive);
        obs.message = msg;
        detail.message = msg;
      }

      if (Object.keys(detail).length > 0) {
        obs.detail = detail;
      }

      try {
        appendJsonlLine(outputPath, obs);
      } catch (err) {
        api.logger.warn(`openclaw-mem: failed to write JSONL: ${String(err)}`);
      }

      if (episodesEnabled) {
        const tsMs = Date.now();
        const sessionId = String(ctx.sessionKey ?? "unknown");
        const agentId = String(ctx.agentId ?? "unknown");
        const toolCallId = String(event.toolCallId ?? ctx.toolCallId ?? "");

        const commonPayload = {
          tool_name: toolName,
          tool_call_id: toolCallId || undefined,
          is_synthetic: event.isSynthetic ?? false,
          memory_backend: annotateMemoryTools ? resolvedMemoryBackend : undefined,
          memory_backend_ready: annotateMemoryTools ? memoryBackendReady : undefined,
          memory_tool: annotateMemoryTools ? isMemoryTool : undefined,
          memory_operation: annotateMemoryTools ? memoryOperation : undefined,
        };
        const commonRefs = {
          tool_name: toolName,
          tool_call_id: toolCallId || undefined,
          source: "hook.persist",
        };

        if (episodesCaptureToolCall) {
          appendEpisode({
            schema: "openclaw-mem.episodes.spool.v0",
            event_id: stableEventId(["tool.call", episodesScope, sessionId, agentId, toolCallId || toolName, tsMs]),
            ts_ms: tsMs,
            scope: episodesScope,
            session_id: sessionId,
            agent_id: agentId,
            type: "tool.call",
            summary: shortText(`tool.call ${toolName}`, episodesSummaryMaxLength),
            payload: commonPayload,
            refs: commonRefs,
          });
        }

        const resultSummary = buildToolResultSummary(toolName, event.message, redactSensitive, episodesSummaryMaxLength);

        if (episodesCaptureToolResult) {
          appendEpisode({
            schema: "openclaw-mem.episodes.spool.v0",
            event_id: stableEventId(["tool.result", episodesScope, sessionId, agentId, toolCallId || toolName, tsMs]),
            ts_ms: tsMs,
            scope: episodesScope,
            session_id: sessionId,
            agent_id: agentId,
            type: "tool.result",
            summary: resultSummary,
            payload: {
              ...commonPayload,
              result_summary: shortText(resultSummary, Math.max(40, episodesSummaryMaxLength - 20)),
            },
            refs: commonRefs,
          });
        }

        if (episodesCaptureOpsAlert && looksLikeFailureSignal(resultSummary)) {
          appendEpisode({
            schema: "openclaw-mem.episodes.spool.v0",
            event_id: stableEventId(["ops.alert", episodesScope, sessionId, agentId, toolCallId || toolName, tsMs]),
            ts_ms: tsMs,
            scope: episodesScope,
            session_id: sessionId,
            agent_id: agentId,
            type: "ops.alert",
            summary: shortText(`ops.alert potential tool failure: ${toolName}`, episodesSummaryMaxLength),
            payload: {
              ...commonPayload,
              signal: "tool_failure_pattern",
            },
            refs: commonRefs,
          });
        }
      }

      // Do not modify the tool result; return undefined to keep it as-is.
      return;
    });

    if (episodesEnabled && episodesCaptureOpsAlert) {
      api.on("agent_end", (event: any) => {
        if (event?.success !== false) return;
        const tsMs = Number.isFinite(Date.parse(String(event?.timestamp ?? "")))
          ? Date.parse(String(event?.timestamp))
          : Date.now();
        const sessionId = String(event?.sessionKey ?? event?.session_id ?? "unknown");
        const agentId = String(event?.agentId ?? event?.agent_id ?? "unknown");
        appendEpisode({
          schema: "openclaw-mem.episodes.spool.v0",
          event_id: stableEventId(["ops.alert", episodesScope, sessionId, agentId, "agent_end", tsMs]),
          ts_ms: tsMs,
          scope: episodesScope,
          session_id: sessionId,
          agent_id: agentId,
          type: "ops.alert",
          summary: buildAgentEndAlertSummary(episodesSummaryMaxLength),
          payload: {
            event: "agent_end",
            success: false,
            reason: shortText(redactSensitiveText(String(event?.error ?? event?.reason ?? "unspecified")), 180),
          },
          refs: {
            source: "agent_end",
          },
        });
      });
    }

    api.logger.info(
      `openclaw-mem: capturing tool results to ${outputPath} (backend=${resolvedMemoryBackend}, ready=${memoryBackendReady})`,
    );

    if (episodesEnabled) {
      api.logger.info(
        `openclaw-mem: episodic auto-mode enabled (spool=${episodesOutputPath}, scope=${episodesScope}, call=${episodesCaptureToolCall}, result=${episodesCaptureToolResult}, alert=${episodesCaptureOpsAlert})`,
      );
    }
  },
};

export default plugin;
