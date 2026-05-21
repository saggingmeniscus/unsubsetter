"""PDF inspector: enumerate font records from a pikepdf Pdf."""
from __future__ import annotations
import re

_SUBSET_PREFIX_RE = re.compile(r"^([A-Z]{6})\+(.+)$")


def split_subset_prefix(base_font: str) -> tuple[str | None, str]:
    """Split a PostScript name into (subset_prefix, base_name).

    Returns (None, base_font) if no valid subset prefix is present.
    """
    m = _SUBSET_PREFIX_RE.match(base_font)
    if m:
        return m.group(1), m.group(2)
    return None, base_font
