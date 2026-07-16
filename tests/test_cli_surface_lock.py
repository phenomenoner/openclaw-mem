from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO

import pytest

from openclaw_mem.cli import build_parser


GOLDEN_COMMAND_PATHS = frozenset(
    """
active-line
active-line pack
artifact
artifact compact-receipt
artifact fetch
artifact peek
artifact rehydrate
artifact stash
backend
bridge
bridge recall
bridge status
bridge store
capsule
capsule diff
capsule export-canonical
capsule inspect
capsule restore
capsule seal
capsule verify
codex
codex doctor
codex install
curate
curate apply
curate review
curate rollback
curate scan
curate verify
continuity
continuity adjudication
continuity attachment-map
continuity auto-run
continuity compare-migration
continuity compare-sessions
continuity current
continuity diff
continuity disable
continuity enable
continuity explain
continuity golden-eval
continuity governance
continuity interventions
continuity ledger
continuity mirror
continuity patterns
continuity public-summary
continuity release
continuity release-history
continuity rule-table
continuity sensitivity
continuity status
continuity threat-feed
continuity triggers
continuity wording-lint
db
db backfill
db info
db migrate
db reindex
db rollback
docs
docs ingest
docs search
doctor
dream-lite
dream-lite apply
dream-lite apply plan
dream-lite apply rollback
dream-lite apply run
dream-lite apply verify
dream-lite director
dream-lite director apply
dream-lite director checkpoint
dream-lite director observe
dream-lite director stage
embed
engine
engine snapshot
engine snapshot checkout
engine snapshot create
engine snapshot delete
engine snapshot list
episodes
episodes append
episodes append-session-store-receipt
episodes embed
episodes extract-sessions
episodes gc
episodes ingest
episodes query
episodes redact
episodes replay
episodes search
export
gbrain-sidecar
gbrain-sidecar consult
gbrain-sidecar jobs-list
gbrain-sidecar jobs-retry
gbrain-sidecar jobs-smoke
gbrain-sidecar jobs-submit
gbrain-sidecar recommend-refresh
gbrain-sidecar refresh-canary
get
goal
goal pack
goal status
governed
governed advisory-dossier
governed apply-review
governed release-check
graph
graph auto-status
graph capture-git
graph capture-md
graph export
graph extract
graph fact
graph fact assert
graph fact current
graph fact guard
graph fact guard-lint
graph fact invalidate
graph fact lint
graph fact measure-extraction
graph fact pack
graph fact propose
graph fact rebuild
graph fact registry
graph fact route
graph fact stale
graph fact timeline
graph health
graph impact
graph index
graph lint
graph match
graph pack
graph preflight
graph query
graph query downstream
graph query drift
graph query filter
graph query lineage
graph query provenance
graph query receipts
graph query subgraph
graph query symbol
graph query upstream
graph query writers
graph readiness
graph render
graph render topology
graph synth
graph synth compile
graph synth recommend
graph synth refresh
graph synth stale
graph topology-diff
graph topology-extract
graph topology-refresh
harness
harness detect
harness install
harness verify
harvest
hybrid
index
ingest
ingest-review
ingest-review source
init
install
mem-system
mem-system status
mem-system verify
mutation
mutation apply
mutation plan
mutation rollback
mutation stage
mutation validate
optimize
optimize assist-apply
optimize canary-advisory
optimize challenger-review
optimize consolidation-review
optimize effect-followup
optimize evolution-review
optimize governor-review
optimize policy-loop
optimize posture-review
optimize review
optimize verifier-bundle
pack
pack-artifacts-observe
profile
qdrant
qdrant recall
qdrant status
route
route auto
recall
routing
routing eval
routing resolve
search
self
self adjudication
self attachment-map
self auto-run
self compare-migration
self compare-sessions
self current
self diff
self disable
self enable
self explain
self golden-eval
self governance
self interventions
self ledger
self mirror
self patterns
self public-summary
self release
self release-history
self rule-table
self sensitivity
self status
self threat-feed
self triggers
self wording-lint
self-curator
self-curator apply
self-curator controller
self-curator plan
self-curator rollback
self-curator skill-review
self-curator verify
semantic
service
service lease
service recall
service status
service-store
service-store init
service-store status
skill-capture
skill-capture propose
skill-curator
skill-curator lint
skill-curator review
status
steward
steward review
store
summarize
surface
surface validate
sync
sync init
sync run
sync status
symbolic-canvas
symbolic-canvas build
timeline
triage
vsearch
writeback-lancedb
writeback-store
writeback-store init
writeback-store status
""".strip().splitlines()
)


def _command_paths(
    parser: argparse.ArgumentParser, prefix: tuple[str, ...] = ()
) -> set[str]:
    paths: set[str] = set()
    for action in parser._actions:
        if not isinstance(action, argparse._SubParsersAction):
            continue
        for name, child in action.choices.items():
            path = (*prefix, name)
            paths.add(" ".join(path))
            paths.update(_command_paths(child, path))
    return paths


def test_cli_command_surface_matches_explicit_golden_list() -> None:
    actual = _command_paths(build_parser())
    missing = sorted(GOLDEN_COMMAND_PATHS - actual)
    added = sorted(actual - GOLDEN_COMMAND_PATHS)
    assert actual == GOLDEN_COMMAND_PATHS, (
        "CLI command surface changed; explicitly review and update the golden list. "
        f"missing={missing!r}, added={added!r}"
    )


@pytest.mark.parametrize(
    "command", sorted(path for path in GOLDEN_COMMAND_PATHS if " " not in path)
)
def test_each_top_level_command_help_exits_successfully(command: str) -> None:
    output = StringIO()
    with redirect_stdout(output), redirect_stderr(output):
        with pytest.raises(SystemExit) as exc_info:
            build_parser().parse_args([command, "--help"])
    assert exc_info.value.code == 0, output.getvalue()
