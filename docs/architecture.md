# Architecture (Design)

`openclaw-mem` is a **local-first memory sidecar** for OpenClaw.

It does **not** replace OpenClaw’s canonical memory slot/backends. Instead, it:
- captures high-signal tool outcomes to durable local storage,
- makes recall **cheap and auditable**,
- adds governance (importance, receipts, redaction),
- and (planned) provides **clean, minimal context bundles** for each request.

Status tags used below: **DONE / PARTIAL / ROADMAP**.

## Philosophy (small, but non-negotiable)

Agent “self/continuity” is largely a narrative constructed from memory. For systems, that continuity should be treated as a **designed interface**: allow narrative, but anchor it in **auditable evidence** (provenance + trust tiers + citations + receipts) so we don’t amplify confident self-deception or poisoned inputs.

## Non-goals

- Becoming the global “memory core” for OpenClaw.
- Auto-writing over operator-authored fields.
- Forcing embeddings/LLM dependence (LLM-assisted features must be opt-in).

## Data flow (today) — **DONE**

```text
OpenClaw tool results
  → JSONL capture
  → harvest/ingest
  → SQLite ledger (FTS + structured columns)
  → progressive recall (search → timeline → get)
```

### Key artifacts

- **Raw observations JSONL**: append-only “what just happened” events (tool outcomes).
- **SQLite DB ledger**: curated, queryable memory with audit metadata.
- **(Planned) Observational log**: a compact, timestamped *derived* layer (“observations about observations”) designed to be:
  - stable-prefix / cache-friendly,
  - importance-scored (log-levels),
  - easy to diff + debug (text-first).
- **Archive + index**: optional rotation + stable pointers for operators.

## Modules

### 1) Capture — **PARTIAL**

- Source: OpenClaw tool results (and optionally message events).
- Output: JSONL observations (append-only).
- Design constraints:
  - safe-by-default redaction
  - bounded payloads
  - stable schemas (upgrade-safe)

### 2) Ingest / Harvest — **DONE**

- Converts JSONL observations into a queryable SQLite ledger.
- Must be **fail-open**: a broken scorer or malformed record must not break ingest.
- Must be **non-destructive**: never overwrite existing operator fields.

### 3) Importance grading (MVP v1) — **PARTIAL**

- Goal: governance, not “smart recall”.
- Deterministic scorer (`heuristic-v1`) fills missing `detail_json.importance`.
- Thresholds (current MVP v1):
  - `>= 0.80` must_remember
  - `>= 0.50` nice_to_have
  - else ignore
- Unset/legacy importance is treated as **unknown** (do not auto-filter by default).

### 4) Lifecycle manager (retain / decay / archive / revive) — **ROADMAP**

Goal: keep memory **high-signal** over long horizons via *use-based* retention.

Core mechanism:
- Each durable record maintains a **reference timestamp** (`last_used_at`) updated only when the record is **actually used**.
- Default “used” signal (cheap + auditable): the record is selected into the final Context Packer bundle (cited as `recordRef`).
- A scheduled lifecycle job applies **soft archive** (reversible) instead of hard delete.

Design notes:
- Do **not** count bulk preload as “use” (otherwise everything stays forever).
- Consider tracking two signals later:
  - `last_retrieved_at` (candidate hit)
  - `last_included_at` (final bundle inclusion; default)
- Decay policy should be tiered (example): `P0` never auto-archive, `P1` 90d, `P2` 30d — but thresholds are tunable.
- Trust is independent: frequent use does **not** promote `untrusted → trusted`.

Receipts:
- `pack --trace` should report which records were “refreshed” this run.
- Lifecycle job should emit an aggregate-only summary (archived counts by tier/trust/importance + reasons).

### 5) Context Packer — **ROADMAP**

Problem: multi-project operation tends to send **too much irrelevant context** to the LLM.

Goal: given a request, produce a **small, clean context bundle** that is:
- relevant to the request,
- biased toward high-importance durable facts,
- auditable (includes citations),
- and cheap (bounded size).

