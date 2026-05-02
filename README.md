# openclaw-mem

**Memory your agent can’t lie about — Store / Pack / Observe for local, cited, rollbackable context.**

`openclaw-mem` turns agent work into a durable local memory trail, then builds bounded `ContextPack` bundles with citations, trust-policy receipts, and traceable include/exclude reasons. Start with a plain SQLite sidecar beside OpenClaw. Promote to the optional mem engine only after the local proof earns the extra surface.

## Start here

1. **Run the synthetic proof:** [Trust-policy synthetic proof](docs/showcase/trust-policy-synthetic-proof.md)
2. **Pick an evaluation path:** [5 minutes / 30 minutes / one afternoon](docs/evaluator-path.md)
3. **Check Core vs Advanced Labs:** [Core vs Advanced Labs](docs/core-vs-advanced-labs.md)
4. **Choose sidecar vs engine:** [Install modes](docs/install-modes.md)
5. **Check shipped vs partial status:** [Reality check & status](docs/reality-check.md)
6. **Read in Traditional Chinese:** [Traditional Chinese edition](docs/zh/index.md)

## What is automatic today?

| Surface | Status | Meaning |
| --- | --- | --- |
| Sidecar observation capture | Automatic when the plugin is enabled | Captures denoised JSONL observations and backend/action annotations. |
| Harvest, triage, and graph capture | Scheduled on configured hosts | Converts captured records into searchable stores and receipts. |
| `pack` | CLI core | Produces bounded `ContextPack` output with citations and trace receipts. |
| Graph routing, optimize assist, continuity, GBrain | Advanced Labs / opt-in lanes | Available for mature operators, but not part of the first evaluation path. |
| Mem-engine Proactive Pack | Optional promotion | Bounded pre-reply recall orchestration after explicit engine adoption. |

## What you get

- **Local-first by default** — JSONL + SQLite, no external database required.
- **Cheap recall loop** — `search → timeline → get` keeps routine lookups fast and inspectable.
- **Bounded packing** — `pack` emits a stable `ContextPack` contract for injection, citations, trust-policy receipts, and trace-backed debugging.
- **Fits real OpenClaw ops** — capture tool outcomes, retain receipts, sanitize runtime artifacts, and keep rollback simple.
- **Upgradeable path** — sidecar first, engine later; no forced migration on day one.
- **Advanced labs are opt-in** — graph routing, GBrain, continuity, Dream Lite, Self Curator review packets, and deeper optimization lanes stay out of the first evaluation path.

## Why this exists

Long-running agents do not just forget. They also accumulate memory that quietly degrades:

- old notes still match the query even when they are no longer useful
- untrusted or hostile content can retrieve well and slip into context
- prompts bloat into giant memory dumps instead of a small, inspectable bundle
- when something goes wrong, it is hard to explain **why** a memory was included

`openclaw-mem` tackles that by building compact memory packs with citations, trace receipts, and trust-policy controls.

## Try it in 5 minutes

You can prove the core behavior locally without touching OpenClaw config.

For the packaged CLI:

```bash
python -m venv .venv
. .venv/bin/activate
pip install openclaw-context-pack
openclaw-mem --db /tmp/openclaw-mem-demo.sqlite status --json
```

For the repository proof fixture:

```bash
git clone https://github.com/phenomenoner/openclaw-mem.git
cd openclaw-mem
uv sync --locked

uv run --python 3.13 --frozen -- \
  python benchmarks/trust_policy_synthetic_proof.py --json
```

### What this proof shows

- vanilla packing selects a quarantined row from synthetic memory
- trust-aware packing excludes that row with an explicit reason
- selected rows keep citation coverage and traceable receipts

Full proof path:
- [Evaluator path](docs/evaluator-path.md)
- [Trust-policy synthetic proof](docs/showcase/trust-policy-synthetic-proof.md)
- [Trust-aware pack proof](docs/showcase/trust-aware-context-pack-proof.md)
- [Command-aware compaction proof](docs/showcase/command-aware-compaction-proof.md)
- [Metrics JSON](docs/showcase/artifacts/trust-aware-context-pack.metrics.json)
- [Synthetic fixture + receipts](docs/showcase/artifacts/index.md)
- [Inside-out demo](docs/showcase/inside-out-demo.md)

## Store + Pack + Observe

The product loop is simple and stable:

1. **Store**: capture, ingest, and query observations with `store`/`ingest`/`search`.
2. **Pack**: run `pack` to get a bounded `bundle_text` and `context_pack` (`schema: openclaw-mem.context-pack.v1`), with citations, trust policy, and trace receipts.
3. **Observe**: use `timeline`, `get`, and `artifact` outputs for explainability and rollback.

When mem-engine is active, **Proactive Pack** extends the same Pack contract into live turns as a small, receipt-backed pre-reply bundle.

## Advanced labs

The first-time evaluator path is **Store / Pack / Observe**. Everything below is opt-in after the core proof is clear.

Advanced lanes currently include:

