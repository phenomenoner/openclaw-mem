# openclaw-mem

**A local-first context supply chain for OpenClaw: store what matters, pack what fits, observe what changed.**

`openclaw-mem` turns agent work into a durable, searchable, auditable memory trail, then assembles bounded context bundles that are small enough to inject and easy to verify.
Start with a local SQLite sidecar. Keep your current OpenClaw memory backend if you want. Promote to the optional mem engine later if you need hybrid recall, policy controls, and safer automation.
When you do promote the engine, the live-turn hook is framed as **Proactive Pack**: bounded pre-reply recall orchestration, not a separate hidden memory layer.

## What you get

- compact memory packs with citations and trace receipts
- trust-policy controls for excluding quarantined content
- sidecar deployment on an existing OpenClaw install
- optional promotion to `openclaw-mem-engine` later for hybrid recall and tighter policy controls
- optional **Proactive Pack** support in `openclaw-mem-engine` for pre-reply bounded recall with receipts and fail-open behavior
- **Local-first by default**: JSONL + SQLite, no external database required
- **Cheap recall loop**: `search → timeline → get` keeps routine lookups fast and inspectable
- **Bounded packing**: `pack` emits a stable `ContextPack` contract for injection, citations, and trace-backed debugging
- **Fits real OpenClaw ops**: capture tool outcomes, retain receipts, and keep rollback simple

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
- [Trust-aware pack proof](docs/showcase/trust-aware-context-pack-proof.md)
- [Command-aware compaction proof](docs/showcase/command-aware-compaction-proof.md)
- [Metrics JSON](docs/showcase/artifacts/trust-aware-context-pack.metrics.json)
- [Synthetic fixture + receipts](docs/showcase/artifacts/index.md)
- [Inside-out demo](docs/showcase/inside-out-demo.md)

## Store + Pack + Observe

The product loop is simple and stable:

1. **Store**: capture, ingest, and query observations with `store`/`ingest`/`search`.
2. **Pack**: run `pack` to get a bounded `bundle_text` and `context_pack` (`schema: openclaw-mem.context-pack.v1`).
3. **Observe**: use `timeline`, `get`, and `artifact` outputs for explainability and rollback.

When mem-engine is active, **Proactive Pack** extends the same Pack contract into live turns as a small, receipt-backed pre-reply bundle.

Example:

```bash
uv run --python 3.13 --frozen -- python -m openclaw_mem pack "What changed this week?" --limit 6 --json
uv run --python 3.13 --frozen -- python -m openclaw_mem artifact stash --from ./tool-output.txt --json
uv run --python 3.13 --frozen -- python -m openclaw_mem artifact peek ocm_artifact:v1:sha256:<64hex> --json
```

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

## Start here

- **Why openclaw-mem still exists:** [`docs/why-openclaw-mem-still-exists.md`](docs/why-openclaw-mem-still-exists.md)
- **OpenClaw 2026.4.15 comparison:** [`docs/openclaw-2026-4-15-comparison.md`](docs/openclaw-2026-4-15-comparison.md)
- **About the product:** [`docs/about.md`](docs/about.md)
- **Proactive Pack:** [`docs/proactive-pack.md`](docs/proactive-pack.md)
- **v2 blueprint:** [`docs/context-supply-chain-blueprint.md`](docs/context-supply-chain-blueprint.md)
- **Choose an install path:** [`docs/install-modes.md`](docs/install-modes.md)
- **Detailed quickstart:** [`QUICKSTART.md`](QUICKSTART.md)
- **Docs site:** <https://phenomenoner.github.io/openclaw-mem/>
- **Reality check / status:** [`docs/reality-check.md`](docs/reality-check.md)
- **Deployment patterns:** [`docs/deployment.md`](docs/deployment.md)
- **Auto-capture plugin:** [`docs/auto-capture.md`](docs/auto-capture.md)
- **Agent memory skill (SOP):** [`docs/agent-memory-skill.md`](docs/agent-memory-skill.md)
- **Optional Mem Engine:** [`docs/mem-engine.md`](docs/mem-engine.md)
- **Release notes:** <https://github.com/phenomenoner/openclaw-mem/releases>

## License

Dual-licensed: **MIT OR Apache-2.0**. See `LICENSE`, `LICENSE-MIT`, and `LICENSE-APACHE`.
