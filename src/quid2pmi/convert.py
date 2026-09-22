"""The end-to-end conversion: STEP in, recognised features annotated, STEP out."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from quiddity import build_raw_recognition_result, import_step_geometry

from .adapters import EXCLUDED_FAMILIES, FEATURE_FAMILIES, SUMMARY_FAMILIES, annotate
from .evidence import annotate_from_evidence
from .geometry import dot, normalise, snap_to_axis, sub
from .layout import BoundingBox, layout
from .model import Annotation, Vec
from .sightlines import SightTester
from .step_pmi import build_document, write_step

ALL_FAMILIES: frozenset[str] = frozenset(FEATURE_FAMILIES) | frozenset(SUMMARY_FAMILIES)


@dataclass(frozen=True)
class ConversionReport:
    """What the conversion did, for the CLI to print and for tests to assert on."""

    source: Path
    output: Path
    counts: dict[str, int]
    unplaced: dict[str, int]
    undrawn: dict[str, int]
    #: Labels whose leader had to cross the solid because no direction was clear.
    obstructed: int
    #: Annotations attached to the feature's own faces rather than the whole part.
    attached: int
    #: Faces coloured by their feature family.
    coloured: int
    #: Labels dropped because a more specific family proved the same face.
    superseded: int
    annotations: tuple[Annotation, ...]

    @property
    def total(self) -> int:
        return len(self.annotations)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": str(self.source),
            "output": str(self.output),
            "annotations": self.total,
            "counts": dict(sorted(self.counts.items())),
            "unplaced": dict(sorted(self.unplaced.items())),
            "undrawn": dict(sorted(self.undrawn.items())),
            "obstructed": self.obstructed,
            "attached": self.attached,
            "coloured": self.coloured,
            "superseded": self.superseded,
            "labels": [
                {
                    "family": a.family,
                    "text": a.label,
                    "anchor": list(a.anchor),
                    "value": a.value,
                    "dimension": a.dimension,
                    "explanation": a.explanation,
                    "faces": len(a.faces),
                }
                for a in self.annotations
            ],
        }


def resolve_families(requested: list[str] | None) -> set[str]:
    """Expand the ``--families`` selection into concrete family names."""
    if not requested:
        return set(FEATURE_FAMILIES)
    chosen: set[str] = set()
    for item in requested:
        for name in item.split(","):
            name = name.strip()
            if not name:
                continue
            if name == "all":
                chosen |= ALL_FAMILIES
            elif name == "features":
                chosen |= set(FEATURE_FAMILIES)
            elif name == "summary":
                chosen |= set(SUMMARY_FAMILIES)
            elif name in EXCLUDED_FAMILIES:
                raise ValueError(f"{name!r} is evidence, not a feature family")
            else:
                chosen.add(name)
    return chosen


#: Families that describe the same geometry in different words. Where two
#: annotations are proved on the same face, only the more specific one is
#: labelled. A turned step names the diameter and the length a lathe works to,
#: which is what the feature is; the boss it is also technically an instance of
#: says less and measures its height differently, so the two disagreed in print:
#: "BOSS D130.94 H 56.42" beside "TURNED D130.94 L57.42" on one cylinder.
SUPERSEDES: dict[str, frozenset[str]] = {"turned_steps": frozenset({"bosses"})}


def _drop_superseded(annotations: list[Annotation]) -> tuple[list[Annotation], int]:
    """Keep one label per face where two families claim the same geometry."""
    claimants: dict[Any, set[str]] = {}
    for annotation in annotations:
        for face in annotation.faces:
            claimants.setdefault(face, set()).add(annotation.family)

    kept: list[Annotation] = []
    for annotation in annotations:
        beaten = any(
            annotation.family in SUPERSEDES.get(other, frozenset())
            for face in annotation.faces
            for other in claimants[face]
        )
        if not beaten:
            kept.append(annotation)
    return kept, len(annotations) - len(kept)


def _reading_directions(annotation: Annotation, box: BoundingBox) -> list[Vec]:
    """Where to stand to read this feature's label, best first.

    The face's own normal, when it faces away from the part -- a turned step is
    read from the side it presents, not from along the lathe axis, and a leader
    that arrives axially meets the cylinder edge-on. A bore's normal points into
    the hole, which is no place to stand, so there the feature's own axis wins.
    """
    out: list[Vec] = []
    outward = normalise(sub(annotation.anchor, box.centre))
    if annotation.surface is not None and (outward is None or dot(annotation.surface, outward) > 0):
        out.append(annotation.surface)
    if annotation.normal is not None:
        out.append(annotation.normal)
    return out


def _by_family(annotations: Sequence[Annotation]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for annotation in annotations:
        counts[annotation.family] = counts.get(annotation.family, 0) + 1
    return counts


def _bounding_box(part: Any) -> BoundingBox:
    bb = part.bounding_box()
    return BoundingBox((bb.min.X, bb.min.Y, bb.min.Z), (bb.max.X, bb.max.Y, bb.max.Z))


def convert(
    source: Path,
    output: Path,
    *,
    families: set[str] | None = None,
    text_height: float | None = None,
    standoff: float | None = None,
    leaders: bool = True,
    explain: bool = False,
    colours: bool = True,
    viewer: Path | None = None,
    quiet: bool = False,
    progress: Callable[[str], None] | None = None,
) -> ConversionReport:
    """Recognise features in ``source`` and write ``output`` with them as PMI.

    Recognition runs in caller coordinates, so every annotation is positioned in
    the coordinate system of the incoming STEP file and lands on the geometry the
    output carries.

    With ``colours`` set, each feature's faces are named and coloured by family.
    That is what makes recognition visible in a viewer: CAD Assistant renders face
    colour and the model tree, but not the graphical annotation text OCCT writes.

    With ``explain`` set, the plain-words description goes into those names. The
    explanation is always present on the returned annotations and in the JSON
    report either way, and ``--viewer`` shows it in full.
    """
    say = progress if progress is not None else lambda _: None

    say("reading STEP")
    part = import_step_geometry(str(source))
    selected = families if families is not None else set(FEATURE_FAMILIES)

    say("recognising features")

    # Prefer the evidence view: it anchors each label on the feature's own proven
    # faces. Families it does not publish -- the pattern summaries -- fall back to
    # the record-derived anchors.
    annotations, unplaced, covered = annotate_from_evidence(part, selected)
    remaining = selected - covered
    if remaining:
        result = build_raw_recognition_result(part)
        extra, extra_unplaced = annotate(result, remaining)
        annotations.extend(extra)
        for family, count in extra_unplaced.items():
            unplaced[family] = unplaced.get(family, 0) + count

    annotations, superseded = _drop_superseded(annotations)

    say("choosing leader directions")
    box = _bounding_box(part)
    tester = SightTester(part.wrapped, box.diagonal * 4.0)
    obstructed = 0
    sighted: list[Annotation] = []
    for annotation in annotations:
        # Test the direction the layout will actually use. The layout snaps a label
        # to one of the six bounding box faces, so sight-testing an unsnapped face
        # normal would clear a direction that is then never used.
        preferred = [
            snap_to_axis(direction) for direction in _reading_directions(annotation, box)
        ]
        direction, clear = tester.choose(annotation.anchor, preferred)
        obstructed += 0 if clear else 1
        sighted.append(replace(annotation, normal=direction))
    annotations = sighted

    say("placing labels")
    placed = layout(annotations, box, text_height=text_height, standoff=standoff)

    say("building annotations")
    doc, written, coloured = build_document(
        part.wrapped,
        placed,
        name=source.stem,
        leaders=leaders,
        colours=colours,
        explain_names=explain,
    )
    say("writing STEP")
    write_step(doc, str(output), quiet=quiet)

    # Report the annotations that reached the file, not the ones we hoped to write.
    kept = tuple(label.annotation for label in written)
    counts = _by_family(kept)
    attempted = _by_family(annotations)
    # Equal-valued annotations are not distinguishable by value, so the shortfall is
    # counted per family rather than by testing membership.
    undrawn = {
        family: attempted[family] - counts.get(family, 0)
        for family in attempted
        if attempted[family] > counts.get(family, 0)
    }

    attached = sum(1 for a in kept if a.faces)
    if viewer is not None:
        # The same document, drawn as a web page. Annotation text is HTML there
        # rather than geometry, so it stays legible at any zoom without the file
        # size that --draw-text costs in the STEP output.
        from .viewer import write_viewer

        say("writing viewer")
        write_viewer(viewer, source.stem, doc, list(kept), box)

    return ConversionReport(
        source,
        output,
        counts,
        unplaced,
        undrawn,
        obstructed,
        attached,
        coloured,
        superseded,
        kept,
    )