- **Graph routing** for topology-aware recall experiments.
- **GBrain sidecar** for bounded read-only lookup and restricted helper-job experiments.
- **Governed continuity side-car** for derived continuity inspection and public-safe summaries.
- **Dream Lite / deeper optimize loops** for research-grade memory maintenance workflows.
- **Self Curator sidecar** for review-only lifecycle packets over skills first, with memory/dream/authority expansion gated behind explicit review.

These lanes are not required for the 5-minute proof, the sidecar install path, or the basic `ContextPack` contract. Treat them as labs until your use case needs them.

Read more:
- [Product positioning](PRODUCT_POSITIONING.md)
- [Core vs Advanced Labs](docs/core-vs-advanced-labs.md)
- [Evaluator path](docs/evaluator-path.md)
- [Architecture](docs/architecture.md)
- [Context pack](docs/context-pack.md)
- [Experimental GBrain sidecar](docs/experimental/gbrain-sidecar/README.md)
- [Optional Mem Engine](docs/mem-engine.md)

## OpenClaw 2026.4.15 and `openclaw-mem`

By OpenClaw 2026.4.15, the native memory and prompt-time integration experience had become noticeably stronger. We are genuinely happy to see that direction mature.

That is good for the ecosystem, good for operators, and good for `openclaw-mem` too.
A stronger foundation makes it easier to keep our own work focused on what matters most: better packs, clearer evidence, and safer memory maintenance.

Our direction is not to shrink back into native features.
It is to build a clearer, more opinionated product layer on top of a stronger foundation.

Read more:
- [Why openclaw-mem still exists in a stronger OpenClaw world](docs/why-openclaw-mem-still-exists.md)
- [openclaw-mem and OpenClaw 2026.4.15](docs/openclaw-2026-4-15-comparison.md)

## Deeper operations live below the fold

`openclaw-mem` also has governed memory-hygiene and artifact-observation tools for mature operator stacks. They are useful after the core product is proven, but they are not required for the first evaluation path.

Start with:

- [Core vs Advanced Labs](docs/core-vs-advanced-labs.md)
- [Evaluator path](docs/evaluator-path.md)
- [Governed optimize assist](docs/optimize-assist.md)
- [Hermes Curator adoption review](docs/hermes-curator-adoption-review.md)
- [Self Curator sidecar v0 contract](docs/specs/self-curator-sidecar-v0.md)
- [Command-aware compaction proof](docs/showcase/command-aware-compaction-proof.md)

Manual Self Curator scout smoke:

```bash
openclaw-mem self-curator skill-review \
  --skill-root ~/.openclaw/workspace/skills \
  --out-root .state/self-curator/runs \
  --json
```

Checkpointed Self Curator apply flow:

```bash
openclaw-mem self-curator plan --mutations-file mutations.json --out plan.json --workspace-root . --json
openclaw-mem self-curator apply --plan plan.json --workspace-root . --checkpoint-root .state/self-curator/checkpoints --receipt-root .state/self-curator/apply-runs --json
openclaw-mem self-curator verify --receipt .state/self-curator/apply-runs/<run>/apply-receipt.json --json
openclaw-mem self-curator rollback --receipt .state/self-curator/apply-runs/<run>/apply-receipt.json --json
```

The scout emits review-only lifecycle artifacts. The apply flow may mutate whitelisted relative workspace files through explicit plans, checkpoints, diffs, receipts, verification, and rollback.

## More links

### Core and adoption

- **Why openclaw-mem still exists:** [`docs/why-openclaw-mem-still-exists.md`](docs/why-openclaw-mem-still-exists.md)
- **OpenClaw 2026.4.15 comparison:** [`docs/openclaw-2026-4-15-comparison.md`](docs/openclaw-2026-4-15-comparison.md)
- **About the product:** [`docs/about.md`](docs/about.md)
- **Proactive Pack:** [`docs/proactive-pack.md`](docs/proactive-pack.md)
- **Choose an install path:** [`docs/install-modes.md`](docs/install-modes.md)
- **Detailed quickstart:** [`QUICKSTART.md`](QUICKSTART.md)
- **Docs site:** <https://phenomenoner.github.io/openclaw-mem/>
- **Traditional Chinese edition:** [`docs/zh/index.md`](docs/zh/index.md)
- **Reality check / status:** [`docs/reality-check.md`](docs/reality-check.md)
- **Deployment patterns:** [`docs/deployment.md`](docs/deployment.md)
- **Auto-capture plugin:** [`docs/auto-capture.md`](docs/auto-capture.md)
- **Agent memory skill (SOP):** [`docs/agent-memory-skill.md`](docs/agent-memory-skill.md)
- **Optional Mem Engine:** [`docs/mem-engine.md`](docs/mem-engine.md)
- **Release notes:** <https://github.com/phenomenoner/openclaw-mem/releases>

## License

Dual-licensed: **MIT OR Apache-2.0**. See `LICENSE`, `LICENSE-MIT`, and `LICENSE-APACHE`.
