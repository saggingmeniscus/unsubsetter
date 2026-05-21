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
    """Parse a font file and return one FontIndexEntry per contained face.

    Uses fontTools' lazy mode and closes each TTFont after extracting names;
    eager loading on large TTC files (e.g., /System/Library/Fonts/*.ttc, some of
    which are 50–180 MB) caused 2.7 GB peak RSS and minutes of wall time on
    a full default-path scan. With lazy=True + close, the same scan finishes in
    ~2 s and uses a few tens of MB.
    """
    suffix = path.suffix.lower()
    entries: list[FontIndexEntry] = []
    if suffix == ".ttc":
        # Probe the face count once via TTCollection, then open each face
        # independently with TTFont(path, fontNumber=i, lazy=True). Opening
        # each face on its own file handle lets us close them cleanly without
        # invalidating the others.
        with open(path, "rb") as f:
            face_count = len(TTCollection(f, lazy=True).fonts)
        for i in range(face_count):
            tt = TTFont(str(path), fontNumber=i, lazy=True)
            entries.append(_entry_from_ttfont(tt, path, i))
            tt.close()
    elif suffix in (".ttf", ".otf"):
        tt = TTFont(str(path), lazy=True)
        entries.append(_entry_from_ttfont(tt, path, None))
        tt.close()
    return entries


from collections.abc import Iterable


class FontIndex:
    """A lookup table from normalized font names to FontIndexEntry."""

    _FONT_EXTS = {".ttf", ".otf", ".ttc"}

    def __init__(self, entries_by_key: dict[str, FontIndexEntry]):
        self._by_key = entries_by_key

    @classmethod
    def build(cls, search_paths: Iterable[Path]) -> "FontIndex":
        by_key: dict[str, FontIndexEntry] = {}
        for root in search_paths:
            root = Path(root)
            if not root.exists():
                continue
            for path in root.rglob("*"):
                if path.suffix.lower() not in cls._FONT_EXTS:
                    continue
                try:
                    entries = read_font_entries(path)
                except Exception:
                    # A corrupt font file shouldn't break the index build.
                    continue
                for e in entries:
                    for key in cls._keys_for(e):
                        by_key.setdefault(key, e)
        return cls(by_key)

    @staticmethod
    def _keys_for(e: FontIndexEntry) -> list[str]:
        keys = []
        for raw in (e.ps_name, e.full_name, f"{e.family} {e.subfamily}".strip()):
            n = normalize_name(raw)
            if n:
                keys.append(n)
        return keys

    def lookup(self, name: str) -> FontIndexEntry | None:
        return self._by_key.get(normalize_name(name))

    def __len__(self) -> int:
        return len({id(e) for e in self._by_key.values()})


def default_search_paths() -> list[Path]:
    """Standard font locations on macOS, plus TeX Live trees if present."""
    home = Path.home()
    candidates = [
        home / "Library/Fonts",
        Path("/Library/Fonts"),
        Path("/System/Library/Fonts/Supplemental"),
        Path("/System/Library/Fonts"),
    ]
    # Add discovered TeX Live font roots.
    for tl_root in sorted(Path("/usr/local/texlive").glob("*/texmf-dist/fonts")):
        for sub in ("opentype", "truetype"):
            p = tl_root / sub
            if p.exists():
                candidates.append(p)
    return [p for p in candidates if p.exists()]