Proposed input signals:
- request text + optional scope tag
- recent session snippets (hot)
- SQLite facts/tasks (warm)
- (optional) graph neighborhood (see next section)

Proposed output (to the LLM):
- 5–15 lines of “relevant state”
- up to N short summaries (not raw logs)
- 1–3 citations (record IDs / URLs), **no private paths**

### Layered context contract (L0/L1/L2) — design hook

Borrow the *pattern* (not the implementation) of layered loading:

- **L0 (abstract)**: 1 line, cheap filtering ("what is this?")
- **L1 (overview)**: short summary + navigation hints ("what’s inside + where to look next")
- **L2 (detail)**: raw record / full tool output / original artifact

The packer should prefer:
1) retrieve/filter by L0/L1,
2) include mostly L1 in the bundle,
3) only pull L2 when strictly necessary (and still bounded + redaction-safe).

This keeps bundles small, reduces token noise, and makes results easier to debug.

### Retrieval trajectory receipts (trace) — non-negotiable for ops

Packing must be observable. Every `pack` run should be able to emit a trace that answers:
- what lanes were searched (hot/warm/cold; and "resources/memory/skills" when applicable)
- which candidates were considered
- why each item was **included/excluded** (importance, trust tier, score, cap, recency, scope)

Proposed interface (draft):
- `openclaw-mem pack --query "..." --budget-tokens <n> --json --trace`
  - `--json` returns the bundle
  - `--trace` returns a machine-readable receipt for audits/debugging (redaction-safe; no raw content)

#### Observational-memory mode (derived, cache-friendly)

A promising variant of Context Packer is to keep a *stable* two-block context window:

1) **OBSERVATIONS**: a compact, timestamped, importance-scored observation log (text-first).
2) **RAW BUFFER**: the most recent uncompressed turns.

An “observer” process periodically compresses RAW BUFFER → OBSERVATIONS once the buffer crosses a size threshold; an infrequent “reflector” prunes low-value observations.

This structure is designed to keep the prompt prefix stable (better caching) while still allowing continuous operation.

See also: [Thought-links →](thought-links.md)

This module is the bridge between “memory governance” and “prompt cleanliness”.

### 6) Graph semantic memory — **ROADMAP**

Goal: support **idea → project matching** and path-justified recommendations.

We represent durable knowledge as typed entities and edges, e.g.:
- entities: `Project`, `Repo`, `Decision`, `Concept`, `Tool`, `Person` (redacted)
- edges: `USES`, `BLOCKED_BY`, `RELATES_TO`, `EVALUATES`, `DECIDES`, `MENTIONS`

Key requirements:
- local-first
- typed edges + traversal
- path justification in outputs (why a recommendation was made)

Storage options (behind an interface):
- **Kuzu** (fast + typed graph; evaluate longevity risk)
- SQLite adjacency lists (simpler; less expressive)
- other graph stores (future)

The graph is optional: the Context Packer should degrade gracefully without it.

## Integration with OpenClaw memory backends

OpenClaw’s memory backend (e.g. `memory-lancedb`) and `openclaw-mem` solve different problems:
- backend auto-recall: *semantic relevance right now*
- `openclaw-mem`: *durable governance + auditable receipts + operator workflows*

### Recommendation (today)

- Keep OpenClaw memory backend as canonical.
- Use `openclaw-mem` for capture + harvest + importance + triage.

### Recommendation (future, after Context Packer exists)

- Consider disabling backend **autoRecall** and instead feed the agent a small, deterministic `openclaw-mem pack` bundle per request.
- This improves noise control and reduces token waste, but requires explicit integration (hook/tool) so recall doesn’t disappear.

## Research tracks (delegate to GitHub scouting)

- Graph store choice & longevity (Kuzu and alternatives)
- Extraction strategies for entities/edges (heuristic first; LLM optional)
- Prompt cleanliness patterns: relevance filtering, bounded summaries, citations
