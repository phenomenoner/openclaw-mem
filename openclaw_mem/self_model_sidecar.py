"""Compatibility alias for :mod:`openclaw_mem.labs.self_model_sidecar`."""
import sys
import warnings
from openclaw_mem.labs import self_model_sidecar as _implementation
warnings.warn("openclaw_mem.self_model_sidecar moved to openclaw_mem.labs", DeprecationWarning, stacklevel=2)
sys.modules[__name__] = _implementation
