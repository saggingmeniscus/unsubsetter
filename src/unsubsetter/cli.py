"""CLI entry point."""
from __future__ import annotations
import sys
from pathlib import Path

import click
import pikepdf

from unsubsetter.applier import run_plan
from unsubsetter.font_index import FontIndex, default_search_paths
from unsubsetter.inspector import inspect_pdf
from unsubsetter.planner import build_plan
from unsubsetter.verifier import verify_structural, verify_visual


def _csv_set(value: str | None) -> set[str]:
    if not value:
        return set()
    return {tok.strip() for tok in value.split(",") if tok.strip()}


@click.command()
@click.argument("input_pdf", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--fix", is_flag=True, help="Write output (default: inspect-only).")
@click.option("--output", "-o", type=click.Path(dir_okay=False, path_type=Path),
              default=None, help="Output path (default: INPUT.unsubset.pdf).")
@click.option("--force", is_flag=True, help="Allow overwriting INPUT_PDF.")
@click.option("--only", default="", help="Comma-separated PostScript names to include.")
@click.option("--exclude", default="", help="Comma-separated PostScript names to skip.")
@click.option("--font-path", "font_paths", multiple=True, type=click.Path(path_type=Path),
              help="Additional font search dir (repeatable).")
@click.option("--verify-visual", "verify_visual_n", type=int, default=0,
              help="After fix, render N random pages and pixel-diff them.")
@click.option("-v", "--verbose", is_flag=True)
@click.version_option()
def cli(
    input_pdf: Path,
    fix: bool,
    output: Path | None,
    force: bool,
    only: str,
    exclude: str,
    font_paths: tuple[Path, ...],
    verify_visual_n: int,
    verbose: bool,
) -> None:
    """Re-embed full (non-subset) fonts in a PDF."""
    search_paths = default_search_paths() + list(font_paths)
    if verbose:
        click.echo(f"Building font index from {len(search_paths)} paths…", err=True)
    index = FontIndex.build(search_paths)
    if verbose:
        click.echo(f"Font index: {len(index)} unique faces.", err=True)

    with pikepdf.open(input_pdf) as pdf:
        records = inspect_pdf(pdf)
        plan = build_plan(records, index, only=_csv_set(only), exclude=_csv_set(exclude))

        click.echo(plan.render())

        if not fix:
            sys.exit(0)

        out_path = output or input_pdf.with_suffix(".unsubset.pdf")
        if out_path.resolve() == input_pdf.resolve() and not force:
            click.echo(
                f"ERROR: --output equals INPUT_PDF; pass --force to overwrite.",
                err=True,
            )
            sys.exit(1)

        if not plan.replaces():
            click.echo("Nothing to replace; not writing output.", err=True)
            sys.exit(0)

        run_plan(pdf, plan, out_path)
        click.echo(f"Wrote {out_path}", err=True)

    # Verification (re-opens output).
    structural = verify_structural(input_pdf, out_path, plan)
    click.echo("\nStructural verification:")
    click.echo(structural.render())
    if not structural.passed:
        sys.exit(2)

    if verify_visual_n > 0:
        visual = verify_visual(input_pdf, out_path, num_pages=verify_visual_n)
        click.echo("\nVisual verification:")
        click.echo(visual.render())
        if not visual.passed:
            sys.exit(3)
