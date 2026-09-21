"""Command line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .adapters import FEATURE_FAMILIES, SUMMARY_FAMILIES
from .convert import convert, resolve_families


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
    parser.add_argument("source", type=Path, help="input STEP file")
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
        "(and in the drawn label when --draw-text is on)",
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
        "--draw-text",
        action="store_true",
        help="also draw label text as annotation geometry. CAD Assistant does not "
        "render it -- OCCT writes no AP242 saved view -- and it dominates file size, "
        "so it is off by default and only useful for viewers that do",
    )
    parser.add_argument("--json", type=Path, help="also write the annotation list as JSON")
    parser.add_argument("-q", "--quiet", action="store_true", help="only report errors")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.source.is_file():
        print(f"quid2pmi: no such file: {args.source}", file=sys.stderr)
        return 2

    output = args.output or args.source.with_name(f"{args.source.stem}-pmi.step")

    try:
        families = resolve_families(args.families)
    except ValueError as exc:
        print(f"quid2pmi: {exc}", file=sys.stderr)
        return 2

    try:
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
            quiet=args.quiet,
        )
    except Exception as exc:
        print(f"quid2pmi: {exc}", file=sys.stderr)
        return 1

    if args.json:
        args.json.write_text(json.dumps(report.to_dict(), indent=2))

    if not args.quiet:
        print(
            f"{report.output}: {report.total} annotations, {report.coloured} faces coloured",
            file=sys.stderr,
        )
        for family, count in sorted(report.counts.items()):
            print(f"  {family:24s} {count}", file=sys.stderr)
        for family, count in sorted(report.unplaced.items()):
            print(f"  {family:24s} {count} record(s) with no anchor point", file=sys.stderr)
        for family, count in sorted(report.undrawn.items()):
            print(f"  {family:24s} {count} label(s) with nothing drawable", file=sys.stderr)
    return 0
