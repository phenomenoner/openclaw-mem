# AGENTS.md — openclaw-mem (for coding agents)

This repo is a small, deterministic-ish **memory layer demo/prototype**.

## Golden path (5 minutes)

```bash
# from repo root
./scripts/inside_out_demo.sh
```

What it does:
- stores a handful of **synthetic** preferences/decisions into a fresh SQLite DB
- runs `openclaw-mem pack` to produce a compact, cited bundle

## Common commands

### Install / run

```bash
uv sync
uv run openclaw-mem --help
```

### Tests

```bash
uv run -- python -m unittest discover -s tests -p "test_*.py" -q
```

### Store synthetic memories into a local DB

```bash
DB=/tmp/mem-demo.sqlite
rm -f "$DB"
uv run openclaw-mem store --db "$DB" --workspace /tmp/mem-ws --category preference --importance 0.8 \
  "Prefers using Asia/Taipei (UTC+8) timezone for time displays."
```

### Pack (safe fallback)

- With API key + embeddings present: hybrid retrieval (FTS + vector)
- Without API key: **FTS-only fail-open** (still produces a bundle)

```bash
uv run openclaw-mem pack --db "$DB" --query "timezone privacy demo style" --trace
```

## Repo landmarks

- CLI entrypoint: `openclaw_mem/cli.py`
- Task marker contract (summary prefix detection): `_summary_has_task_marker()`
- Inside-Out demo docs: `docs/showcase/inside-out-demo.md`
- Demo script: `scripts/inside_out_demo.sh`

## Environment variables

- `OPENAI_API_KEY` (optional; enables vector search / embeddings)
- `OPENCLAW_MEM_OPENAI_BASE_URL` (optional)
- `OPENCLAW_MEM_EMBED_MODEL` (optional)

## Guardrails

- Keep demos **synthetic** (no secrets / no personal notes).
- Prefer changes that are:
  - deterministic
  - test-covered
  - fail-open (don’t crash a demo due to missing credentials)
