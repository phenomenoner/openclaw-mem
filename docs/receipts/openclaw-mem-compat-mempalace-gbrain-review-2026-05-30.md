# openclaw-mem compatibility and consolidation review - 2026-05-30

Status: reviewed / recommendation artifact
Requested by: CK
Generated: 2026-05-30 Asia/Taipei, 2026-05-29 UTC
Scope: `openclaw-mem` family against live OpenClaw 2026.5.26, plus current MemPalace/GBrain/reference-project lessons
Topology impact: unchanged. No live config mutation, Gateway restart, backend switch, cron change, push, tag, or release was performed.

## Verdict

The current `openclaw-mem` stack is broadly compatible with OpenClaw 2026.5.26. The live slot owner is `openclaw-mem-engine`; it registers with the current core memory runtime, prompt hook surface, and memory tool contract shape. No P0 crash risk was found in this review.

The real priority is not adding another memory system. The priority is making the current memory stack inspectable and falsifiable before more feature absorption:

1. Fix one live config mismatch: `symbolicCanvas.autoBuild.command` points at `openclaw-mem`, but `openclaw-mem` is not on PATH.
2. Add or promote a single `mem-system verify` style report that names enabled, inert, writing, indexed, stale, and fallback state by lane.
3. Keep GBrain and MemPalace lessons as selective design inputs. Do not import their full product surfaces or broaden writers.

## Live Host Snapshot

OpenClaw:

- CLI/Gateway: OpenClaw 2026.5.26, git/tag `10ad3aa`.
- Gateway probe: reachable via `openclaw gateway status`.
- `openclaw status`: Memory enabled through plugin `openclaw-mem-engine`; plugin compatibility showed none in fast status.
- Update note: host reports an OpenClaw update is available, but this review targets the current 2026.5.26 runtime and does not recommend mixing upgrade work into this line.

`openclaw-mem`:

- Repo HEAD: `04ee01b` (`v1.9.24`, `chore: release v1.9.24`).
- Worktree had pre-existing dirty files under `extensions/openclaw-mem-engine/*`; they were not reverted.
- CLI status via `uv run --python 3.13 --frozen python -m openclaw_mem status --json`: `openclaw_mem=1.9.24`.
- `openclaw-mem` is not currently on shell PATH.
- `gbrain` is not currently on shell PATH.

Live sanitized memory config:

- `plugins.slots.memory = openclaw-mem-engine`.
- `memory-core` and `memory-lancedb` are disabled.
- Retrieval backend: `qdrant-edge`, fallback `lancedb`.
- `autoRecall.enabled=false`, but `autoRecall.routeAuto.enabled=true`.
- `autoCapture.enabled=true`.
- `docsColdLane.enabled=true`, 21 source roots, `ingestOnStart=false`.
- `workingSet.enabled=true`, `persist=false`.
- `symbolicCanvas.autoBuild.enabled=true`, command `openclaw-mem`.
- `gbrainMirror.enabled=true`, `importOnStore=true`, command `/root/.openclaw/workspace/tools/gbrain_mirror_import.sh`.

State size / coverage snapshot:

| Store | Count or size |
|---|---:|
| `observations` | 63,707 rows |
| `docs_chunks` | 86,776 rows |
| `docs_embeddings` | 9,829 rows |
| `episodic_events` | 205,530 rows |
| `episodic_event_embeddings` | 24 rows |
| LanceDB state | 3.4G |
| Qdrant live shard | 28M, symlink-resolved |
| `openclaw-mem.sqlite` | 680M |
| `gbrain-mirror` | 980K |

Interpretation: the engine status surface is not enough by itself. It reports only a small observation-embedding count while docs and episodic lanes have separate coverage. A consolidated verifier needs per-lane coverage and freshness, not one global embedding number.

## Findings

### P1 Must-Fix: symbolic canvas command mismatch

