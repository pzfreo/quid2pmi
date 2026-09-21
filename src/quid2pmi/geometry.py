"""Small vector helpers shared by the record adapters and the layout."""

from __future__ import annotations

import math

from .model import Vec

AXIS_VECTORS: dict[str, Vec] = {
    "x": (1.0, 0.0, 0.0),
    "y": (0.0, 1.0, 0.0),
    "z": (0.0, 0.0, 1.0),
}


def axis_vector(letter: str | None) -> Vec | None:
    """Map a Quiddity axis letter to a unit vector, or ``None`` if unrecognised."""
    if not isinstance(letter, str):
        return None
    return AXIS_VECTORS.get(letter.lower())


def add(a: Vec, b: Vec) -> Vec:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a: Vec, b: Vec) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def scale(a: Vec, k: float) -> Vec:
    return (a[0] * k, a[1] * k, a[2] * k)


def dot(a: Vec, b: Vec) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a: Vec, b: Vec) -> Vec:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def length(a: Vec) -> float:
    return math.sqrt(dot(a, a))


def normalise(a: Vec) -> Vec | None:
    """Unit vector, or ``None`` for a vector too short to carry a direction."""
    n = length(a)
    if n < 1e-9:
        return None
    return (a[0] / n, a[1] / n, a[2] / n)


def perpendicular(a: Vec) -> Vec:
    """Any unit vector perpendicular to ``a``."""
    helper = (0.0, 0.0, 1.0) if abs(a[2]) < 0.9 else (1.0, 0.0, 0.0)
    out = normalise(cross(a, helper))
    return out if out is not None else (1.0, 0.0, 0.0)


def as_point(value: object) -> Vec | None:
    """Coerce a 3-element sequence of numbers to a point, else ``None``."""
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return None
    try:
        return (float(value[0]), float(value[1]), float(value[2]))
    except (TypeError, ValueError):
        return None


def snap_to_axis(direction: Vec) -> Vec:
    """Snap a direction to the nearest of the six principal axes.

    Labels are grouped onto the six faces of the part's bounding box, so that
    every label in a group shares one text plane and can be laid out in 2D.
    """
    idx = max(range(3), key=lambda i: abs(direction[i]))
    sign = 1.0 if direction[idx] >= 0 else -1.0
    out = [0.0, 0.0, 0.0]
    out[idx] = sign
    return (out[0], out[1], out[2])
