# openclaw-mem

> Smart memory management plugin for OpenClaw — observation capture, AI compression, and progressive disclosure search.

`openclaw-mem` is the planned memory-layer plugin for [OpenClaw](https://openclaw.ai). It captures tool-use observations automatically, compresses them with AI into structured learnings, and exposes a token-efficient 3-layer progressive disclosure search CLI. Designed to slot into OpenClaw's native `memory-core` (sqlite-vec + BM25 hybrid) without adding external dependencies.

## 🙏 Credits & Inspiration

This project is heavily inspired by **[thedotmack/claude-mem](https://github.com/thedotmack/claude-mem)** — a persistent memory compression system for Claude Code that pioneered the observation → AI compression → progressive disclosure pipeline. The core architecture (hook-based capture, SQLite + FTS5 storage, 3-layer search, session lifecycle management) is adapted from that work for the OpenClaw ecosystem.

Thank you [@thedotmack](https://github.com/thedotmack) 🎉

## 📄 Current Status

🏗️ **Planning phase.** The adoption plan and architecture design live in [`docs/claude-mem-adoption-plan.md`](docs/claude-mem-adoption-plan.md). Implementation will follow a phased rollout.

## 📖 Architecture at a Glance

```
Tool executions (hook) → SQLite observations → AI batch compression
                                                      ↓
                                              memory/YYYY-MM-DD.md  ←→  Native memorySearch
                                                      ↓
                                         openclaw-mem CLI (3-layer search)
                                           search → timeline → get
```

- **Observation capture** via `tool_result_persist` hook — 100% capture rate.
- **AI compression** — 50 raw observations → ~500-token summary (10x compression).
- **Progressive disclosure search** — Layer 1 (compact index, ~50–100 tok/result) → Layer 2 (timeline context) → Layer 3 (full details). ~10x token savings vs. full dump.
- **Proactive memory tools** — `memory_store` and `memory_recall` tools for the agent to explicitly save/retrieve important facts (preferences, decisions, entities).
- **Native storage** — SQLite + FTS5 + sqlite-vec. No ChromaDB, no external deps.
- **Integrates with existing memory** — writes learnings into `memory/*.md`; OpenClaw's built-in `memorySearch` picks them up automatically.

## 🚀 Planned CLI

```bash
openclaw-mem status                        # Store stats, embedding status
openclaw-mem search "auth bug" --limit 20  # Layer 1: compact index
openclaw-mem timeline 23 41 57 --window 4  # Layer 2: chronological context
openclaw-mem get 23 41 57                  # Layer 3: full details
openclaw-mem summarize --session latest    # Run AI compression
openclaw-mem export --to MEMORY.md         # Export learnings to long-term memory
```

## 📄 License

MIT
