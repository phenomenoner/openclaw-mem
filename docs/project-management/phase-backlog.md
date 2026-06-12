# Phase backlog

Source: `D:\Warehouse\Research\Claude_Discuss\OpenClaw-mem\02-整合優化-Phase規劃與Backlog.md` v1.1, 2026-06-12.

Purpose: complete file-driven coverage of the phase plan before implementation.

## Phase strategy

Product direction: governance niche first, integration route second. Do not compete head-on as a generic memory/recall layer.

Strategic axes:

- S1 positioning convergence: story, labs freeze, naming, docs shape.
- S2 integration entry: MCP server, hooks, ContextPack file contract, quickstart.
- S3 evidence weaponization: standard retrieval benchmarks plus MemGov-Bench.
- S4 retrieval catch-up: rerank, decay v2, entity linking lite, routing.
- S5 governance depth: trust tiers, conflict detection, learning records, governed writeback.

Immediate cut line:

- P1-2, P1-9, and P0-4 are the first operating gate.
- P0-8 and P1-8 are the next host-safety gate.
- P1-1 follows once contract fixtures stop drifting.

## Phase overview

| Phase | Name | Suggested window | Core delivery | Status |
|---|---|---|---|
| P0 | Convergence and foundation | 2 weeks | labs freeze, docs reorg, naming, CI baseline, KPI baseline | todo |
| P1 | Integration base | 4 weeks | MCP v1, ContextPack v1 compatibility, file contract producer, fixtures, hooks, quickstart | released-v1.9.27 |
| P2 | Retrieval catch-up and public scores | 4-6 weeks | rerank, decay v2, LongMemEval/LoCoMo results | todo |
| P3 | Governance depth and governance benchmark | 4-6 weeks | trust tiers GA, conflict detection, MemGov-Bench v1, Self Curator write channel | todo |
| P4 | Ecosystem integration and growth | continuous | harness channel B, lancedb-pro governance plugin, web viewer, launch | todo |

## P0 - Convergence and foundation

Goal: turn the research playground into a product core plus explicit labs area.

Exit criteria: a new visitor can explain the product in 5 minutes; core module list is <= 15; CI is green; KPI baseline is recorded.

| ID | Priority | Size | Status | Delivery | Acceptance |
|---|---:|---:|---|---|---|
| P0-1 | P0 | M | todo | Labs freeze, `core` vs `experimental/labs`, and legacy gateway deprecation plan. | Core modules <= 15; labs README; compatibility shim; README/CHANGELOG deprecation and replacement path. |
| P0-2 | P0 | S | todo | Docs reorg into user docs, specs, archive. | User docs <= 10; any user doc reachable in <= 2 clicks; archive excluded from navigation. |
| P0-3 | P0 | S | decided-doc-pass-needed | Keep `openclaw-context-pack` as the PyPI distribution because `openclaw-mem` is already taken; preserve `openclaw-mem` as the CLI/import-facing product name where shipped. | Install/import behavior documented and tested; README relationship statement is consistent. |
| P0-4 | P0 | S | ready | One-sentence story. | Repo description and README first line use the agreed tagline; 30-second blind read passes. |
| P0-5 | P0 | M | todo | CI and test baseline. | Lint, unit tests, synthetic proof in GitHub Actions; README badge; coverage baseline recorded. |
| P0-6 | P1 | S | todo | KPI definition and baseline. | `docs/metrics-baseline.md` contains pack latency, token distribution, citation coverage, synthetic proof pass rate, and install-to-first-pack steps. |
| P0-7 | P1 | S | partial-check | License alignment. | MIT and Apache license files plus README statement agree. Current repo already has `LICENSE` and `LICENSE-APACHE`; verify text and README. |
| P0-8 | P0 | S | todo | SQLite internal schema version marker and unstable-schema warning. | `PRAGMA user_version` or meta table exists; docs say SQLite internals are not external contract; mismatch behavior is documented for harness consumers. |

P0 non-goals: new product features, labs feature work, retrieval algorithm changes.

## P1 - Integration base

Goal: connect to the 2026 agent integration surface with MCP, hooks, and a stable ContextPack producer contract.

Exit criteria: a Claude Code/Cursor user can install in 5 minutes and see a cited pack; ContextPack v1 compatibility has schema tests and shared fixtures.

