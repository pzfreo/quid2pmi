"""Place annotation labels around the part so they are readable and do not overlap.

Every label is assigned to one of the six faces of the part's bounding box, which
gives a single text plane per group. Within a group the labels are laid out in
that plane's 2D coordinates, starting from each feature's own projected position
and pushed apart only where they would collide. Each label keeps a leader line
back to the point it describes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .geometry import add, cross, dot, normalise, scale, snap_to_axis, sub
from .model import Annotation, Vec

#: Text rows are this many text heights apart.
LINE_PITCH = 1.45
#: A label is pushed this far clear of the bounding box face it sits on.
STANDOFF_FRACTION = 0.10
#: Nominal glyph advance as a fraction of text height, for collision boxes.
GLYPH_WIDTH = 0.62


@dataclass(frozen=True)
class BoundingBox:
    min: Vec
    max: Vec

    @property
    def centre(self) -> Vec:
        return tuple((self.min[i] + self.max[i]) / 2.0 for i in range(3))  # type: ignore[return-value]

    @property
    def diagonal(self) -> float:
        return math.sqrt(sum((self.max[i] - self.min[i]) ** 2 for i in range(3)))

    def extent_along(self, direction: Vec) -> float:
        """Half-extent of the box along ``direction``, measured from its centre."""
        half = [(self.max[i] - self.min[i]) / 2.0 for i in range(3)]
        return sum(abs(direction[i]) * half[i] for i in range(3))


@dataclass(frozen=True)
class PlacedLabel:
    """An annotation with a resolved text plane, text origin and leader path."""

    annotation: Annotation
    origin: Vec
    x_dir: Vec
    y_dir: Vec
    height: float
    leader: tuple[Vec, ...]


def _plane_axes(normal: Vec) -> tuple[Vec, Vec]:
    """In-plane right and up directions for a label plane, chosen so text is upright.

    For a label read along a horizontal direction, "up" is world +Z. For one read
    along Z there is no such preference, so world +Y is used instead.
    """
    if abs(normal[2]) > 0.9:
        up_hint: Vec = (0.0, 1.0, 0.0)
    else:
        up_hint = (0.0, 0.0, 1.0)
    x_dir = normalise(cross(up_hint, normal))
    if x_dir is None:  # pragma: no cover - guarded by the hint choice above
        x_dir = (1.0, 0.0, 0.0)
    y_dir = normalise(cross(normal, x_dir)) or (0.0, 0.0, 1.0)
    return x_dir, y_dir


def _direction_for(annotation: Annotation, box: BoundingBox) -> Vec:
    """The outward direction a label is read from, snapped to a principal axis."""
    if annotation.normal is not None:
        unit = normalise(annotation.normal)
        if unit is not None:
            return snap_to_axis(unit)
    outward = normalise(sub(annotation.anchor, box.centre))
    if outward is None:
        return (0.0, 0.0, 1.0)
    return snap_to_axis(outward)


def _overlaps(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def layout(
    annotations: list[Annotation],
    box: BoundingBox,
    text_height: float | None = None,
    standoff: float | None = None,
) -> list[PlacedLabel]:
    """Resolve every annotation to a text plane, position and leader line."""
    if not annotations:
        return []
    diagonal = box.diagonal or 1.0
    height = text_height if text_height else max(diagonal / 45.0, 1e-3)
    clearance = standoff if standoff is not None else diagonal * STANDOFF_FRACTION

    groups: dict[Vec, list[Annotation]] = {}
    for annotation in annotations:
        groups.setdefault(_direction_for(annotation, box), []).append(annotation)

    placed: list[PlacedLabel] = []
    for normal, members in groups.items():
        x_dir, y_dir = _plane_axes(normal)
        plane_offset = box.extent_along(normal) + clearance
        plane_point = add(box.centre, scale(normal, plane_offset))
        base = dot(plane_point, normal)

        # Project each anchor into the plane's own 2D coordinates.
        projected: list[tuple[float, float, Annotation]] = []
        for annotation in members:
            rel = sub(annotation.anchor, plane_point)
            projected.append((dot(rel, x_dir), dot(rel, y_dir), annotation))
        projected.sort(key=lambda item: (-item[1], item[0]))

        taken: list[tuple[float, float, float, float]] = []
        for u, v, annotation in projected:
            rows = len(annotation.text)
            widest = max(len(line) for line in annotation.text)
            width = widest * GLYPH_WIDTH * height
            block = rows * LINE_PITCH * height
            # Start at the feature's own position, then slide up until clear.
            cu, cv = u, v
            attempts = 0
            while attempts < 200:
                candidate = (cu, cv - block, cu + width, cv)
                if not any(_overlaps(candidate, other) for other in taken):
                    break
                cv += LINE_PITCH * height
                attempts += 1
            taken.append((cu, cv - block, cu + width, cv))

            origin = add(
                add(plane_point, scale(x_dir, cu)),
                scale(y_dir, cv - LINE_PITCH * height),
            )
            # Leader: out of the label's left edge, then straight to the feature.
            elbow = add(origin, scale(y_dir, -0.35 * height))
            gap = base - dot(annotation.anchor, normal)
            anchor_in_plane = add(annotation.anchor, scale(normal, gap))
            leader = (elbow, anchor_in_plane, annotation.anchor)
            placed.append(PlacedLabel(annotation, origin, x_dir, y_dir, height, leader))
    return placed
