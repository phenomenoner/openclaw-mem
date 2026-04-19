import { execFile as execFileCb } from "node:child_process";
import fs from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";

const execFile = promisify(execFileCb);

const DEFAULT_COMMAND = "gbrain";
const DEFAULT_TIMEOUT_MS = 12000;
const MAX_TIMEOUT_MS = 30000;

function clampTimeout(raw) {
  const parsed = typeof raw === "number" ? raw : Number(raw);
  if (!Number.isFinite(parsed)) return DEFAULT_TIMEOUT_MS;
  return Math.max(500, Math.min(MAX_TIMEOUT_MS, Math.floor(parsed)));
}

function toStringArray(raw) {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item) => (typeof item === "string" ? item.trim() : ""))
    .filter(Boolean)
    .slice(0, 64);
}

function yamlScalar(raw) {
  const text = String(raw ?? "");
  return JSON.stringify(text);
}

function markdownText(raw) {
  return String(raw ?? "").replace(/\r\n/g, "\n").trim();
}

function isoTimestamp(raw) {
  const parsed = typeof raw === "number" ? raw : Number(raw);
  if (!Number.isFinite(parsed)) return new Date().toISOString();
  return new Date(parsed).toISOString();
}

function safeTitle(raw) {
  const compact = String(raw ?? "").replace(/\s+/g, " ").trim();
  if (!compact) return "Memory";
  return compact.length > 72 ? `${compact.slice(0, 72).trimEnd()}…` : compact;
}

function buildMirrorMarkdown(memory) {
  const lines = [
    "---",
    `memory_id: ${yamlScalar(memory.id)}`,
    `source: ${yamlScalar("openclaw-mem-engine.memory_store")}`,
    `category: ${yamlScalar(memory.category)}`,
    `importance_label: ${yamlScalar(memory.importanceLabel)}`,
    `scope: ${yamlScalar(memory.scope)}`,
    `created_at: ${yamlScalar(isoTimestamp(memory.createdAt))}`,
  ];

  if (typeof memory.importance === "number") {
    lines.push(`importance: ${String(memory.importance)}`);
  }

  lines.push("---", "", `# ${safeTitle(memory.text)}`, "", markdownText(memory.text), "");
  return `${lines.join("\n")}`;
}

async function defaultRunner({ command, args, timeoutMs, env }) {
  try {
    const { stdout, stderr } = await execFile(command, args, {
      timeout: timeoutMs,
      maxBuffer: 2 * 1024 * 1024,
      env: env && typeof env === "object" ? { ...process.env, ...env } : process.env,
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
    };
  }
}

function receiptBase(config) {
  return {
    enabled: Boolean(config?.enabled),
    mirrorRoot: typeof config?.mirrorRoot === "string" && config.mirrorRoot.trim() ? config.mirrorRoot.trim() : null,
    command: String(config?.command || DEFAULT_COMMAND).trim() || DEFAULT_COMMAND,
    commandArgs: toStringArray(config?.commandArgs),
    timeoutMs: clampTimeout(config?.timeoutMs),
    importOnStore: config?.importOnStore !== false,
  };
}

function buildImportArgs(base) {
  return [...base.commandArgs, "import", String(base.mirrorRoot || ""), "--workers", "1"];
}

function compactText(raw, maxChars = 200) {
  const text = String(raw || "").replace(/\s+/g, " ").trim();
  if (!text) return "";
  return text.length > maxChars ? `${text.slice(0, maxChars).trimEnd()}…` : text;
}

export async function mirrorMemoryToGbrain({ memory, config, runner = defaultRunner, env }) {
  const started = Date.now();
  const base = receiptBase(config);

  if (!base.enabled || !base.mirrorRoot) {
    return {
      mirrored: false,
      imported: false,
      blocked: false,
      receipt: {
        ...base,
        attempted: false,
        mirrored: false,
        imported: false,
        filePath: null,
        importArgs: [],
        latencyMs: Date.now() - started,
      },
    };
  }

  const filePath = path.join(base.mirrorRoot, `${memory.id}.md`);
  const importArgs = base.importOnStore ? buildImportArgs(base) : [];

  try {
    await fs.mkdir(base.mirrorRoot, { recursive: true });
    await fs.writeFile(filePath, buildMirrorMarkdown(memory), "utf8");
  } catch (err) {
    return {
      mirrored: false,
      imported: false,
      blocked: false,
      receipt: {
        ...base,
        attempted: true,
        mirrored: false,
        imported: false,
        filePath,
        importArgs,
        errorCode: typeof err?.code === "string" ? err.code : null,
        errorMessage: String(err?.message || err),
        latencyMs: Date.now() - started,
      },
    };
  }

  if (!base.importOnStore) {
    return {
      mirrored: true,
      imported: false,
      blocked: false,
      receipt: {
        ...base,
        attempted: true,
        mirrored: true,
        imported: false,
        filePath,
        importArgs,
        importSkipped: true,
        latencyMs: Date.now() - started,
      },
    };
  }

  const result = await runner({
    command: base.command,
    args: importArgs,
    timeoutMs: base.timeoutMs,
    env,
  });

  return {
    mirrored: true,
    imported: Boolean(result.ok),
    blocked: false,
    receipt: {
      ...base,
      attempted: true,
      mirrored: true,
      imported: Boolean(result.ok),
      filePath,
      importArgs,
      exitCode: result.exitCode,
      errorCode: result.errorCode,
      errorMessage: result.errorMessage,
      stdoutPreview: compactText(result.stdout),
      stderrPreview: compactText(result.stderr),
      latencyMs: Date.now() - started,
    },
  };
}

export const __private__ = {
  buildMirrorMarkdown,
  buildImportArgs,
  receiptBase,
};