| ID | Priority | Size | Status | Delivery | Acceptance |
|---|---:|---:|---|---|---|
| P1-1 | P0 | L | released | stdio MCP server v1 with 7 stable tools via `openclaw-mem-mcp`; committed tool-description hash manifest. | One-line `claude mcp add`; JSON schema and integration tests; deterministic tool descriptions and hash list; latency receipts. |
| P1-2 | P0 | M | released | Keep `openclaw-mem.context-pack.v1` canonical for v1 and preserve shipped field casing; prove compatibility with shared fixtures/adapters instead of renaming v1. | Compatibility fixtures and schema tests are in repo; v1 stability statement is documented. |
| P1-3 | P0 | M | released | Lifecycle hooks package via `openclaw-mem-hooks` for SessionStart/PostToolUse/SessionEnd. | Fail-open SessionStart/PostToolUse/SessionEnd helpers and tests. |
| P1-4 | P0 | S | released | Quickstart refresh into CLI proof, MCP route, Channel A route, and hooks route. | Three integration routes documented; zh follow-up remains docs hygiene. |
| P1-5 | P1 | M | released | Progressive reveal/token visibility through compact MCP search, ContextPack budgets, and receipts. | Search includes compact summaries and estimated tokens; pack receipts include token budgets. |
| P1-6 | P2 | S | released | `<private>` / redaction markers skipped by MCP store and Channel A ingest. | Marked content skipped with tests. |
| P1-7 | P2 | S | released | CLI UX pass through focused integration entrypoints and docs. | New user can complete quickstart integration routes without deeper docs. |
| P1-8 | P0 | M | released | Channel A file contract producer via `openclaw-mem-channel-a`. | JSONL -> ingest -> pack -> `<packs-dir>/<agent>/latest.json`; per-agent namespace; private/missing rows safe. |
| P1-9 | P0 | S | released | Shared fixtures for pack validation and ingest idempotency plus committed MCP tool hash fixture. | Legal, oversized, missing-field, and idempotency fixtures pass producer CI; harness-side import remains downstream. |

P1 cut line: P1-5 and P1-6 are deferred to P2. P1-3 starts with Claude Code only.

P1 non-goals: HTTP API server, web viewer, retrieval algorithm changes.

## P2 - Retrieval catch-up and public scores

Goal: make retrieval quality good enough that it does not block adoption, then publish reproducible numbers.

Exit criteria: LongMemEval or LoCoMo report is public and reproducible; rerank and decay v2 ship behind feature flags.

| ID | Priority | Size | Status | Delivery | Acceptance |
|---|---:|---:|---|---|---|
| P2-1 | P0 | L | todo | Standard benchmark harness. | `make bench-longmemeval` or equivalent; JSON result and report in repo. |
| P2-2 | P0 | M | todo | Optional cross-encoder reranking. | R@5 improvement recorded; off flag preserves baseline behavior. |
| P2-3 | P0 | L | todo | Decay v2 and tier promotion/demotion. | Every tier move emits receipt; one-command rollback; benchmark impact measured; bump P0-8 schema marker if tables change. |
| P2-4 | P1 | M | todo | Self-contained fact standard. | `graph lint` reports unresolved pronouns/time ambiguity; violation rate enters KPI. |
| P2-5 | P1 | L | todo | Entity linking lite. | Person/project/path entities queryable; fused retrieval not worse than two-signal retrieval; schema marker bump if needed. |
| P2-6 | P2 | M | todo | Query auto-routing across FTS/vector/graph/temporal facts. | Trace receipt records route decision; flag can force a single path. |
| P2-7 | P2 | M | todo | Pluggable embedding backend and `reembed`. | Backend swap without contract break; support matrix documented. |

P2 also receives deferred P1-5 and P1-6.

P2 non-goals: multimodal memory, cloud service, chasing benchmark #1.

## P3 - Governance depth and governance benchmark

Goal: make governance the differentiated weapon and publish MemGov-Bench v1.

Exit criteria: MemGov-Bench v1 is public with data and scripts; trust tiers GA; Self Curator write channel ships with receipts and rollback.

