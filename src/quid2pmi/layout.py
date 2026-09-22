"""Place annotation labels around the part so they are readable and do not overlap.

Every label is assigned to one of the six faces of the part's bounding box, which
gives a single text plane per group. Within a group the labels are laid out on a
bounded grid in that plane: each one takes the free cell nearest its own feature,
so labels stay beside what they describe and the block as a whole cannot run away
from the part. Each label keeps a leader line back to the point it describes.
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
#: How far the leader stands off the surface before turning, as a fraction of
#: text height. Long enough to read as perpendicular, short enough not to float.
STUB = 0.8

#: Gap between neighbouring grid cells, as a fraction of text height.
CELL_GAP = 0.8
#: The label block on one bounding box face may grow to this multiple of that
#: face, before the text is scaled down to keep the labels beside the part.
FIT_MARGIN = 1.8


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

    @property
    def normal(self) -> Vec:
        x, y = self.x_dir, self.y_dir
        return cross(x, y)


def _stands_off(annotation: Annotation) -> bool:
    """Whether the leader can leave along the surface without entering the part.

    A face's normal points out of the solid, which for a bore wall means *into*
    the hole. Standing off along it there would send the leader through material
    on its way back out. It is only safe where the surface faces the same way the
    label is read from.
    """
    if annotation.surface is None or annotation.normal is None:
        return False
    return dot(annotation.surface, annotation.normal) > 0.2


def _plane_axes(normal: Vec) -> tuple[Vec, Vec]:
    """In-plane right and up directions for a label plane, chosen so text is upright.

    For a label read along a horizontal direction, "up" is world +Z. For one read
    along Z there is no such preference, so world +Y is used instead.
    """
    up_hint: Vec = (0.0, 1.0, 0.0) if abs(normal[2]) > 0.9 else (0.0, 0.0, 1.0)
    x_dir = normalise(cross(up_hint, normal)) or (1.0, 0.0, 0.0)
    y_dir = normalise(cross(normal, x_dir)) or (0.0, 0.0, 1.0)
    return x_dir, y_dir


def _direction_for(annotation: Annotation, box: BoundingBox) -> Vec:
    """The outward direction a label is read from, snapped to a principal axis."""
    if annotation.normal is not None:
        unit = normalise(annotation.normal)
        if unit is not None:
            return snap_to_axis(unit)
    outward = normalise(sub(annotation.anchor, box.centre))
    return snap_to_axis(outward) if outward is not None else (0.0, 0.0, 1.0)


def _spiral(count: int) -> list[tuple[int, int]]:
    """Grid offsets ordered by how far they sit from the origin cell."""
    reach = int(math.isqrt(max(count, 1))) + 2
    cells = [
        (column, row) for column in range(-reach, reach + 1) for row in range(-reach, reach + 1)
    ]
    cells.sort(key=lambda cell: (abs(cell[0]) + abs(cell[1]), abs(cell[1]), cell[0], cell[1]))
    return cells


def _assign_cells(
    projected: list[tuple[float, float, Annotation]],
    cell_w: float,
    cell_h: float,
) -> list[tuple[float, float, Annotation]]:
    """Give each label the free grid cell nearest its own feature.

    Snapping to a grid bounds the layout: a label can only ever move to a cell,
    and cells are allocated outward from the feature, so a crowded face spreads
    sideways rather than marching off to infinity.
    """
    offsets = _spiral(len(projected))
    taken: set[tuple[int, int]] = set()
    placed: list[tuple[float, float, Annotation]] = []
    # Outermost features choose first, so they keep the outer cells.
    order = sorted(
        range(len(projected)),
        key=lambda i: -(projected[i][0] ** 2 + projected[i][1] ** 2),
    )
    for index in order:
        u, v, annotation = projected[index]
        home = (round(u / cell_w), round(v / cell_h))
        for du, dv in offsets:
            cell = (home[0] + du, home[1] + dv)
            if cell not in taken:
                taken.add(cell)
                placed.append((cell[0] * cell_w, cell[1] * cell_h, annotation))
                break
        else:  # pragma: no cover - the spiral is sized to always have room
            placed.append((u, v, annotation))
    return placed


def _grid_shape(count: int) -> tuple[int, int]:
    """Columns and rows a grid of ``count`` cells spans."""
    columns = max(1, math.isqrt(count - 1) + 1 if count > 1 else 1)
    rows = -(-count // columns)
    return columns, rows


def _fitted_height(groups: dict[Vec, list[Annotation]], box: BoundingBox, base: float) -> float:
    """Shrink the text until each face's block of labels sits beside the part.

    Label blocks scale linearly with text height, so a single ratio suffices. Long
    text is what makes this necessary: a wrapped explanation at the default height
    is a block wider than a small part, and sixty of them would spread far enough
    that the labels are a speck at any zoom that fits them all.
    """
    height = base
    for normal, members in groups.items():
        x_dir, y_dir = _plane_axes(normal)
        widest = max(max(len(line) for line in a.text) for a in members)
        tallest = max(len(a.text) for a in members)
        columns, rows = _grid_shape(len(members))
        span_u = columns * (widest * GLYPH_WIDTH + CELL_GAP) * base
        span_v = rows * (tallest * LINE_PITCH + CELL_GAP) * base
        allowed_u = max(2.0 * box.extent_along(x_dir), box.diagonal * 0.5) * FIT_MARGIN
        allowed_v = max(2.0 * box.extent_along(y_dir), box.diagonal * 0.5) * FIT_MARGIN
        for span, allowed in ((span_u, allowed_u), (span_v, allowed_v)):
            if span > allowed:
                height = min(height, base * allowed / span)
    return max(height, base * 0.05)


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
    clearance = standoff if standoff is not None else diagonal * STANDOFF_FRACTION

    groups: dict[Vec, list[Annotation]] = {}
    for annotation in annotations:
        groups.setdefault(_direction_for(annotation, box), []).append(annotation)

    if text_height:
        height = text_height
    else:
        height = _fitted_height(groups, box, max(diagonal / 45.0, 1e-3))

    placed: list[PlacedLabel] = []
    for normal, members in groups.items():
        x_dir, y_dir = _plane_axes(normal)
        plane_point = add(box.centre, scale(normal, box.extent_along(normal) + clearance))
        base = dot(plane_point, normal)

        projected = [
            (
                dot(sub(a.anchor, plane_point), x_dir),
                dot(sub(a.anchor, plane_point), y_dir),
                a,
            )
            for a in members
        ]
        widest = max(max(len(line) for line in a.text) for a in members)
        tallest = max(len(a.text) for a in members)
        cell_w = widest * GLYPH_WIDTH * height + CELL_GAP * height
        cell_h = tallest * LINE_PITCH * height + CELL_GAP * height

        for u, v, annotation in _assign_cells(projected, cell_w, cell_h):
            origin = add(add(plane_point, scale(x_dir, u)), scale(y_dir, v))
            # Leader: out of the label's lower-left corner, across the label plane
            # to the feature's own position in it, then straight in to the feature.
            # The last leg leaves the surface along its own normal, as a drawing's
            # does, rather than along whichever axis the label plane happens to be:
            # into a bore wall that is the difference between radial and sideways.
            elbow = add(origin, scale(y_dir, -0.35 * height))
            stub = annotation.anchor
            surface = annotation.surface if _stands_off(annotation) else None
            if surface is not None:
                stub = add(annotation.anchor, scale(surface, STUB * height))
            gap = base - dot(stub, normal)
            leader = (elbow, add(stub, scale(normal, gap)), stub, annotation.anchor)
            placed.append(PlacedLabel(annotation, origin, x_dir, y_dir, height, leader))
    return placed
