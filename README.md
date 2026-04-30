# openclaw-mem

**Memory your agent can’t lie about — Store / Pack / Observe for local, cited, rollbackable context.**

`openclaw-mem` turns agent work into a durable local memory trail, then builds bounded `ContextPack` bundles with citations, trust-policy receipts, and traceable include/exclude reasons. Start with a plain SQLite sidecar beside OpenClaw. Promote to the optional mem engine only after the local proof earns the extra surface.

## Start here

1. **Run the local benchmark:** [Plain-vanilla ContextPack benchmark](docs/showcase/plain-vanilla-context-pack-benchmark.md)
2. **Check shipped vs partial status:** [Reality check & status](docs/reality-check.md)
3. **Run the CLI path:** [Quickstart](QUICKSTART.md)
4. **Choose sidecar vs engine:** [Install modes](docs/install-modes.md)
5. **Check what is automatic:** [Automation status](docs/automation-status.md)
6. **Read in Traditional Chinese:** [Traditional Chinese edition](docs/zh/index.md)

## What is automatic today?

| Surface | Status | Meaning |
| --- | --- | --- |
| Sidecar observation capture | Automatic when the plugin is enabled | Captures denoised JSONL observations and backend/action annotations. |
| Harvest, triage, and graph capture | Scheduled on configured hosts | Converts captured records into searchable stores and receipts. |
| `pack`, graph routing, optimize assist, continuity | CLI / opt-in lanes | Available, but not assumed to run in every live agent turn. |
| Mem-engine Proactive Pack | Optional promotion | Bounded pre-reply recall orchestration after explicit engine adoption. |

## What you get

- **Local-first by default** — JSONL + SQLite, no external database required.
- **Cheap recall loop** — `search → timeline → get` keeps routine lookups fast and inspectable.
- **Bounded packing** — `pack` emits a stable `ContextPack` contract for injection, citations, trust-policy receipts, and trace-backed debugging.
- **Fits real OpenClaw ops** — capture tool outcomes, retain receipts, sanitize runtime artifacts, and keep rollback simple.
- **Upgradeable path** — sidecar first, engine later; no forced migration on day one.
- **Advanced labs are opt-in** — graph routing, GBrain, continuity, Dream Lite, and deeper optimization lanes stay out of the first evaluation path.

## Why this exists

Long-running agents do not just forget. They also accumulate memory that quietly degrades:

- old notes still match the query even when they are no longer useful
- untrusted or hostile content can retrieve well and slip into context
- prompts bloat into giant memory dumps instead of a small, inspectable bundle
- when something goes wrong, it is hard to explain **why** a memory was included

`openclaw-mem` tackles that by building compact memory packs with citations, trace receipts, and trust-policy controls.

## Try it in 5 minutes

You can prove the core behavior locally without touching OpenClaw config.

```bash
git clone https://github.com/phenomenoner/openclaw-mem.git
cd openclaw-mem
uv sync --locked

DB=/tmp/openclaw-mem-proof.sqlite
uv run --python 3.13 --frozen -- python -m openclaw_mem ingest \
  --db "$DB" \
  --json \
  --file ./docs/showcase/artifacts/trust-aware-context-pack.synthetic.jsonl

uv run --python 3.13 --frozen -- python -m openclaw_mem pack \
  --db "$DB" \
  --query "trust-aware context packing prompt pack receipts hostile durable memory provenance" \
  --limit 5 \
  --budget-tokens 500 \
  --trace
```

### What this proof shows

- the same query can change its result set when a trust policy is applied
- quarantined content can be excluded with an explicit reason
- every include/exclude decision stays inspectable through receipts and trace output

Full proof path:
- [Plain-vanilla ContextPack benchmark](docs/showcase/plain-vanilla-context-pack-benchmark.md)
- [Trust-aware pack proof](docs/showcase/trust-aware-context-pack-proof.md)
- [Command-aware compaction proof](docs/showcase/command-aware-compaction-proof.md)
- [Metrics JSON](docs/showcase/artifacts/trust-aware-context-pack.metrics.json)
- [Synthetic fixture + receipts](docs/showcase/artifacts/index.md)
- [Inside-out demo](docs/showcase/inside-out-demo.md)

## Store + Pack + Observe

The product loop is simple and stable:

1. **Store**: capture, ingest, and query observations with `store`/`ingest`/`search`.
2. **Pack**: run `pack` to get a bounded `bundle_text` and `context_pack` (`schema: openclaw-mem.context-pack.v1`), with optional protected-tail continuity and graph-aware synthesis preference.
3. **Observe**: use `timeline`, `get`, and `artifact` outputs for explainability and rollback.

When mem-engine is active, **Proactive Pack** extends the same Pack contract into live turns as a small, receipt-backed pre-reply bundle.

## Advanced labs

The first-time evaluator path is **Store / Pack / Observe**. Everything below is opt-in after the core proof is clear.

Advanced lanes currently include:

- **Graph routing** for topology-aware recall experiments.
- **GBrain sidecar** for bounded read-only lookup and restricted helper-job experiments.
- **Governed continuity side-car** for derived continuity inspection and public-safe summaries.
- **Dream Lite / deeper optimize loops** for research-grade memory maintenance workflows.

These lanes are not required for the 5-minute benchmark, the sidecar install path, or the basic `ContextPack` contract. Treat them as labs until your use case needs them.

Read more:
- [Product positioning](PRODUCT_POSITIONING.md)
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

