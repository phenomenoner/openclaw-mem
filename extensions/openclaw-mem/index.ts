import type { OpenClawPluginApi } from "openclaw/plugin-sdk";
import fs from "node:fs";
import path from "node:path";

const DEFAULT_OUTPUT = "~/.openclaw/memory/openclaw-mem-observations.jsonl";

type PluginConfig = {
  enabled?: boolean;
  outputPath?: string;
  includeTools?: string[];
  excludeTools?: string[];
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

const plugin = {
  id: "openclaw-mem",
  name: "OpenClaw Mem",
  description: "Capture tool results into JSONL for openclaw-mem ingestion",
  kind: "utility",

  register(api: OpenClawPluginApi) {
    const cfg = (api.pluginConfig ?? {}) as PluginConfig;
    const outputPath = api.resolvePath(cfg.outputPath ?? DEFAULT_OUTPUT);

    api.on("tool_result_persist", (event, ctx) => {
      if (!shouldCapture(event.toolName ?? ctx.toolName, cfg)) return;

      const obs = {
        ts: new Date().toISOString(),
        kind: "tool",
        tool_name: event.toolName ?? ctx.toolName,
        tool_call_id: event.toolCallId ?? ctx.toolCallId,
        session_key: ctx.sessionKey,
        agent_id: ctx.agentId,
        is_synthetic: event.isSynthetic ?? false,
        message: event.message,
      };

      try {
        fs.mkdirSync(path.dirname(outputPath), { recursive: true });
        fs.appendFileSync(outputPath, JSON.stringify(obs) + "\n", "utf-8");
      } catch (err) {
        api.logger.warn(`openclaw-mem: failed to write JSONL: ${String(err)}`);
      }

      // Do not modify the tool result; return undefined to keep it as-is.
      return;
    });
  },
};

export default plugin;
