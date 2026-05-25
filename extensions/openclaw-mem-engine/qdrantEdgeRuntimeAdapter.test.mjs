import test from "node:test";
import assert from "node:assert/strict";

import { resolveQdrantEdgeRuntimeAdapterConfig, runQdrantEdgeSearch } from "./qdrantEdgeRuntimeAdapter.js";

test("qdrant runtime adapter config defaults are bounded", () => {
  const cfg = resolveQdrantEdgeRuntimeAdapterConfig({ timeoutMs: 999999, searchCommandArgs: ["-m", 1, "bridge"] });
  assert.equal(cfg.searchCommand, "python3");
  assert.deepEqual(cfg.searchCommandArgs, ["-m", "bridge"]);
  assert.equal(cfg.timeoutMs, 30000);
});

test("qdrant runtime adapter sends bounded JSON request and normalizes hits", async () => {
  const calls = [];
  const hits = await runQdrantEdgeSearch({
    config: { searchCommand: "bridge", searchCommandArgs: ["--json"], timeoutMs: 500 },
    request: { kind: "vector", query: "alpha", vector: [0.1, 0.2], limit: 1, scope: "global", labels: ["must_remember"] },
    runner: async (call) => {
      calls.push(call);
      const req = JSON.parse(call.stdin);
      assert.equal(req.schema, "openclaw-mem-engine.qdrant-edge.search.request.v1");
      assert.equal(req.kind, "vector");
      assert.deepEqual(req.labels, ["must_remember"]);
      return {
        ok: true,
        exitCode: 0,
        stdout: JSON.stringify({ ok: true, hits: [{ id: "mem-1", text: "Alpha", score: 0.9, row: { scope: "global", category: "fact" } }] }),
        stderr: "",
      };
    },
  });
  assert.equal(calls[0].command, "bridge");
  assert.deepEqual(calls[0].args, ["--json"]);
  assert.equal(calls[0].timeoutMs, 500);
  assert.equal(hits[0].row.id, "mem-1");
  assert.equal(hits[0].row.text, "Alpha");
  assert.equal(hits[0].row.scope, "global");
  assert.equal(hits[0].score, 0.9);
});

test("qdrant runtime adapter throws bounded errors for bridge failure", async () => {
  await assert.rejects(
    () => runQdrantEdgeSearch({
      config: { searchCommand: "bridge" },
      request: { kind: "fts", query: "alpha", limit: 1 },
      runner: async () => ({ ok: false, exitCode: 2, stdout: "", stderr: "bad", errorCode: "nonzero_exit", errorMessage: "exit 2" }),
    }),
    /exit 2/,
  );
});

test("qdrant runtime adapter throws bounded errors for invalid JSON", async () => {
  await assert.rejects(
    () => runQdrantEdgeSearch({
      config: {},
      request: { kind: "fts", query: "alpha", limit: 1 },
      runner: async () => ({ ok: true, exitCode: 0, stdout: "not-json", stderr: "" }),
    }),
    /invalid JSON/,
  );
});
