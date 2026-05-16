import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

import {
  buildTraceFromAgentEvent,
  resolveSymbolicCanvasAutoConfig,
  runSymbolicCanvasAutoBuild,
} from "./symbolicCanvasAuto.js";

test("symbolic canvas auto config is disabled by default and bounded", () => {
  const cfg = resolveSymbolicCanvasAutoConfig({ maxNodes: 999, timeoutMs: 999999, maxLabelChars: 1 });
  assert.equal(cfg.enabled, false);
  assert.equal(cfg.maxNodes, 24);
  assert.equal(cfg.timeoutMs, 15000);
  assert.equal(cfg.maxLabelChars, 40);
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

test("runSymbolicCanvasAutoBuild skips when disabled or below min messages", async () => {
  assert.deepEqual(await runSymbolicCanvasAutoBuild({ config: { enabled: false } }), {
    ok: true,
    skipped: true,
    skipReason: "disabled",
    elapsedMs: 0,
  });

  const below = await runSymbolicCanvasAutoBuild({
    config: { enabled: true, minMessages: 2 },
    event: { success: true, messages: [{ role: "user", content: "only one" }] },
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
        { role: "user", content: "Start" },
        { role: "assistant", content: "Done" },
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
