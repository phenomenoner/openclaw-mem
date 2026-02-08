# Quickstart

This page is a GitHub Pages friendly entrypoint.

Canonical quickstart lives here:
- <https://github.com/phenomenoner/openclaw-mem/blob/main/QUICKSTART.md>

## Minimal local run

```bash
git clone https://github.com/phenomenoner/openclaw-mem.git
cd openclaw-mem
uv sync --locked

# status
uv run --python 3.13 -- python -m openclaw_mem status --json
```

## Next

- Production deployment patterns: [deployment](deployment.md)
- Memory slot ownership boundaries: [ecosystem-fit](ecosystem-fit.md)
