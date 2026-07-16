"""Shared output-free privacy marker checks."""

PRIVATE_MARKERS = ("<private>", "</private>", "[NOEXPORT]", "[PRIVATE]", "[NOMEM]")


def is_private_text(text: str) -> bool:
    upper = str(text or "").upper()
    lower = str(text or "").lower()
    return any(marker.lower() in lower for marker in PRIVATE_MARKERS) or "PRIVATE:" in upper