## Governed optimization updates

`openclaw-mem` now ships a review-first workflow for one low-risk class of memory maintenance updates.

Current shipped path:
- `openclaw-mem optimize review` — read-only health signals
- `openclaw-mem optimize evolution-review` — prepares low-risk maintenance candidates
- `openclaw-mem optimize governor-review` — records explicit decisions
- `openclaw-mem optimize assist-apply` — applies only approved low-risk observation updates with before/after and rollback receipts

Each assist apply run now also emits a compact effect artifact so later autonomy phases can measure whether mutations helped, held steady, or regressed instead of treating writes as blind maintenance.

The first bounded write class is intentionally narrow:
- update `observations.detail_json.lifecycle.stale_candidate`
- update `observations.detail_json.lifecycle.stale_reason_code`
- update `observations.detail_json.importance.score`
- update `observations.detail_json.importance.label`
- add bounded `observations.detail_json.optimization.assist` metadata

Example dry rehearsal:

```bash
uv run --python 3.13 --frozen -- python -m openclaw_mem optimize evolution-review --json > evolution.json
uv run --python 3.13 --frozen -- python -m openclaw_mem optimize governor-review --from-file evolution.json --approve-stale --approve-importance --json > governor.json
uv run --python 3.13 --frozen -- python -m openclaw_mem optimize assist-apply --from-file governor.json --dry-run --json
```

Example bounded write run:

```bash
uv run --python 3.13 --frozen -- python -m openclaw_mem optimize assist-apply --from-file governor.json --json
```

Scheduled worker form:

```bash
uv run --python 3.13 --frozen -- python tools/optimize_assist_runner.py --json
```

That runner keeps the full packet chain in one bounded scheduled surface and stays dry-run unless `--allow-apply` is set.

Receipts are written under `~/.openclaw/memory/openclaw-mem/optimize-assist/` by default.
If the packet is malformed, unapproved, duplicated, or exceeds caps, the run aborts before write.

### Command-aware compaction, minimal operator path

If you already use a compactor such as RTK, keep it in the Observe path first:

```bash
# 1) Produce raw + compact outputs with your own toolchain
my-compactor git diff --stat > ./compact-git-diff.txt
git diff --stat > ./raw-git-diff.txt

# 2) Bind them into a sideband receipt
uv run --python 3.13 --frozen -- python -m openclaw_mem artifact compact-receipt \
  --command "git diff --stat" \
  --tool my-compactor \
  --compact-file ./compact-git-diff.txt \
  --raw-file ./raw-git-diff.txt \
  --json > ./compaction-receipt.json

# 3) Recover bounded raw evidence later, from the receipt or raw handle
uv run --python 3.13 --frozen -- python -m openclaw_mem artifact rehydrate \
  --receipt-file ./compaction-receipt.json \
  --max-chars 1200 \
  --json
```

When a compaction receipt is later selected by `pack`, the response may include:
- `compaction_sideband` for raw recovery metadata
- `compaction_policy_hints` for advisory family-level guidance (`git_diff`, `test_failures`, `long_logs`, `generic`)
- `trace.extensions.compaction_sideband` / `compaction_policy_hints` for auditable preference receipts

## More links

### Core and adoption

- **Why openclaw-mem still exists:** [`docs/why-openclaw-mem-still-exists.md`](docs/why-openclaw-mem-still-exists.md)
- **OpenClaw 2026.4.15 comparison:** [`docs/openclaw-2026-4-15-comparison.md`](docs/openclaw-2026-4-15-comparison.md)
- **About the product:** [`docs/about.md`](docs/about.md)
- **Proactive Pack:** [`docs/proactive-pack.md`](docs/proactive-pack.md)
- **v2 blueprint:** [`docs/context-supply-chain-blueprint.md`](docs/context-supply-chain-blueprint.md)
- **Choose an install path:** [`docs/install-modes.md`](docs/install-modes.md)
- **Detailed quickstart:** [`QUICKSTART.md`](QUICKSTART.md)
- **Docs site:** <https://phenomenoner.github.io/openclaw-mem/>
- **Traditional Chinese edition:** [`docs/zh/index.md`](docs/zh/index.md)
- **Reality check / status:** [`docs/reality-check.md`](docs/reality-check.md)
- **Deployment patterns:** [`docs/deployment.md`](docs/deployment.md)
- **Auto-capture plugin:** [`docs/auto-capture.md`](docs/auto-capture.md)
- **Agent memory skill (SOP):** [`docs/agent-memory-skill.md`](docs/agent-memory-skill.md)
- **Pack policy contract:** [`docs/specs/context-pack-policy-v1.1.md`](docs/specs/context-pack-policy-v1.1.md)
- **Optional Mem Engine:** [`docs/mem-engine.md`](docs/mem-engine.md)
- **Release notes:** <https://github.com/phenomenoner/openclaw-mem/releases>

### Advanced labs

- **Experimental GBrain sidecar:** [`docs/experimental/gbrain-sidecar/README.md`](docs/experimental/gbrain-sidecar/README.md)
- **Continuity side-car ops lane:** [`skills/self-model-sidecar.ops.md`](skills/self-model-sidecar.ops.md)
- **GBrain sidecar ops lane:** [`skills/gbrain-sidecar.ops.md`](skills/gbrain-sidecar.ops.md)

## License

Dual-licensed: **MIT OR Apache-2.0**. See `LICENSE`, `LICENSE-MIT`, and `LICENSE-APACHE`.
