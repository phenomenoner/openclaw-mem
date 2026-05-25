export async function runRetrievalSearch({ plan, kind, lanceSearch, qdrantSearch, onFallback }) {
  if (!plan || plan.selectedBackend !== "qdrant-edge") {
    return {
      backend: "lancedb",
      attemptedBackend: plan?.selectedBackend ?? "lancedb",
      fallbackUsed: false,
      reason: plan?.reason ?? "default_or_configured_lancedb",
      results: await lanceSearch(),
    };
  }

  if (typeof qdrantSearch !== "function") {
    if (typeof onFallback === "function") {
      onFallback({ kind, reason: "qdrant_edge_search_unwired", fallbackBackend: plan.fallbackBackend ?? "lancedb" });
    }
    return {
      backend: plan.fallbackBackend ?? "lancedb",
      attemptedBackend: "qdrant-edge",
      fallbackUsed: true,
      reason: "qdrant_edge_search_unwired",
      results: await lanceSearch(),
    };
  }

  try {
    return {
      backend: "qdrant-edge",
      attemptedBackend: "qdrant-edge",
      fallbackUsed: false,
      reason: "qdrant_edge_ready",
      results: await qdrantSearch(),
    };
  } catch (err) {
    if (typeof onFallback === "function") {
      onFallback({
        kind,
        reason: "qdrant_edge_search_failed",
        fallbackBackend: plan.fallbackBackend ?? "lancedb",
        errorName: err && typeof err === "object" && "name" in err ? err.name : "Error",
      });
    }
    return {
      backend: plan.fallbackBackend ?? "lancedb",
      attemptedBackend: "qdrant-edge",
      fallbackUsed: true,
      reason: "qdrant_edge_search_failed",
      results: await lanceSearch(),
    };
  }
}
