#!/usr/bin/env python3
"""Add an AP242 saved view to a STEP file written by OCCT.

OCCT's STEPCAFControl_Writer emits graphical PMI -- draughting callouts as
tessellated annotation occurrences on a draughting model -- but writes no saved
view, because it has no view mode at all. Measured against the NIST PMI
reference suite, that is the *only* structural difference in quid2pmi's output:
the annotations themselves are the same kinds of entity.

Viewers drive graphical PMI display from saved views, so without one there is
nothing to switch on. This turns the plain

    #N = DRAUGHTING_MODEL('', (callouts...), #context);

into the combined draughting-model-and-representation that NIST's files use,

    #N = (
    CHARACTERIZED_OBJECT(*,*)
    CHARACTERIZED_REPRESENTATION()
    DRAUGHTING_MODEL()
    REPRESENTATION('<name>', (#camera, callouts...), #context)
    );

and adds the camera, its view volume and frame, plus the relationship that ties
the view to the part's shape representation.

    python add_saved_view.py part.step                 # in place, .bak kept
    python add_saved_view.py part.step -o viewed.step
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

#: Matches the plain draughting model OCCT writes, across its wrapped lines.
DRAUGHTING_MODEL = re.compile(
    r"#(?P<id>\d+)\s*=\s*DRAUGHTING_MODEL\(\s*''\s*,\s*\((?P<items>[^)]*)\)\s*,\s*#(?P<ctx>\d+)\s*\)\s*;",
    re.S,
)
BREP_REP = re.compile(r"#(?P<id>\d+)\s*=\s*ADVANCED_BREP_SHAPE_REPRESENTATION\(", re.S)
AXIS_PLACEMENT = re.compile(r"#(?P<id>\d+)\s*=\s*AXIS2_PLACEMENT_3D\(", re.S)
CARTESIAN_POINT = re.compile(r"#(?P<id>\d+)\s*=\s*CARTESIAN_POINT\(", re.S)
ENTITY_ID = re.compile(r"^#(\d+)\s*=", re.M)


class NoDraughtingModel(Exception):
    """The file carries no graphical PMI to build a view around."""


def _next_id(text: str) -> int:
    ids = [int(m.group(1)) for m in ENTITY_ID.finditer(text)]
    if not ids:
        raise ValueError("no STEP entities found")
    return max(ids) + 1


def _first(pattern: re.Pattern[str], text: str, what: str) -> str:
    match = pattern.search(text)
    if match is None:
        raise ValueError(f"no {what} found")
    return match.group("id")


def add_saved_view(text: str, name: str = "MBD_0", extent: float = 1000.0) -> tuple[str, int]:
    """Return the file with a saved view added, and the annotation count it covers."""
    model = DRAUGHTING_MODEL.search(text)
    if model is None:
        raise NoDraughtingModel(
            "no DRAUGHTING_MODEL in this file: it carries no graphical PMI"
        )

    items = " ".join(model.group("items").split())
    context = model.group("ctx")
    count = len([i for i in items.split(",") if i.strip()])

    brep = _first(BREP_REP, text, "ADVANCED_BREP_SHAPE_REPRESENTATION")
    placement = _first(AXIS_PLACEMENT, text, "AXIS2_PLACEMENT_3D")

    origin = _first(CARTESIAN_POINT, text, "CARTESIAN_POINT")

    base = _next_id(text)
    box, volume, camera, mapping, mapped, view, relation = (base + n for n in range(7))

    # Wired as the NIST PMI reference files wire it:
    #   the view volume is anchored on a cartesian point, not a placement;
    #   the camera is published through a representation map and mapped item;
    #   and the relationship ties the combined view to the *plain* draughting
    #   model that already owns the annotations -- not to the B-rep.
    added = f"""#{box} = PLANAR_BOX('{name}',{extent:.6f},{extent:.6f},#{placement});
#{volume} = VIEW_VOLUME(.PARALLEL.,#{origin},{extent:.6f},0.,.F.,0.,.F.,.F.,#{box});
#{camera} = CAMERA_MODEL_D3('{name}',#{placement},#{volume});
#{mapping} = REPRESENTATION_MAP(#{camera},#{brep});
#{mapped} = MAPPED_ITEM('',#{mapping},#{placement});
#{view} = (
CHARACTERIZED_OBJECT(*,*)
CHARACTERIZED_REPRESENTATION()
DRAUGHTING_MODEL()
REPRESENTATION('{name}',(#{camera},{items},#{mapped}),#{context})
);
#{relation} = MECHANICAL_DESIGN_AND_DRAUGHTING_RELATIONSHIP('','',#{view},#{model.group("id")});
"""

    # The original plain draughting model is left in place: it is what the
    # annotations already belong to, and removing it would orphan them in
    # readers that do not follow the saved view.
    #
    # A STEP file has two ENDSEC; markers -- one closing HEADER, one closing
    # DATA -- so the insert must target the last, not the first.
    cut = text.rfind("ENDSEC;")
    if cut < 0:
        raise ValueError("no ENDSEC; terminating the DATA section")
    return text[:cut] + added + text[cut:], count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("source", type=Path, help="STEP file written by OCCT")
    parser.add_argument("-o", "--output", type=Path, help="write here instead of in place")
    parser.add_argument("--name", default="MBD_0", help="saved view name (default: MBD_0)")
    parser.add_argument(
        "--extent", type=float, default=1000.0, help="view volume size in model units"
    )
    args = parser.parse_args(argv)

    if not args.source.is_file():
        print(f"add_saved_view: no such file: {args.source}", file=sys.stderr)
        return 2

    text = args.source.read_text(errors="ignore")
    try:
        updated, count = add_saved_view(text, args.name, args.extent)
    except (NoDraughtingModel, ValueError) as exc:
        print(f"add_saved_view: {exc}", file=sys.stderr)
        return 1

    destination = args.output or args.source
    if args.output is None:
        shutil.copy2(args.source, args.source.with_suffix(args.source.suffix + ".bak"))
    destination.write_text(updated)
    print(f"{destination}: saved view {args.name!r} over {count} annotations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
