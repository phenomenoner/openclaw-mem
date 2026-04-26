# openclaw-mem

**Memory your agent can’t lie about — a local context supply chain you can grep, diff, and roll back.**

`openclaw-mem` turns agent work into a durable, searchable, auditable memory trail, then assembles bounded context bundles that are small enough to inject and easy to verify. Start with a local SQLite sidecar beside OpenClaw, keep your current memory backend, and promote to the optional mem engine only when hybrid recall and policy controls earn their keep.
When you do promote the engine, the live-turn hook is framed as **Proactive Pack**: bounded pre-reply recall orchestration, not a separate hidden memory layer.

## Start here

1. **Verify locally in ~60 seconds:** [Reality check & status](docs/reality-check.md)
2. **Run the CLI path:** [Quickstart](QUICKSTART.md)
3. **Choose sidecar vs engine:** [Install modes](docs/install-modes.md)
4. **Check what is automatic:** [Automation status](docs/automation-status.md)
5. **See the product gaps:** [OpenClaw user improvement roadmap](docs/openclaw-user-improvement-roadmap.md)
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
- **Bounded packing** — `pack` emits a stable `ContextPack` contract for injection, citations, graph-aware synthesis preference, protected fresh tails, and trace-backed debugging.
- **Fits real OpenClaw ops** — capture tool outcomes, retain receipts, sanitize runtime artifacts, and keep rollback simple.
- **Upgradeable path** — sidecar first, engine later; no forced migration on day one.
- **Governed continuity side-car** — optional `continuity` surface for derived self/continuity inspection, adjudication, public-safe summaries, and explicit weaken/rebind/retire receipts.

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
2. **Pack**: run `pack` to get a bounded `bundle_text` and `context_pack` (`schema: openclaw-mem.context-pack.v1`), with optional protected-tail continuity and graph-aware synthesis preference.
3. **Observe**: use `timeline`, `get`, and `artifact` outputs for explainability and rollback.

When mem-engine is active, **Proactive Pack** extends the same Pack contract into live turns as a small, receipt-backed pre-reply bundle.

## Experimental GBrain sidecar

`openclaw-mem` also ships an **experimental GBrain sidecar**.
It is **not enabled by default**, carries **no stability guarantee**, and is still documented as an experimental rollout rather than a default product path.

For teams that want to test two bounded additions, it currently offers:

- a **read-only GBrain lookup** that can add extra Pack candidates without changing `ContextPack`
- a **restricted background-job bridge** for one deterministic helper lane at a time

Use it when you want to evaluate whether GBrain can improve retrieval support or bounded helper execution without changing memory ownership.
Do not treat it as a second truth store, a backend replacement, or a general-purpose job runner.

Read more:
- [Experimental GBrain sidecar](docs/experimental/gbrain-sidecar/README.md)
- [Optional Mem Engine + GBrain mirror](docs/mem-engine.md)

## Governed continuity side-car

`openclaw-mem` also ships an optional derived continuity lane.
This is not a second truth store, and it is not presented as consciousness.
It is a governed side-car that helps operators inspect what continuity claims the system is currently making, how strong those claims are allowed to be, and when those claims should be weakened, rebound, or retired.

Core operator surfaces:

