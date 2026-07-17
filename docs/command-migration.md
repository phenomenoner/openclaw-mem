# Command migration

The primary command model is now `recall` for retrieval, `store` for direct memory writes, `curate` for governed maintenance, and `sync` for external writeback. Existing commands remain callable aliases; no removal date is set. JSON alias responses add a `deprecated` object with the recommended command, while the underlying result remains available without information loss.

## Retrieval

| Previous command | Primary command |
| --- | --- |
| `search "query"` | `recall "query" --mode lexical` |
| `vsearch "query"` | `recall "query" --mode vector` |
| `search-hybrid "query"` | `recall "query" --mode hybrid` |
| `search "query" --graph ...` | `recall "query" --mode graph ...` |

Use `recall "query" --mode auto` for normal operation. It selects hybrid when vector capability is available and otherwise degrades to lexical with `mode_effective`, `routing_reason`, and optional `degraded_from` evidence in the receipt.

## Governance

| Primary command | Previous implementation surface |
| --- | --- |
| `curate scan --target memory` | `optimize review` plus `optimize evolution-review` |
| `curate scan --target episodes` | `optimize consolidation-review` |
| `curate scan --target skills` | `skill-curator review` |
| `curate scan --target facts` | `graph fact lint` plus `graph fact stale` |
| `curate review --target ...` | `optimize governor-review` |
| `curate apply --target memory` | `optimize assist-apply` |
| `curate apply --target skills` | governed `self-curator plan/apply` |
| `curate verify --target ...` | `optimize verifier-bundle` |
| `curate rollback --target ... --receipt ...` | assist/self-curator receipt rollback |

The new receipt is `openclaw-mem.curate.<verb>.v1`; the complete legacy receipt is retained under `inner`. Mutating actions still require the same approval flags, drift checks, caps, and rollback evidence as their underlying governed command.

## External synchronization

| Previous surface | Primary command |
| --- | --- |
| LanceDB writeback status/run/init | `sync status|run|init --backend lancedb` |
| service store/writeback status/run/init | `sync status|run|init --backend service` |
| Qdrant readiness/probe | `sync status --backend qdrant` |

An unavailable optional backend returns a structured unsupported/not-installed receipt rather than a traceback. The wrapper never invents write support that the backend does not provide.

## Help and compatibility

`openclaw-mem --help` shows the six primary top-level surfaces: `recall`, `store`, `curate`, `sync`, `graph`, and `db`. Use `openclaw-mem --help-all` to inspect every compatibility and advanced command. Automation can migrate one command at a time because aliases remain functional and their deprecation fields are additive.
