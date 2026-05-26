# Repo graph ingest experiment

`repo-graph-ingest` is an experimental, file-only way to use an upstream repository knowledge graph as **candidate Pack/Observe context**.

It is designed for comparison and onboarding workflows:

```text
Understand-Anything knowledge-graph.json
→ compact ContextPack-style artifact
→ lexical baseline vs graph-neighborhood comparison
→ report.md + comparison.json receipts
```

## Safety posture

This experiment does **not**:

- install an upstream agent skill
- write durable memory Store records
- modify Gateway, plugin, cron, or runtime config
- treat the upstream graph as source of truth

The graph output is useful as context and navigation support. It should be verified before driving product or ops decisions.

## Run the experiment

```bash
python scripts/repo_graph_neighborhood_experiment.py \
  --graph /path/to/.understand-anything/knowledge-graph.json \
  --repo-root /path/to/repo \
  --out-dir /tmp/repo-graph-experiment \
  --query "retrieval backend selection" \
  --query "graph context pack creation"
```

The output directory contains:

- `pack.json` — compact ContextPack-style candidate context
- `comparison.json` — machine-readable baseline vs graph-neighborhood comparison
- `report.md` — human-readable summary
- `manifest.json` — graph digest, repo commit, and output map

## Metrics

For each query, the experiment records:

- baseline lexical path count
- graph path count including neighbors
- overlapping paths
- novel graph paths
- neighborhood novelty rate

These are directional diagnostics, not benchmark claims. Use them to decide whether graph-neighborhood expansion improves a specific Pack-lane workflow before integrating it into a larger pipeline.
