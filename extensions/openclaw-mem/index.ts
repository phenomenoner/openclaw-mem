import type { OpenClawPluginApi } from "openclaw/plugin-sdk";
import fs from "node:fs";
import path from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

const DEFAULT_OUTPUT = "~/.openclaw/memory/openclaw-mem-observations.jsonl";
const MAX_MESSAGE_LENGTH = 1000; // Truncate large messages to prevent bloat

type PluginConfig = {
  enabled?: boolean;
  outputPath?: string;
  includeTools?: string[];
  excludeTools?: string[];
  captureMessage?: boolean; // Default: false (message can be huge)
  maxMessageLength?: number;
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

function extractSummary(message: any): string {
  // Extract a compact summary from the message content
  if (!message || !message.content) return "";
  
  try {
    const content = Array.isArray(message.content) ? message.content : [message.content];
    const textParts = content
      .filter((c: any) => c.type === "text")
      .map((c: any) => c.text || "")
      .join(" ");
    
    return textParts.slice(0, 200).trim();
  } catch {
    return "";
  }
}

function truncateMessage(message: any, maxLength: number): any {
  if (!message || !message.content) return message;
  
  try {
    const content = Array.isArray(message.content) ? message.content : [message.content];
    const truncated = content.map((c: any) => {
      if (c.type === "text" && c.text && c.text.length > maxLength) {
        return { ...c, text: c.text.slice(0, maxLength) + "... [truncated]" };
      }
      return c;
    });
    
    return { ...message, content: truncated };
  } catch {
    return message;
  }
}

const plugin = {
  id: "openclaw-mem",
  name: "OpenClaw Mem",
  description: "Capture tool results into JSONL for openclaw-mem ingestion",
  kind: "utility",

  tools: {
    memory_store: {
      description: "Store a memory into the long-term knowledge base.",
      parameters: {
        type: "object",
        properties: {
          text: { type: "string", description: "The memory content to store" },
          category: { type: "string", description: "Category (e.g., preference, fact, task)" },
          importance: { type: "number", description: "Importance (1-5), default 3" },
        },
        required: ["text"],
      },
      handler: async (args: any) => {
        try {
          // text is positional in CLI
          const cmdArgs = ["-m", "openclaw_mem", "store", args.text];
          if (args.category) cmdArgs.push("--category", args.category);
          if (args.importance) cmdArgs.push("--importance", String(args.importance));

          // Use uv to run with correct python environment
          const { stdout } = await execFileAsync("uv", ["run", "--python", "3.13", "--", "python", ...cmdArgs], {
            cwd: path.resolve(__dirname, "../../..") // Go up to workspace root where pyproject.toml is
          });
          return { content: [{ type: "text", text: stdout.trim() || "Memory stored." }] };
        } catch (err: any) {
          return { 
            isError: true, 
            content: [{ type: "text", text: `Failed to store memory: ${err.message}\n${err.stderr || ""}` }] 
          };
        }
      }
    },
    memory_recall: {
      description: "Recall memories relevant to a query.",
      parameters: {
        type: "object",
        properties: {
          query: { type: "string", description: "Search query" },
          limit: { type: "number", description: "Max results (default 5)" }
        },
        required: ["query"]
      },
      handler: async (args: any) => {
        try {
          // query is positional in CLI
          const cmdArgs = ["-m", "openclaw_mem", "hybrid", args.query];
          if (args.limit) cmdArgs.push("--limit", String(args.limit));

          // Use uv to run with correct python environment
          const { stdout } = await execFileAsync("uv", ["run", "--python", "3.13", "--", "python", ...cmdArgs], {
            cwd: path.resolve(__dirname, "../../..")
          });
          return { content: [{ type: "text", text: stdout.trim() }] };
        } catch (err: any) {
          return { 
            isError: true, 
            content: [{ type: "text", text: `Failed to recall memory: ${err.message}\n${err.stderr || ""}` }] 
          };
        }
      }
    }
  },

  register(api: OpenClawPluginApi) {
    const cfg = (api.pluginConfig ?? {}) as PluginConfig;
    const outputPath = api.resolvePath(cfg.outputPath ?? DEFAULT_OUTPUT);
    const captureMessage = cfg.captureMessage ?? false;
    const maxMessageLength = cfg.maxMessageLength ?? MAX_MESSAGE_LENGTH;

    api.on("tool_result_persist", (event, ctx) => {
      if (!shouldCapture(event.toolName ?? ctx.toolName, cfg)) return;

      const toolName = event.toolName ?? ctx.toolName;
      const summary = extractSummary(event.message);

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
        obs.message = truncateMessage(event.message, maxMessageLength);
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
  },
};

export default plugin;
