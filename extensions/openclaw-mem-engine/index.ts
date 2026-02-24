/**
 * openclaw-mem-engine (M0)
 *
 * Enable (no config apply here):
 * 1) Add this extension folder to OpenClaw plugin load paths.
 *    - Example (config): plugins.loadPaths += ["/root/.openclaw/workspace/openclaw-mem-dev/extensions"]
 * 2) Set the memory slot to this plugin:
 *    - plugins.slots.memory = "openclaw-mem-engine"
 * 3) Configure embeddings (either):
 *    - plugins.entries["openclaw-mem-engine"].embedding.apiKey = "${OPENAI_API_KEY}"
 *    - or set env: OPENAI_API_KEY
 *
 * Smoke:
 * - memory_store({ text: "I prefer dark mode", importance: 0.8, category: "preference" })
 * - memory_recall({ query: "What UI mode do I prefer?", limit: 3 })
 * - memory_forget({ memoryId: "<id from store>" })
 */

import { randomUUID } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { performance } from "node:perf_hooks";
import type * as LanceDB from "@lancedb/lancedb";
import { Type } from "@sinclair/typebox";
import type { OpenClawPluginApi } from "openclaw/plugin-sdk";

// ============================================================================
// Config
// ============================================================================

type MemoryCategory = "preference" | "fact" | "decision" | "entity" | "other";

const MemoryCategorySchema = Type.Union([
  Type.Literal("preference"),
  Type.Literal("fact"),
  Type.Literal("decision"),
  Type.Literal("entity"),
  Type.Literal("other"),
]);

type PluginConfig = {
  embedding?: {
    apiKey?: string;
    model?: "text-embedding-3-small" | "text-embedding-3-large";
  };
  dbPath?: string;
  tableName?: string;
};

const DEFAULT_DB_PATH = "~/.openclaw/memory/lancedb";
const DEFAULT_TABLE_NAME = "memories";
const DEFAULT_MODEL: NonNullable<NonNullable<PluginConfig["embedding"]>["model"]> =
  "text-embedding-3-small";

function vectorDimsForModel(model: string): number {
  switch (model) {
    case "text-embedding-3-large":
      return 3072;
    case "text-embedding-3-small":
    default:
      return 1536;
  }
}

type ImportanceLabel = "must_remember" | "nice_to_have" | "ignore" | "unknown";
type ScopeMode = "explicit" | "inferred" | "global";

const DEFAULT_RECALL_LIMIT = 5;
const MAX_RECALL_LIMIT = 50;
const RRF_K = 60;

function normalizeImportance(raw: unknown): number | undefined {
  if (typeof raw === "number" && Number.isFinite(raw)) {
    return Math.max(0, Math.min(1, raw));
  }
  if (typeof raw === "string") {
    const parsed = Number(raw.trim());
    if (Number.isFinite(parsed)) {
      return Math.max(0, Math.min(1, parsed));
    }
  }
  return undefined;
}

function importanceLabel(score: number | undefined): ImportanceLabel {
  if (typeof score !== "number") return "unknown";
  if (score >= 0.8) return "must_remember";
  if (score >= 0.5) return "nice_to_have";
  return "ignore";
}

function normalizeImportanceLabel(raw: unknown): ImportanceLabel | undefined {
  if (typeof raw !== "string") return undefined;

  const normalized = raw.trim().toLowerCase().replace(/[-\s]+/g, "_");
  if (!normalized) return undefined;

  const aliases: Record<string, ImportanceLabel> = {
    must_remember: "must_remember",
    nice_to_have: "nice_to_have",
    ignore: "ignore",
    unknown: "unknown",
    none: "unknown",
    high: "must_remember",
    medium: "nice_to_have",
    low: "ignore",
    trivial: "ignore",
  };

  return aliases[normalized];
}

function resolveImportanceLabel(rawScore: number | undefined, rawLabel: unknown): ImportanceLabel {
  const labeled = normalizeImportanceLabel(rawLabel);
  if (labeled) return labeled;
  return importanceLabel(rawScore);
}

// ============================================================================
// LanceDB loader
// ============================================================================

