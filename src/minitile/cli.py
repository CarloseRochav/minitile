"""Command-line interface (Section 9.2).

Exit codes for ``run``: 0 ok, 1 invalid design, 2 illegal placement, 3 unroutable net(s).
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich import box
from rich.console import Console
from rich.measure import Measurement
from rich.table import Table

from minitile.api import Floorplan
from minitile.metrics import MINUS, percent_change
from minitile.model import Result
from minitile.parser import DesignError

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_ILLEGAL = 2
EXIT_UNROUTABLE = 3

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="minitile: place modules on a grid, route nets, report metrics.",
)

DesignArg = Annotated[Path, typer.Argument(help="Design YAML file.")]


def _console() -> Console:
    return Console(highlight=False, soft_wrap=True)


def _print_errors(console: Console, errors: list[str]) -> None:
    console.print("[bold red]Invalid design:[/]")
    for e in errors:
        console.print(f"  - {e}", markup=False)


def _fmt_num(x: float) -> str:
    return f"{x:,.0f}"


ARROW = "\N{RIGHTWARDS ARROW}"
__all__ = ["ARROW", "MINUS", "app", "percent_change"]


def _unicode_ok(console: Console) -> bool:
    """True if the console encoding can print the arrow and minus glyphs (not cp1252)."""
    try:
        (ARROW + MINUS).encode(console.encoding)
    except (UnicodeEncodeError, LookupError):
        return False
    return True


def header_line(result: Result, unicode: bool = True) -> str:
    arrow, minus = (ARROW, MINUS) if unicode else ("->", "-")
    s = result.summary
    legal = f"legal: {'yes' if s.legal else 'no'}"
    if s.placement_skipped:
        return f"placement: skipped (all modules fixed)  {legal}"
    change = percent_change(s.cost_initial, s.cost_final, minus)
    return (
        f"Placement cost: {_fmt_num(s.cost_initial)} {arrow} {_fmt_num(s.cost_final)} "
        f"({change})  {legal}  seed: {s.seed}  "
        f"iterations: {s.iterations:,}"
    )


def print_table(console: Console, result: Result) -> None:
    """Print the header line, the per-net table and any violations."""
    unicode = _unicode_ok(console)
    arrow = ARROW if unicode else "->"
    console.print(header_line(result, unicode), markup=False)
    table = Table(box=box.SIMPLE_HEAD, pad_edge=False)
    table.add_column("Net", justify="left")
    for col in ("Width", "Length", "Manhattan", "Detour", "Stages"):
        table.add_column(col, justify="right")
    table.add_column("Status", justify="left")
    styles = {"ok": "green", "detour_warning": "yellow", "unroutable": "bold red"}
    for n in result.nets:
        table.add_row(
            f"{n.src}{arrow}{n.dst}",
            str(n.width),
            "-" if n.length is None else str(n.length),
            str(n.manhattan),
            "-" if n.detour is None else f"{n.detour:.3f}",
            "-" if n.pipeline_stages is None else str(n.pipeline_stages),
            f"[{styles[n.status]}]{n.status}[/]",
        )
    # Not a terminal (pipe, file, test runner): print at natural width instead of truncating
    # long net names to the default 80 columns.
    if not console.is_terminal:
        natural = Measurement.get(console, console.options.update(width=10_000), table).maximum
        console.width = max(console.width, natural)
    console.print(table)
    s = result.summary
    for v in s.violations:
        console.print(f"[red]violation:[/] {v}")
    max_detour = "-" if s.max_detour is None else f"{s.max_detour:.3f}"
    console.print(
        f"Total weighted length: {s.total_weighted_length:,.3f}  "
        f"pipeline stages: {s.total_pipeline_stages}  max detour: {max_detour}  "
        f"unroutable: {s.unroutable_count}",
        markup=False,
    )


@app.command()
def validate(design: DesignArg) -> None:
    """Validate a design file. Prints OK or every error found."""
    console = _console()
    try:
        Floorplan.load(design)
    except DesignError as e:
        _print_errors(console, e.errors)
        raise typer.Exit(EXIT_INVALID) from None
    console.print("OK")


@app.command()
def run(
    design: DesignArg,
    seed: Annotated[int, typer.Option(help="Random seed for annealing.")] = 0,
    iterations: Annotated[int, typer.Option(min=0, help="Annealing iterations.")] = 20_000,
    out: Annotated[Path | None, typer.Option(help="Write the JSON result here.")] = None,
    svg: Annotated[Path | None, typer.Option(help="Also write an SVG drawing here.")] = None,
) -> None:
    """Validate, place, route and report a design."""
    console = _console()
    try:
        fp = Floorplan.load(design)
    except DesignError as e:
        _print_errors(console, e.errors)
        raise typer.Exit(EXIT_INVALID) from None
    result = fp.place(seed=seed, iterations=iterations).route().report()
    if out is not None:
        result.to_json(out)
    if svg is not None:
        result.to_svg(svg)
    print_table(console, result)
    if not result.summary.legal:
        raise typer.Exit(EXIT_ILLEGAL)
    if result.summary.unroutable_count > 0:
        raise typer.Exit(EXIT_UNROUTABLE)


@app.command()
def report(
    result_json: Annotated[Path, typer.Argument(help="Result JSON from `run --out`.")],
) -> None:
    """Print the table from a saved JSON result."""
    console = _console()
    try:
        result = Result.from_json(result_json)
    except (OSError, ValueError, ValidationError) as e:
        console.print(f"[bold red]Cannot read result:[/] {e}")
        raise typer.Exit(1) from None
    print_table(console, result)


@app.command("render")
def render_cmd(
    result_json: Annotated[Path, typer.Argument(help="Result JSON from `run --out`.")],
    out: Annotated[Path, typer.Option(help="SVG file to write.")],
    cell: Annotated[int, typer.Option(min=1, help="Pixels per grid cell.")] = 10,
) -> None:
    """Draw a saved JSON result as an SVG."""
    console = _console()
    try:
        result = Result.from_json(result_json)
        result.to_svg(out, cell=cell)
    except (OSError, ValueError, ValidationError) as e:
        console.print(f"[bold red]Cannot render result:[/] {e}", markup=True)
        raise typer.Exit(1) from None
    console.print(f"wrote {out}", markup=False)


if __name__ == "__main__":  # pragma: no cover
    app()
