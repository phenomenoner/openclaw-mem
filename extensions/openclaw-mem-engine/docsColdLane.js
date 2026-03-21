import fs from "node:fs/promises";
import path from "node:path";
import { execFile as execFileCb } from "node:child_process";
import { promisify } from "node:util";

const execFile = promisify(execFileCb);

function escapeRegex(text) {
  return text.replace(/[|\\{}()[\]^$+?.]/g, "\\$&");
}

function globToRegExp(glob) {
  const src = String(glob || "").trim();
  if (!src) {
    return /^.*\.md$/i;
  }

  let out = "^";
  for (let i = 0; i < src.length; i += 1) {
    const ch = src[i];
    if (ch === "*") {
      const next = src[i + 1];
      const next2 = src[i + 2];
      // Support "**/" matching zero or more directory segments so root files match too.
      if (next === "*" && next2 === "/") {
        out += "(?:.*\\/)?";
        i += 2;
      } else if (next === "*") {
        out += ".*";
        i += 1;
      } else {
        out += "[^/]*";
      }
      continue;
    }
    if (ch === "?") {
      out += "[^/]";
      continue;
    }
    if (ch === "/") {
      out += "\\/";
      continue;
    }
    out += escapeRegex(ch);
  }
  out += "$";
  return new RegExp(out, "i");
}

function toPosixRel(root, target) {
  const rel = path.relative(root, target);
  return rel.split(path.sep).join("/");
}

function normalizeScopeToken(scope) {
  return String(scope || "")
    .trim()
    .toLowerCase()
    .replace(/^\[?(iso|scope):/i, "")
    .replace(/^\/+/, "")
    .replace(/\]+$/, "")
    .trim();
}

function shortScopeKey(scope) {
  const normalized = normalizeScopeToken(scope);
  if (!normalized) return "";
  return normalized.split(/[/:]/)[0] || normalized;
}

function coerceArray(value, fallback = []) {
  if (!Array.isArray(value)) return fallback;
  return value
    .map((item) => (typeof item === "string" ? item.trim() : ""))
    .filter(Boolean);
}

async function walkMarkdownFiles(rootAbs, limit) {
  const out = [];
  const stack = [rootAbs];

  while (stack.length > 0 && out.length < limit) {
    const current = stack.pop();
    if (!current) break;

    let entries;
    try {
      entries = await fs.readdir(current, { withFileTypes: true });
    } catch {
      continue;
    }

    entries.sort((a, b) => a.name.localeCompare(b.name));

    for (const entry of entries) {
      if (out.length >= limit) break;
      const abs = path.join(current, entry.name);
      if (entry.isDirectory()) {
        stack.push(abs);
        continue;
      }
      if (!entry.isFile()) continue;
      if (!entry.name.toLowerCase().endsWith(".md")) continue;
      out.push(abs);
    }
  }

  out.sort();
  return out;
}

export async function collectDocsFiles({ sourceRoots, sourceGlobs, maxFiles = 5000 }) {
  const roots = coerceArray(sourceRoots);
  const globs = coerceArray(sourceGlobs, ["**/*.md"]);
  const globRegexes = globs.map(globToRegExp);

  const files = [];
  const missingRoots = [];
  const seen = new Set();

  for (const rootRaw of roots) {
    const rootAbs = path.resolve(rootRaw);
    let stat;
    try {
      stat = await fs.stat(rootAbs);
    } catch {
      missingRoots.push(rootAbs);
      continue;
    }

    const candidates = [];
    if (stat.isFile()) {
      if (rootAbs.toLowerCase().endsWith(".md")) {
        candidates.push(rootAbs);
      }
    } else if (stat.isDirectory()) {
      const walked = await walkMarkdownFiles(rootAbs, Math.max(1, maxFiles));
      candidates.push(...walked);
    }

    for (const candidateAbs of candidates) {
      if (files.length >= maxFiles) break;
      const rel = stat.isFile() ? path.basename(candidateAbs) : toPosixRel(rootAbs, candidateAbs);
      const matches = globRegexes.some((re) => re.test(rel));
      if (!matches) continue;
      const key = path.resolve(candidateAbs);
      if (seen.has(key)) continue;
      seen.add(key);
      files.push(key);
    }
  }

  files.sort();

  return {
    files,
    missingRoots,
    globs,
  };
}