let lancedbImportPromise: Promise<typeof import("@lancedb/lancedb")> | null = null;
const loadLanceDB = async (): Promise<typeof import("@lancedb/lancedb")> => {
  if (!lancedbImportPromise) {
    lancedbImportPromise = import("@lancedb/lancedb");
  }
  try {
    return await lancedbImportPromise;
  } catch (err) {
    throw new Error(`openclaw-mem-engine: failed to load LanceDB. ${String(err)}`, { cause: err });
  }
};

// ============================================================================
// DB layer
// ============================================================================

type MemoryRow = {
  id: string;
  text: string;
  vector: number[];
  createdAt: number;
  category: MemoryCategory;
  importance?: number | null;
  importance_label: string;
  scope: string;
  trust_tier: string;
};

type RecallResult = {
  row: Omit<MemoryRow, "vector">;
  distance: number;
  score: number;
};

function toImportanceRecord(raw: unknown): number | undefined {
  return normalizeImportance(raw);
}

function scopeFilterExpr(scope: string): string {
  const safeScope = scope.replace(/'/g, "''");
  if (scope === "global") {
    return `(scope = '${safeScope}' OR scope IS NULL OR scope = '')`;
  }
  return `scope = '${safeScope}'`;
}

function extractScopeFromText(rawText: unknown): string | undefined {
  if (typeof rawText !== "string") return undefined;

  const matches = [...rawText.matchAll(/\[(ISO|SCOPE):\s*([^\]]+)\]/gi)];
  let isoScope: string | undefined;
  let scopeScope: string | undefined;

  for (const [, kind, value] of matches) {
    const scope = value.trim();
    if (!scope) continue;

    if (kind.toUpperCase() === "ISO" && !isoScope) {
      isoScope = scope;
    }

    if (kind.toUpperCase() === "SCOPE" && !scopeScope) {
      scopeScope = scope;
    }
  }

  if (isoScope) return isoScope;
  return scopeScope;
}

function resolveScope(mode: {
  explicitScope?: string;
  text: string;
}): { scope: string; scopeMode: ScopeMode } {
  const explicit = (mode.explicitScope ?? "").trim();
  if (explicit) {
    return { scope: explicit, scopeMode: "explicit" };
  }

  const inferred = extractScopeFromText(mode.text);
  if (inferred) {
    return { scope: inferred, scopeMode: "inferred" };
  }

  return { scope: "global", scopeMode: "global" };
}

function clampLimit(rawLimit: number | undefined): number {
  const parsed = Number(rawLimit);
  if (!Number.isFinite(parsed)) return DEFAULT_RECALL_LIMIT;
  return Math.max(1, Math.min(MAX_RECALL_LIMIT, Math.floor(parsed)));
}

function fuseRecall(results: {
  vector: RecallResult[];
  fts: RecallResult[];
  limit: number;
}): { order: RecallResult[] } {
  const fused = new Map<string, { row: RecallResult["row"]; distance: number; score: number }>();

  for (const [index, item] of results.fts.entries()) {
    const id = item.row.id;
    if (!id) continue;

    const existing = fused.get(id);
    const contribution = 1 / (RRF_K + index + 1);
    if (existing) {
      existing.score += contribution;
      continue;
    }

    fused.set(id, {
      row: item.row,
      distance: item.distance,
      score: contribution,
    });
  }

  for (const [index, item] of results.vector.entries()) {
    const id = item.row.id;
    if (!id) continue;

    const existing = fused.get(id);
    const contribution = 1 / (RRF_K + index + 1);
    if (existing) {
      existing.score += contribution;
      if (item.distance) existing.distance = item.distance;
      continue;
    }

    fused.set(id, {
      row: item.row,
      distance: item.distance,
      score: contribution,
    });
  }

  const order = Array.from(fused.values())
    .sort((a, b) => {
      if (b.score !== a.score) return b.score - a.score;
      return a.row.id.localeCompare(b.row.id);
    })
    .slice(0, limit)
    .map((item) => ({
      row: item.row,
      distance: item.distance,
      score: item.score,
    }));

  return { order };
}

class MemoryDB {
  private db: LanceDB.Connection | null = null;
  private table: LanceDB.Table | null = null;
  private initPromise: Promise<void> | null = null;

