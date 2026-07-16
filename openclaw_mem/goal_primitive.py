"""Compatibility alias for :mod:`openclaw_mem.labs.goal_primitive`."""
import sys
import warnings
from openclaw_mem.labs import goal_primitive as _implementation
warnings.warn("openclaw_mem.goal_primitive moved to openclaw_mem.labs", DeprecationWarning, stacklevel=2)
sys.modules[__name__] = _implementation
