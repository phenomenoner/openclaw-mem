"""Governance and operational command ownership declarations."""

from __future__ import annotations

import argparse
from typing import Tuple


COMMANDS: Tuple[str, ...] = (
    "optimize", "skill-curator", "steward", "governed", "mutation", "continuity",
    "harness", "codex", "routing", "skill-capture", "mem-system", "pack-artifacts-observe",
)


def register(_parser: argparse.ArgumentParser) -> Tuple[str, ...]:
    return COMMANDS
