# Routing manual

Break ties in this order: docs search (canonical wording), topology search (location and impact), graph match (idea-to-project candidates), durable recall (preferences and decisions), confirmed store, then session-local no-op.

## Lane boundaries

- L1 durable memory stores compact confirmed facts, not raw evidence.
- L2 docs search owns canonical documents and SOPs.
- L3 topology and graph search own location, dependency, impact, and candidate routing.
- Episodic search owns verbatim session evidence; it does not silently promote evidence to durable truth.
- Synthesis cards and symbolic canvases are derived artifacts. Keep covered raw refs and provenance.

## Graph and routing

Run `openclaw-mem graph readiness --json` before autonomous graph routing. Use `openclaw-mem route auto <query> --json` as the fail-open router. If readiness is red, report the limitation and fall back to docs, recall, or repository inspection. Before ambiguous file-changing work, ground the repository with `openclaw-mem routing resolve <query> --workspace-root <workspace> --json`.

Prefer a fresh synthesis card only when its receipt preserves `preferredCardRefs` and `coveredRawRefs`. Use `openclaw-mem graph synth recommend --json` before an explicit refresh.

## Governed maintenance

Scout observation maintenance with `openclaw-mem optimize evolution-review --json`; keep judgment in `optimize governor-review`, and route approved mutation through `optimize assist-apply` with receipts and rollback. Do not collapse scout, governor, and writer roles.

Dream Lite apply is governed: `apply plan` and `apply verify` are dry-run gates; `apply run` is a narrow governor-approved refresh canary. `compile_new_card` and Director artifacts remain proposals or rehearsals, never hidden authority changes.

Before risky engine dataset mutation, run `openclaw-mem engine snapshot create --tag <tag> --reason <reason> --json`. Checkout and delete require explicit confirmation, and active-dataset checkout may require restart approval.

## Tool mapping

- Recall/store: `memory_recall`, `memory_store`
- Docs: `memory_docs_search`
- Topology: `openclaw-mem graph query <query> --json`
- Idea routing: `openclaw-mem graph match <query> --json`
- Verbatim evidence: `openclaw-mem episodes search <query> --mode hybrid --trace --json`
- Bounded context: `openclaw-mem pack --query <query> --trace --json`
