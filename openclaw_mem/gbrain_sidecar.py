"""Compatibility alias for :mod:`openclaw_mem.labs.gbrain_sidecar`."""
import sys
import warnings
from openclaw_mem.labs import gbrain_sidecar as _implementation
warnings.warn("openclaw_mem.gbrain_sidecar moved to openclaw_mem.labs", DeprecationWarning, stacklevel=2)
sys.modules[__name__] = _implementation
