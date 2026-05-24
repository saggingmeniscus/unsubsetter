"""Applier: executes a Plan on a pikepdf Pdf."""
from __future__ import annotations
import os
import re
import tempfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Callable

from fontTools.cffLib import CFFFontSet
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


_BFCHAR_BLOCK_RE = re.compile(rb"beginbfchar(.*?)endbfchar", re.DOTALL)
_BFRANGE_BLOCK_RE = re.compile(rb"beginbfrange(.*?)endbfrange", re.DOTALL)
_HEX_TOKEN_RE = re.compile(rb"<([0-9A-Fa-f]+)>")


def _hex_to_str(hex_bytes: bytes) -> str:
    """Decode a CMap <HHHH...> token as UTF-16BE into a Python str."""
    raw = bytes.fromhex(hex_bytes.decode("ascii"))
    # Pad to even length defensively (CMap hex is always even, but…).
    if len(raw) % 2:
        raw = b"\x00" + raw
    return raw.decode("utf-16-be", errors="replace")


def _parse_to_unicode_cmap(record) -> dict[int, str] | None:
    """Parse the /ToUnicode CMap of a Type0 font record into {cid: unicode_str}.

    Returns None if the record has no /ToUnicode entry. Handles bfchar and
    the simple <start> <end> <dst_start> form of bfrange. Array form of
    bfrange and other CMap shapes are silently skipped (CIDs with no parsed
    entry just won't appear in the result).
    """
    type0 = record.font_obj
    if "/ToUnicode" not in type0:
        return None
    body = bytes(type0["/ToUnicode"].read_bytes())

    result: dict[int, str] = {}

    for block in _BFCHAR_BLOCK_RE.findall(body):
        tokens = _HEX_TOKEN_RE.findall(block)
        for i in range(0, len(tokens) - 1, 2):
            cid = int(tokens[i], 16)
            result[cid] = _hex_to_str(tokens[i + 1])

    for block in _BFRANGE_BLOCK_RE.findall(body):
        # Tokenize the block in order, distinguishing hex tokens from arrays.
        # The body of a bfrange is a sequence of either:
        #   <start> <end> <dst_start>       — incrementing range
        #   <start> <end> [<dst1> <dst2>…]  — explicit array (skipped here)
        tokens: list[tuple[str, bytes]] = []
        pos = 0
        while pos < len(block):
            m = _HEX_TOKEN_RE.match(block, pos)
            if m:
                tokens.append(("hex", m.group(1)))
                pos = m.end()
                continue
            if block[pos:pos + 1] == b"[":
                close = block.find(b"]", pos)
                if close == -1:
                    break
                tokens.append(("array", b""))
                pos = close + 1
                continue
            pos += 1
        # Process triples.
        i = 0
        while i + 2 < len(tokens):
            kind_s, val_s = tokens[i]
            kind_e, val_e = tokens[i + 1]
            kind_d, val_d = tokens[i + 2]
            if kind_s == "hex" and kind_e == "hex" and kind_d == "hex":
                start = int(val_s, 16)
                end = int(val_e, 16)
                dst_start_str = _hex_to_str(val_d)
                base = ord(dst_start_str[-1]) if dst_start_str else 0
                prefix = dst_start_str[:-1] if len(dst_start_str) > 1 else ""
                for offset, cid in enumerate(range(start, end + 1)):
                    result[cid] = prefix + chr(base + offset)
                i += 3
            elif kind_s == "hex" and kind_e == "hex" and kind_d == "array":
                # Explicit-array bfrange form; best-effort parser skips it.
                i += 3
            else:
                i += 1
    return result


def _disk_cmap_codepoint_to_gid(tt: TTFont) -> dict[int, int]:
    """Build a {unicode_codepoint: gid} map from a TTFont's best cmap."""
    best = tt["cmap"].getBestCmap() or {}
    glyph_order = tt.getGlyphOrder()
    name_to_gid = {name: gid for gid, name in enumerate(glyph_order)}
    return {cp: name_to_gid[name] for cp, name in best.items() if name in name_to_gid}


