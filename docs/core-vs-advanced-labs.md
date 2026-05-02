# Core vs Advanced Labs

`openclaw-mem` has one public core and several optional advanced lanes.

If you are evaluating the product for the first time, start with **Core**. Advanced Labs are useful only after you trust the Store / Pack / Observe loop.

## Core product

| Surface | Status | Why it belongs in Core |
| --- | --- | --- |
| Store | Core | Capture or ingest local memory records into inspectable JSONL/SQLite artifacts. |
| Pack | Core | Produce bounded `ContextPack` output with citations, trust policy, and trace receipts. |
| Observe | Core | Inspect timelines, exact records, pack traces, receipts, and rollback-friendly artifacts. |
| Sidecar install | Core | Lets operators evaluate without replacing the active OpenClaw memory backend. |
| Trust-policy synthetic proof | Core proof | Shows, on public synthetic data, how a trust-aware pack excludes quarantined content with an explicit reason. |
| Optional mem engine promotion | Core adoption path | Extends the same Pack contract into live-turn use only when the operator opts in. |

## Advanced Labs

These lanes are intentionally not required for the first evaluation path.

| Surface | Status | Keep-out tape |
| --- | --- | --- |
| Graph routing / synthesis | Advanced Lab | Useful for topology-aware recall experiments; not required for basic Store / Pack / Observe. |
| GBrain sidecar | Experimental Lab | Read-only lookup and restricted helper-job experiments; not a second truth store. |
| Continuity / self-model side-car | Advanced Lab | Derived continuity inspection and public-safe summaries; not a memory source of truth. |
| Dream Lite / dreaming director | Experimental Lab | Research-grade suggestion and rehearsal workflows; not part of the default memory path. |
| Optimize assist / autonomy loops | Advanced Lab | Governed maintenance workflows for mature operators; not needed to prove the core wedge. |
| Self Curator engine | Advanced Lab | Checkpointed lifecycle review/apply loops. Current scheduled lane may mutate `SKILL.md` body sections with rollback receipts; memory/dream/authority surfaces remain gated. |
| Command-aware compaction | Advanced Lab | Observe-path artifact handling for long outputs; not required for the first proof. |

## Evaluation rule of thumb

If a feature does not help you answer one of these questions, postpone it:

1. Can I store local memory records in a way I can inspect?
2. Can I pack relevant context with citations and receipts?
3. Can I explain why a memory was included or excluded?
4. Can I adopt this beside my current OpenClaw memory without a forced backend swap?

When those are clear, Advanced Labs are available for deeper operations.
