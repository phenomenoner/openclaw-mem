# TencentDB-Agent-Memory adoption review

Date: 2026-05-15
Status: implemented first absorption slice
External source: <https://github.com/Tencent/TencentDB-Agent-Memory>
Trust posture: external untrusted product research; upstream benchmark claims are not treated as locally reproduced proof.

## Verdict

TencentDB-Agent-Memory is useful as a design reference, not as a replacement or live dependency for `openclaw-mem`.

The strongest transferable idea is **symbolic short-term memory**: offload verbose evidence to files, keep a compact Mermaid-style canvas in context, and drill down via stable node ids. This fits `openclaw-mem`'s Store / Pack / Observe model without adopting Tencent's plugin, postinstall patching, automatic persona writes, or backend topology.

## Comparison

| Axis | TencentDB-Agent-Memory | openclaw-mem local canon | Adoption decision |
|---|---|---|---|
| Product spine | automatic memory pipeline | Store / Pack / Observe with citations, trust policy, receipts, rollback | Keep openclaw-mem spine |
| Long-term model | L0 conversation → L1 atom → L2 scenario → L3 persona | durable records + bounded ContextPack + optional advanced labs | Absorb as read-model vocabulary only |
| Short-term compression | Mermaid canvas + offloaded raw refs | context packs, artifacts, command-aware compaction, advanced labs | Absorb symbolic canvas helper |
| Storage | SQLite + sqlite-vec default; optional Tencent Cloud Vector DB | local SQLite sidecar plus operator-selected retrieval/index backends and advanced graph/docs lanes | Do not replace backend |
| Recall | automatic capture/extract/recall before turns | governed pack, manual/routeAuto/proactive pack depending install mode | Do not auto-enable broad recall |
| Persona | auto L3 persona generation | MEMORY/SOUL authority + self-model sidecars with gated apply | Reject automatic authority mutation |
| Host integration | OpenClaw plugin, contextEngine slot, runtime patch script | sidecar-first; engine after proof; no live dist hot-swap | Do not install live plugin |
| Debuggability | readable L2/L3/canvas files and refs | citations, include/exclude reasons, trace receipts, rollback | Compatible; strengthen observe docs |

## Value items selected

### 1. Symbolic canvas

**Why valuable:**
Long tool sessions are often too verbose for live context. A compact task graph gives the model and operator a shared map while preserving drill-down refs.

**Local interpretation:**
Add a deterministic helper that converts a small task trace into:

- Mermaid graph text
- stable `node_id` index
- refs to raw evidence
- missing-ref / unresolved-edge warnings

**Implemented:** `openclaw-mem symbolic-canvas build`.

### 2. Layered drill-down vocabulary

**Why valuable:**
Tencent's top → mid → raw chain is a clean debugging story: abstract state should always point back to evidence.

**Local interpretation:**
Map it onto Store / Pack / Observe:

- Store: raw evidence / observations / artifacts
- Pack: compact canvas / node index as bounded injection candidate
- Observe: node_id and refs as receipts

**Implemented:** docs and output schema include this mapping.

### 3. L0-L3 memory language

**Why valuable:**
It provides a useful way to discuss memory evolution from raw dialogue to reusable patterns.

**Local boundary:**
Use as analysis vocabulary for Dream Lite / self-model sidecar, not as an automatic writer into `MEMORY.md`, `SOUL.md`, or authority surfaces.

**Implemented now:** documented in blade map and adoption boundary. Runtime implementation deferred.

## Value items rejected for now

1. **Plugin installation** — rejected because live install would add another memory owner and may patch host behavior.
2. **`postinstall` runtime patch** — rejected for main harness safety; any host patch requires separate controlled plan and rollback.
3. **Automatic L3/persona writes** — rejected because CK authority surfaces require governed review/apply.
4. **Backend replacement** — rejected because `openclaw-mem` already has an operator-selected retrieval/backend posture; Tencent's SQLite/sqlite-vec path is an alternate package design, not a required upgrade path.
5. **Unreproduced benchmark claims** — noted as upstream claims only, not product proof.

## Implemented slice

Files:

- `openclaw_mem/symbolic_canvas.py`
- `openclaw_mem/cli.py` (`symbolic-canvas build`)
- `tests/test_symbolic_canvas.py`
- `docs/symbolic-canvas.md`
- `docs/specs/tencentdb-agent-memory-absorption-blade-map-v0.md`
- `handoffs/receipts/2026-05-15_tencentdb-agent-memory-absorption/`

CLI:

```bash
openclaw-mem symbolic-canvas build \
  --from-file trace.json \
  --base-dir . \
  --out .state/canvas.json \
  --mermaid-out .state/canvas.mmd \
  --json
```

Properties:

- file-only command
- no DB connection required
- no model call
- no Gateway/config/plugin mutation
- no backend topology change

## Verification

Focused tests:

```bash
uv run --python 3.13 --frozen pytest tests/test_symbolic_canvas.py tests/test_cli.py -q
```

Result: `143 passed, 22 subtests passed`.

CLI smoke receipt:

- `handoffs/receipts/2026-05-15_tencentdb-agent-memory-absorption/symbolic-canvas-smoke.json`
- asserted `ok=true`, `nodes=4`, `missing_refs=0`

Diff hygiene:

```bash
git diff --check -- openclaw_mem/symbolic_canvas.py openclaw_mem/cli.py tests/test_symbolic_canvas.py docs/symbolic-canvas.md docs/specs/tencentdb-agent-memory-absorption-blade-map-v0.md README.md
```

Result: passed.

## Remaining useful follow-ups

1. Add a Pack adapter that can include symbolic-canvas artifacts as a bounded `ContextPack` source with citations.
2. Add a command-aware compaction bridge that can emit trace JSON from selected tool-call receipts, still without live Gateway patching.
3. Add a Dream Lite reviewer that can propose scenario/persona-style summaries as advisory packets, not authority writes.
4. Add a benchmark comparing normal verbose receipts vs symbolic-canvas injection on a fixed long-task fixture.

## Topology impact

Unchanged. This slice added docs, tests, a Python module, a file-only CLI command, and receipts. It did not install TencentDB-Agent-Memory, patch OpenClaw, restart Gateway, or change memory backend configuration.