def _validate_cff_replace(action: Replace) -> None:
    """Refuse if the disk CFF doesn't match the subset on glyph identity.

    Uses the PDF's /ToUnicode CMap as the source of truth for what each
    subset CID is supposed to render as. Under XeLaTeX's CID-wrapping
    convention, subset CID c == disk GID c, so we verify that the disk
    font's cmap maps the subset's Unicode codepoint to the same GID.
    """
    full_tt = TTFont(str(action.source_path))
    if "CFF " not in full_tt:
        raise UnsupportedFontError(
            f"disk font {action.source_path} is not CFF-flavored "
            f"(expected for {action.record.ps_name})"
        )
    subset_cid_to_unicode = _parse_to_unicode_cmap(action.record)
    if subset_cid_to_unicode is None:
        raise UnsupportedFontError(
            f"font {action.record.ps_name} has no /ToUnicode CMap; "
            f"unsubsetter cannot verify the disk font matches the embedded "
            f"subset without semantic identity for each CID. Exclude this "
            f"font with --exclude."
        )
    disk_cp_to_gid = _disk_cmap_codepoint_to_gid(full_tt)
    disk_glyph_count = len(full_tt.getGlyphOrder())

    missing: list[int] = []
    mismatches: list[tuple[int, str, int]] = []  # (cid, unicode_str, actual_disk_gid)
    for cid in sorted(action.record.used_cids):
        if cid >= disk_glyph_count:
            missing.append(cid)
            continue
        unicode_str = subset_cid_to_unicode.get(cid)
        if not unicode_str or len(unicode_str) != 1:
            # No /ToUnicode entry, or multi-codepoint value we can't trivially
            # invert. Coverage check above is the only assertion.
            continue
        cp = ord(unicode_str)
        actual_gid = disk_cp_to_gid.get(cp)
        if actual_gid is None:
            mismatches.append((cid, unicode_str, -1))
        elif actual_gid != cid:
            mismatches.append((cid, unicode_str, actual_gid))

    if missing or mismatches:
        first = (
            f"CID {mismatches[0][0]} ({mismatches[0][1]!r}): "
            f"subset expects disk GID {mismatches[0][0]}, "
            f"disk maps codepoint to GID {mismatches[0][2]}"
            if mismatches
            else f"CID {missing[0]} not in disk font"
        )
        raise UnsupportedFontError(
            f"CFF glyph correspondence check failed for {action.record.ps_name}: "
            f"{len(missing)} CIDs missing from disk font, "
            f"{len(mismatches)} CIDs map to a different glyph in the disk font. "
            f"The disk font does not match the embedded subset's glyph identity; "
            f"exclude this font with --exclude or supply a matching version via "
            f"--font-path. First problem: {first}"
        )


_VALIDATORS: dict[tuple[str, str | None], ValidatorFn] = {
    ("Type0", "CIDFontType2"): _validate_truetype_replace,
    ("Type0", "CIDFontType0"): _validate_cff_replace,
}


def _read_embedded_cff(record) -> CFFFontSet:
    """Parse the /FontFile3 stream of a CIDFontType0 record into a CFFFontSet.

    Handles both /Subtype variants:
      - /CIDFontType0C: raw CFF bytes.
      - /OpenType: an OTF wrapper; extract the CFF table.
    """
    descriptor = record.font_obj["/DescendantFonts"][0]["/FontDescriptor"]
    file_obj = descriptor["/FontFile3"]
    file_bytes = bytes(file_obj.read_bytes())
    subtype = str(file_obj.get("/Subtype", "")).lstrip("/")

    cff = CFFFontSet()
    if subtype == "OpenType":
        # OTF wrapper. Decompile via TTFont and pull the CFF table.
        tt = TTFont(BytesIO(file_bytes))
        if "CFF " not in tt:
            raise UnsupportedFontError(
                f"FontFile3 /Subtype OpenType but contains no CFF table "
                f"for {record.ps_name}"
            )
        return tt["CFF "].cff
    cff.decompile(BytesIO(file_bytes), otFont=None)
    return cff


def _cid_to_glyph_name(cff: CFFFontSet) -> dict[int, str]:
    """Build a {document_cid: glyph_name} map from a CFFFontSet.

    Two CFF flavors are handled:
      - CID-keyed CFF (has ROS): charset is a list of glyph names — typically
        the conventional 'cidNNNNN' form, with '.notdef' at GID 0. The CID is
        parsed out of the name. '.notdef' is excluded (content streams should
        never reference it as a CID, and it would collide with the GID 0
        entry of the name-keyed branch).
      - Name-keyed CFF (no ROS): charset is a list of real glyph names. Under
        PDF /CIDFontType0 wrapping with Identity-H, the document's CIDs are
        the embedded font's GIDs directly, so we key by GID.
    """
    top = cff.topDictIndex[0]
    charset = top.charset
    if hasattr(top, "ROS"):
        result: dict[int, str] = {}
        for name in charset:
            if name == ".notdef":
                continue
            if name.startswith("cid"):
                try:
                    cid = int(name[3:])
                except ValueError:
                    continue
                result[cid] = name
        return result
    return {gid: name for gid, name in enumerate(charset)}


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


def _build_widths_array_cff(tt: TTFont, used_cids: frozenset[int]) -> pikepdf.Array:
    """Build a PDF /W array for a CFF font, covering all used CIDs.

    Width source: the CFF's CharStrings. T2CharString populates `.width`
    only after the program is walked, so we drive each charstring through
    a NullPen. For name-keyed CFFs (the common disk case) CID == GID ==
    index into glyph order; for CID-keyed CFFs we look up the cidNNNNN-
    named charstring.
    """
    from fontTools.pens.basePen import NullPen

    cff = tt["CFF "].cff
    top = cff.topDictIndex[0]
    char_strings = top.CharStrings
    cid_to_name = _cid_to_glyph_name(cff)
    upem = tt["head"].unitsPerEm

    def width_for(cid: int) -> int:
        name = cid_to_name.get(cid)
        if name is None or name not in char_strings:
            return 0
        cs = char_strings[name]
        cs.draw(NullPen())  # populates cs.width via charstring interpretation
        return round((cs.width or 0) * 1000 / upem)

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
