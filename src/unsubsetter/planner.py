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
