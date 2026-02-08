import type { OpenClawPluginApi } from "openclaw/plugin-sdk";
import fs from "node:fs";
import path from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

const DEFAULT_OUTPUT = "~/.openclaw/memory/openclaw-mem-observations.jsonl";
const MAX_MESSAGE_LENGTH = 1000; // Truncate large messages to prevent bloat
const PROJECT_ROOT = path.resolve(__dirname, "../../..");

type PluginConfig = {
  enabled?: boolean;
  outputPath?: string;
  includeTools?: string[];
  excludeTools?: string[];
  captureMessage?: boolean; // Default: false (message can be huge)
  maxMessageLength?: number;
  redactSensitive?: boolean; // Default: true
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

async function runOpenClawMemCli(args: string[]): Promise<string> {
  const cmd = ["run", "--python", "3.13", "--", "python", "-m", "openclaw_mem", ...args];
  const { stdout } = await execFileAsync("uv", cmd, {
    cwd: PROJECT_ROOT,
  });
  return stdout.trim();
}

const plugin = {
  id: "openclaw-mem",
  name: "OpenClaw Mem",
  description: "Capture tool results into JSONL for openclaw-mem ingestion",
  kind: "utility",

  register(api: OpenClawPluginApi) {
    const cfg = (api.pluginConfig ?? {}) as PluginConfig;
    const outputPath = api.resolvePath(cfg.outputPath ?? DEFAULT_OUTPUT);
    const captureMessage = cfg.captureMessage ?? false;
    const maxMessageLength = cfg.maxMessageLength ?? MAX_MESSAGE_LENGTH;
    const redactSensitive = cfg.redactSensitive ?? true;

    // Official OpenClaw tool registration path (api.registerTool)
    api.registerTool(
      {
        name: "memory_store",
        description: "Store a memory into the openclaw-mem long-term knowledge base.",
        parameters: {
          type: "object",
          properties: {
            text: { type: "string", description: "The memory content to store" },
            text_en: { type: "string", description: "Optional English translation/summary" },
            lang: { type: "string", description: "Language code for original text (e.g., zh, ja, es)" },
            category: { type: "string", description: "Category (e.g., preference, fact, task)" },
            importance: { type: "number", description: "Importance (1-5), default 3" },
          },
          required: ["text"],
        },
        async execute(_toolCallId: string, rawParams: unknown) {
          const args = (rawParams ?? {}) as {
            text?: string;
            text_en?: string;
            lang?: string;
            category?: string;
            importance?: number;
          };

          if (!args.text) {
            return {
              isError: true,
              content: [{ type: "text", text: "Missing required parameter: text" }],
            };
          }

          try {
            const cmdArgs = ["store", args.text];
            if (args.text_en) cmdArgs.push("--text-en", args.text_en);
            if (args.lang) cmdArgs.push("--lang", args.lang);
            if (args.category) cmdArgs.push("--category", args.category);
            if (args.importance !== undefined) cmdArgs.push("--importance", String(args.importance));

            const out = await runOpenClawMemCli(cmdArgs);
            return { content: [{ type: "text", text: out || "Memory stored." }] };
          } catch (err: any) {
            return {
              isError: true,
              content: [
                {
                  type: "text",
                  text: `Failed to store memory: ${err?.message || String(err)}\n${err?.stderr || ""}`,
                },
              ],
            };
          }
        },
      },
      { name: "memory_store" },
    );

    api.registerTool(
      {
        name: "memory_recall",
        description: "Recall memories relevant to a query from openclaw-mem.",
        parameters: {
          type: "object",
          properties: {
            query: { type: "string", description: "Search query" },
            query_en: { type: "string", description: "Optional English query for additional vector route" },
            limit: { type: "number", description: "Max results (default 5)" },
          },
          required: ["query"],
        },
        async execute(_toolCallId: string, rawParams: unknown) {
          const args = (rawParams ?? {}) as { query?: string; query_en?: string; limit?: number };

          if (!args.query) {
            return {
              isError: true,
              content: [{ type: "text", text: "Missing required parameter: query" }],
            };
          }

          try {
            const cmdArgs = ["hybrid", args.query];
            if (args.query_en) cmdArgs.push("--query-en", args.query_en);
            if (args.limit !== undefined) cmdArgs.push("--limit", String(args.limit));

            const out = await runOpenClawMemCli(cmdArgs);
            return { content: [{ type: "text", text: out }] };
          } catch (err: any) {
            return {
              isError: true,
              content: [
                {
                  type: "text",
                  text: `Failed to recall memory: ${err?.message || String(err)}\n${err?.stderr || ""}`,
                },
              ],
            };
          }
        },
      },
      { name: "memory_recall" },
    );

    api.on("tool_result_persist", (event, ctx) => {
      if (!shouldCapture(event.toolName ?? ctx.toolName, cfg)) return;

      const toolName = event.toolName ?? ctx.toolName;
      const summary = extractSummary(event.message, redactSensitive);

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

      // Optionally include full message (truncated)
      if (captureMessage && event.message) {
        obs.message = truncateMessage(event.message, maxMessageLength, redactSensitive);
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

    api.logger.info(`openclaw-mem: capturing tool results to ${outputPath}`);
    api.logger.info("openclaw-mem: registered tools memory_store + memory_recall via api.registerTool");
  },
};

export default plugin;
