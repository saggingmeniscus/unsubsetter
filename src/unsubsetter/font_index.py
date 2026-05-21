"""Font index: scans font search paths and resolves font names to disk files."""
from __future__ import annotations
import re

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_name(name: str) -> str:
    """Normalize a font name for indexing: lowercase + strip non-alphanumeric."""
    return _NON_ALNUM.sub("", name.lower())