Live config enables symbolic-canvas auto build with `command: "openclaw-mem"`, but the binary is not on PATH. The route-auto and docs cold-lane paths use the safer `uv run --project /root/.openclaw/workspace/openclaw-mem --python 3.13 --frozen python -m openclaw_mem` shape or have fallback logic. `symbolicCanvasAuto.js` currently executes the configured command directly.

Recommendation:

- Either change the live config command/args to the same `uv run ... python -m openclaw_mem` form, after CK approval because it is a live config mutation.
- Or patch `symbolicCanvasAuto.js` to have the same fallback candidate strategy as docs cold lane, then test and restart at a controlled boundary.

Verifier:

```bash
node --test extensions/openclaw-mem-engine/symbolicCanvasAuto.test.mjs
```

Then run one qualified `agent_end` symbolic-canvas smoke after config/code change and confirm a receipt with no `ENOENT`.

### P1: routeAuto is live even while autoRecall is off

The current code registers prompt hook work when either `autoRecall` or `routeAuto` is enabled. With `autoRecall.enabled=false` and `routeAuto.enabled=true`, nontrivial prompts may still shell out through `uv` with a 5s timeout and 2MiB buffer.

Recommendation:

- Keep it only if live route hints are intentional.
- Add a small route-auto latency receipt rollup: p50, p95, timeout/error count, and prompt chars.
- Consider lowering timeout only after data.

### P1: Qdrant Edge is acceptable as active read index, but needs recurring fallback drills

Qdrant Edge has prior evidence of strong latency vs LanceDB on the sampled workload, and the current runtime reports it as active with LanceDB fallback. The bridge still shells out to Python and loads/closes the shard per vector search.

Recommendation:

- Keep Qdrant Edge active as read index/cache, not writer.
- Add a recurring or manual fallback drill: break/move the bridge or shard in fixture config and verify fallback to LanceDB plus receipt.
- Benchmark p95 under concurrent realistic queries before raising recall volume or enabling broader autoRecall.
- Consider a persistent bridge or shard-open cache only if p95 becomes a real gate.

### P1: GBrain mirror should stay experimental and measured

Local GBrain checkout is older than upstream: local wrapper reports `gbrain 0.26.0`; current upstream `package.json` on master reports `0.41.29.0`. The wrapper works, but GBrain doctor reports no embeddings and 0 percent graph/timeline coverage on the local brain. That makes it unsuitable as a promoted recall substrate today.

Recommendation:

- Keep `gbrainMirror` as experimental write-through mirror only.
- Do not use it as truth owner.
- Before keeping `importOnStore=true` long term, measure mirror success, import latency, and failure count for one day.
- Any disable/enable change requires CK approval because it changes live write side effects.

### P1: docs cold lane should be tightened by coverage and source-root reporting

Docs cold lane is valuable and already indexed, but its source roots are broad. A docs search for the compatibility query returned vector hits with empty FTS top-k, which is a useful warning: lexical/date/path retrieval may still miss expected docs.

Recommendation:

- Add a docs-index coverage report: root count, indexed files, stale files, chunks, embedding coverage, FTS-only hit checks, and top misses.
- Keep docs cold lane as cited cold evidence, not bootstrap or durable memory.
- Do not narrow source roots without a small regression query set.

### P1: working set is enabled but mostly inert while autoRecall is off

`workingSet.enabled=true` in config can mislead operators because Working Set injection happens inside the full autoRecall/Proactive Pack path. With autoRecall off, it is effectively dormant for prompt injection.

Recommendation:

- Split status wording into `configured`, `active this turn`, and `inert because autoRecall=false`.
- Do not promote Working Set until A/B shows quality lift, not only token reduction.

### P1: no-write/mutation audit is now necessary

Some "read-like" surfaces still write receipts or shadow logs. A `pack --trace` smoke in this review produced a `pack_lifecycle_shadow_log` append (`writes_shadow_log=1`) while not mutating durable truth. That is acceptable as Observe, but it proves the need for explicit no-write accounting.

