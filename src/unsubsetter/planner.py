"""Planner: combines inspection + font index + filters into a list of actions."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Union

from unsubsetter.inspector import FontRecord


@dataclass(frozen=True)
class Replace:
    record: FontRecord
    source_path: Path
    ttc_face: int | None


@dataclass(frozen=True)
class Skip:
    record: FontRecord
    reason: str


Action = Union[Replace, Skip]


@dataclass(frozen=True)
class Plan:
    actions: list[Action]

    def replaces(self) -> list[Replace]:
        return [a for a in self.actions if isinstance(a, Replace)]

    def skips(self) -> list[Skip]:
        return [a for a in self.actions if isinstance(a, Skip)]

    def render(self) -> str:
        lines = []
        for a in self.actions:
            r = a.record
            base = r.ps_name if r is not None else "?"
            if isinstance(a, Replace):
                face = f" (face {a.ttc_face})" if a.ttc_face is not None else ""
                lines.append(f"  REPLACE  {base:40}  → {a.source_path}{face}")
            else:
                lines.append(f"  SKIP     {base:40}  ({a.reason})")
        replaces = len(self.replaces())
        skips = len(self.skips())
        header = f"Plan: {replaces} replace, {skips} skip"
        return header + "\n" + "\n".join(lines)


from unsubsetter.font_index import FontIndex, normalize_name


def build_plan(
    records: list[FontRecord],
    index: FontIndex,
    only: set[str] | None = None,
    exclude: set[str] | None = None,
) -> Plan:
    only_norm = {normalize_name(n) for n in (only or set())}
    exclude_norm = {normalize_name(n) for n in (exclude or set())}

    actions: list[Action] = []
    for rec in records:
        ps_norm = normalize_name(rec.ps_name)

        if rec.subset_prefix is None:
            actions.append(Skip(rec, "not subsetted"))
            continue
        if only_norm and ps_norm not in only_norm:
            actions.append(Skip(rec, "not selected by --only"))
            continue
        if ps_norm in exclude_norm:
            actions.append(Skip(rec, "excluded by --exclude"))
            continue
        if rec.subtype == "Type1":
            actions.append(Skip(rec, "unsupported type: Type1 (V1 handles CID TrueType only)"))
            continue
        if rec.subtype != "Type0" or rec.descendant_subtype != "CIDFontType2":
            actions.append(Skip(
                rec,
                f"unsupported type: {rec.subtype}/{rec.descendant_subtype or '-'}"
                f" (CFF or non-composite — V1 handles CID TrueType only)",
            ))
            continue

        entry = index.lookup(rec.ps_name)
        if entry is None:
            actions.append(Skip(rec, f"font not found on disk: {rec.ps_name}"))
            continue
        actions.append(Replace(rec, entry.path, entry.ttc_face))

    return Plan(actions=actions)
