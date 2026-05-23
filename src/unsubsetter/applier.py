"""Applier: executes a Plan on a pikepdf Pdf."""
from __future__ import annotations
import os
import tempfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Callable

from fontTools.ttLib import TTFont

import pikepdf

from unsubsetter.errors import UnsupportedFontError
from unsubsetter.planner import Plan, Replace

ApplierFn = Callable[[pikepdf.Pdf, "Replace"], None]
ValidatorFn = Callable[["Replace"], None]


def load_full_font_bytes(path: Path, ttc_face: int | None) -> bytes:
    """Load a font from disk and return its TTF binary.

    For TTC inputs, extract only the requested face as a standalone TTF.
    """
    kwargs = {"fontNumber": ttc_face} if ttc_face is not None else {}
    tt = TTFont(str(path), **kwargs)
    buf = BytesIO()
    tt.save(buf)
    return buf.getvalue()


def apply_truetype_cid_replace(pdf: pikepdf.Pdf, action: Replace) -> None:
    """Execute a CID TrueType Replace; assumes Validate has already run."""
    full_bytes = load_full_font_bytes(action.source_path, action.ttc_face)
    full_tt = TTFont(BytesIO(full_bytes))

    font_obj = action.record.font_obj
    descendant = font_obj["/DescendantFonts"][0]
    descriptor = descendant["/FontDescriptor"]

    # 1. Replace FontFile2 stream.
    descriptor["/FontFile2"] = pdf.make_stream(full_bytes)
    descriptor["/FontFile2"]["/Length1"] = len(full_bytes)

    # 2. Strip subset prefix from BaseFont on both dicts.
    _strip_subset_prefix(font_obj, "/BaseFont")
    _strip_subset_prefix(descendant, "/BaseFont")
    _strip_subset_prefix(descriptor, "/FontName")

    # 3. CIDToGIDMap = /Identity (XeLaTeX TrueType subsets preserve GIDs).
    descendant["/CIDToGIDMap"] = pikepdf.Name("/Identity")

    # 4. Rebuild /W array covering all used CIDs (plus original /W keys).
    widths = _build_widths_array(full_tt, action.record.used_cids)
    descendant["/W"] = widths
    # /DW (default width) — set from .notdef or 1000 as conventional default.
    descendant["/DW"] = _default_width(full_tt)

    # 5. Update FontDescriptor metrics.
    _update_descriptor_metrics(descriptor, full_tt)


_APPLIERS: dict[tuple[str, str | None], ApplierFn] = {
    ("Type0", "CIDFontType2"): apply_truetype_cid_replace,
}


def apply_replace(pdf: pikepdf.Pdf, action: Replace) -> None:
    """Execute a single Replace action by dispatching on font subtype."""
    key = (action.record.subtype, action.record.descendant_subtype)
    applier = _APPLIERS.get(key)
    if applier is None:
        raise UnsupportedFontError(
            f"no applier registered for {key} (font: {action.record.ps_name}); "
            f"this Replace action should not have been built — planner bug"
        )
    applier(pdf, action)


@dataclass
class ValidationReport:
    failures: list[tuple[Replace, str]] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures

    def render(self) -> str:
        if not self.failures:
            return "  (no validation failures)"
        lines = []
        for action, msg in self.failures:
            name = action.record.ps_name if action is not None else "?"
            lines.append(f"  [FAIL] {name}: {msg}")
        return "\n".join(lines)


def validate_plan(plan: Plan) -> ValidationReport:
    """Run per-font correctness checks for every Replace action.

    Returns a ValidationReport; passed=True iff no failures. Skip actions
    are ignored.
    """
    report = ValidationReport()
    for action in plan.actions:
        if not isinstance(action, Replace):
            continue
        try:
            _validate_one(action)
        except UnsupportedFontError as exc:
            report.failures.append((action, str(exc)))
    return report


def _validate_one(action: Replace) -> None:
    key = (action.record.subtype, action.record.descendant_subtype)
    validator = _VALIDATORS.get(key)
    if validator is None:
        raise UnsupportedFontError(
            f"no validator registered for {key} (font: {action.record.ps_name})"
        )
    validator(action)