```bash
uv run --python 3.13 --frozen -- python -m openclaw_mem continuity current --json
uv run --python 3.13 --frozen -- python -m openclaw_mem continuity attachment-map --snapshot <snapshot.json> --json
uv run --python 3.13 --frozen -- python -m openclaw_mem continuity adjudication --snapshot <snapshot.json> --json
uv run --python 3.13 --frozen -- python -m openclaw_mem continuity public-summary --snapshot <snapshot.json> --json
uv run --python 3.13 --frozen -- python -m openclaw_mem continuity explain --snapshot <snapshot.json> --stance <id> --json
uv run --python 3.13 --frozen -- python -m openclaw_mem continuity sensitivity --snapshot <snapshot.json> --stance <id> --json
uv run --python 3.13 --frozen -- python -m openclaw_mem continuity patterns --json
uv run --python 3.13 --frozen -- python -m openclaw_mem continuity triggers --snapshot <snapshot.json> --json
uv run --python 3.13 --frozen -- python -m openclaw_mem continuity interventions --snapshot <snapshot.json> --json
uv run --python 3.13 --frozen -- python -m openclaw_mem continuity compare-sessions --left-scope <scope-a> --left-session-id <session-a> --right-scope <scope-b> --right-session-id <session-b> --json
uv run --python 3.13 --frozen -- python -m openclaw_mem continuity wording-lint --snapshot <snapshot.json> --json
uv run --python 3.13 --frozen -- python -m openclaw_mem continuity release-history --json
```

Control-plane activation is explicit and starts autonomous snapshot + receipt generation under `~/.openclaw/memory/openclaw-mem/self-model-sidecar/` until you disable it:

```bash
uv run --python 3.13 --frozen -- python -m openclaw_mem continuity enable --cadence-seconds 300 --json
uv run --python 3.13 --frozen -- python -m openclaw_mem continuity status --json
uv run --python 3.13 --frozen -- python -m openclaw_mem continuity disable --json
```

For the real 72h endurance gate, run the self-closing soak controller instead of hand-counting receipts. It advances one autorun cycle per wake, writes status under `~/.openclaw/memory/openclaw-mem/self-model-sidecar/soak/`, emits a clear warning on anomalous gaps/drift, and disables its own cron job after a healthy 72h window closes:

```bash
python3 tools/self_model_sidecar_soak_controller.py \
  --repo-root /root/.openclaw/workspace/openclaw-mem \
  --run-dir /root/.openclaw/memory/openclaw-mem/self-model-sidecar \
  --cadence-seconds 300 \
  --target-hours 72
```

Use it when you need auditable continuity receipts, migration comparison, or public-safe hedged summaries, not when you need a new source of truth. The lane stays rebuildable from memory-of-record by design.

Updated operator loop:
- `continuity explain` answers why one claim exists, including adjudication reasons and release history.
- `continuity sensitivity` measures fragility by removing top evidence and recomputing the claim state.
- `continuity patterns`, `triggers`, and `interventions` turn persisted receipts into a governed operator loop instead of raw JSON archaeology.
- `continuity wording-lint` catches selfhood inflation and missing hedges before copy leaves the operator lane.

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
- **Traditional Chinese edition:** [`docs/zh/index.md`](docs/zh/index.md)
- **Reality check / status:** [`docs/reality-check.md`](docs/reality-check.md)
- **Deployment patterns:** [`docs/deployment.md`](docs/deployment.md)
- **Experimental GBrain sidecar:** [`docs/experimental/gbrain-sidecar/README.md`](docs/experimental/gbrain-sidecar/README.md)
- **Continuity side-car ops lane:** [`skills/self-model-sidecar.ops.md`](skills/self-model-sidecar.ops.md)
- **GBrain sidecar ops lane:** [`skills/gbrain-sidecar.ops.md`](skills/gbrain-sidecar.ops.md)
- **Auto-capture plugin:** [`docs/auto-capture.md`](docs/auto-capture.md)
- **Agent memory skill (SOP):** [`docs/agent-memory-skill.md`](docs/agent-memory-skill.md)
- **Pack policy contract:** [`docs/specs/context-pack-policy-v1.1.md`](docs/specs/context-pack-policy-v1.1.md)
- **Optional Mem Engine:** [`docs/mem-engine.md`](docs/mem-engine.md)
- **Release notes:** <https://github.com/phenomenoner/openclaw-mem/releases>

## License

Dual-licensed: **MIT OR Apache-2.0**. See `LICENSE`, `LICENSE-MIT`, and `LICENSE-APACHE`.
