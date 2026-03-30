# Portable Pack Capsules

`openclaw-mem` can package a governed pack into a small **portable capsule** without pretending that the capsule is the new source of truth.

This is the memvid-inspired line we chose to adopt:
- keep portability
- keep receipts
- keep provenance/trust governance outside the capsule itself

## Why this exists

A portable capsule is useful when you want to:
- move a bounded pack between hosts
- archive a specific recall result with integrity checks
- compare a past capsule against a current governed store
- produce a small audit artifact instead of replaying a whole retrieval live

What it is **not**:
- not a governed restore/import contract
- not a replacement for `openclaw-mem` storage/governance
- not a merge engine

## Commands

### 1) Seal a capsule

```bash
DB=/tmp/openclaw-mem-proof.sqlite
OUT=/tmp/openclaw-mem-capsules/trust-aware-demo

openclaw-mem capsule seal \
  --db "$DB" \
  --query "trust-aware context packing prompt pack receipts hostile durable memory provenance" \
  --pack-trust-policy exclude_quarantined_fail_open \
  --stash-artifact \
  --gzip-artifact \
  --out "$OUT"
```

### 2) Inspect the capsule (read-only)

```bash
CAPSULE=$(find "$OUT" -mindepth 1 -maxdepth 1 -type d | sort | tail -1)
openclaw-mem capsule inspect "$CAPSULE"
```

### 3) Verify capsule integrity

```bash
openclaw-mem capsule verify "$CAPSULE"
```

### 4) Diff the capsule against a target store (read-only)

```bash
openclaw-mem capsule diff \
  "$CAPSULE" \
  --db "$DB" \
  --write-receipt \
  --write-report-md
```

### 5) Export canonical artifact (bounded write + dry-run preview)

```bash
CANONICAL_OUT=/tmp/openclaw-mem-canonical-export
openclaw-mem capsule export-canonical --db "$DB" --to "$CANONICAL_OUT" --json
openclaw-mem capsule export-canonical --db "$DB" --dry-run --to "$CANONICAL_OUT" --json
```

## Files you get

After `seal`:
- `manifest.json`
  - includes forward-compat metadata like `capsule_version`, `exported_at`, and `integrity_hash`
- `bundle.json`
- `bundle_text.md`
- `trace.json` (when available)
- `artifact_stash.json` (when artifact stash is enabled)

After `diff --write-receipt --write-report-md`:
- `diff.latest.json`
- `diff.latest.md`

After `export-canonical` (non-dry-run; timestamped directory under `--to`):
- `manifest.json` (`openclaw-mem.canonical-capsule.v1`)
- `observations.jsonl`
- `index.json`
- `provenance.json`

## Boundary rules

### `seal`
- wraps `openclaw-mem pack --json --trace`
- packages the result into a timestamped capsule directory
- optional `artifact stash` is a receipt convenience, not a new storage system

### `inspect`
- verifies first, then shows capsule metadata and a small bundle preview
- can emit human-readable output or structured JSON
- explicitly marks current v0 pack capsules as **not restorable**

### `verify`
- checks declared capsule files against `manifest.json`
- validates sha256 + byte counts
- fails on tamper/drift

### `diff`
- verifies first
- compares capsule items to a target observation store
- current match rule: normalized `kind + summary` exact match
- emits `present` vs `missing`
- **does not mutate** the target store

### `export-canonical`
- non-dry-run writes a versioned canonical artifact directory and runs self-verify
- `--dry-run` emits canonical-manifest contract preview only
- supports machine-readable JSON output (`--json`)
- explicitly states restore/import is not supported yet
- explicitly keeps cross-store migration/merge out of scope

## Why inspect + diff come before restore

We explicitly chose **inspect/diff before restore** because the current capsule captures pack-level selection output, not full canonical observation detail/provenance.

So `inspect` and `diff` are honest read-only lanes.
A future restore/import line would need a stronger canonical artifact contract first.

## Verifier checklist

### Same-store audit
- seal from a test DB
- verify passes
- diff against the same DB → `present > 0`, `missing = 0`

### Empty-store audit
- diff against an empty/missing observations store → `missing > 0`
- `target_store_table_status` should make the situation explicit

### Tamper detection
- modify `bundle_text.md`
- verify should fail non-zero

## Compatibility wrappers

Primary lane is now first-class under `openclaw-mem capsule ...`.

Compatibility wrappers still exist:

```bash
openclaw-mem-pack-capsule seal ...
openclaw-mem-pack-capsule inspect <capsule_dir>
openclaw-mem-pack-capsule verify <capsule_dir>
openclaw-mem-pack-capsule diff <capsule_dir> --db <path> --write-receipt --write-report-md
openclaw-mem-pack-capsule export-canonical --to <output_root> --json
python3 ./tools/pack_capsule.py export-canonical --dry-run --to <output_root> --json
```

Both wrappers delegate to the same implementation as `openclaw-mem capsule ...`.
