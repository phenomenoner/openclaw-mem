from __future__ import annotations

import re
import unicodedata
from typing import Any, Optional


def normalize_scope_token(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    token = unicodedata.normalize("NFKC", str(raw)).strip().lower()
    if not token:
        return None
    token = re.sub(r"[\s]+", "-", token)
    token = re.sub(r"[^a-z0-9._:/-]+", "-", token)
    token = re.sub(r"-+", "-", token)
    token = re.sub(r"^[-./:_]+", "", token)
    token = re.sub(r"[-./:_]+$", "", token)
    return token or None
