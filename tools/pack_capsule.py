#!/usr/bin/env python3
"""Compatibility wrapper for portable pack capsules.

Primary lane is now first-class:
  openclaw-mem capsule <subcommand>

This helper remains for backwards compatibility and delegates to the same
implementation module used by `openclaw-mem capsule ...` and
`openclaw-mem-pack-capsule ...`.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from openclaw_mem.capsule import standalone_main


if __name__ == "__main__":
    raise SystemExit(standalone_main())
