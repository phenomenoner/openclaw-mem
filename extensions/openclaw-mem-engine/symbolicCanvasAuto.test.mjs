import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import {
  buildTraceFromAgentEvent,
  resolveSymbolicCanvasAutoConfig,
  runSymbolicCanvasAutoBuild,
  shouldRunSymbolicCanvasAutoBuild,
} from "./symbolicCanvasAuto.js";

test("symbolic canvas auto config is disabled by default and bounded", () => {
  const cfg = resolveSymbolicCanvasAutoConfig({ maxNodes: 999, timeoutMs: 999999, maxLabelChars: 1 });
  assert.equal(cfg.enabled, false);
  assert.equal(cfg.maxNodes, 24);
  assert.equal(cfg.timeoutMs, 15000);
  assert.equal(cfg.maxLabelChars, 40);
  assert.equal(cfg.triggerMode, "qualified");
});

test("qualified trigger ignores routine/skill-heavy turns and accepts handoff turns", () => {
  const routine = {
    success: true,
    messages: [
      { role: "system", content: "very long skill text should not qualify" },
      { role: "tool", content: "SKILL.md contents ..." },
      { role: "user", content: "之前我們在曦那邊碰到一個問題" },
      { role: "assistant", content: "我查一下" },
    ],
  };
  assert.deepEqual(shouldRunSymbolicCanvasAutoBuild(routine, {}, { enabled: true }), {
    ok: false,
    reason: "not_qualified",
  });

  const handoff = {
    success: true,
    messages: [
      { role: "user", content: "請做 checkpoint handoff receipt" },
      { role: "assistant", content: "closure verifier complete" },
    ],
  };
  const result = shouldRunSymbolicCanvasAutoBuild(handoff, {}, { enabled: true });
  assert.equal(result.ok, true);
  assert.equal(result.reason, "qualified_pattern");
});

test("always trigger mode preserves broad agent_end behavior when explicitly requested", () => {
  const event = { success: true, messages: [{ role: "user", content: "routine" }] };
  assert.deepEqual(shouldRunSymbolicCanvasAutoBuild(event, {}, { enabled: true, triggerMode: "always" }), {
    ok: true,
    reason: "trigger_mode_always",
  });
});

test("buildTraceFromAgentEvent creates bounded sequential message graph", () => {
  const trace = buildTraceFromAgentEvent(
    {
      messages: [
        { role: "system", content: "skip" },
        { role: "user", content: "Please do the thing" },
        { role: "assistant", content: "I did step one" },
        { role: "tool", content: "skip" },
        { role: "user", content: [{ type: "text", text: "Finish it" }] },
      ],
    },
    { sessionKey: "discord:abc/def", agentId: "main" },
    { maxNodes: 3, maxLabelChars: 80 },
  );

  assert.equal(trace.task_id, "auto-discord:abc_def");
  assert.equal(trace.nodes.length, 3);
  assert.deepEqual(trace.edges, [
    ["m001_user", "m002_assistant", "next"],
    ["m002_assistant", "m003_user", "next"],
  ]);
  assert.equal(trace.nodes[0].refs[0].startsWith("artifact:openclaw-session-message:"), true);
});

test("runSymbolicCanvasAutoBuild skips when disabled, unqualified, or below min messages", async () => {
  assert.deepEqual(await runSymbolicCanvasAutoBuild({ config: { enabled: false } }), {
    ok: true,
    skipped: true,
    skipReason: "disabled",
    elapsedMs: 0,
  });

  const unqualified = await runSymbolicCanvasAutoBuild({
    config: { enabled: true },
    event: { success: true, messages: [{ role: "user", content: "ordinary chat" }, { role: "assistant", content: "ordinary reply" }] },
  });
  assert.equal(unqualified.skipped, true);
  assert.equal(unqualified.skipReason, "not_qualified");

  const below = await runSymbolicCanvasAutoBuild({
    config: { enabled: true, minMessages: 3 },
    event: { success: true, messages: [{ role: "user", content: "checkpoint" }, { role: "assistant", content: "receipt" }] },
  });
  assert.equal(below.skipped, true);
  assert.equal(below.skipReason, "too_few_messages");
});

