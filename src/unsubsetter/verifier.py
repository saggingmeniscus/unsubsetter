"""Verifier: structural and optional visual checks on the output PDF."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

import pikepdf

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
