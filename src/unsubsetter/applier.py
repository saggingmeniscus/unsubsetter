"""Applier: executes a Plan on a pikepdf Pdf."""
from __future__ import annotations
from io import BytesIO
from pathlib import Path

from fontTools.ttLib import TTFont


def load_full_font_bytes(path: Path, ttc_face: int | None) -> bytes:
    """Load a font from disk and return its TTF binary.

    For TTC inputs, extract only the requested face as a standalone TTF.
    """
    kwargs = {"fontNumber": ttc_face} if ttc_face is not None else {}
    tt = TTFont(str(path), **kwargs)
    buf = BytesIO()
    tt.save(buf)
    return buf.getvalue()
