"""Ring-0 command ownership declarations."""

from __future__ import annotations

import argparse
from typing import Tuple


COMMANDS: Tuple[str, ...] = (
    "status", "doctor", "profile", "backend", "ingest", "harvest", "store",
    "search", "vsearch", "hybrid", "pack", "timeline", "get", "episodes",
    "docs", "db",
)


def register(_parser: argparse.ArgumentParser) -> Tuple[str, ...]:
    return COMMANDS
