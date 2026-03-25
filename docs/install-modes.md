# Choose an install path

There are **three sane ways** to adopt `openclaw-mem`.
Pick the lightest one that solves your problem.

## Quick-start decision guide

- **Prove it locally (5 minutes)** → start with **Path 1: Local proof**
- **Run sidecar on existing OpenClaw (default)** → choose **Path 2: Sidecar on existing OpenClaw**
- **Promote to optional mem engine when needed** → use **Path 3: Optional Mem Engine**

---

## Path 1 — Local proof in one repo

### Choose this when

- you want a 5-minute product proof
- you do not want to touch OpenClaw config yet
- you want to inspect the SQLite / JSON outputs first

### What changes

- clone repo
- `uv sync --locked`
- generate or provide a JSONL file
- run local recall commands against SQLite

### What you get

- local DB
- deterministic CLI receipts
- proof that `search → timeline → get` works

### First step

Go to [Quickstart](quickstart.md).

### Rollback

Delete the test DB or the repo checkout. No OpenClaw state changed.

---

## Path 2 — Sidecar on an existing OpenClaw install

### Choose this when

- you already use `memory-core` or `memory-lancedb`
- you want capture, freshness, auditability, and local recall
- you want minimal migration risk

### What changes

- enable the `openclaw-mem` plugin
- point it at a JSONL output path
- schedule `harvest` on a freshness cadence
- optionally add embed/index on a slower cadence
- if installing from a marketplace/package registry, this role maps to `@phenomenoner/openclaw-mem`

### What you get

- tool-result capture
- SQLite recall surface
- backend-aware observability
- deterministic triage / ops workflows
- no slot ownership change

### First step

Read:

- [Quickstart](quickstart.md)
- [Deployment guide](deployment.md)
- [Auto-capture plugin](auto-capture.md)
- [Agent memory skill (SOP)](agent-memory-skill.md) (recommended agent prompt contract)

### Rollback

Disable the plugin, stop harvest jobs, remove the symlink if you added one. Your native memory slot stays untouched.

---

## Path 3 — Optional Mem Engine as slot owner

### Choose this when

- sidecar mode already proved useful
- you want hybrid recall, policies, and bounded automation in the active memory slot
- you are comfortable doing a controlled switch with smoke tests and rollback

### What changes

- keep the sidecar for capture / audit
- enable `openclaw-mem-engine`
- switch `plugins.slots.memory`
- smoke test store / recall / forget
- if installing from a marketplace/package registry, this role maps to `@phenomenoner/openclaw-mem-engine`

### What you get

- hybrid recall path
- operator-tunable receipts and policies
- more explicit control over recall/capture behavior
- one-line rollback to `memory-core` or `memory-lancedb`

### First step

Read:

- [Mem Engine reference](mem-engine.md)
- [Ecosystem fit](ecosystem-fit.md)
- [Deployment guide](deployment.md)
- [Agent memory skill (SOP)](agent-memory-skill.md) (recommended agent prompt contract)

### Rollback

Switch `plugins.slots.memory` back to the prior backend and restart OpenClaw.

---

## Recommended default

If you are deciding between paths, choose **Path 2: sidecar on an existing OpenClaw install**.

That is where `openclaw-mem` is easiest to justify:

- high observability value
- low migration risk
- clean rollback
- you can still promote to the engine later

## After you choose

- [About the product](about.md)
- [Quickstart](quickstart.md)
- [Reality check & status](reality-check.md)
- [Deployment guide](deployment.md)