function parseJsonLoose(text) {
  const raw = String(text || "").trim();
  if (!raw) return null;

  try {
    return JSON.parse(raw);
  } catch {
    // Continue.
  }

  // Try extracting a JSON substring (handles logs before/after a JSON block).
  const first = raw.search(/[{[]/);
  if (first >= 0) {
    const last = Math.max(raw.lastIndexOf("}"), raw.lastIndexOf("]"));
    if (last > first) {
      const candidate = raw.slice(first, last + 1).trim();
      try {
        return JSON.parse(candidate);
      } catch {
        // Continue.
      }
    }
  }

  const lines = raw.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  for (let i = lines.length - 1; i >= 0; i -= 1) {
    const line = lines[i];
    if (!line.startsWith("{") && !line.startsWith("[")) continue;
    try {
      return JSON.parse(line);
    } catch {
      // Continue.
    }
  }

  return null;
}

async function runOpenclawMemJson(args, timeoutMs = 240000) {
  try {
    const { stdout, stderr } = await execFile("openclaw-mem", args, {
      timeout: timeoutMs,
      maxBuffer: 8 * 1024 * 1024,
    });

    const payload = parseJsonLoose(stdout) ?? parseJsonLoose(stderr);
    return {
      ok: true,
      payload,
      stdout: String(stdout || ""),
      stderr: String(stderr || ""),
    };
  } catch (err) {
    const stdout = String(err?.stdout || "");
    const stderr = String(err?.stderr || "");
    const payload = parseJsonLoose(stdout) ?? parseJsonLoose(stderr);
    return {
      ok: false,
      payload,
      stdout,
      stderr,
      error: err?.code === "ENOENT"
        ? "openclaw-mem_not_found"
        : String(err?.message || err),
    };
  }
}

function toNumber(value, fallback = 0) {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const n = Number(value);
    if (Number.isFinite(n)) return n;
  }
  return fallback;
}

function clipSnippet(text, maxChars) {
  const compact = String(text || "").replace(/\s+/g, " ").trim();
  if (!compact) return "";
  const cap = Math.max(80, Math.min(1200, Math.floor(toNumber(maxChars, 280))));
  return compact.length > cap ? `${compact.slice(0, cap)}…` : compact;
}

function matchesScope(row, scope, strategy, scopeMap) {
  const normalizedScope = normalizeScopeToken(scope);
  if (!normalizedScope || normalizedScope === "global") return true;

  const repo = String(row.repo || "").toLowerCase();
  const docPath = String(row.path || "").toLowerCase();

  if (strategy === "none") return true;

  if (strategy === "repo_prefix") {
    const key = shortScopeKey(normalizedScope);
    if (!key) return true;
    return repo === key || docPath.startsWith(`${key}/`);
  }

  if (strategy === "path_prefix") {
    const prefix = normalizedScope.replace(/:/g, "/");
    return docPath.startsWith(`${prefix}/`) || docPath === prefix || docPath.includes(`/${prefix}/`);
  }

  if (strategy === "map") {
    const direct = scopeMap?.[normalizedScope] || [];
    const key = shortScopeKey(normalizedScope);
    const fallback = scopeMap?.[key] || [];
    const prefixes = [...direct, ...fallback]
      .map((item) => String(item || "").trim().toLowerCase().replace(/^\/+/, ""))
      .filter(Boolean);

    if (prefixes.length === 0) return false;

    return prefixes.some((prefix) => repo === prefix || docPath.startsWith(`${prefix}/`) || docPath === prefix);
  }

  return true;
}

function normalizeDocsHit(row, maxSnippetChars) {
  const recordRef = String(row.recordRef || `doc:${row.repo || "local"}:${row.path || ""}#${row.chunk_id || row.id || "chunk"}`);
  const id = String(row.id ?? recordRef);
  const score = Number.isFinite(Number(row.rrf_score)) ? Number(row.rrf_score) : toNumber(row.score, 0);

  return {
    id,
    recordRef,
    title: String(row.title || "").trim(),
    headingPath: String(row.heading_path || "").trim(),
    text: clipSnippet(row.text, maxSnippetChars),
    path: String(row.path || "").trim(),
    repo: String(row.repo || "local").trim(),
    docKind: String(row.doc_kind || "doc").trim(),
    score,
    match: Array.isArray(row.match)
      ? row.match.filter((item) => typeof item === "string")
      : [],
    source_kind: "operator",
    trust_tier: "operator",
  };
}

export async function docsIngestWithCli({
  sqlitePath,
  sourceRoots,
  sourceGlobs,
  maxChunkChars,
  embedOnIngest,
}) {
  const roots = coerceArray(sourceRoots);
  const globs = coerceArray(sourceGlobs, ["**/*.md"]);

  const collected = await collectDocsFiles({
    sourceRoots: roots,
    sourceGlobs: globs,
    maxFiles: 5000,
  });

  const receipt = {
    ok: true,
    sqlitePath,
    sourceRoots: roots,
    sourceGlobs: globs,
    filesMatched: collected.files.length,
    missingRoots: collected.missingRoots,
    batches: 0,
    files_ingested: 0,
    chunks_total: 0,
    chunks_inserted: 0,
    chunks_updated: 0,
    chunks_unchanged: 0,
    chunks_deleted: 0,
    embedded: 0,
  };

  if (roots.length === 0) {
    return {
      receipt: {
        ...receipt,
        ok: false,
        skipped: true,
        skipReason: "no_source_roots",
      },
      error: "no_source_roots",
    };
  }

  if (collected.files.length === 0) {
    return {
      receipt: {
        ...receipt,
        skipped: true,
        skipReason: "no_matching_markdown",
      },
      error: null,
    };
  }

  const cap = Math.max(200, Math.min(4000, Math.floor(toNumber(maxChunkChars, 1400))));
  const batchSize = 120;
  const errors = [];

  for (let i = 0; i < collected.files.length; i += batchSize) {
    const batch = collected.files.slice(i, i + batchSize);
    receipt.batches += 1;

    const args = ["--db", sqlitePath, "--json", "docs", "ingest"];
    for (const file of batch) {
      args.push("--path", file);
    }
    args.push("--max-chars", String(cap));
    args.push(embedOnIngest === false ? "--no-embed" : "--embed");

    const result = await runOpenclawMemJson(args);
    if (!result.ok && !result.payload) {
      errors.push(result.error || "ingest_failed");
      continue;
    }

    const payload = result.payload && typeof result.payload === "object" ? result.payload : {};
    receipt.files_ingested += toNumber(payload.files_ingested, 0);
    receipt.chunks_total += toNumber(payload.chunks_total, 0);
    receipt.chunks_inserted += toNumber(payload.chunks_inserted, 0);
    receipt.chunks_updated += toNumber(payload.chunks_updated, 0);
    receipt.chunks_unchanged += toNumber(payload.chunks_unchanged, 0);
    receipt.chunks_deleted += toNumber(payload.chunks_deleted, 0);
    receipt.embedded += toNumber(payload.embedded, 0);

    if (payload.embed_error) {
      errors.push(String(payload.embed_error));
    }
    if (!result.ok) {
      errors.push(result.error || "ingest_failed");
    }
  }

  if (errors.length > 0) {
    receipt.ok = false;
  }

  return {
    receipt,
    error: errors.length > 0 ? errors.slice(0, 3).join("; ") : null,
  };
}

export async function docsSearchWithCli({
  sqlitePath,
  query,
  scope,
  limit,
  maxSnippetChars,
  searchFtsK,
  searchVecK,
  searchRrfK,
  scopeMappingStrategy,
  scopeMap,
}) {
  const trimmedQuery = String(query || "").trim();
  if (!trimmedQuery) {
    return {
      items: [],
      filteredByScope: 0,
      rawCandidates: 0,
      scopedCandidates: 0,
      error: "empty_query",
    };
  }

  const boundedLimit = Math.max(1, Math.min(10, Math.floor(toNumber(limit, 3))));
  const normalizedScope = normalizeScopeToken(scope);
  const hasScopedQuery = Boolean(normalizedScope && normalizedScope !== "global");
  const scopedOverfetchLimit = hasScopedQuery
    ? Math.max(
        boundedLimit,
        Math.min(
          50,
          Math.max(
            boundedLimit * 5,
            Math.floor(toNumber(searchFtsK, 20)),
            Math.floor(toNumber(searchVecK, 20)),
          ),
        ),
      )
    : boundedLimit;

  const args = [
    "--db",
    sqlitePath,
    "--json",
    "docs",
    "search",
    trimmedQuery,
    "--limit",
    String(scopedOverfetchLimit),
    "--fts-k",
    String(Math.max(scopedOverfetchLimit, Math.floor(toNumber(searchFtsK, 20)))),
    "--vec-k",
    String(Math.max(scopedOverfetchLimit, Math.floor(toNumber(searchVecK, 20)))),
    "--k",
    String(Math.max(1, Math.floor(toNumber(searchRrfK, 60)))),
  ];

  const result = await runOpenclawMemJson(args);
  if (!result.ok && !result.payload) {
    return {
      items: [],
      filteredByScope: 0,
      rawCandidates: 0,
      scopedCandidates: 0,
      error: result.error || "docs_search_failed",
    };
  }

  const payload = result.payload && typeof result.payload === "object" ? result.payload : {};
  const rawRows = Array.isArray(payload.results) ? payload.results : [];

  const strategy = ["none", "repo_prefix", "path_prefix", "map"].includes(scopeMappingStrategy)
    ? scopeMappingStrategy
    : "repo_prefix";

  const filtered = hasScopedQuery
    ? rawRows.filter((row) => matchesScope(row, normalizedScope, strategy, scopeMap))
    : rawRows;

  const items = filtered
    .slice(0, boundedLimit)
    .map((row) => normalizeDocsHit(row, maxSnippetChars));

  return {
    items,
    filteredByScope: hasScopedQuery ? Math.max(0, rawRows.length - filtered.length) : 0,
    rawCandidates: rawRows.length,
    scopedCandidates: filtered.length,
    error: result.ok ? null : result.error || "docs_search_failed",
  };
}

// Internal exports for unit tests (not part of the public plugin surface).
export const __private__ = {
  globToRegExp,
  normalizeScopeToken,
  matchesScope,
};