| ID | Priority | Size | Status | Delivery | Acceptance |
|---|---:|---:|---|---|---|
| P3-1 | P0 | L | todo | MemGov-Bench v1. | Dataset and scripts open; README leaderboard; includes poisoning, citation, conflict, rollback, exclusion explainability, and MCP tool-description poisoning. |
| P3-2 | P0 | M | todo | Provenance and trust tiers GA. | Spec shipped; default untrusted for tool/web/skill sources; promotion receipts; poisoning scenarios measured. |
| P3-3 | P0 | M | todo | Conflict detection v1. | Conflict cases measured in MemGov-Bench; no automatic deletion/overwrite. |
| P3-4 | P1 | M | todo | Learning records and feedback loop. | Operator correction affects later packs with measurable receipt trail. |
| P3-5 | P1 | L | todo | Self Curator write channel. | dry-run, before/after, apply, rollback artifact; two-week soak without data loss. |
| P3-6 | P2 | M | todo | Sunrise Stage B/C. | Promotion gate receipts; rollback to Stage A. |
| P3-7 | P2 | S | todo | Memory health report. | CLI and MCP expose staleness, citation coverage, untrusted ratio, conflicts, archive candidates. |

P3 non-goal: autonomous unreviewed mutation.

## P4 - Ecosystem integration and growth

Goal: connect the governance layer to more hosts and publish the story.

| ID | Priority | Size | Status | Delivery | Acceptance |
|---|---:|---:|---|---|---|
| P4-1 | P0 | L | todo | Rust harness channel B MCP direct recall. | p95 <= 300ms; timeout/errors fall back to channel A latest pack; tool description hash check passes. |
| P4-2 | P1 | L | todo | lancedb-pro governance plugin/interoperability. | Users can add citation/trust receipts without replacing storage; upstream README link if accepted. |
| P4-3 | P1 | L | todo | Web viewer. | `openclaw-mem ui`; receipt browser, pack/exclusion view, trust dashboard, rollback action. |
| P4-4 | P0 | M | todo | Formal launch. | MemGov-Bench report, narrative article, 5-minute demo video, two-week metrics review. |
| P4-5 | P2 | M | todo | Multi-host hooks. | Gemini CLI, OpenCode, Codex hook recipes with smoke tests. |
| P4-6 | P2 | M | todo | Memory Governance Playbook. | Standalone readable SOP; cited by launch materials. |

## Icebox

| Item | Source | Reconsider only when |
|---|---|---|
| Multimodal memory | SimpleMem Omni comparison | real user demand issues >= 3 |
| Hosted cloud service | mem0/supermemory comparison | MAU > 500 or clear willingness to pay |
| GBrain sidecar, Dream Lite, Symbolic Canvas, self_model, mutation_framework labs | existing project labs | P0-P3 complete and core KPI passes |
| External connectors such as Drive/Notion | supermemory comparison | governance positioning is already stable |
| Deep typed graph schema | old graph semantic memory roadmap | cognee-style route is validated |

## Phase KPI table

| Metric | P0 baseline | P2 target | P4 target |
|---|---|---|---|
| install to first pack | measure | <= 5 minutes | <= 3 minutes |
| LongMemEval R@5 | not run | public number, target >= 85% | >= 90% |
| MemGov-Bench poisoning block rate | n/a | designed | >= 95% and public leader |
| Citation coverage | measure | >= 95% | 100% contract-enforced |
| Core module count | about 40+ suspected | <= 15 | <= 15 |
| GitHub stars | 28 in source plan | 200+ after score publication | 2,000+ three months after launch |
| MCP adoption proxy | measure pip/downloads | +100% MoM | sustained growth |

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---:|---:|---|
| Single-maintainer capacity slips phases | high | medium | P0/P1/P2 priority cuts; icebox discipline; automate with harness and tests. |
| Benchmark scores are weak | medium | medium | Do not claim recall leadership; publish as same league plus unique governance; improve P2-2/P2-3 before launch. |
| OpenClaw native memory absorbs sidecar space | medium | high | Stay as governance layer above storage; P4-2 cross-storage compatibility. |
| MemGov-Bench gets ignored | medium | high | Tie to memory poisoning and prompt injection; use harness live gateway receipts as credible demo. |
| Rename/reorg breaks existing users | low | low | Keep deprecation shim and one-version alias. |
| lancedb-pro interoperability is rejected | medium | low | Build one-way compatibility instead of depending on upstream acceptance. |
| Harness direct-reads SQLite tables and P2 changes schema silently | high | high | P0-8 schema marker plus P1-8 channel A migration. |
| Consumer-side ContextPack contract solidifies before producer decision | high | medium | Resolve P1-2 immediately; add P1-9 shared fixtures and additive evolution rules. |

## This week

1. P0-4: finalize one-sentence product story.
2. P0-8: add SQLite internal schema version marker.
3. P1-8: implement channel A file contract producer.
