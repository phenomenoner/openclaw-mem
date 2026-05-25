import test from "node:test";
import assert from "node:assert/strict";

import { runQdrantEdgeSearch } from "./qdrantEdgeRuntimeAdapter.js";
import { runRetrievalSearch } from "./retrievalRuntimeRouter.js";

test("FTS Qdrant bridge missing-vector failure falls back to LanceDB", async () => {
  const fallbacks = [];
  const result = await runRetrievalSearch({
    plan: { selectedBackend: "qdrant-edge", fallbackBackend: "lancedb" },
    kind: "fts",
    lanceSearch: async () => ["lancedb-fts"],
    qdrantSearch: () => runQdrantEdgeSearch({
      config: { searchCommand: "fake" },
      request: { kind: "fts", query: "alpha", limit: 1 },
      runner: async () => ({ ok: true, exitCode: 0, stdout: JSON.stringify({ ok: false, errorCode: "missing_vector", error: "qdrant-edge bridge requires vector search input" }), stderr: "" }),
    }),
    onFallback: (receipt) => fallbacks.push(receipt),
  });

  assert.deepEqual(result.results, ["lancedb-fts"]);
  assert.equal(result.backend, "lancedb");
  assert.equal(result.fallbackUsed, true);
  assert.equal(result.reason, "qdrant_edge_search_failed");
  assert.equal(fallbacks[0].kind, "fts");
});