Recommendation:

- Add a fixture no-write audit for routeAuto, docsColdLane, workingSet, symbolicCanvas, gbrainMirror, pack shadow, and Qdrant fallback paths.
- The report must distinguish canonical memory writes, Observe receipts, shadow logs, mirror writes, and temp files.

### P2: plugin/version readback drift

Repo/package reports `openclaw-mem=1.9.24`, but enabled plugin table still shows sidecar `1.9.11` and engine `0.0.9`. This is not a runtime compatibility break, but it weakens operator readback confidence.

Recommendation:

- Align manifest/package versions or document the split clearly: product package version vs extension package version.

## External Design Review

Primary sources checked on 2026-05-29 UTC:

- MemPalace `pyproject.toml`: <https://raw.githubusercontent.com/MemPalace/mempalace/main/pyproject.toml>
- MemPalace README: <https://raw.githubusercontent.com/MemPalace/mempalace/main/README.md>
- GBrain `package.json`: <https://raw.githubusercontent.com/garrytan/gbrain/master/package.json>
- GBrain README: <https://raw.githubusercontent.com/garrytan/gbrain/master/README.md>

Current external snapshot:

- MemPalace main reports version `3.3.6`, Python `>=3.9`, Chroma default backend, local embedding dependencies, verbatim storage, wings/rooms/drawers, temporal KG, MCP tools, autosave hooks, and `sweep` for per-message drawers.
- GBrain master reports version `0.41.29.0`, Bun `>=1.3.10`, PGLite/Postgres/pgvector architecture, OpenClaw plugin API `>=2026.4.0`, hybrid search, synthesized `think` answers with citations/gap analysis, graph signals, schema packs, jobs, MCP/OAuth, and many skills.

Adoption decisions:

| Source idea | Decision | Local interpretation |
|---|---|---|
| MemPalace verbatim/per-message storage | Absorb narrowly | Strengthen episodic semantic lane and per-message A/B fixtures. Evidence only, no auto-promotion. |
| MemPalace wings/rooms/drawers naming | Reject/inspiration only | Existing memory-strata model is clearer for `openclaw-mem`. |
| MemPalace temporal KG | Absorb as bounded validity/invalidation ideas | Use for graph/provenance and temporal intent, not as a new truth owner. |
| MemPalace Chroma backend | Reject | Current LanceDB/Qdrant boundary is enough. |
| MemPalace broad MCP tools | Reject | Avoid tool sprawl unless it replaces an existing surface. |
| GBrain synthesis/gap analysis | Absorb | Highest value: Pack should say known/stale/conflicting/missing, not only selected chunks. |
| GBrain graph signals | Absorb experimentally | Add trace-only adjacency/corroboration/crowding signals before ranking changes. |
| GBrain schema packs | Consolidate as mini-contract | Version local strata/type registry. Do not import agent-authored schema mutation. |
| GBrain jobs/minions | Keep restricted | Current sidecar helper family boundary is right. |
| GBrain MCP/OAuth/company brain | Reject for core | Out of scope for local-first `openclaw-mem` unless product direction changes. |
| GBrain mirror | Keep experimental | Mirror/substrate only, not truth owner. |

## Recommended Roadmap

### Slice 1: `mem-system verify` consolidated status

Goal: one read-only report that answers:

- Which lanes are enabled, inert, or writing?
- Which lane owns durable truth?
- What optional helpers are active but unverified?
- What changed since last receipt?
- What is embedding/index coverage by lane?
- Can Qdrant fail over to LanceDB?
- Are `gbrainMirror`, `routeAuto`, and symbolic canvas actually doing anything?

This is the highest-ROI next slice because it prevents memory theater before adding more memory.

### Slice 2: Fix symbolic canvas command or fallback

After CK approval for config/code mutation, make symbolic-canvas auto build use the same robust CLI invocation pattern as routeAuto/docs cold lane. Verify with targeted node tests and one live qualified receipt.

