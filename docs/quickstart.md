# Quickstart

This page is a GitHub Pages friendly entrypoint.

Canonical quickstart lives here:
- <https://github.com/phenomenoner/openclaw-mem/blob/main/QUICKSTART.md>

Reality check & status:
- [reality-check.md](reality-check.md)

## Minimal local run

```bash
git clone https://github.com/phenomenoner/openclaw-mem.git
cd openclaw-mem
uv sync --locked

# status + backend posture
uv run --python 3.13 --frozen -- python -m openclaw_mem --json status
uv run --python 3.13 --frozen -- python -m openclaw_mem --json backend
```

## Next

- Production deployment patterns: [deployment](deployment.md)
- Memory slot ownership boundaries: [ecosystem-fit](ecosystem-fit.md)