test("runSymbolicCanvasAutoBuild writes json and mermaid via runner", async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "symbolic-auto-"));
  const receipt = await runSymbolicCanvasAutoBuild({
    stateDir: tmp,
    config: { enabled: true, outputDir: "out", minMessages: 2, command: "fake-openclaw-mem" },
    event: {
      success: true,
      messages: [
        { role: "user", content: "checkpoint Start" },
        { role: "assistant", content: "Done receipt" },
      ],
    },
    runner: async ({ args, input }) => {
      const out = args[args.indexOf("--out") + 1];
      const mmd = args[args.indexOf("--mermaid-out") + 1];
      const fromFile = args[args.indexOf("--from-file") + 1];
      const trace = JSON.parse(fs.readFileSync(fromFile, "utf8") || input);
      fs.writeFileSync(out, JSON.stringify({ ok: true, kind: "openclaw-mem.symbolic-canvas.v0", task_id: trace.task_id }));
      fs.writeFileSync(mmd, "graph LR\n");
      return { ok: true, exitCode: 0, stdout: JSON.stringify({ ok: true, kind: "openclaw-mem.symbolic-canvas.v0" }), stderr: "" };
    },
  });

  assert.equal(receipt.ok, true);
  assert.equal(receipt.skipped, false);
  assert.equal(receipt.command, "fake-openclaw-mem");
  assert.equal(fs.existsSync(receipt.traceOut), true);
  assert.equal(fs.existsSync(receipt.jsonOut), true);
  assert.equal(fs.existsSync(receipt.mermaidOut), true);
});

test("runSymbolicCanvasAutoBuild falls back to repo-local uv module when default command is missing", async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "symbolic-auto-fallback-"));
  const calls = [];
  const receipt = await runSymbolicCanvasAutoBuild({
    stateDir: tmp,
    config: { enabled: true, outputDir: "out", minMessages: 2 },
    event: {
      success: true,
      messages: [
        { role: "user", content: "checkpoint Start" },
        { role: "assistant", content: "Done receipt" },
      ],
    },
    runner: async ({ command, args }) => {
      calls.push({ command, args });
      if (command === "openclaw-mem") {
        return { ok: false, exitCode: null, stdout: "", stderr: "", errorCode: "ENOENT", errorMessage: "spawn openclaw-mem ENOENT" };
      }
      const out = args[args.indexOf("--out") + 1];
      const mmd = args[args.indexOf("--mermaid-out") + 1];
      fs.writeFileSync(out, JSON.stringify({ ok: true, kind: "openclaw-mem.symbolic-canvas.v0" }));
      fs.writeFileSync(mmd, "graph LR\n");
      return { ok: true, exitCode: 0, stdout: JSON.stringify({ ok: true, kind: "openclaw-mem.symbolic-canvas.v0" }), stderr: "" };
    },
  });

  assert.equal(receipt.ok, true);
  assert.equal(receipt.configuredCommand, "openclaw-mem");
  assert.equal(receipt.command, "uv");
  assert.equal(receipt.fallbackUsed, true);
  assert.equal(receipt.attempts.length, 2);
  assert.equal(calls[0].command, "openclaw-mem");
  assert.equal(calls[1].command, "uv");
  assert.deepEqual(calls[1].args.slice(0, 2), ["run", "--project"]);
  assert.equal(calls[1].args.includes("-m"), true);
  assert.equal(calls[1].args.includes("openclaw_mem"), true);
});

test("runSymbolicCanvasAutoBuild preserves custom command behavior when command is missing", async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "symbolic-auto-custom-"));
  const calls = [];
  const receipt = await runSymbolicCanvasAutoBuild({
    stateDir: tmp,
    config: { enabled: true, outputDir: "out", minMessages: 2, command: "custom-openclaw-mem" },
    event: {
      success: true,
      messages: [
        { role: "user", content: "checkpoint Start" },
        { role: "assistant", content: "Done receipt" },
      ],
    },
    runner: async ({ command, args }) => {
      calls.push({ command, args });
      return { ok: false, exitCode: null, stdout: "", stderr: "", errorCode: "ENOENT", errorMessage: "spawn custom-openclaw-mem ENOENT" };
    },
  });

  assert.equal(receipt.ok, false);
  assert.equal(receipt.configuredCommand, "custom-openclaw-mem");
  assert.equal(receipt.command, "custom-openclaw-mem");
  assert.equal(receipt.fallbackUsed, false);
  assert.equal(receipt.attempts.length, 1);
  assert.equal(calls.length, 1);
});
