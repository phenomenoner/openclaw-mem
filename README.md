# openclaw-mem

A memory layer for [OpenClaw](https://github.com/openclaw/openclaw) that keeps agent context small, cited, and less likely to be polluted by stale or untrusted content.

## What you get

- compact memory packs with citations and trace receipts
- trust-policy controls for excluding quarantined content
- sidecar deployment on an existing OpenClaw install
- optional promotion to `openclaw-mem-engine` later for hybrid recall and tighter policy controls

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
  --trace \
  --pack-trust-policy exclude_quarantined_fail_open
```

### What this proof shows

- the same query can change its result set when a trust policy is applied
- quarantined content can be excluded with an explicit reason
- every include/exclude decision stays inspectable through receipts and trace output

Full proof path:
- [Trust-aware pack proof](docs/showcase/trust-aware-context-pack-proof.md)
- [Metrics JSON](docs/showcase/artifacts/trust-aware-context-pack.metrics.json)
- [Synthetic fixture + receipts](docs/showcase/artifacts/index.md)
- [Inside-out demo](docs/showcase/inside-out-demo.md)

## Install paths

Three paths: local proof, sidecar plugin, or full memory engine.
Read the guide: [Choose an install path](docs/install-modes.md)

## Start here

- [Quickstart](docs/quickstart.md)
- [Reality check & status](docs/reality-check.md)
- [Deployment guide](docs/deployment.md)

## License

Dual-licensed: **MIT OR Apache-2.0**, at your option.

- MIT terms: `LICENSE` (root canonical text for GitHub/license-scanner detection)
- Apache 2.0 terms: `LICENSE-APACHE` (root canonical text for GitHub/license-scanner detection)
