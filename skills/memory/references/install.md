# Install and availability

- Distribution: `openclaw-context-pack`
- Console command: `openclaw-mem`
- Python package: `openclaw_mem`

```bash
pip install openclaw-context-pack
pip install "openclaw-context-pack[qdrant]"
pip install "openclaw-context-pack[embed]"
```

Source maintainers use `uv sync --locked`. Packaged users should use PyPI. In Agent Harness lanes, pass `--harness-home <path>` so database, configuration, environment, and state-file resolution remain explicit. For temporary store smoke tests, add `--no-file-write` unless a Markdown side effect is under test.

Local embeddings use `OPENCLAW_MEM_EMBED_PROVIDER=local`; the default is `openai`. The local model is downloaded on first use and then supports offline reuse.
