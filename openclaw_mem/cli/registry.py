"""Command ownership registry for the compatibility CLI package.

The parser remains byte-compatible while command families are extracted behind
small modules.  Registry metadata is attached to the parser so tests and future
modules can validate ownership without importing optional implementations.
"""

from __future__ import annotations

import argparse
import importlib
from typing import Dict, Tuple


MODULES: Tuple[str, ...] = (
    "core_cmds",
    "graph_cmds",
    "engine_cmds",
    "labs_cmds",
    "ops_cmds",
)


def register(parser: argparse.ArgumentParser) -> Dict[str, str]:
    ownership: Dict[str, str] = {}
    for module_name in MODULES:
        module = importlib.import_module(f"openclaw_mem.cli.{module_name}")
        for command in module.register(parser):
            previous = ownership.setdefault(command, module_name)
            if previous != module_name:
                raise RuntimeError(f"CLI command ownership collision: {command}: {previous}/{module_name}")
    setattr(parser, "openclaw_command_registry", dict(sorted(ownership.items())))
    return ownership
