# Documentation lifecycle and public-facing hygiene

The repository keeps both current operator guidance and historical engineering
evidence. They serve different purposes and must not be presented as if they
have equal operational authority.

## Authority order

When documents disagree, use this order:

1. current CLI help and machine-readable receipts
2. `README.md`, [Quickstart](quickstart.md), and pages in the active MkDocs nav
3. current contract/reference pages under `docs/`
4. historical release notes, receipts, specs, research, and archive material

Archived content explains how a decision was reached; it does not override
current commands, defaults, or safety gates.

## Document classes

| Class | Location | Public site behavior | Maintenance rule |
| --- | --- | --- | --- |
| Current guide/reference | active MkDocs nav | searchable and navigable | update with behavior changes; command examples must remain executable |
| Current generated asset | generated docs/snippets | linked only when useful | edit canonical source and regenerate |
| Historical archive | `docs/archive/` | archive indexes only | retain for provenance; add a superseded banner |
| Receipt/evidence | `docs/receipts/`, dated closure docs | excluded from site search | immutable except redaction, link repair, or an explicit correction note |
| Internal plan/spec/research | `docs/specs/`, `docs/launch/`, `docs/series/` | excluded from site search | never represent as shipped behavior |
| Legacy compatibility guide | stable historical URL, Archive nav | accessible but visibly retired | preserve links; point new users to the replacement |

## Retirement criteria

Retire or archive a document when any of these is true:

- a completed run/report supersedes its active control checklist
- its command surface is legacy and a current replacement exists
- it is a draft release note for an already superseded version
- it is research/adoption input rather than local product authority
- its primary value is provenance rather than current operation

Do not delete useful receipts merely to reduce file count. Move them out of the
active navigation and keep their status explicit.

## Public-facing hygiene rules

- Never publish tokens, credentials, raw memory rows, personal identifiers, or
  real operator database/config paths.
- Use placeholders such as `<memory.sqlite>`, `<harness-home>`,
  `<openclaw-mem-repo>`, and `<operator-only>`.
- Label external research as untrusted design input, not reproduced proof.
- Label optional/labs behavior accurately; fail-open fallback is not full
  backend parity.
- Keep retired pages out of the active Reference section.
- Prefer GitHub Releases over multiple active release-note pages.
- Run strict MkDocs, link/skill tests, and the docs hygiene scan before release.

## 2026-07-17 audit

The v2 release audit reviewed all 279 Markdown documents then present plus the
MkDocs navigation, HTML control mirror, and root handoffs. It:

- replaced the pre-v2 upgrade checklist with a v2 local-agent guide and archived
  the old checklist
- archived the completed 2026-06-12 project-management control surface
- moved legacy gateway guides from active Reference navigation to Archive
- kept receipts, dated closures, specs, research, and old release notes in Git
  while excluding them from public site search
- promoted still-current CLI exit, DB concurrency, graph usage, portable
  capsule, and experimental graph pages into an explicit nav category
- removed machine-local paths and operator-specific identifiers from tracked
  documentation

Future audits should update this section only when the classification rules or
material archive boundaries change.
