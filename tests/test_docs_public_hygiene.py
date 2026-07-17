from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOC_SUFFIXES = {".md", ".html", ".yml", ".yaml"}
FORBIDDEN_PUBLIC_MARKERS = (
    "D:\\Warehouse\\",
    "C:\\Users\\user\\",
    "/home/agent/",
    "lyria-working-ledger",
)


def _document_paths() -> list[Path]:
    paths: list[Path] = []
    for root in (REPO_ROOT / "docs", REPO_ROOT / "handoffs"):
        paths.extend(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in DOC_SUFFIXES)
    paths.extend(path for path in REPO_ROOT.glob("*.md") if path.is_file())
    paths.append(REPO_ROOT / "mkdocs.yml")
    return sorted(set(paths))


def test_tracked_document_surfaces_do_not_expose_machine_local_markers() -> None:
    hits: list[str] = []
    for path in _document_paths():
        text = path.read_text(encoding="utf-8", errors="replace")
        for marker in FORBIDDEN_PUBLIC_MARKERS:
            if marker in text:
                hits.append(f"{path.relative_to(REPO_ROOT)}: {marker}")
    assert hits == [], "machine-local/public-hygiene markers found:\n" + "\n".join(hits)


def test_completed_project_control_surface_is_archived() -> None:
    assert not (REPO_ROOT / "docs" / "project-management").exists()
    archived = REPO_ROOT / "docs" / "archive" / "project-management-2026-06-12" / "README.md"
    text = archived.read_text(encoding="utf-8")
    assert "ARCHIVED / SUPERSEDED" in text
    assert "RUN-B-REPORT.md" in text


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
