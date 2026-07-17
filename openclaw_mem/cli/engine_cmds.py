"""Retrieval-engine and writeback command ownership declarations."""

from __future__ import annotations

import argparse
from typing import Tuple


COMMANDS: Tuple[str, ...] = (
    "engine", "service-store", "writeback-store", "writeback-lancedb", "embed",
    "docs-embed", "qdrant",
)


def register(_parser: argparse.ArgumentParser) -> Tuple[str, ...]:
    return COMMANDS
