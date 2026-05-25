import test from "node:test";
import assert from "node:assert/strict";

import { runRetrievalSearch } from "./retrievalRuntimeRouter.js";

test("runtime router uses LanceDB by default", async () => {
  const result = await runRetrievalSearch({
    plan: { selectedBackend: "lancedb", reason: "default_or_configured_lancedb" },
    kind: "vector",
    lanceSearch: async () => ["lance"],
  });
  assert.deepEqual(result.results, ["lance"]);
  assert.equal(result.backend, "lancedb");
  assert.equal(result.fallbackUsed, false);
});

test("runtime router falls back when Qdrant search is unwired", async () => {
  const fallbacks = [];
  const result = await runRetrievalSearch({
    plan: { selectedBackend: "qdrant-edge", fallbackBackend: "lancedb" },
    kind: "fts",
    lanceSearch: async () => ["fallback"],
    onFallback: (receipt) => fallbacks.push(receipt),
  });
  assert.deepEqual(result.results, ["fallback"]);
  assert.equal(result.backend, "lancedb");
  assert.equal(result.attemptedBackend, "qdrant-edge");
  assert.equal(result.fallbackUsed, true);
  assert.equal(result.reason, "qdrant_edge_search_unwired");
  assert.deepEqual(fallbacks, [{ kind: "fts", reason: "qdrant_edge_search_unwired", fallbackBackend: "lancedb" }]);
});

test("runtime router uses Qdrant search when wired", async () => {
  const result = await runRetrievalSearch({
    plan: { selectedBackend: "qdrant-edge", fallbackBackend: "lancedb" },
    kind: "vector",
    lanceSearch: async () => ["lance"],
    qdrantSearch: async () => ["qdrant"],
  });
  assert.deepEqual(result.results, ["qdrant"]);
  assert.equal(result.backend, "qdrant-edge");
  assert.equal(result.fallbackUsed, false);
});

test("runtime router falls back when Qdrant search throws", async () => {
  const fallbacks = [];
  const result = await runRetrievalSearch({
    plan: { selectedBackend: "qdrant-edge", fallbackBackend: "lancedb" },
    kind: "vector",
    lanceSearch: async () => ["lance-after-error"],
    qdrantSearch: async () => {
      throw new TypeError("boom");
    },
    onFallback: (receipt) => fallbacks.push(receipt),
  });
  assert.deepEqual(result.results, ["lance-after-error"]);
  assert.equal(result.backend, "lancedb");
  assert.equal(result.fallbackUsed, true);
  assert.equal(result.reason, "qdrant_edge_search_failed");
  assert.equal(fallbacks[0].errorName, "TypeError");
});
