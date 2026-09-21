"""Command line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .adapters import FEATURE_FAMILIES, SUMMARY_FAMILIES
from .completion import SHELLS, generate
from .convert import convert, resolve_families
from .profiles import PROFILES, resolve_profile
from .status import Reporter


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="quid2pmi",
        description=(
            "Recognise features in a STEP file with Quiddity and write a new STEP file "
            "carrying them as AP242 PMI annotations, for viewing in CAD Assistant."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Feature families:\n  "
            + "\n  ".join(FEATURE_FAMILIES)
            + "\n\nSummary families (use --families summary or all):\n  "
            + "\n  ".join(SUMMARY_FAMILIES)
        ),
    )
    # Optional so that --completion and --version work on their own; its absence
    # is reported below rather than by argparse.
    parser.add_argument("source", type=Path, nargs="?", help="input STEP file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="output STEP file (default: <source stem>-pmi.step beside the input)",
    )
    parser.add_argument(
        "-f",
        "--families",
        action="append",
        metavar="NAMES",
        help="comma-separated families, or 'features', 'summary', 'all' (default: features)",
    )
    parser.add_argument(
        "--text-height",
        type=float,
        help="label text height in model units (default: bounding box diagonal / 45)",
    )
    parser.add_argument(
        "--standoff",
        type=float,
        help="distance from the part's bounding box to the label plane "
        "(default: 10%% of the bounding box diagonal)",
    )
    parser.add_argument("--font", default="Arial", help="label font (default: Arial)")
    parser.add_argument(
        "--no-leaders", action="store_true", help="omit the leader line from label to feature"
    )
    parser.add_argument(
        "-e",
        "--explain",
        action="store_true",
        help="describe each feature in plain words, in its model-tree name "
        "(and in the drawn label unless --no-draw-text)",
    )
    parser.add_argument(
        "--explain-width",
        type=int,
        default=44,
        metavar="CHARS",
        help="wrap explanation text at this many characters (default: 44)",
    )
    parser.add_argument(
        "--no-colour",
        "--no-color",
        dest="no_colour",
        action="store_true",
        help="do not colour each feature's faces by family",
    )
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILES),
        default="cad-assistant",
        help="viewer to write for: "
        + "; ".join(f"{name} -- {p.summary}" for name, p in sorted(PROFILES.items())),
    )
    parser.add_argument(
        "--no-draw-text",
        dest="draw_text",
        action="store_false",
        help="write only the leader into each PMI presentation, not the label text. "
        "The text is what the file size is made of, so this is much smaller -- at "
        "the cost of annotations no viewer can read without the semantic values",
    )
    parser.add_argument(
        "--viewer",
        type=Path,
        metavar="HTML",
        help="also write a self-contained web page showing the features, via "
        "step-pmi-viewer; labels there are HTML rather than glyph outlines, so "
        "they stay legible at any zoom",
    )
    parser.add_argument("--json", type=Path, help="also write the annotation list as JSON")
    parser.add_argument("-q", "--quiet", action="store_true", help="only report errors")
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="also show the STEP writer's own progress output",
    )
    parser.add_argument(
        "--plain",
        action="store_true",
        help="plain terminal output, without colour or a spinner",
    )
    parser.add_argument(
        "--completion",
        choices=SHELLS,
        metavar="SHELL",
        help=f"print a shell completion script ({', '.join(SHELLS)}) and exit",
    )
    parser.add_argument("--version", action="version", version=f"quid2pmi {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.completion:
        print(generate(parser, args.completion, list(FEATURE_FAMILIES)))
        return 0

    reporter = Reporter(quiet=args.quiet, colour=not args.plain)

    if args.source is None:
        parser.print_usage(sys.stderr)
        reporter.failure("an input STEP file is required")
        return 2

    if not args.source.is_file():
        reporter.failure(f"no such file: {args.source}")
        return 2

    output = args.output or args.source.with_name(f"{args.source.stem}-pmi.step")

    try:
        families = resolve_families(args.families)
    except ValueError as exc:
        reporter.failure(str(exc))
        return 2

    try:
        viewer = resolve_profile(args.profile)
    except ValueError as exc:
        reporter.failure(str(exc))
        return 2

    stage: dict[str, object] = {}

    def phase(description: str) -> None:
        """Swap the spinner's caption as the conversion moves on."""
        status = stage.get("status")
        if status is not None:
            status.update(f"[dim]{description}[/dim]")  # type: ignore[attr-defined]

    try:
        with reporter.running() as status:
            stage["status"] = status
            report = convert(
                args.source,
                output,
                families=families,
                text_height=args.text_height,
                standoff=args.standoff,
                font=args.font,
                leaders=not args.no_leaders,
                explain=args.explain,
                explain_width=args.explain_width,
                colours=not args.no_colour,
                draw_text=args.draw_text,
                profile=viewer,
                viewer=args.viewer,
                quiet=not args.verbose,
                progress=phase,
            )
    except Exception as exc:
        reporter.failure(str(exc))
        return 1

    if args.json:
        args.json.write_text(json.dumps(report.to_dict(), indent=2))

    reporter.summary(report)
    return 0
