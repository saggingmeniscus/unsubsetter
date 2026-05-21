"""Font index: scans font search paths and resolves font names to disk files."""
from __future__ import annotations
import re
from dataclasses import dataclass
from pathlib import Path

from fontTools.ttLib import TTFont, TTCollection

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_name(name: str) -> str:
    """Normalize a font name for indexing: lowercase + strip non-alphanumeric."""
    return _NON_ALNUM.sub("", name.lower())


@dataclass(frozen=True)
class FontIndexEntry:
    path: Path
    ttc_face: int | None     # None for plain .ttf/.otf; integer for .ttc faces
    ps_name: str             # name table ID 6
    full_name: str           # name table ID 4
    family: str              # name table ID 1
    subfamily: str           # name table ID 2


def _entry_from_ttfont(tt: TTFont, path: Path, ttc_face: int | None) -> FontIndexEntry:
    name = tt["name"]
    return FontIndexEntry(
        path=path,
        ttc_face=ttc_face,
        ps_name=name.getDebugName(6) or "",
        full_name=name.getDebugName(4) or "",
        family=name.getDebugName(1) or "",
        subfamily=name.getDebugName(2) or "",
    )


def read_font_entries(path: Path) -> list[FontIndexEntry]:
    """Parse a font file and return one FontIndexEntry per contained face."""
    suffix = path.suffix.lower()
    if suffix == ".ttc":
        coll = TTCollection(str(path))
        return [_entry_from_ttfont(tt, path, i) for i, tt in enumerate(coll.fonts)]
    if suffix in (".ttf", ".otf"):
        tt = TTFont(str(path))
        return [_entry_from_ttfont(tt, path, None)]
    return []