### Slice 3: Retrieval A/B harness

Use 20 to 30 CK-real queries:

- baseline engine recall
- Qdrant Edge vs LanceDB
- docs cold lane
- episodic lexical/hybrid
- graph-assisted route
- optional GBrain consult

Metrics: hit@1, hit@5, citation correctness, stale-hit rate, p50/p95 latency, prompt chars, and write side effects.

### Slice 4: Pack gap analysis

Add trace/report fields for:

- known evidence
- stale evidence
- contradicted evidence
- uncited evidence
- missing coverage
- why current evidence is insufficient

This is the most valuable GBrain design to absorb while preserving Store/Pack/Observe.

### Slice 5: Verbatim episodic consolidation

Run MemPalace-style per-message retrieval A/B against grouped episodic sessions. Promote only if raw-trail questions improve without context bloat or privacy leakage.

## Approval Boundaries

Ask CK before:

- OpenClaw config mutation
- Gateway restart
- enabling/disabling `gbrainMirror`
- enabling autoRecall
- changing Qdrant/LanceDB backend
- changing docs source roots
- running live docs/episodes/graph ingest or lifecycle writeback
- data migration, snapshot restore, push, tag, release, auth/permission change, or external posting

## Verification Receipts

Commands run by parent or review lanes:

```bash
openclaw gateway status
openclaw status
openclaw plugins list
uv run --python 3.13 --frozen python -m openclaw_mem status --json
node --test extensions/openclaw-mem-engine/docsColdLane.test.mjs extensions/openclaw-mem-engine/coreRuntimeRegistration.test.mjs extensions/openclaw-mem-engine/retrievalBackendBoundary.test.mjs extensions/openclaw-mem-engine/retrievalRuntimeRouter.test.mjs extensions/openclaw-mem-engine/qdrantEdgeRuntimeAdapter.test.mjs extensions/openclaw-mem-engine/gbrainMirror.test.mjs
uv run --python 3.13 --frozen pytest -q tests/test_gbrain_sidecar.py tests/test_mem_engine_docs_cold_lane.py tests/test_mem_engine_write_authority.py tests/test_mem_engine_route_auto_hook.py tests/test_mem_engine_scope_budget.py tests/test_workingset_multipass_eval.py
uv run --python 3.13 --frozen python -m openclaw_mem docs search --help
uv run --python 3.13 --frozen python -m openclaw_mem gbrain-sidecar --help
/root/.openclaw/workspace/tools/gbrain_mirror_import.sh --version
/root/.openclaw/workspace/tools/gbrain_mirror_import.sh doctor
git diff --check -- extensions/openclaw-mem-engine/coreRuntimeRegistration.test.mjs extensions/openclaw-mem-engine/docsColdLane.js extensions/openclaw-mem-engine/docsColdLane.test.mjs extensions/openclaw-mem-engine/index.ts extensions/openclaw-mem-engine/openclaw.plugin.json
```

Results:

- Node focused tests: 32 passed.
- Python focused tests: 38 passed.
- Diff check on pre-existing dirty engine files: passed.
- GBrain wrapper reports local `gbrain 0.26.0`.
- GBrain doctor: health 80/100, with warnings for no embeddings and 0 percent graph/timeline coverage.

## Residual Uncertainty

- No live config was changed, so symbolic-canvas fix is recommended but not applied.
- No Gateway restart occurred.
- No Qdrant failure drill was performed in this pass.
- No live autoCapture/gbrainMirror one-day soak was performed.
- External benchmark claims from MemPalace/GBrain were treated as upstream claims, not local proof.

## Closure

Current level: L2/L3 review artifact. The artifact is written and verified by file readback. Runtime topology is unchanged. The total goal is not "memory stack optimized"; it is "review complete with next optimization gates identified." The next owner should be Lyria through a bounded implementation slice, starting with `mem-system verify` or symbolic-canvas command hardening after CK approval for live config/code change.
