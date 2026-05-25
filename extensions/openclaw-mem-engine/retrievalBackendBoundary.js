const BACKENDS = ["lancedb", "qdrant-edge"];
const FALLBACK_BACKENDS = ["lancedb"];

export const DEFAULT_RETRIEVAL_BACKEND_CONFIG = Object.freeze({
  backend: "lancedb",
  qdrantEdge: Object.freeze({
    enabled: false,
    shardRoot: "memory/qdrant-edge",
    vectorName: "text",
    optimizeOnRebuild: true,
    fallbackBackend: "lancedb",
    searchCommand: "python3",
    searchCommandArgs: [],
    timeoutMs: 1500,
  }),
});

function assertPlainObject(value, label) {
  if (value == null || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
}

function assertAllowedKeys(value, allowed, label) {
  const unknown = Object.keys(value).filter((key) => !allowed.includes(key));
  if (unknown.length > 0) {
    throw new Error(`${label} has unknown keys: ${unknown.join(", ")}`);
  }
}

export function resolveRetrievalBackendConfig(raw = {}) {
  assertPlainObject(raw, "retrieval backend config");
  assertAllowedKeys(raw, ["backend", "qdrantEdge"], "retrieval backend config");

  const backend = raw.backend == null ? DEFAULT_RETRIEVAL_BACKEND_CONFIG.backend : String(raw.backend);
  if (!BACKENDS.includes(backend)) {
    throw new Error(`retrieval backend must be one of: ${BACKENDS.join(", ")}`);
  }

  let qdrantEdge = { ...DEFAULT_RETRIEVAL_BACKEND_CONFIG.qdrantEdge };
  if (raw.qdrantEdge != null) {
    assertPlainObject(raw.qdrantEdge, "qdrantEdge config");
    assertAllowedKeys(
      raw.qdrantEdge,
      ["enabled", "shardRoot", "vectorName", "optimizeOnRebuild", "fallbackBackend", "searchCommand", "searchCommandArgs", "timeoutMs"],
      "qdrantEdge config",
    );
    qdrantEdge = {
      enabled: typeof raw.qdrantEdge.enabled === "boolean" ? raw.qdrantEdge.enabled : qdrantEdge.enabled,
      shardRoot: typeof raw.qdrantEdge.shardRoot === "string" && raw.qdrantEdge.shardRoot.trim()
        ? raw.qdrantEdge.shardRoot.trim()
        : qdrantEdge.shardRoot,
      vectorName: typeof raw.qdrantEdge.vectorName === "string" && raw.qdrantEdge.vectorName.trim()
        ? raw.qdrantEdge.vectorName.trim()
        : qdrantEdge.vectorName,
      optimizeOnRebuild: typeof raw.qdrantEdge.optimizeOnRebuild === "boolean"
        ? raw.qdrantEdge.optimizeOnRebuild
        : qdrantEdge.optimizeOnRebuild,
      fallbackBackend: typeof raw.qdrantEdge.fallbackBackend === "string" && raw.qdrantEdge.fallbackBackend.trim()
        ? raw.qdrantEdge.fallbackBackend.trim()
        : qdrantEdge.fallbackBackend,
      searchCommand: typeof raw.qdrantEdge.searchCommand === "string" && raw.qdrantEdge.searchCommand.trim()
        ? raw.qdrantEdge.searchCommand.trim()
        : qdrantEdge.searchCommand,
      searchCommandArgs: Array.isArray(raw.qdrantEdge.searchCommandArgs)
        ? raw.qdrantEdge.searchCommandArgs.filter((item) => typeof item === "string")
        : qdrantEdge.searchCommandArgs,
      timeoutMs: typeof raw.qdrantEdge.timeoutMs === "number" && Number.isFinite(raw.qdrantEdge.timeoutMs)
        ? Math.max(100, Math.min(30000, Math.floor(raw.qdrantEdge.timeoutMs)))
        : qdrantEdge.timeoutMs,
    };
  }

  if (!FALLBACK_BACKENDS.includes(qdrantEdge.fallbackBackend)) {
    throw new Error(`qdrantEdge.fallbackBackend must be one of: ${FALLBACK_BACKENDS.join(", ")}`);
  }
  if (backend === "qdrant-edge" && !qdrantEdge.enabled) {
    throw new Error("qdrant-edge backend requires qdrantEdge.enabled=true");
  }

  return { backend, qdrantEdge };
}

export function planRetrievalBackend(config, probes = {}) {
  const cfg = resolveRetrievalBackendConfig(config);
  const qdrantAvailable = probes.qdrantEdgeAvailable === true;
  const qdrantDimensionMatches = probes.qdrantEdgeDimensionMatches !== false;

  if (cfg.backend === "lancedb") {
    return {
      selectedBackend: "lancedb",
      fallbackBackend: null,
      reason: "default_or_configured_lancedb",
      canonicalWritesAllowed: true,
      qdrantEdge: cfg.qdrantEdge,
    };
  }

  if (!qdrantAvailable) {
    return {
      selectedBackend: cfg.qdrantEdge.fallbackBackend,
      fallbackBackend: cfg.qdrantEdge.fallbackBackend,
      reason: "qdrant_edge_unavailable",
      canonicalWritesAllowed: true,
      qdrantEdge: cfg.qdrantEdge,
    };
  }

  if (!qdrantDimensionMatches) {
    return {
      selectedBackend: cfg.qdrantEdge.fallbackBackend,
      fallbackBackend: cfg.qdrantEdge.fallbackBackend,
      reason: "qdrant_edge_dimension_mismatch",
      canonicalWritesAllowed: true,
      qdrantEdge: cfg.qdrantEdge,
    };
  }

  return {
    selectedBackend: "qdrant-edge",
    fallbackBackend: cfg.qdrantEdge.fallbackBackend,
    reason: "qdrant_edge_ready",
    canonicalWritesAllowed: false,
    qdrantEdge: cfg.qdrantEdge,
  };
}

export function assertRetrievalBackendDoesNotOwnCanonicalWrites(plan) {
  if (plan.selectedBackend === "qdrant-edge" && plan.canonicalWritesAllowed) {
    throw new Error("qdrant-edge must not own canonical writes");
  }
  return true;
}
