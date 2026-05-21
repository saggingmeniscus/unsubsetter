"""Verifier: structural and optional visual checks on the output PDF."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import random
import subprocess
import tempfile

import pikepdf
from PIL import Image, ImageChops

from unsubsetter.inspector import inspect_pdf
from unsubsetter.planner import Plan, Replace


@dataclass
class VerificationReport:
    checks: list[tuple[str, bool, str]] = field(default_factory=list)  # (name, ok, detail)

    @property
    def passed(self) -> bool:
        return all(ok for _, ok, _ in self.checks)

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append((name, ok, detail))

    def failures(self) -> list[str]:
        return [f"{n}: {d}" for n, ok, d in self.checks if not ok]

    def render(self) -> str:
        lines = []
        for name, ok, detail in self.checks:
            mark = "OK  " if ok else "FAIL"
            extra = f" — {detail}" if detail else ""
            lines.append(f"  [{mark}] {name}{extra}")
        return "\n".join(lines)


def verify_structural(
    original_path: Path,
    modified_path: Path,
    plan: Plan,
) -> VerificationReport:
    """Re-parse the modified PDF and check structural invariants against the original."""
    report = VerificationReport()

    try:
        orig_pdf = pikepdf.open(original_path)
        mod_pdf = pikepdf.open(modified_path)
    except Exception as exc:
        report.add("open_modified_pdf", False, str(exc))
        return report
    report.add("open_modified_pdf", True)

    # Page count.
    same_pages = len(orig_pdf.pages) == len(mod_pdf.pages)
    report.add(
        "page count matches",
        same_pages,
        f"orig={len(orig_pdf.pages)} mod={len(mod_pdf.pages)}",
    )

    # MediaBoxes.
    if same_pages:
        for i, (op, mp) in enumerate(zip(orig_pdf.pages, mod_pdf.pages)):
            o_mb = list(op.get("/MediaBox", []))
            m_mb = list(mp.get("/MediaBox", []))
            report.add(f"page {i+1} MediaBox", o_mb == m_mb, f"orig={o_mb} mod={m_mb}")

    # Per-Replace checks.
    # Match by ps_name: after save/reload object numbers may shift.
    mod_records_by_psname = {r.ps_name: r for r in inspect_pdf(mod_pdf)}
    for action in plan.actions:
        if not isinstance(action, Replace):
            continue
        ps = action.record.ps_name
        target = mod_records_by_psname.get(ps)
        if target is None:
            report.add(f"font {ps} present", False, "object not found in modified PDF")
            continue
        report.add(f"font {ps} prefix stripped", target.subset_prefix is None,
                   f"got prefix={target.subset_prefix}")
        # CIDToGIDMap should now be /Identity.
        desc = target.font_obj["/DescendantFonts"][0]
        cid_map = str(desc.get("/CIDToGIDMap", "")).strip()
        report.add(f"font {ps} CIDToGIDMap=Identity", cid_map == "/Identity", cid_map)

    orig_pdf.close()
    mod_pdf.close()
    return report


def verify_visual(
    original_path: Path,
    modified_path: Path,
    num_pages: int,
    seed: int | None = None,
    max_pixel_diff: int = 3,
    max_diff_ratio: float = 0.001,
) -> VerificationReport:
    """Render N random pages from both PDFs and pixel-diff them.

    Returns a VerificationReport with one check per sampled page.
    """
    report = VerificationReport()
    rng = random.Random(seed)
    with pikepdf.open(original_path) as pdf:
        total_pages = len(pdf.pages)
    if total_pages == 0:
        report.add("visual: page count > 0", False, "0 pages")
        return report

    sample_size = min(num_pages, total_pages)
    pages = sorted(rng.sample(range(1, total_pages + 1), sample_size))

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        for page_num in pages:
            orig_png = _render_page(original_path, page_num, td_path / f"orig_{page_num}")
            mod_png = _render_page(modified_path, page_num, td_path / f"mod_{page_num}")
            if orig_png is None or mod_png is None:
                report.add(f"page {page_num} render", False, "pdftoppm failed")
                continue
            ok, detail = _images_match(orig_png, mod_png, max_pixel_diff, max_diff_ratio)
            report.add(f"page {page_num} visual diff", ok, detail)
    return report


def _render_page(pdf_path: Path, page: int, prefix: Path) -> Path | None:
    """Render one page to PNG at 150 DPI via pdftoppm. Returns the PNG path or None."""
    try:
        subprocess.run(
            ["pdftoppm", "-r", "150", "-f", str(page), "-l", str(page),
             "-png", str(pdf_path), str(prefix)],
            check=True, capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    # pdftoppm appends -NN.png; the digit count varies with total pages.
    candidates = list(prefix.parent.glob(prefix.name + "-*.png"))
    return candidates[0] if candidates else None


def _images_match(
    a_path: Path, b_path: Path, max_pixel_diff: int, max_diff_ratio: float,
) -> tuple[bool, str]:
    a = Image.open(a_path).convert("RGB")
    b = Image.open(b_path).convert("RGB")
    if a.size != b.size:
        return False, f"size mismatch {a.size} vs {b.size}"
    diff = ImageChops.difference(a, b)
    bbox = diff.getbbox()
    if bbox is None:
        return True, "identical"
    # Count pixels with any channel > max_pixel_diff.
    diffs = sum(
        1 for px in diff.crop(bbox).get_flattened_data() if max(px) > max_pixel_diff
    )
    total = a.size[0] * a.size[1]
    ratio = diffs / total
    if ratio <= max_diff_ratio:
        return True, f"{diffs}/{total} differing pixels (ratio {ratio:.4%})"
    return False, f"{diffs}/{total} differing pixels (ratio {ratio:.4%})"
