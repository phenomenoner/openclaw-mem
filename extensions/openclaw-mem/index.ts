import type { OpenClawPluginApi } from "openclaw/plugin-sdk";
import fs from "node:fs";
import path from "node:path";

const DEFAULT_OUTPUT = "memory/openclaw-mem-observations.jsonl";
const MAX_MESSAGE_LENGTH = 1000; // Truncate large messages to prevent bloat
const DEFAULT_MEMORY_TOOLS = [
  "memory_search",
  "memory_get",
  "memory_store",
  "memory_recall",
  "memory_forget",
];

type BackendMode = "auto" | "memory-core" | "memory-lancedb";

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

const plugin = {
  id: "openclaw-mem",
  name: "OpenClaw Mem",
  description: "Capture tool results into JSONL for openclaw-mem ingestion",
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
        fs.mkdirSync(path.dirname(outputPath), { recursive: true });
        fs.appendFileSync(outputPath, JSON.stringify(obs) + "\n", "utf-8");
      } catch (err) {
        api.logger.warn(`openclaw-mem: failed to write JSONL: ${String(err)}`);
      }

      // Do not modify the tool result; return undefined to keep it as-is.
      return;
    });

    api.logger.info(
      `openclaw-mem: capturing tool results to ${outputPath} (backend=${resolvedMemoryBackend}, ready=${memoryBackendReady})`,
    );
  },
};

export default plugin;
