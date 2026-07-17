from __future__ import annotations

import io
import re
import subprocess
import tarfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOC_SUFFIXES = {".md", ".html", ".yml", ".yaml"}
FORBIDDEN_PUBLIC_MARKERS = (
    "D:\\Warehouse\\",
    "C:\\Users\\user\\",
    "/home/agent/",
    "lyria-working-ledger",
)
INTERNAL_ROOT_LEDGER = re.compile(r"^(?:PROGRESS-RUN-[^/]+|RUN-[^/]+-REPORT)\.md$")
FORBIDDEN_PUBLIC_PATHS = {
    "handoffs/2026-07-17-openclaw-mem-run-a-handoff.md",
}
PUBLIC_ARCHIVE_PATHS = (
    "docs",
    "handoffs",
    "openclaw_mem",
    "skills",
    "mkdocs.yml",
    ":(glob)*.md",
)

# Existing audience-mismatch debt is tracked as a non-growth budget while it is
# removed incrementally. Dedicated path and release-note assertions below keep
# the completed v2 execution ledgers from returning.
AUDIENCE_MARKER_LIMITS = {
    "personal CK token": (re.compile(r"(?<![A-Za-z0-9_])CK(?![A-Za-z0-9_])"), 75),
    "Lyria token": (re.compile(r"(?<![A-Za-z0-9_])Lyria(?![A-Za-z0-9_])"), 35),
    "Chinese Lyria token": (re.compile("藍璃"), 0),
    "legacy workspace path": (re.compile(r"/root/\.openclaw/workspace"), 97),
    "personal approval flag": (re.compile(r"--ck-approved"), 3),
    "personal approval status": (re.compile(r"NEEDS_CK"), 10),
}


def _document_paths() -> list[Path]:
    paths: list[Path] = []
    for root in (REPO_ROOT / "docs", REPO_ROOT / "handoffs"):
        paths.extend(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in DOC_SUFFIXES)
    paths.extend(path for path in REPO_ROOT.glob("*.md") if path.is_file())
    paths.append(REPO_ROOT / "mkdocs.yml")
    return sorted(set(paths))


def _public_archive_text() -> dict[str, str]:
    result = subprocess.run(
        ["git", "archive", "--format=tar", "HEAD", "--", *PUBLIC_ARCHIVE_PATHS],
        cwd=REPO_ROOT,
        check=True,
        stdout=subprocess.PIPE,
    )
    files: dict[str, str] = {}
    with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:") as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            extracted = archive.extractfile(member)
            if extracted is None:
                continue
            files[member.name] = extracted.read().decode("utf-8", errors="replace")
    return files


def test_tracked_document_surfaces_do_not_expose_machine_local_markers() -> None:
    hits: list[str] = []
    for path in _document_paths():
        text = path.read_text(encoding="utf-8", errors="replace")
        for marker in FORBIDDEN_PUBLIC_MARKERS:
            if marker in text:
                hits.append(f"{path.relative_to(REPO_ROOT)}: {marker}")
    assert hits == [], "machine-local/public-hygiene markers found:\n" + "\n".join(hits)


def test_completed_project_control_surface_is_archived() -> None:
    for filename in (
        "PROGRESS-RUN-A.md",
        "PROGRESS-RUN-B.md",
        "RUN-A-REPORT.md",
        "RUN-B-REPORT.md",
    ):
        assert not (REPO_ROOT / filename).exists()
    assert not (REPO_ROOT / "docs" / "project-management").exists()
    archived = REPO_ROOT / "docs" / "archive" / "project-management-2026-06-12" / "README.md"
    text = archived.read_text(encoding="utf-8")
    assert "ARCHIVED / SUPERSEDED" in text
    assert "docs/releases-v2.0.0.md" in text
    assert "RUN-B-REPORT.md" not in text


def test_git_archive_excludes_internal_execution_ledgers() -> None:
    files = _public_archive_text()
    leaked = sorted(
        path
        for path in files
        if INTERNAL_ROOT_LEDGER.fullmatch(path) or path in FORBIDDEN_PUBLIC_PATHS
    )
    assert leaked == [], "internal execution ledgers found in git archive:\n" + "\n".join(leaked)


def test_v2_release_notes_use_product_language() -> None:
    text = _public_archive_text()["docs/releases-v2.0.0.md"]
    forbidden = ("Run A", "Run B", "Run C", "task ledger")
    hits = [marker for marker in forbidden if marker in text]
    assert hits == [], "internal execution language found in v2 release notes: " + ", ".join(hits)


def test_public_audience_mismatch_debt_does_not_grow() -> None:
    files = _public_archive_text()
    text = "\n".join(files.values())
    over_budget: list[str] = []
    for label, (pattern, limit) in AUDIENCE_MARKER_LIMITS.items():
        count = len(pattern.findall(text))
        if count > limit:
            over_budget.append(f"{label}: {count} > {limit}")
    assert over_budget == [], "public audience-mismatch debt grew:\n" + "\n".join(over_budget)


def test_upgrade_guide_covers_safe_local_agent_transition() -> None:
    guide = (REPO_ROOT / "docs" / "upgrade-checklist.md").read_text(encoding="utf-8")
    required = (
        "stop writers",
        "db migrate",
        "--dry-run",
        "--receipt-out",
        "db rollback",
        "install --harness",
        "doctor --harness",
        "openclaw-mem-mcp",
        "--no-file-write",
        "v2.0.0",
    )
    for fragment in required:
        assert fragment in guide


def test_legacy_gateway_guides_are_archive_only_in_navigation() -> None:
    config = (REPO_ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    reference = config.split("  - Reference:", 1)[1].split("  - Advanced Labs:", 1)[0]
    archive = config.split("  - Archive:", 1)[1].split("  - 繁體中文:", 1)[0]
    legacy = (
        "harness-persistent-memory.md",
        "remote-memory-gateway.md",
        "shared-memory-gateway-agent-guide.md",
    )
    for path in legacy:
        assert path not in reference
        assert path in archive
