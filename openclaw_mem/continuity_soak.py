"""Compatibility alias for :mod:`openclaw_mem.labs.continuity_soak`."""
import sys
import warnings
from openclaw_mem.labs import continuity_soak as _implementation
warnings.warn("openclaw_mem.continuity_soak moved to openclaw_mem.labs", DeprecationWarning, stacklevel=2)
sys.modules[__name__] = _implementation
