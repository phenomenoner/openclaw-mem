"""Experimental command ownership declarations kept off the stable core API."""

from __future__ import annotations

import argparse
from typing import Tuple


COMMANDS: Tuple[str, ...] = (
    "dream-lite", "gbrain", "self", "self-curator", "symbolic-canvas", "capsule",
)


def register(_parser: argparse.ArgumentParser) -> Tuple[str, ...]:
    return COMMANDS