  constructor(
    private readonly dbPath: string,
    private readonly tableName: string,
    private readonly vectorDim: number,
  ) {}

  private async ensureInitialized(): Promise<void> {
    if (this.table) return;
    if (this.initPromise) return this.initPromise;
    this.initPromise = this.doInitialize();
    return this.initPromise;
  }

  private async doInitialize(): Promise<void> {
    const lancedb = await loadLanceDB();
    this.db = await lancedb.connect(this.dbPath);

    const tables = await this.db.tableNames();
    if (tables.includes(this.tableName)) {
      this.table = await this.db.openTable(this.tableName);
      return;
    }

    // Create table with a single row to establish schema, then delete it.
    const schemaRow: MemoryRow = {
      id: "__schema__",
      text: "",
      vector: Array.from({ length: this.vectorDim }).fill(0),
      createdAt: 0,
      category: "other",
      importance: 0,
      importance_label: "unknown",
      scope: "global",
      trust_tier: "unknown",
    };

    this.table = await this.db.createTable(this.tableName, [schemaRow]);
    await this.table.delete('id = "__schema__"');
  }

  async add(row: MemoryRow): Promise<void> {
    await this.ensureInitialized();
    await this.table!.add([row]);
  }

  async vectorSearch(vector: number[], limit: number, scope?: string): Promise<RecallResult[]> {
    await this.ensureInitialized();

    const query = this.table!.vectorSearch(vector);
    if (scope) query.where(scopeFilterExpr(scope));

    const results = await query.limit(limit).toArray();

    return results.map((r: any) => {
      const distance = typeof r._distance === "number" ? r._distance : 0;
      const score = 1 / (1 + distance);
      return {
        row: {
          id: String(r.id),
          text: String(r.text ?? ""),
          createdAt: Number(r.createdAt ?? 0),
          category: (r.category ?? "other") as MemoryRow["category"],
          importance: toImportanceRecord(r.importance),
          importance_label: String(r.importance_label ?? ""),
          scope: String(r.scope ?? ""),
          trust_tier: String(r.trust_tier ?? ""),
        },
        distance,
        score,
      };
    });
  }

  async fullTextSearch(query: string, limit: number, scope?: string): Promise<RecallResult[]> {
    await this.ensureInitialized();

    const q = this.table!.search(query, "fts", ["text"]);
    if (scope) q.where(scopeFilterExpr(scope));

    const results = await q.limit(limit).toArray();

    return results.map((r: any) => {
      const score = typeof r._score === "number" ? r._score : 0;
      return {
        row: {
          id: String(r.id),
          text: String(r.text ?? ""),
          createdAt: Number(r.createdAt ?? 0),
          category: (r.category ?? "other") as MemoryRow["category"],
          importance: toImportanceRecord(r.importance),
          importance_label: String(r.importance_label ?? ""),
          scope: String(r.scope ?? ""),
          trust_tier: String(r.trust_tier ?? ""),
        },
        distance: 0,
        score,
      };
    });
  }

  async deleteById(id: string): Promise<void> {
    await this.ensureInitialized();

    if (id === "__schema__") {
      throw new Error("Refusing to delete reserved schema row.");
    }

    // Prevent LanceDB filter injection.
    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (!uuidRegex.test(id)) {
      throw new Error(`Invalid memoryId format: ${id}`);
    }

    await this.table!.delete(`id = '${id}'`);
  }
}

// ============================================================================
// OpenAI embeddings (fetch)
// ============================================================================

class OpenAIEmbeddings {
  constructor(
    private readonly apiKey: string,
    private readonly model: string,
  ) {}

  async embed(input: string): Promise<number[]> {
    const resp = await fetch("https://api.openai.com/v1/embeddings", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${this.apiKey}`,
      },
      body: JSON.stringify({ model: this.model, input }),
    });

    if (!resp.ok) {
      const body = await resp.text().catch(() => "");
      throw new Error(
        `openclaw-mem-engine: embeddings failed (${resp.status} ${resp.statusText}) ${body.slice(0, 500)}`,
      );
    }

    const json: any = await resp.json();
    const emb = json?.data?.[0]?.embedding;
    if (!Array.isArray(emb)) {
      throw new Error("openclaw-mem-engine: embeddings response missing data[0].embedding");
    }
    return emb as number[];
  }
}

// ============================================================================
// Plugin
// ============================================================================

function resolveEnvVars(value: string): string {
  return value.replace(/\$\{([^}]+)\}/g, (_, envVar) => {
    const envValue = process.env[String(envVar)];
    return envValue ?? "";
  });
}

function readBundledMemoryLanceDbApiKey(api: OpenClawPluginApi): string {
  try {
    const stateDir = api.runtime.state.resolveStateDir();
    const cfgPath = path.join(stateDir, "openclaw.json");
    if (!fs.existsSync(cfgPath)) return "";
    const raw = fs.readFileSync(cfgPath, "utf8");
    const json = JSON.parse(raw) as any;
    const key = json?.plugins?.entries?.["memory-lancedb"]?.config?.embedding?.apiKey;
    return typeof key === "string" ? key.trim() : "";
  } catch {
    return "";
  }
}

function resolveEmbeddingApiKey(api: OpenClawPluginApi, cfg: PluginConfig): string {
  const fromCfg = (cfg.embedding?.apiKey ?? "").trim();
  const resolvedCfg = resolveEnvVars(fromCfg).trim();
  if (resolvedCfg) return resolvedCfg;

  const fromEnv = (process.env.OPENAI_API_KEY ?? "").trim();
  if (fromEnv) return fromEnv;

  // Fallback: reuse the bundled memory-lancedb key to avoid duplicating secrets.
  const fromMemoryLanceDb = resolveEnvVars(readBundledMemoryLanceDbApiKey(api)).trim();
  if (fromMemoryLanceDb) return fromMemoryLanceDb;

  return "";
}

function resolveStateRelativePath(api: OpenClawPluginApi, input: string | undefined, fallback: string): string {
  const stateDir = api.runtime.state.resolveStateDir();
  const raw = (input ?? fallback).trim();

  // Treat ~/.openclaw as an alias for the resolved state dir.
  if (raw === "~/.openclaw" || raw.startsWith("~/.openclaw/") || raw.startsWith("~\\.openclaw\\")) {
    const suffix = raw.replace(/^~[\\/]\.openclaw[\\/]?/, "");
    return path.resolve(stateDir, suffix);
  }

  // Resolve relative paths under the OpenClaw state dir.
  if (!raw.startsWith("~") && !path.isAbsolute(raw)) {
    return path.resolve(stateDir, raw);
  }

  return api.resolvePath(raw);
}

const memoryPlugin = {
  id: "openclaw-mem-engine",
  name: "OpenClaw Mem Engine",
  description: "Optional memory slot backend (LanceDB + OpenAI embeddings)",
  kind: "memory" as const,

  register(api: OpenClawPluginApi) {
    const cfg = (api.pluginConfig ?? {}) as PluginConfig;

    const model = cfg.embedding?.model ?? DEFAULT_MODEL;
    const vectorDim = vectorDimsForModel(model);

    const apiKey = resolveEmbeddingApiKey(api, cfg);

    const resolvedDbPath = resolveStateRelativePath(api, cfg.dbPath, DEFAULT_DB_PATH);
    const tableName = (cfg.tableName ?? DEFAULT_TABLE_NAME).trim() || DEFAULT_TABLE_NAME;

    const db = new MemoryDB(resolvedDbPath, tableName, vectorDim);
    const embeddings = apiKey ? new OpenAIEmbeddings(apiKey, model) : null;

    api.logger.info(
      `openclaw-mem-engine: registered (db=${resolvedDbPath}, table=${tableName}, model=${model}, lazyInit=true)`,
    );

    // ----------------------------------------------------------------------
    // Tools: memory_recall
    // ----------------------------------------------------------------------

    api.registerTool(
      {
        name: "memory_recall",
        label: "Memory Recall",
        description:
          "Search through long-term memories. Use when you need context about user preferences, past decisions, or previously discussed topics.",
        parameters: Type.Object({
          query: Type.String({ description: "Search query" }),
          limit: Type.Optional(Type.Number({ description: `Max results (default: ${DEFAULT_RECALL_LIMIT})` })),
          scope: Type.Optional(Type.String({ description: "Scope hint (optional)" })),
        }),
        async execute(_toolCallId: string, params: unknown) {
          const t0 = performance.now();
          const {
            query,
            limit,
            scope: scopeInput,
          } = params as { query: string; limit?: number; scope?: string };

          if (!embeddings) {
            return {
              content: [
                {
                  type: "text",
                  text: "openclaw-mem-engine is not configured (missing embedding.apiKey / OPENAI_API_KEY).",
                },
              ],
              details: { error: "missing_api_key" },
            };
          }

          const normalizedLimit = clampLimit(limit);
          const { scope, scopeMode } = resolveScope({ explicitScope: scopeInput, text: query });
          const searchLimit = Math.max(normalizedLimit, normalizedLimit * 2);

          const vector = await embeddings.embed(query);

          const scopeFilterApplied = scopeMode === "global" || scopeMode === "inferred" || scopeMode === "explicit";

          const [ftsResults, vecResults] = await Promise.all([
            db.fullTextSearch(query, Math.min(searchLimit, MAX_RECALL_LIMIT), scope).catch(() => []),
            db.vectorSearch(vector, Math.min(searchLimit, MAX_RECALL_LIMIT), scope).catch(() => []),
          ]);

          const fused = fuseRecall({ vector: vecResults, fts: ftsResults, limit: normalizedLimit });
          const latencyMs = Math.round(performance.now() - t0);

          const memories = fused.order.map((r) => {
            const normalizedImportance = toImportanceRecord(r.row.importance);
            const normalizedLabel = resolveImportanceLabel(normalizedImportance, r.row.importance_label);

            return {
              id: r.row.id,
              text: r.row.text,
              category: r.row.category,
              importance: normalizedImportance ?? null,
              importance_label: normalizedLabel,
              scope: r.row.scope,
              trust_tier: r.row.trust_tier,
              createdAt: r.row.createdAt,
              distance: r.distance,
              score: r.score,
            };
          });

          if (memories.length === 0) {
            return {
              content: [{ type: "text", text: "No relevant memories found." }],
              details: {
                count: 0,
                memories: [],
                receipt: {
                  dbPath: resolvedDbPath,
                  tableName,
                  limit: normalizedLimit,
                  model,
                  latencyMs,
                  ftsCount: ftsResults.length,
                  vecCount: vecResults.length,
                  fusedCount: 0,
                  scopeMode,
                  scope,
                  scopeFilterApplied,
                },
              },
            };
          }

          const lines = memories
            .map((m, i) => {
              const scorePct = (m.score * 100).toFixed(0);
              const preview = m.text.length > 240 ? `${m.text.slice(0, 240)}…` : m.text;
              return `${i + 1}. [${m.category}] ${preview} (${scorePct}%)`;
            })
            .join("\n");

          return {
            content: [{ type: "text", text: `Found ${memories.length} memories:\n\n${lines}` }],
            details: {
              count: memories.length,
              memories,
              receipt: {
                dbPath: resolvedDbPath,
                tableName,
                limit: normalizedLimit,
                model,
                latencyMs,
                ftsCount: ftsResults.length,
                vecCount: vecResults.length,
                fusedCount: memories.length,
                scopeMode,
                scope,
                scopeFilterApplied,
              },
            },
          };
        },
      },
      { name: "memory_recall" },
    );

    // ----------------------------------------------------------------------
    // Tools: memory_store
    // ----------------------------------------------------------------------

    api.registerTool(
      {
        name: "memory_store",
        label: "Memory Store",
        description: "Save important information in long-term memory. Use for preferences, facts, decisions.",
        parameters: Type.Object({
          text: Type.String({ description: "Information to remember" }),
          importance: Type.Optional(Type.Number({ description: "Importance 0-1" })),
          category: Type.Optional(MemoryCategorySchema),
          scope: Type.Optional(Type.String({ description: "Scope hint (optional)" })),
        }),
        async execute(_toolCallId: string, params: unknown) {
          const t0 = performance.now();
          const {
            text,
            importance,
            category = "other",
            scope: scopeInput,
          } = params as { text: string; importance?: number; category?: MemoryCategory; scope?: string };

          if (!embeddings) {
            return {
              content: [
                {
                  type: "text",
                  text: "openclaw-mem-engine is not configured (missing embedding.apiKey / OPENAI_API_KEY).",
                },
              ],
              details: { error: "missing_api_key" },
            };
          }

          const { scope, scopeMode } = resolveScope({ explicitScope: scopeInput, text });
          const normalizedImportance = toImportanceRecord(importance);
          const normalizedLabel = importanceLabel(normalizedImportance);
          const vector = await embeddings.embed(text);
          const id = randomUUID();
          const createdAt = Date.now();

          const row: MemoryRow = {
            id,
            text,
            vector,
            createdAt,
            category,
            trust_tier: "user",
            scope,
            importance_label: normalizedLabel,
          };

          if (typeof normalizedImportance === "number") {
            row.importance = normalizedImportance;
          }

          await db.add(row);

          const latencyMs = Math.round(performance.now() - t0);

          return {
            content: [{ type: "text", text: `Stored memory (${row.category}, ${row.importance_label}): ${id}` }],
            details: {
              action: "created",
              id,
              createdAt,
              category: row.category,
              importance: row.importance ?? null,
              importance_label: row.importance_label,
              scope: row.scope,
              receipt: {
                dbPath: resolvedDbPath,
                tableName,
                model,
                latencyMs,
                scope,
                scopeMode,
                scopeFilterApplied: true,
              },
            },
          };
        },
      },
      { name: "memory_store" },
    );

    // ----------------------------------------------------------------------
    // Tools: memory_forget
    // ----------------------------------------------------------------------

    api.registerTool(
      {
        name: "memory_forget",
        label: "Memory Forget",
        description: "Delete specific memories. GDPR-compliant.",
        parameters: Type.Object({
          query: Type.Optional(Type.String({ description: "Search to find memory" })),
          memoryId: Type.Optional(Type.String({ description: "Specific memory ID" })),
        }),
        async execute(_toolCallId: string, params: unknown) {
          const t0 = performance.now();
          const { query, memoryId } = params as { query?: string; memoryId?: string };

          if (memoryId) {
            await db.deleteById(memoryId);
            const latencyMs = Math.round(performance.now() - t0);
            return {
              content: [{ type: "text", text: `Memory forgotten: ${memoryId}` }],
              details: {
                action: "deleted",
                id: memoryId,
                receipt: { dbPath: resolvedDbPath, tableName, latencyMs },
              },
            };
          }

          // M0: query-based deletion is intentionally NOT automatic.
          // We only return candidates to reduce accidental deletion.
          if (query) {
            if (!embeddings) {
              return {
                content: [
                  {
                    type: "text",
                    text: "openclaw-mem-engine is not configured (missing embedding.apiKey / OPENAI_API_KEY).",
                  },
                ],
                details: { error: "missing_api_key" },
              };
            }

            const vector = await embeddings.embed(query);
            const results = await db.vectorSearch(vector, 5);
            const latencyMs = Math.round(performance.now() - t0);

            if (results.length === 0) {
              return {
                content: [{ type: "text", text: "No matching memories found." }],
                details: {
                  action: "candidates",
                  found: 0,
                  receipt: { dbPath: resolvedDbPath, tableName, model, latencyMs },
                },
              };
            }

            const list = results
              .map((r) => `- ${r.row.id} [${r.row.category}] ${(r.score * 100).toFixed(0)}% ${r.row.text.slice(0, 80)}…`)
              .join("\n");

            return {
              content: [
                {
                  type: "text",
                  text: `Found ${results.length} candidates. Re-run with memoryId to delete:\n\n${list}`,
                },
              ],
              details: {
                action: "candidates",
                found: results.length,
                candidates: results.map((r) => ({
                  id: r.row.id,
                  text: r.row.text,
                  category: r.row.category,
                  score: r.score,
                  createdAt: r.row.createdAt,
                })),
                receipt: { dbPath: resolvedDbPath, tableName, model, latencyMs },
              },
            };
          }

          return {
            content: [{ type: "text", text: "Provide memoryId (or query to list candidates)." }],
            details: { error: "missing_param" },
          };
        },
      },
      { name: "memory_forget" },
    );
  },
};

export default memoryPlugin;
