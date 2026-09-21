"""Terminal output: progress while converting, and a readable summary after.

The summary shows each family in the colour its faces are given in the STEP file,
so the terminal and the viewer agree: what reads as amber here is amber there.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Protocol

from rich.console import Console
from rich.table import Table
from rich.text import Text

from .palette import colour_for

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .convert import ConversionReport

#: Shown against a family whose colour is written into the file.
SWATCH = "■■"


class _Stage(Protocol):
    """What the CLI needs of a spinner: the ability to change its caption."""

    def update(self, status: str) -> None: ...  # pragma: no cover - protocol only


class _Silent:
    """Stand-in used when there is no terminal to draw a spinner on."""

    def update(self, status: str) -> None:
        return None


def _hex(family: str) -> str:
    red, green, blue = colour_for(family)
    return f"#{int(red * 255):02x}{int(green * 255):02x}{int(blue * 255):02x}"


def _si(size: int) -> str:
    for unit, scale in (("GB", 1 << 30), ("MB", 1 << 20), ("kB", 1 << 10)):
        if size >= scale:
            return f"{size / scale:.1f} {unit}"
    return f"{size} B"


class Reporter:
    """Progress and results for one conversion.

    Falls back to plain lines when stderr is not a terminal, so piping the tool
    into a file or a build log stays readable.
    """

    def __init__(self, quiet: bool = False, colour: bool | None = None) -> None:
        self.quiet = quiet
        self.console = Console(stderr=True, no_color=colour is False)

    @contextmanager
    def running(self) -> Iterator[_Stage]:
        """A spinner whose caption follows the conversion, yielding its handle.

        Yields an inert handle when output is quiet or not going to a terminal,
        so callers need no branch of their own.
        """
        if self.quiet or not self.console.is_terminal:
            yield _Silent()
            return
        with self.console.status("[dim]starting[/dim]", spinner="dots") as status:
            yield status

    def failure(self, message: str) -> None:
        self.console.print(Text("error", style="bold red"), Text(message))

    def summary(self, report: ConversionReport) -> None:
        """Print what was written, per family, in the families' own colours."""
        if self.quiet:
            return
        if not self.console.is_terminal:
            self._plain(report)
            return

        table = Table(box=None, pad_edge=False, show_header=True, header_style="dim")
        table.add_column("", width=2)
        table.add_column("feature", style="bold")
        table.add_column("found", justify="right")
        for family, count in sorted(report.counts.items(), key=lambda kv: (-kv[1], kv[0])):
            table.add_row(
                Text(SWATCH, style=_hex(family)),
                family.replace("_", " "),
                str(count),
            )

        size = report.output.stat().st_size if report.output.is_file() else 0
        self.console.print()
        self.console.print(table)
        self.console.print()
        self.console.print(
            Text.assemble(
                ("  ", ""),
                (f"{report.total}", "bold"),
                (" annotations  ", "dim"),
                (f"{report.coloured}", "bold"),
                (" faces coloured  ", "dim"),
                (f"{_si(size)}", "bold"),
                (f"  [{report.profile}]", "dim"),
            )
        )
        # soft_wrap so a long path is left to the terminal instead of being
        # broken mid-word, which makes it uncopyable.
        self.console.print(Text(f"  {report.output}", style="cyan"), soft_wrap=True)

        for family, count in sorted(report.unplaced.items()):
            self.console.print(
                Text(f"  {family}: {count} record(s) with no anchor point", style="yellow")
            )
        for family, count in sorted(report.undrawn.items()):
            self.console.print(
                Text(f"  {family}: {count} label(s) with nothing drawable", style="yellow")
            )
        if report.obstructed:
            self.console.print(
                Text(
                    f"  {report.obstructed} leader(s) could not avoid crossing the part",
                    style="yellow",
                )
            )
        self.console.print()

    def _plain(self, report: ConversionReport) -> None:
        print(
            f"{report.output}: {report.total} annotations, "
            f"{report.coloured} faces coloured [{report.profile}]",
            file=self.console.file,
        )
        for family, count in sorted(report.counts.items()):
            print(f"  {family:24s} {count}", file=self.console.file)
        for family, count in sorted(report.unplaced.items()):
            print(f"  {family:24s} {count} record(s) with no anchor point", file=self.console.file)
        for family, count in sorted(report.undrawn.items()):
            print(f"  {family:24s} {count} label(s) with nothing drawable", file=self.console.file)