def _validate_truetype_replace(action: Replace) -> None:
    """Refuse if the disk font lacks any CID the PDF references."""
    full_bytes = load_full_font_bytes(action.source_path, action.ttc_face)
    full_tt = TTFont(BytesIO(full_bytes))
    glyph_count = len(full_tt.getGlyphOrder())
    if action.record.used_cids and max(action.record.used_cids) >= glyph_count:
        raise UnsupportedFontError(
            f"disk font {action.source_path} has {glyph_count} glyphs but the "
            f"PDF references CID {max(action.record.used_cids)} for "
            f"{action.record.ps_name}; the file on disk is a different version "
            f"of the font than the one originally embedded — exclude this font "
            f"with --exclude or supply the correct file via --font-path."
        )


_VALIDATORS: dict[tuple[str, str | None], ValidatorFn] = {
    ("Type0", "CIDFontType2"): _validate_truetype_replace,
}


def _strip_subset_prefix(obj: pikepdf.Object, key: str) -> None:
    raw = str(obj[key]).lstrip("/")
    if len(raw) > 7 and raw[6] == "+" and raw[:6].isupper() and raw[:6].isalpha():
        obj[key] = pikepdf.Name("/" + raw[7:])


def _build_widths_array(tt: TTFont, used_cids: frozenset[int]) -> pikepdf.Array:
    """Build a PDF /W array covering the used CIDs.

    Format: [CID [w1 w2 ...]] runs — we use the simplest form, one entry per
    consecutive run of CIDs. Widths come from the full font's hmtx in font
    design units (units-per-em = 1000 conventional, scaled from tt.upem).
    """
    hmtx = tt["hmtx"]
    glyph_order = tt.getGlyphOrder()
    upem = tt["head"].unitsPerEm
    # PDF widths are in 1/1000 em.
    def width_for(gid: int) -> int:
        if gid >= len(glyph_order):
            return 0
        gname = glyph_order[gid]
        adv = hmtx.metrics.get(gname, (0, 0))[0]
        return round(adv * 1000 / upem)

    if not used_cids:
        return pikepdf.Array([])

    sorted_cids = sorted(used_cids)
    result: list = []
    run_start = sorted_cids[0]
    run_widths = [width_for(run_start)]
    for cid in sorted_cids[1:]:
        if cid == run_start + len(run_widths):
            run_widths.append(width_for(cid))
        else:
            result.extend([run_start, pikepdf.Array(run_widths)])
            run_start = cid
            run_widths = [width_for(cid)]
    result.extend([run_start, pikepdf.Array(run_widths)])
    return pikepdf.Array(result)


def _default_width(tt: TTFont) -> int:
    hmtx = tt["hmtx"]
    upem = tt["head"].unitsPerEm
    notdef_adv = hmtx.metrics.get(".notdef", (1000, 0))[0]
    return round(notdef_adv * 1000 / upem)


def _update_descriptor_metrics(descriptor: pikepdf.Object, tt: TTFont) -> None:
    """Update Ascent, Descent, CapHeight, ItalicAngle, FontBBox, etc. from full font."""
    upem = tt["head"].unitsPerEm
    def scale(value: int) -> int:
        return round(value * 1000 / upem)

    os2 = tt["OS/2"]
    hhea = tt["hhea"]
    head = tt["head"]
    post = tt["post"]

    descriptor["/Ascent"] = scale(os2.sTypoAscender if hasattr(os2, "sTypoAscender") else hhea.ascent)
    descriptor["/Descent"] = scale(os2.sTypoDescender if hasattr(os2, "sTypoDescender") else hhea.descent)
    descriptor["/CapHeight"] = scale(getattr(os2, "sCapHeight", os2.sTypoAscender))
    descriptor["/XHeight"] = scale(getattr(os2, "sxHeight", 0) or 0)
    descriptor["/ItalicAngle"] = float(post.italicAngle)
    descriptor["/FontBBox"] = pikepdf.Array([
        scale(head.xMin), scale(head.yMin), scale(head.xMax), scale(head.yMax),
    ])
    # StemV is hard to compute exactly; PDF readers don't strictly require it.
    # 80 is a conventional placeholder for regular weight, 120 for bold.
    descriptor["/StemV"] = 80


def run_plan(pdf: pikepdf.Pdf, plan: Plan, output_path: Path) -> None:
    """Apply every Replace action in the plan, then write the PDF atomically."""
    for action in plan.actions:
        if isinstance(action, Replace):
            apply_replace(pdf, action)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=output_path.stem + ".",
        suffix=".tmp.pdf",
        dir=str(output_path.parent),
    )
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        pdf.save(str(tmp_path))
        os.replace(tmp_path, output_path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise
