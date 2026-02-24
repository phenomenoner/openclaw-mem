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

function importanceLabel(importance: number): string {
  const x = Math.max(0, Math.min(1, importance));
  if (x >= 0.9) return "high";
  if (x >= 0.7) return "medium";
  if (x >= 0.4) return "low";
  return "trivial";
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
  importance: number;
  importance_label: string;
  scope: string;
  trust_tier: string;
};

type RecallResult = {
  row: Omit<MemoryRow, "vector">;
  distance: number;
  score: number;
};

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
      importance_label: "none",
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

  async vectorSearch(vector: number[], limit: number): Promise<RecallResult[]> {
    await this.ensureInitialized();

    const results = await this.table!.vectorSearch(vector).limit(limit).toArray();

    return results.map((r: any) => {
      const distance = typeof r._distance === "number" ? r._distance : 0;
      const score = 1 / (1 + distance);
      return {
        row: {
          id: String(r.id),
          text: String(r.text ?? ""),
          createdAt: Number(r.createdAt ?? 0),
          category: (r.category ?? "other") as MemoryRow["category"],
          importance: Number(r.importance ?? 0),
          importance_label: String(r.importance_label ?? ""),
          scope: String(r.scope ?? ""),
          trust_tier: String(r.trust_tier ?? ""),
        },
        distance,
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

    const apiKey = cfg.embedding?.apiKey ?? process.env.OPENAI_API_KEY;

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
          limit: Type.Optional(Type.Number({ description: "Max results (default: 5)" })),
        }),
        async execute(_toolCallId: string, params: unknown) {
          const t0 = performance.now();
          const { query, limit = 5 } = params as { query: string; limit?: number };

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
          const results = await db.vectorSearch(vector, Math.max(1, Math.min(50, limit)));

          const latencyMs = Math.round(performance.now() - t0);

          if (results.length === 0) {
            return {
              content: [{ type: "text", text: "No relevant memories found." }],
              details: {
                count: 0,
                receipt: { dbPath: resolvedDbPath, tableName, limit, model, latencyMs },
              },
            };
          }

          const lines = results
            .map((r, i) => {
              const scorePct = (r.score * 100).toFixed(0);
              const preview = r.row.text.length > 240 ? `${r.row.text.slice(0, 240)}…` : r.row.text;
              return `${i + 1}. [${r.row.category}] ${preview} (${scorePct}%)`;
            })
            .join("\n");

          return {
            content: [{ type: "text", text: `Found ${results.length} memories:\n\n${lines}` }],
            details: {
              count: results.length,
              memories: results.map((r) => ({
                id: r.row.id,
                text: r.row.text,
                category: r.row.category,
                importance: r.row.importance,
                importance_label: r.row.importance_label,
                scope: r.row.scope,
                trust_tier: r.row.trust_tier,
                createdAt: r.row.createdAt,
                distance: r.distance,
                score: r.score,
              })),
              receipt: {
                dbPath: resolvedDbPath,
                tableName,
                limit,
                model,
                latencyMs,
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
          importance: Type.Optional(Type.Number({ description: "Importance 0-1 (default: 0.7)" })),
          category: Type.Optional(MemoryCategorySchema),
        }),
        async execute(_toolCallId: string, params: unknown) {
          const t0 = performance.now();
          const {
            text,
            importance = 0.7,
            category = "other",
          } = params as { text: string; importance?: number; category?: MemoryCategory };

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

          const vector = await embeddings.embed(text);
          const id = randomUUID();
          const createdAt = Date.now();
          const imp = Math.max(0, Math.min(1, importance));

          const row: MemoryRow = {
            id,
            text,
            vector,
            createdAt,
            category,
            importance: imp,
            importance_label: importanceLabel(imp),
            scope: "global",
            trust_tier: "user",
          };

          await db.add(row);

          const latencyMs = Math.round(performance.now() - t0);

          return {
            content: [{ type: "text", text: `Stored memory (${row.category}, ${row.importance_label}): ${id}` }],
            details: {
              action: "created",
              id,
              createdAt,
              category: row.category,
              importance: row.importance,
              importance_label: row.importance_label,
              receipt: { dbPath: resolvedDbPath, tableName, model, latencyMs },
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
