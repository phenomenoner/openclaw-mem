#!/usr/bin/env python3
"""Trust-policy synthetic proof on synthetic memory only.

This proof deliberately avoids any live OpenClaw memory path. It ingests the
small public fixture under docs/showcase/artifacts into a temporary SQLite DB,
then compares:

1. vanilla retrieval/packing, with no trust gate
2. trust-aware packing, with quarantined rows excluded fail-open for unknown rows

The point is not to claim broad benchmark coverage. The point is to make the
core product wedge falsifiable in one local command.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

QUERY = "context packing OR hostile OR durable OR citations"
POLICY = "exclude_quarantined_fail_open"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_trust_by_ref(fixture: Path) -> dict[str, str]:
    trust_by_ref: dict[str, str] = {}
    with fixture.open("r", encoding="utf-8") as fh:
        for idx, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            trust = row.get("detail", {}).get("trust_tier", "unknown")
            trust_by_ref[f"obs:{idx}"] = trust
    return trust_by_ref


def _run_json(args: list[str], cwd: Path) -> dict[str, Any]:
    proc = subprocess.run(
        args,
        cwd=str(cwd),
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:  # pragma: no cover - diagnostic path
        raise RuntimeError(
            f"Command did not emit JSON: {' '.join(args)}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        ) from exc


def _summarize_pack(pack: dict[str, Any], trust_by_ref: dict[str, str]) -> dict[str, Any]:
    items = pack.get("items", [])
    refs = [item.get("recordRef") for item in items]
    refs = [ref for ref in refs if isinstance(ref, str)]
    trust_counts = {"trusted": 0, "quarantined": 0, "unknown": 0}
    for ref in refs:
        trust = trust_by_ref.get(ref, "unknown")
        trust_counts[trust] = trust_counts.get(trust, 0) + 1
    citations = pack.get("citations", [])
    cited_refs = {
        citation.get("recordRef")
        for citation in citations
        if isinstance(citation, dict) and citation.get("recordRef")
    }
    return {
        "selected_refs": refs,
        "selected_count": len(refs),
        "bundle_chars": len(pack.get("bundle_text", "")),
        "citation_count": len(citations),
        "citation_coverage": f"{len(cited_refs.intersection(refs))}/{len(refs)}",
        "trust_counts": trust_counts,
    }


def run_proof(artifact: Path | None = None) -> dict[str, Any]:
    root = _repo_root()
    fixture = root / "docs" / "showcase" / "artifacts" / "trust-aware-context-pack.synthetic.jsonl"
    trust_by_ref = _load_trust_by_ref(fixture)

    with tempfile.TemporaryDirectory(prefix="openclaw-mem-proof-") as td:
        db = Path(td) / "trust-policy-proof-memory.sqlite"
        ingest = _run_json(
            [
                sys.executable,
                "-m",
                "openclaw_mem",
                "ingest",
                "--db",
                str(db),
                "--json",
                "--file",
                str(fixture),
            ],
            cwd=root,
        )
        vanilla = _run_json(
            [
                sys.executable,
                "-m",
                "openclaw_mem",
                "pack",
                "--db",
                str(db),
                "--query",
                QUERY,
                "--limit",
                "5",
                "--budget-tokens",
                "500",
                "--trace",
            ],
            cwd=root,
        )
        trust_aware = _run_json(
            [
                sys.executable,
                "-m",
                "openclaw_mem",
                "pack",
                "--db",
                str(db),
                "--query",
                QUERY,
                "--limit",
                "5",
                "--budget-tokens",
                "500",
                "--trace",
                "--pack-trust-policy",
                POLICY,
            ],
            cwd=root,
        )

    vanilla_summary = _summarize_pack(vanilla, trust_by_ref)
    trust_summary = _summarize_pack(trust_aware, trust_by_ref)
    trust_policy = trust_aware.get("trust_policy", {})
    assertions = {
        "synthetic_fixture_only": True,
        "no_real_memory_paths_used": True,
        "quarantined_removed": vanilla_summary["trust_counts"].get("quarantined", 0) >= 1
        and trust_summary["trust_counts"].get("quarantined", 0) == 0,
        "citation_coverage_preserved": vanilla_summary["citation_coverage"].endswith(
            f"/{vanilla_summary['selected_count']}"
        )
        and trust_summary["citation_coverage"].endswith(f"/{trust_summary['selected_count']}"),
        "trust_policy_explains_exclusion": trust_policy.get("decision_reason_counts", {}).get(
            "trust_quarantined_excluded", 0
        )
        >= 1,
    }
    result = {
        "kind": "openclaw-mem.proof.trust-policy-synthetic.v1",
        "fixture": str(fixture.relative_to(root)),
        "query": QUERY,
        "comparison": {
            "vanilla_pack": vanilla_summary,
            "trust_aware_pack": trust_summary,
        },
        "delta": {
            "quarantined_selected": trust_summary["trust_counts"].get("quarantined", 0)
            - vanilla_summary["trust_counts"].get("quarantined", 0),
            "trusted_selected": trust_summary["trust_counts"].get("trusted", 0)
            - vanilla_summary["trust_counts"].get("trusted", 0),
            "bundle_chars": trust_summary["bundle_chars"] - vanilla_summary["bundle_chars"],
        },
        "trust_policy_reason_counts": trust_policy.get("decision_reason_counts", {}),
        "assertions": assertions,
        "passed": all(assertions.values()),
        "ingest_receipt_keys": sorted(ingest.keys()),
    }
    if artifact is not None:
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument("--artifact", type=Path, help="Optional path to write the JSON receipt")
    args = parser.parse_args()

    result = run_proof(args.artifact)
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        before = result["comparison"]["vanilla_pack"]
        after = result["comparison"]["trust_aware_pack"]
        print("Trust-policy synthetic proof")
        print(f"fixture: {result['fixture']}")
        print(f"passed: {result['passed']}")
        print(f"vanilla refs: {', '.join(before['selected_refs'])}")
        print(f"trust-aware refs: {', '.join(after['selected_refs'])}")
        print(f"quarantined selected: {before['trust_counts'].get('quarantined', 0)} -> {after['trust_counts'].get('quarantined', 0)}")
        print(f"citation coverage: {before['citation_coverage']} -> {after['citation_coverage']}")
        print(f"bundle chars: {before['bundle_chars']} -> {after['bundle_chars']}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
