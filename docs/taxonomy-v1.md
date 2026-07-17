# Memory taxonomy v1

OpenClaw Memory uses eight canonical kinds for durable memories:

| Kind | Meaning |
| --- | --- |
| `fact` | Stable factual knowledge |
| `preference` | A user or project preference |
| `decision` | A choice that was made |
| `entity` | A person, system, repository, or other named subject |
| `event` | A time-bound occurrence |
| `plan` | Intended future work |
| `learning` | A problem paired with its solution or lesson |
| `note` | Useful material without a stronger deterministic classification |

`tool` remains a legacy capture alias. New `note`, `tool`, or empty-kind observations pass through a local deterministic bilingual classifier. Explicit stronger kinds are authoritative and are never overwritten. The rules recognize decision, preference, plan, and problem-plus-solution language in English and Chinese; low-confidence material stays `note`. Classification never calls a model or network service.

Taxonomy is enabled by default. Automatically classified `note`, `tool`, and empty-kind writes add `detail_json.classification = {method, confidence}`; stronger explicit kinds keep their existing stored shape. Set `[taxonomy] enabled = false` in `~/.openclaw-mem/config.toml`, or `OPENCLAW_MEM_TAXONOMY_ENABLED=0`, to preserve the pre-taxonomy write shape for classifiable captures too.

Existing databases require no migration. Preview and apply the idempotent backfill explicitly:

```text
openclaw-mem db backfill --kind --dry-run --json
openclaw-mem db backfill --kind --json
```

The backfill only touches `note`, `tool`, and empty kinds that do not already carry classification metadata. Its receipt includes before/after distributions. Taxonomy is independent from lifecycle state and trust/quarantine policy.
