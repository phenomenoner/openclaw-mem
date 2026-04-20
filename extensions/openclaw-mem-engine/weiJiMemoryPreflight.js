import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { execFile as execFileCb } from "node:child_process";
import { promisify } from "node:util";

const execFile = promisify(execFileCb);

const DEFAULT_TIMEOUT_MS = 12_000;
const MAX_TIMEOUT_MS = 120_000;
const WRAPPER_EXIT_QUEUED = 40;
const WRAPPER_EXIT_REJECTED = 41;

function parseJsonLoose(text) {
  const raw = String(text || "").trim();
  if (!raw) return null;

  try {
    return JSON.parse(raw);
  } catch {
    // Continue.
  }

  const first = raw.search(/[{[]/);
  if (first >= 0) {
    const last = Math.max(raw.lastIndexOf("}"), raw.lastIndexOf("]"));
    if (last > first) {
      const candidate = raw.slice(first, last + 1).trim();
      try {
        return JSON.parse(candidate);
      } catch {
        // Continue.
      }
    }
  }

  const lines = raw
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  for (let i = lines.length - 1; i >= 0; i -= 1) {
    const line = lines[i];
    if (!line.startsWith("{") && !line.startsWith("[")) continue;
    try {
      return JSON.parse(line);
    } catch {
      // Continue.
    }
  }

  return null;
}

function normalizeStatus(payload) {
  const status = payload?.result?.memory_governor?.status;
  if (typeof status !== "string") return null;
  const normalized = status.trim().toLowerCase();
  return normalized || null;
}

function normalizeOptionalString(value) {
  if (typeof value !== "string") return null;
  const normalized = value.trim();
  return normalized || null;
}

function clampTimeout(raw) {
  const parsed = typeof raw === "number" ? raw : Number(raw);
  if (!Number.isFinite(parsed)) return DEFAULT_TIMEOUT_MS;
  return Math.max(1_000, Math.min(MAX_TIMEOUT_MS, Math.floor(parsed)));
}

function toStringArray(raw) {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item) => (typeof item === "string" ? item.trim() : ""))
    .filter(Boolean)
    .slice(0, 64);
}

async function defaultRunner({ command, args, timeoutMs }) {
  try {
    const { stdout, stderr } = await execFile(command, args, {
      timeout: timeoutMs,
      maxBuffer: 4 * 1024 * 1024,
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
  const command = String(config?.command || "weiji-memory-preflight").trim() || "weiji-memory-preflight";
  const commandArgs = toStringArray(config?.commandArgs);
  const timeoutMs = clampTimeout(config?.timeoutMs);
  const failMode = config?.failMode === "closed" ? "closed" : "open";
  const failOnQueued = Boolean(config?.failOnQueued);
  const failOnRejected = Boolean(config?.failOnRejected);
  const dbPath = typeof config?.dbPath === "string" && config.dbPath.trim() ? config.dbPath.trim() : null;

  return {
    command,
    commandArgs,
    timeoutMs,
    failMode,
    failOnQueued,
    failOnRejected,
    dbPath,
  };
}

export async function runWeiJiMemoryPreflight({ intent, config, runner = defaultRunner }) {
  const started = Date.now();
  const base = receiptBase(config);

  if (!Boolean(config?.enabled)) {
    return {
      allowed: true,
      blocked: false,
      receipt: {
        enabled: false,
        attempted: false,
        decision: "allow",
        mode: "disabled",
        latencyMs: Date.now() - started,
      },
      envelope: null,
    };
  }

  const tmpRoot = await fs.mkdtemp(path.join(os.tmpdir(), "openclaw-weiji-memory-intent-"));
  const intentPath = path.join(tmpRoot, "intent.json");

  try {
    await fs.writeFile(intentPath, `${JSON.stringify(intent)}\n`, "utf8");

    const args = [...base.commandArgs, "--intent", intentPath];
    if (base.dbPath) {
      args.push("--db", base.dbPath);
    }
    if (base.failOnQueued) {
      args.push("--fail-on-queued");
    }
    if (base.failOnRejected) {
      args.push("--fail-on-rejected");
    }

    const commandResult = await runner({
      command: base.command,
      args,
      timeoutMs: base.timeoutMs,
    });

    const payload = parseJsonLoose(commandResult.stdout) ?? parseJsonLoose(commandResult.stderr);
    const envelope = payload && typeof payload === "object" ? payload : null;
    const wrapperExitCode = Number.isFinite(Number(envelope?.exit_code))
      ? Number(envelope.exit_code)
      : (commandResult.exitCode ?? null);
    const failReason = typeof envelope?.fail_reason === "string" ? envelope.fail_reason : null;
    const governorStatus = normalizeStatus(envelope);
    const reviewRequired = envelope?.result?.memory_governor?.review_required === true;
    const traceId = normalizeOptionalString(envelope?.result?.memory_governor?.trace_id);
    const writeId = normalizeOptionalString(
      envelope?.result?.memory_governor?.write_id ?? envelope?.result?.memory_governor?.request_payload?.write_id,
    );
    const bridgeMode = normalizeOptionalString(envelope?.result?.memory_governor?.bridge?.mode);
    const nextSafeMove = normalizeOptionalString(envelope?.result?.next_safe_move);
    const shadowMode = envelope?.result?.shadow_mode === true;

    const policyBlock =
      wrapperExitCode === WRAPPER_EXIT_QUEUED ||
      wrapperExitCode === WRAPPER_EXIT_REJECTED ||
      (base.failOnQueued && governorStatus === "queued") ||
      (base.failOnRejected && governorStatus === "rejected");

    const runtimeFailed = !commandResult.ok && !policyBlock;
    const blocked = policyBlock || (runtimeFailed && base.failMode === "closed");

    const receipt = {
      enabled: true,
      attempted: true,
      decision: blocked ? "block" : "allow",
      mode: base.failOnQueued || base.failOnRejected ? "enforced" : "advisory",
      command: base.command,
      args,
      timeoutMs: base.timeoutMs,
      failMode: base.failMode,
      wrapperOk: envelope?.ok === true,
      wrapperExitCode,
      wrapperFailReason: failReason,
      governorStatus,
      reviewRequired,
      traceId,
      writeId,
      bridgeMode,
      nextSafeMove,
      shadowMode,
      errorCode: commandResult.errorCode,
      errorMessage: commandResult.errorMessage,
      policyBlock,
      runtimeFailed,
      latencyMs: Date.now() - started,
    };

    return {
      allowed: !blocked,
      blocked,
      receipt,
      envelope,
    };
  } catch (err) {
    const blocked = base.failMode === "closed";
    return {
      allowed: !blocked,
      blocked,
      receipt: {
        enabled: true,
        attempted: true,
        decision: blocked ? "block" : "allow",
        mode: "error",
        command: base.command,
        args: [...base.commandArgs, "--intent", intentPath],
        timeoutMs: base.timeoutMs,
        failMode: base.failMode,
        wrapperOk: false,
        wrapperExitCode: null,
        wrapperFailReason: "intent_write_error",
        governorStatus: null,
        reviewRequired: false,
        errorCode: "intent_write_error",
        errorMessage: String(err?.message || err),
        policyBlock: false,
        runtimeFailed: true,
        latencyMs: Date.now() - started,
      },
      envelope: null,
    };
  } finally {
    await fs.rm(tmpRoot, { recursive: true, force: true });
  }
}

export const __private__ = {
  parseJsonLoose,
  normalizeStatus,
  clampTimeout,
};
