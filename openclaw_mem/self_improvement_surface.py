"""Compatibility alias for :mod:`openclaw_mem.labs.self_improvement_surface`."""
import sys
import warnings
from openclaw_mem.labs import self_improvement_surface as _implementation
warnings.warn("openclaw_mem.self_improvement_surface moved to openclaw_mem.labs", DeprecationWarning, stacklevel=2)
sys.modules[__name__] = _implementation
