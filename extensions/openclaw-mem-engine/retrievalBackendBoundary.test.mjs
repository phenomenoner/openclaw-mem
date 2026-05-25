import test from "node:test";
import assert from "node:assert/strict";

import {
  assertRetrievalBackendDoesNotOwnCanonicalWrites,
  planRetrievalBackend,
  resolveRetrievalBackendConfig,
} from "./retrievalBackendBoundary.js";

test("retrieval backend defaults to LanceDB with Qdrant Edge disabled", () => {
  const cfg = resolveRetrievalBackendConfig({});
  assert.equal(cfg.backend, "lancedb");
  assert.equal(cfg.qdrantEdge.enabled, false);
  assert.equal(cfg.qdrantEdge.fallbackBackend, "lancedb");

  const plan = planRetrievalBackend(cfg);
  assert.equal(plan.selectedBackend, "lancedb");
  assert.equal(plan.reason, "default_or_configured_lancedb");
  assert.equal(plan.canonicalWritesAllowed, true);
});

test("qdrant-edge must be explicitly enabled before selection", () => {
  assert.throws(
    () => resolveRetrievalBackendConfig({ backend: "qdrant-edge", qdrantEdge: { enabled: false } }),
    /requires qdrantEdge.enabled=true/,
  );
});

test("qdrant-edge plans as read-only index/cache when available", () => {
  const plan = planRetrievalBackend(
    { backend: "qdrant-edge", qdrantEdge: { enabled: true, shardRoot: "memory/qdrant-edge-test" } },
    { qdrantEdgeAvailable: true, qdrantEdgeDimensionMatches: true },
  );
  assert.equal(plan.selectedBackend, "qdrant-edge");
  assert.equal(plan.reason, "qdrant_edge_ready");
  assert.equal(plan.fallbackBackend, "lancedb");
  assert.equal(plan.canonicalWritesAllowed, false);
  assert.equal(assertRetrievalBackendDoesNotOwnCanonicalWrites(plan), true);
});

test("qdrant-edge accepts bridge command config", () => {
  const cfg = resolveRetrievalBackendConfig({
    backend: "qdrant-edge",
    qdrantEdge: {
      enabled: true,
      searchCommand: "python3",
      searchCommandArgs: ["scripts/qdrant_edge_query_bridge.py", 123, "--flag"],
      timeoutMs: 500,
    },
  });
  assert.equal(cfg.qdrantEdge.searchCommand, "python3");
  assert.deepEqual(cfg.qdrantEdge.searchCommandArgs, ["scripts/qdrant_edge_query_bridge.py", "--flag"]);
  assert.equal(cfg.qdrantEdge.timeoutMs, 500);
});

test("qdrant-edge falls back to LanceDB when unavailable", () => {
  const plan = planRetrievalBackend(
    { backend: "qdrant-edge", qdrantEdge: { enabled: true } },
    { qdrantEdgeAvailable: false },
  );
  assert.equal(plan.selectedBackend, "lancedb");
  assert.equal(plan.fallbackBackend, "lancedb");
  assert.equal(plan.reason, "qdrant_edge_unavailable");
  assert.equal(plan.canonicalWritesAllowed, true);
});

test("qdrant-edge falls back to LanceDB on dimension mismatch", () => {
  const plan = planRetrievalBackend(
    { backend: "qdrant-edge", qdrantEdge: { enabled: true } },
    { qdrantEdgeAvailable: true, qdrantEdgeDimensionMatches: false },
  );
  assert.equal(plan.selectedBackend, "lancedb");
  assert.equal(plan.fallbackBackend, "lancedb");
  assert.equal(plan.reason, "qdrant_edge_dimension_mismatch");
  assert.equal(plan.canonicalWritesAllowed, true);
});

test("canonical write guard rejects malformed Qdrant ownership plan", () => {
  assert.throws(
    () => assertRetrievalBackendDoesNotOwnCanonicalWrites({ selectedBackend: "qdrant-edge", canonicalWritesAllowed: true }),
    /must not own canonical writes/,
  );
});

test("config rejects unknown keys and non-LanceDB fallback", () => {
  assert.throws(() => resolveRetrievalBackendConfig({ backend: "lancedb", surprise: true }), /unknown keys/);
  assert.throws(
    () => resolveRetrievalBackendConfig({ qdrantEdge: { enabled: true, fallbackBackend: "qdrant-edge" } }),
    /fallbackBackend must be one of: lancedb/,
  );
});
