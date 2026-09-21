"""Anchor annotations on the faces recognition actually proved.

The record adapters in :mod:`quid2pmi.adapters` derive an anchor from a record's
own values, which is often a point on a feature's *axis* rather than on its
surface -- a hole's ``location`` sits one radius inside the bore. Quiddity's
evidence view resolves each accepted feature to the caller's own faces, and
``inspect_face`` proves a point on a face's real trim. Using those gives a leader
that lands on the feature instead of near it.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from quiddity.evidence import build_recognition_evidence
from quiddity.inspection import inspect_face

from .adapters import ADAPTERS, callout_for, generic_annotation, singular
from .geometry import normalise
from .model import Annotation, Vec


def _anchor_of(face: Any) -> Vec | None:
    """A point proved to lie in or on ``face``'s actual trim."""
    try:
        anchor = inspect_face(face).anchor
    except Exception:
        return None
    if anchor is None:
        return None
    if hasattr(anchor, "X"):
        return (float(anchor.X), float(anchor.Y), float(anchor.Z))
    if isinstance(anchor, (tuple, list)) and len(anchor) == 3:
        return (float(anchor[0]), float(anchor[1]), float(anchor[2]))
    return None


def _normal_at(face: Any, anchor: Vec) -> Vec | None:
    try:
        normal = face.normal_at(anchor)
    except Exception:
        return None
    return normalise((float(normal.X), float(normal.Y), float(normal.Z)))


def _best_face(faces: list[Any]) -> Any | None:
    """The largest face, which is the one a leader can most reliably land on."""
    usable = [f for f in faces if getattr(f, "area", 0.0) > 0.0]
    if not usable:
        return None
    return max(usable, key=lambda f: f.area)


def annotate_from_evidence(
    part: Any, families: set[str]
) -> tuple[list[Annotation], dict[str, int], set[str]]:
    """Adapt every accepted feature, anchored on its own proven geometry.

    Returns the annotations, a per-family count of features that produced none,
    and the set of families the evidence view covered -- so the caller can fall
    back to the record-only path for families it did not.
    """
    view = build_recognition_evidence(part)
    annotations: list[Annotation] = []
    unplaced: dict[str, int] = {}
    covered: set[str] = set()

    for feature in view.features:
        family = view.family(feature)
        covered.add(family)
        if family not in families:
            continue
        record = view.record(feature)
        to_dict = getattr(record, "to_dict", None)
        if to_dict is None:
            unplaced[family] = unplaced.get(family, 0) + 1
            continue
        payload = to_dict()
        adapter = ADAPTERS.get(family)
        made = adapter(payload) if adapter else generic_annotation(family, payload)

        defining = [view.face(ref) for ref in view.defining_faces(feature)]
        constituent = [view.face(ref) for ref in view.constituent_faces(feature)]
        faces = tuple(constituent or defining)

        face = _best_face(defining) or _best_face(constituent)
        anchor = _anchor_of(face) if face is not None else None

        if made is None:
            # The record gave no anchor, but its geometry still can.
            if anchor is None:
                unplaced[family] = unplaced.get(family, 0) + 1
                continue
            made = generic_annotation(family, payload) or Annotation(
                family, (singular(family).upper(),), anchor
            )
        if anchor is not None:
            made = replace(
                made,
                anchor=anchor,
                normal=made.normal or _normal_at(face, anchor),
            )
        annotations.append(
            replace(made, faces=faces, callout=callout_for(family, payload, made.text))
        )

    return annotations, unplaced, covered
