"""PDF inspector: enumerate font records from a pikepdf Pdf."""
from __future__ import annotations
import logging
import re
from dataclasses import dataclass
from collections import defaultdict

import pikepdf

_log = logging.getLogger(__name__)

_SUBSET_PREFIX_RE = re.compile(r"^([A-Z]{6})\+(.+)$")
_CMAP_SUFFIXES = ("-Identity-H", "-Identity-V")


def split_subset_prefix(base_font: str) -> tuple[str | None, str]:
    """Split a PostScript name into (subset_prefix, base_name).

    Returns (None, base_font) if no valid subset prefix is present.

    Type0 fonts may have a CMap suffix appended to the BaseFont, e.g.
    "LHTESP+TeXGyreTermes-Regular-Identity-H". The CMap suffix is stripped
    so the returned base name matches the disk font's name-table
    PostScript name (used for font index lookup).
    """
    m = _SUBSET_PREFIX_RE.match(base_font)
    prefix, name = (m.group(1), m.group(2)) if m else (None, base_font)
    for suffix in _CMAP_SUFFIXES:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
            break
    return prefix, name


@dataclass(frozen=True)
class FontRecord:
    font_obj: pikepdf.Object            # the /Font dict
    base_font: str                       # raw /BaseFont value (with subset prefix if present)
    subset_prefix: str | None
    ps_name: str                         # base_font minus subset prefix
    subtype: str                         # 'Type0', 'TrueType', 'Type1', ...
    descendant_subtype: str | None       # 'CIDFontType2', 'CIDFontType0', or None
    encoding: str                        # raw or named encoding
    has_font_file: bool
    font_file_kind: str | None           # 'FontFile', 'FontFile2', 'FontFile3', or None
    used_cids: frozenset[int]


def _stringify_name(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value).lstrip("/")


def _font_file_kind(descriptor: pikepdf.Object) -> str | None:
    for key in ("/FontFile", "/FontFile2", "/FontFile3"):
        if key in descriptor:
            return key.lstrip("/")
    return None


def _collect_used_cids(pdf: pikepdf.Pdf) -> dict[int, set[int]]:
    """Walk every page's content stream, return {font_obj_objgen0: set(cids)}.

    Each page has a /Resources/Font dict mapping resource name (e.g. /F12) to
    a font object. Content streams say "/F12 12 Tf" (set font to F12) then
    "(...) Tj" with bytes that are 2-byte big-endian CIDs under Identity-H.
    """
    result: dict[int, set[int]] = defaultdict(set)
    for page_num, page in enumerate(pdf.pages, start=1):
        try:
            instructions = list(pikepdf.parse_content_stream(page))
        except Exception as exc:
            # A bad content stream means CIDs from that page won't be counted
            # toward any font's /W rebuild. Surface it via -v so the user
            # knows why a width array might be undersized.
            _log.warning("page %d: skipping unparseable content stream: %s", page_num, exc)
            continue
        # Build {resource_name -> font_obj} for this page.
        resources = page.get("/Resources", pikepdf.Dictionary())
        fonts = resources.get("/Font", pikepdf.Dictionary())
        current_font_obj: pikepdf.Object | None = None
        for operands, op in instructions:
            op_str = str(op)
            if op_str == "Tf":
                name = operands[0]
                current_font_obj = fonts.get(name)
            elif op_str in ("Tj", "'", '"') and current_font_obj is not None:
                # Last operand is the string for Tj/'; for " it's also last.
                s = operands[-1]
                _accumulate_cids(s, result[current_font_obj.objgen[0]])
            elif op_str == "TJ" and current_font_obj is not None:
                # operands[0] is an array of strings and numbers.
                for item in operands[0]:
                    if isinstance(item, (pikepdf.String, bytes)):
                        _accumulate_cids(item, result[current_font_obj.objgen[0]])
    return result


def _accumulate_cids(s, bucket: set[int]) -> None:
    raw = bytes(s) if not isinstance(s, bytes) else s
    # Identity-H uses 2-byte big-endian CIDs. Pad if odd-length (shouldn't happen).
    for i in range(0, len(raw) - 1, 2):
        bucket.add((raw[i] << 8) | raw[i + 1])


def inspect_pdf(pdf: pikepdf.Pdf) -> list[FontRecord]:
    """Enumerate all font objects in the PDF and return one FontRecord each."""
    cid_map = _collect_used_cids(pdf)
    records: list[FontRecord] = []
    seen: set[tuple[int, int]] = set()
    for obj in pdf.objects:
        if not isinstance(obj, pikepdf.Dictionary):
            continue
        if obj.get("/Type") != pikepdf.Name("/Font"):
            continue
        key = obj.objgen
        if key in seen:
            continue
        seen.add(key)

        base_font = _stringify_name(obj.get("/BaseFont"))
        subset_prefix, ps_name = split_subset_prefix(base_font)
        subtype = _stringify_name(obj.get("/Subtype"))
        if subtype in ("CIDFontType0", "CIDFontType2"):
            continue
        encoding_obj = obj.get("/Encoding")
        encoding = _stringify_name(encoding_obj) if encoding_obj is not None else ""

        descendant_subtype = None
        descriptor = obj.get("/FontDescriptor")
        if subtype == "Type0":
            descendants = obj.get("/DescendantFonts")
            if descendants is not None and len(descendants) > 0:
                desc = descendants[0]
                descendant_subtype = _stringify_name(desc.get("/Subtype"))
                # The actual FontDescriptor for Type 0 lives on the descendant.
                descriptor = desc.get("/FontDescriptor")

        has_font_file = False
        font_file_kind = None
        if descriptor is not None:
            font_file_kind = _font_file_kind(descriptor)
            has_font_file = font_file_kind is not None

        records.append(FontRecord(
            font_obj=obj,
            base_font=base_font,
            subset_prefix=subset_prefix,
            ps_name=ps_name,
            subtype=subtype,
            descendant_subtype=descendant_subtype,
            encoding=encoding,
            has_font_file=has_font_file,
            font_file_kind=font_file_kind,
            used_cids=frozenset(cid_map.get(key[0], set())),
        ))
    return records
