# Legacy command mapping

The compatibility commands remain callable. JSON receipts add a `deprecated`
object with the replacement and no scheduled removal; text mode prints one
stderr line while preserving stdout.

| Legacy command | Unified replacement |
| --- | --- |
| `optimize review` | `curate scan --target memory` |
| `optimize evolution-review` | `curate scan --target memory` |
| `optimize consolidation-review` | `curate scan --target episodes` |
| `skill-curator review` | `curate scan --target skills` |
| `self-curator skill-review` | `curate scan --target skills` |
| `graph fact lint` / `graph fact stale` | `curate scan --target facts` |
| `optimize governor-review` | `curate review --target memory` |
| `optimize assist-apply` | `curate apply --target memory` |
| `self-curator plan` / `self-curator apply` | `curate apply --target skills` |
| `optimize verifier-bundle` | `curate verify --target memory` |
| `self-curator verify` | `curate verify --target skills` |
| `self-curator rollback` | `curate rollback --target skills` |

Memory rollback is now executable through `curate rollback --target memory`
using the `rollback_ref` emitted by a successful assist-apply receipt. It
refuses partial restore when any current row hash has drifted.
