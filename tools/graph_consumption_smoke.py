from pathlib import Path

from openclaw_mem.cli import _connect, _insert_observation


def main() -> None:
    outdir = Path("handoffs/receipts/2026-03-31_graph-consumption")
    outdir.mkdir(parents=True, exist_ok=True)
    db = outdir / "graph-consumption-smoke.sqlite"
    if db.exists():
        db.unlink()

    conn = _connect(str(db))
    _insert_observation(
        conn,
        {
            "ts": "2026-03-31T05:30:00Z",
            "kind": "fact",
            "tool_name": "memory_store",
            "summary": "openclaw-mem roadmap dependency note and graph integration receipt",
            "detail": {
                "importance": {"score": 0.86, "label": "must_remember"},
                "trust_tier": "trusted",
            },
        },
    )
    conn.commit()
    conn.close()
    print(db)


if __name__ == "__main__":
    main()
