"""Graph command ownership declarations."""

from __future__ import annotations

import argparse
from typing import Tuple


COMMANDS: Tuple[str, ...] = ("graph", "graph-index", "graph-pack")


def register(_parser: argparse.ArgumentParser) -> Tuple[str, ...]:
    return COMMANDS
