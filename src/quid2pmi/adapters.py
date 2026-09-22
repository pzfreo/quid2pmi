"""Turn Quiddity feature records into neutral :class:`~quid2pmi.model.Annotation` values.

Each family gets an explicit adapter, because the records are deliberately
family-specific: some carry an outright 3D point, others carry an axis letter
plus spans from which a point has to be reconstructed. A family with no adapter
falls back to :func:`generic_annotation`, which labels what it can and reports
the record as unplaced when it cannot find a point.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import replace
from typing import Any

from .geometry import add, as_point, axis_vector, normalise, perpendicular, scale, sub
from .model import (
    DIM_ANGLE,
    DIM_DIAMETER,
    DIM_LENGTH,
    DIM_RADIUS,
    DIM_THICKNESS,
    Annotation,
    Vec,
)

#: Used in the terse STEP label, whose text is drawn as glyph outlines: the
#: Latin capital O with stroke is present in every font we might fall back to,
#: where the typographically correct diameter sign is not.
DIAMETER_SIGN = "\u00d8"
#: Used in drawing callouts, which are rendered as HTML by the viewer and can
#: have the real diameter sign -- the same character step-pmi-viewer writes for
#: authored PMI, so the two read alike.
DIAMETER_CALLOUT = "\u2300"

#: Drawing symbols used in callouts.
DEPTH = "\u21a7"  # downwards arrow from bar
COUNTERBORE = "\u2334"  # conclusive
COUNTERSINK = "\u2335"
TIMES = "\u00d7"
DEGREE = "\u00b0"

#: Families carrying a recognised feature, emitted unless the caller narrows the set.
FEATURE_FAMILIES: tuple[str, ...] = (
    "holes",
    "bosses",
    "polygonal_bosses",
    "countersinks",
    "double_d_bores",
    "slots",
    "oriented_slots",
    "section_recesses",
    "pads",
    "gusset_ribs",
    "chamfers",
    "fillets",
    "blends",
    "grooves",
    "flats",
    "plates",
    "through_steps",
    "angled_steps",
    "paired_ramp_steps",
    "circular_blind_steps",
    "turned_steps",
    "step_levels",
)

#: Families summarising other families. Off by default: they duplicate leaders.
SUMMARY_FAMILIES: tuple[str, ...] = (
    "hole_patterns",
    "slot_patterns",
    "oriented_slot_patterns",
    "section_recess_patterns",
    "gusset_rib_patterns",
    "turned_profiles",
    "polygonal_stock",
    "repeating_radial_profiles",
)

#: Not features: raw evidence, diagnostics, or objects holding live topology.
EXCLUDED_FAMILIES: frozenset[str] = frozenset(
    {"cylinders", "risers", "rotational", "section_recess_refusals", "step_ladder"}
)


AXIS_WORDS = {"x": "the X axis", "y": "the Y axis", "z": "the Z axis"}


def axis_phrase(letter: object) -> str:
    """Name an axis for prose, falling back to the raw value when unrecognised."""
    return AXIS_WORDS.get(str(letter).lower(), f"axis {letter}")


def direction_phrase(vector: Vec | None) -> str:
    """Name an axis-aligned direction for prose, e.g. ``+Z``; empty when it is not."""
    if vector is None:
        return ""
    for index, letter in enumerate("XYZ"):
        if abs(vector[index]) > 0.999:
            return f"{'+' if vector[index] > 0 else '-'}{letter}"
    return ""


def singular(family: str) -> str:
    """Singular form of a family name, for prose and generic labels.

    Stripping a trailing "s" is not enough: it turns "bosses" into "bosse".
    """
    word = family.replace("_", " ")
    for ending in ("sses", "ses", "xes", "ches", "shes"):
        if word.endswith(ending):
            return word[:-2]
    return word[:-1] if word.endswith("s") else word


def num(value: object, places: int = 3) -> str:
    """Format a length or angle for a drawing label, without trailing zeros."""
    try:
        f = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return str(value)
    text = f"{f:.{places}f}".rstrip("0").rstrip(".")
    return text if text not in ("", "-0") else "0"


# --------------------------------------------------------------------------
# Anchor reconstruction for records that carry no outright 3D point
# --------------------------------------------------------------------------


def _frame_anchor(frame: dict[str, Any], run_interval: Any, boundary: Any) -> Vec | None:
    """Centroid of a swept section record (oriented slots, section recesses)."""
    origin = as_point(frame.get("origin"))
    run = as_point(frame.get("run"))
    u = as_point(frame.get("u"))
    v = as_point(frame.get("v"))
    if origin is None or run is None or u is None or v is None:
        return None
    point = origin
    if isinstance(run_interval, (list, tuple)) and len(run_interval) == 2:
        point = add(point, scale(run, (float(run_interval[0]) + float(run_interval[1])) / 2.0))
    points = boundary if isinstance(boundary, (list, tuple)) else ()
    uv: list[tuple[float, float]] = []
    for entry in points:
        pair = entry.get("point") if isinstance(entry, dict) else None
        if isinstance(pair, (list, tuple)) and len(pair) == 2:
            uv.append((float(pair[0]), float(pair[1])))
    if uv:
        mean_u = sum(pair[0] for pair in uv) / len(uv)
        mean_v = sum(pair[1] for pair in uv) / len(uv)
        point = add(add(point, scale(u, mean_u)), scale(v, mean_v))
    return point


def _radial_anchor(origin: Vec, axis: Vec, radius: float) -> tuple[Vec, Vec]:
    """A point on a cylinder of ``radius`` about ``axis``, with its outward normal."""
    radial = perpendicular(axis)
    return add(origin, scale(radial, radius)), radial


def _span_anchor(
    axis_letter: str,
    body_key: Any,
    position: float,
) -> Vec | None:
    """Centre of the part's bounding box, moved to ``position`` along ``axis_letter``.

    ``body_key`` is Quiddity's per-body key whose first six values are the body's
    bounding box. It is the only extent such records carry.
    """
    axis = axis_vector(axis_letter)
    if axis is None or not isinstance(body_key, (list, tuple)) or len(body_key) < 6:
        return None
    lo = [float(v) for v in body_key[0:3]]
    hi = [float(v) for v in body_key[3:6]]
    centre = [(lo[i] + hi[i]) / 2.0 for i in range(3)]
    idx = max(range(3), key=lambda i: abs(axis[i]))
    centre[idx] = position
    return (centre[0], centre[1], centre[2])


# --------------------------------------------------------------------------
# Per-family adapters
# --------------------------------------------------------------------------


def _hole(d: dict[str, Any]) -> Annotation | None:
    loc = as_point(d.get("location"))
    if loc is None:
        return None
    axis = as_point(d.get("axis"))
    parts = [f"HOLE {DIAMETER_SIGN}{num(d.get('diameter'))}"]
    bottom = d.get("bottom")
    if bottom == "through":
        parts.append("THRU")
    elif d.get("depth") is not None:
        parts.append(f"{num(d.get('depth'))} DEEP")
    extras = [e for e in ("cbore", "spotface", "csink") if d.get(e)]
    parts.extend(e.upper() for e in extras)
    # The axis points into the material; the label reads from outside.
    normal = normalise(scale(axis, -1.0)) if axis else None
    prose = f"Cylindrical hole of {num(d.get('diameter'))} diameter"
    if bottom == "through":
        prose += ", passing right through the part"
    elif d.get("depth") is not None:
        prose += f", {num(d.get('depth'))} deep with a {bottom or 'plain'} bottom"
    facing = direction_phrase(normal)
    if facing:
        prose += f", opening towards {facing}"
    prose += "."
    if extras:
        prose += " Entry treatment: " + ", ".join(extras) + "."
    return Annotation("holes", tuple(parts), loc, normal, d.get("diameter"), DIM_DIAMETER, prose)


def _boss(d: dict[str, Any]) -> Annotation | None:
    loc = as_point(d.get("location"))
    if loc is None:
        return None
    axis = as_point(d.get("axis"))
    text = (f"BOSS {DIAMETER_SIGN}{num(d.get('diameter'))}", f"H {num(d.get('height'))}")
    normal = normalise(axis) if axis else None
    prose = (
        f"Cylindrical boss of {num(d.get('diameter'))} diameter standing "
        f"{num(d.get('height'))} proud of its base"
    )
    facing = direction_phrase(normal)
    prose += f", rising towards {facing}." if facing else "."
    return Annotation("bosses", text, loc, normal, d.get("diameter"), DIM_DIAMETER, prose)


def _chamfer(d: dict[str, Any]) -> Annotation | None:
    at = as_point(d.get("at"))
    if at is None:
        return None
    text = (f"CHAMFER {num(d.get('leg1'))}x{num(d.get('leg2'))}", f"{num(d.get('angle'), 1)}deg")
    prose = (
        f"{'Turned' if d.get('turned') else 'Prismatic'} chamfer about "
        f"{axis_phrase(d.get('axis'))}, legs {num(d.get('leg1'))} and {num(d.get('leg2'))} "
        f"at {num(d.get('angle'), 1)} degrees."
    )
    # The leg, not the angle, is the value carried semantically. An angular size
    # renders as a swept arc with an .EQUAL. qualifier, and a part with many
    # chamfers becomes unreadable; the angle stays in the label and explanation.
    return Annotation("chamfers", text, at, None, d.get("leg1"), DIM_THICKNESS, prose)


def _fillet(d: dict[str, Any]) -> Annotation | None:
    at = as_point(d.get("at"))
    if at is None:
        return None
    prose = (
        f"{'Turned' if d.get('turned') else 'Prismatic'} fillet of radius "
        f"{num(d.get('radius'))} about {axis_phrase(d.get('axis'))}."
    )
    return Annotation(
        "fillets",
        (f"FILLET R{num(d.get('radius'))}",),
        at,
        None,
        d.get("radius"),
        DIM_RADIUS,
        prose,
    )


def _blend(d: dict[str, Any]) -> Annotation | None:
    path = d.get("path")
    radius = d.get("radius")
    if not isinstance(path, dict):
        return None

    # A blend follows either a circle, given as centre/normal/radius, or a
    # straight edge, given as a point and direction. Handling only the circular
    # form leaves every blend along a straight edge unlabelled.
    centre = as_point(path.get("center"))
    normal = as_point(path.get("normal"))
    path_radius = path.get("radius")
    anchor: Vec
    facing: Vec | None
    if centre is not None and normal is not None and path_radius is not None:
        anchor, facing = _radial_anchor(centre, normal, float(path_radius))
        along = f" following a circular path of radius {num(path_radius)}"
    else:
        straight = as_point(path.get("at"))
        if straight is None:
            return None
        anchor, facing = straight, None
        direction = as_point(path.get("direction"))
        along = f" along {direction_phrase(direction)}" if direction_phrase(direction) else ""

    side = d.get("side")
    text = (f"BLEND R{num(radius)}", str(side).upper()) if side else (f"BLEND R{num(radius)}",)
    prose = f"{str(side).capitalize() if side else 'Rolling'} blend of radius {num(radius)}{along}."
    return Annotation("blends", text, anchor, facing, radius, DIM_RADIUS, prose)


def _groove(d: dict[str, Any]) -> Annotation | None:
    at = as_point(d.get("at"))
    axis = axis_vector(d.get("axis"))
    diameter = d.get("diameter")
    if at is None or axis is None or diameter is None:
        return None
    anchor, radial = _radial_anchor(at, axis, float(diameter) / 2.0)
    text = (f"GROOVE W{num(d.get('width'))}", f"{DIAMETER_SIGN}{num(diameter)}")
    prose = (
        f"Groove {num(d.get('width'))} wide turned down to {num(diameter)} diameter "
        f"about {axis_phrase(d.get('axis'))}."
    )
    return Annotation("grooves", text, anchor, radial, diameter, DIM_DIAMETER, prose)


def _flat(d: dict[str, Any]) -> Annotation | None:
    at = as_point(d.get("at"))
    if at is None:
        return None
    axis = as_point(d.get("axis_direction")) or axis_vector(d.get("axis"))
    normal = None
    if axis is not None:
        # The flat faces away from the turning axis, so remove the axial component
        # of the vector from a point on that axis to the flat.
        origin = _axis_line_origin(str(d.get("axis", "")), d.get("axis_line"))
        offset = sub(at, origin)
        radial = sub(offset, scale(axis, sum(offset[i] * axis[i] for i in range(3))))
        normal = normalise(radial)
    prose = (
        f"Machined flat on a turned body, {num(d.get('across'))} across, "
        f"cut parallel to {axis_phrase(d.get('axis'))}."
    )
    return Annotation(
        "flats",
        (f"FLAT {num(d.get('across'))} ACROSS",),
        at,
        normal,
        d.get("across"),
        DIM_THICKNESS,
        prose,
    )


def _axis_line_origin(axis_letter: str, axis_line: Any) -> Vec:
    """A point on a turning axis, from Quiddity's two off-axis coordinates."""
    order = "xyz"
    letter = axis_letter.lower()
    if letter not in order or not isinstance(axis_line, (list, tuple)) or len(axis_line) != 2:
        return (0.0, 0.0, 0.0)
    idx = order.index(letter)
    others = [i for i in range(3) if i != idx]
    point = [0.0, 0.0, 0.0]
    try:
        point[others[0]] = float(axis_line[0])
        point[others[1]] = float(axis_line[1])
    except (TypeError, ValueError):
        return (0.0, 0.0, 0.0)
    return (point[0], point[1], point[2])


def _through_step(d: dict[str, Any]) -> Annotation | None:
    at = as_point(d.get("at"))
    if at is None:
        return None
    prose = (
        f"Step running the full {num(d.get('length'))} of the part "
        f"along {axis_phrase(d.get('axis'))}."
    )
    return Annotation(
        "through_steps",
        (f"THRU STEP L{num(d.get('length'))}",),
        at,
        None,
        d.get("length"),
        DIM_LENGTH,
        prose,
    )


def _angled_step(d: dict[str, Any]) -> Annotation | None:
    at = as_point(d.get("at"))
    if at is None:
        return None
    text = (
        f"ANGLED STEP {num(d.get('angle'), 1)}deg",
        f"{num(d.get('leg1'))}x{num(d.get('leg2'))}",
    )
    prose = (
        f"Step cut at {num(d.get('angle'), 1)} degrees with legs {num(d.get('leg1'))} and "
        f"{num(d.get('leg2'))}, running {num(d.get('length'))} along "
        f"{axis_phrase(d.get('axis'))}."
    )
    return Annotation("angled_steps", text, at, None, d.get("angle"), DIM_ANGLE, prose)


def _ramp_step(d: dict[str, Any]) -> Annotation | None:
    at = as_point(d.get("at"))
    if at is None:
        return None
    text = (f"RAMP {num(d.get('angle'), 1)}deg", f"L{num(d.get('length'))}")
    prose = (
        f"Matched pair of ramped steps at {num(d.get('angle'), 1)} degrees, "
        f"{num(d.get('length'))} long along {axis_phrase(d.get('axis'))}."
    )
    return Annotation("paired_ramp_steps", text, at, None, d.get("angle"), DIM_ANGLE, prose)


def _blind_step(d: dict[str, Any]) -> Annotation | None:
    line = d.get("centreline")
    if not isinstance(line, (list, tuple)) or len(line) != 2:
        return None
    a, b = as_point(line[0]), as_point(line[1])
    if a is None or b is None:
        return None
    mid = scale(add(a, b), 0.5)
    text = (f"BLIND STEP R{num(d.get('radius'))}", f"L{num(d.get('length'))}")
    prose = (
        f"Blind step with a circular end of radius {num(d.get('radius'))}, "
        f"{num(d.get('length'))} long along {axis_phrase(d.get('axis'))}."
    )
    return Annotation("circular_blind_steps", text, mid, None, d.get("radius"), DIM_RADIUS, prose)


def _turned_step(d: dict[str, Any]) -> Annotation | None:
    axis = axis_vector(d.get("axis"))
    profile = d.get("profile")
    diameter = d.get("diameter")
    if axis is None or diameter is None or not isinstance(profile, dict):
        return None
    origin = as_point(profile.get("axis_origin"))
    if origin is None:
        return None
    mid = (float(d.get("lo", 0.0)) + float(d.get("hi", 0.0))) / 2.0
    anchor, radial = _radial_anchor(add(origin, scale(axis, mid)), axis, float(diameter) / 2.0)
    text = (
        f"TURNED {DIAMETER_SIGN}{num(diameter)}",
        f"L{num(float(d.get('hi', 0.0)) - float(d.get('lo', 0.0)))}",
    )
    prose = (
        f"Turned step of {num(diameter)} diameter running from {num(d.get('lo'))} to "
        f"{num(d.get('hi'))} along {axis_phrase(d.get('axis'))}."
    )
    return Annotation("turned_steps", text, anchor, radial, diameter, DIM_DIAMETER, prose)


def _pad(d: dict[str, Any]) -> Annotation | None:
    try:
        lo = (float(d["x0"]), float(d["y0"]), float(d["z0"]))
        hi = (float(d["x1"]), float(d["y1"]), float(d["z1"]))
    except (KeyError, TypeError, ValueError):
        return None
    axis = axis_vector(d.get("axis"))
    if axis is None:
        return None
    idx = max(range(3), key=lambda i: abs(axis[i]))
    direction = 1 if float(d.get("direction", 1)) >= 0 else -1
    centre = [(lo[i] + hi[i]) / 2.0 for i in range(3)]
    centre[idx] = hi[idx] if direction > 0 else lo[idx]
    height = abs(hi[idx] - lo[idx])
    normal = scale(axis, float(direction))
    across = [abs(hi[i] - lo[i]) for i in range(3) if i != idx]
    facing = direction_phrase(normal)
    prose = (
        f"Raised pad standing {num(height)} proud"
        + (f" of the {facing} face" if facing else "")
        + f", {num(across[0])} by {num(across[1])} across."
    )
    return Annotation(
        "pads",
        (f"PAD H{num(height)}",),
        (centre[0], centre[1], centre[2]),
        normal,
        height,
        DIM_THICKNESS,
        prose,
    )


def _plate(d: dict[str, Any]) -> Annotation | None:
    axis = axis_vector(d.get("axis"))
    if axis is None:
        return None
    hi = d.get("hi")
    if hi is None:
        return None
    anchor = _span_anchor(str(d.get("axis")), d.get("body_key"), float(hi))
    if anchor is None:
        return None
    thickness = abs(float(hi) - float(d.get("lo", 0.0)))
    text = (f"PLATE T{num(thickness)}", f"{num(d.get('u'))}x{num(d.get('v'))}")
    prose = (
        f"Plate-like body {num(thickness)} thick along {axis_phrase(d.get('axis'))}, "
        f"measuring {num(d.get('u'))} by {num(d.get('v'))} in plane."
    )
    return Annotation("plates", text, anchor, axis, thickness, DIM_THICKNESS, prose)


def _step_level(d: dict[str, Any]) -> Annotation | None:
    z = d.get("z")
    xs, ys = d.get("x_span"), d.get("y_span")
    if z is None or not isinstance(xs, (list, tuple)) or not isinstance(ys, (list, tuple)):
        return None
    anchor = (
        (float(xs[0]) + float(xs[1])) / 2.0,
        (float(ys[0]) + float(ys[1])) / 2.0,
        float(z),
    )
    prose = (
        f"Planar face at Z {num(z)}, spanning X {num(xs[0])} to {num(xs[1])} and "
        f"Y {num(ys[0])} to {num(ys[1])}."
    )
    return Annotation("step_levels", (f"LEVEL Z{num(z)}",), anchor, (0.0, 0.0, 1.0), z, None, prose)


def _slot(d: dict[str, Any]) -> Annotation | None:
    width_axis = str(d.get("width_axis", "")).lower()
    long_axis = str(d.get("long_axis", "")).lower()
    depth_axis = {"x", "y", "z"} - {width_axis, long_axis}
    if len(depth_axis) != 1:
        return None
    depth_letter = next(iter(depth_axis))
    order = "xyz"
    point = [0.0, 0.0, 0.0]
    try:
        point[order.index(long_axis)] = (float(d["lo"]) + float(d["hi"])) / 2.0
        point[order.index(width_axis)] = float(d["w_center"])
        point[order.index(depth_letter)] = float(d["d_hi"])
    except (KeyError, TypeError, ValueError):
        return None
    normal = axis_vector(depth_letter)
    depth = float(d.get("d_hi", 0.0)) - float(d.get("d_lo", 0.0))
    text = (f"SLOT {num(d.get('width'))}x{num(d.get('length'))}", f"D{num(depth)}")
    prose = (
        f"Slot {num(d.get('width'))} wide and {num(d.get('length'))} long, {num(depth)} deep, "
        f"running along {axis_phrase(long_axis)} and opening towards "
        f"{direction_phrase(normal) or axis_phrase(depth_letter)}"
    )
    if d.get("end_radius") is not None:
        prose += f", ends radiused to {num(d.get('end_radius'))}"
    return Annotation(
        "slots",
        text,
        (point[0], point[1], point[2]),
        normal,
        d.get("width"),
        DIM_THICKNESS,
        prose + ".",
    )


def _oriented_slot(d: dict[str, Any]) -> Annotation | None:
    source = d.get("source")
    if not isinstance(source, dict):
        return None
    section = source.get("section")
    boundary = section.get("boundary") if isinstance(section, dict) else None
    frame = source.get("frame")
    if not isinstance(frame, dict):
        return None
    anchor = _frame_anchor(frame, source.get("run_interval"), boundary)
    if anchor is None:
        return None
    width = d.get("width")
    text = ("ORIENTED SLOT",) if width is None else (f"ORIENTED SLOT W{num(width)}",)
    run = source.get("run_interval")
    prose = "Slot running at an angle to the part's own axes"
    if width is not None:
        prose += f", {num(width)} wide"
    if isinstance(run, (list, tuple)) and len(run) == 2:
        prose += f", {num(float(run[1]) - float(run[0]))} long"
    return Annotation("oriented_slots", text, anchor, None, width, DIM_THICKNESS, prose + ".")


def _section_recess(d: dict[str, Any]) -> Annotation | None:
    geom = d.get("geometry")
    if not isinstance(geom, dict):
        return None
    frame = geom.get("frame")
    profile = geom.get("profile")
    if not isinstance(frame, dict):
        return None
    boundary = profile.get("boundary") if isinstance(profile, dict) else None
    anchor = _frame_anchor(frame, geom.get("run_interval"), boundary)
    if anchor is None:
        return None
    classification = d.get("classification")
    kind = shape = None
    if isinstance(classification, dict):
        kind = classification.get("feature_kind")
        shape = classification.get("section_shape")
    text = [str(kind or "RECESS").upper()]
    if shape:
        text.append(str(shape).upper())
    run = geom.get("run_interval")
    length = None
    if isinstance(run, (list, tuple)) and len(run) == 2:
        length = float(run[1]) - float(run[0])
        text.append(f"L{num(length)}")
    words = str(kind or "recess").replace("_", " ")
    prose = f"Swept {words}"
    if shape:
        prose += f" with a {str(shape).replace('_', ' ')} cross-section"
    if length is not None:
        prose += f", swept {num(length)} along its run"
    ends = geom.get("ends")
    if isinstance(ends, dict):
        conditions = [
            str(end.get("condition"))
            for end in (ends.get("low"), ends.get("high"))
            if isinstance(end, dict) and end.get("condition")
        ]
        if conditions:
            prose += f". Ends: {', '.join(conditions)}"
    # The run length is the one size a swept recess has, and it was already being
    # printed in the callout. Giving it a type as well makes the annotation
    # machine-readable rather than a picture of text with a leader.
    return Annotation(
        "section_recesses",
        tuple(text),
        anchor,
        None,
        length,
        DIM_LENGTH if length is not None else None,
        prose + ".",
    )


def _bolt_circle(d: dict[str, Any]) -> Annotation | None:
    centre = as_point(d.get("center"))
    if centre is None:
        return None
    holes = d.get("holes")
    count = len(holes) if isinstance(holes, (list, tuple)) else 0
    text = (f"{count}x ON {DIAMETER_SIGN}{num(d.get('diameter'))} BC",)
    prose = (
        f"Pattern of {count} holes equally spaced on a bolt circle of "
        f"{num(d.get('diameter'))} diameter."
    )
    return Annotation("hole_patterns", text, centre, None, d.get("diameter"), DIM_DIAMETER, prose)


ADAPTERS: dict[str, Callable[[dict[str, Any]], Annotation | None]] = {
    "holes": _hole,
    "bosses": _boss,
    "chamfers": _chamfer,
    "fillets": _fillet,
    "blends": _blend,
    "grooves": _groove,
    "flats": _flat,
    "through_steps": _through_step,
    "angled_steps": _angled_step,
    "paired_ramp_steps": _ramp_step,
    "circular_blind_steps": _blind_step,
    "turned_steps": _turned_step,
    "pads": _pad,
    "plates": _plate,
    "step_levels": _step_level,
    "slots": _slot,
    "oriented_slots": _oriented_slot,
    "section_recesses": _section_recess,
    "hole_patterns": _bolt_circle,
}

#: Keys searched, in order, when a family has no explicit adapter.
GENERIC_POINT_KEYS = ("location", "at", "center", "centre", "origin", "position")


def generic_annotation(family: str, d: dict[str, Any]) -> Annotation | None:
    """Best-effort annotation for a family with no explicit adapter."""
    anchor = None
    for key in GENERIC_POINT_KEYS:
        anchor = as_point(d.get(key))
        if anchor is not None:
            break
    if anchor is None:
        return None
    numeric = [
        (k, v) for k, v in d.items() if isinstance(v, (int, float)) and not isinstance(v, bool)
    ]
    scalars = [f"{k.upper()} {num(v)}" for k, v in numeric][:2]
    words = singular(family)
    text = (words.upper(), *scalars)
    prose = f"Recognised {words}"
    if numeric:
        prose += " with " + ", ".join(f"{k.replace('_', ' ')} {num(v)}" for k, v in numeric[:4])
    return Annotation(family, text, anchor, None, explanation=prose + ".")


# --------------------------------------------------------------------------
# Drawing callouts
# --------------------------------------------------------------------------


def _hole_callout(d: dict[str, Any]) -> str:
    parts = [f"{DIAMETER_CALLOUT}{num(d.get('diameter'))}"]
    if d.get("bottom") == "through":
        parts.append("THRU")
    elif d.get("depth") is not None:
        parts.append(f"{DEPTH}{num(d.get('depth'))}")
    if d.get("cbore") or d.get("spotface"):
        parts.append(COUNTERBORE)
    if d.get("csink"):
        parts.append(COUNTERSINK)
    return " ".join(parts)


#: How each family reads as a drawing callout: the value, then the feature word.
#: Written separately from the terse STEP label because a drawing leads with the
#: size and says what the feature is quietly, where a STEP annotation name has to
#: identify the family first.
_CALLOUTS: dict[str, Callable[[dict[str, Any]], tuple[str, str]]] = {
    "holes": lambda d: (_hole_callout(d), "hole"),
    "bosses": lambda d: (
        # A boss stands proud, so it takes no depth symbol.
        f"{DIAMETER_CALLOUT}{num(d.get('diameter'))} {TIMES}{num(d.get('height'))}",
        "boss",
    ),
    "chamfers": lambda d: (
        f"{num(d.get('leg1'))}{TIMES}{num(d.get('angle'), 1)}{DEGREE}",
        "chamfer",
    ),
    "fillets": lambda d: (f"R{num(d.get('radius'))}", "fillet"),
    "blends": lambda d: (f"R{num(d.get('radius'))}", str(d.get("side") or "blend")),
    "grooves": lambda d: (
        f"{DIAMETER_CALLOUT}{num(d.get('diameter'))} {TIMES}{num(d.get('width'))}",
        "groove",
    ),
    "turned_steps": lambda d: (f"{DIAMETER_CALLOUT}{num(d.get('diameter'))}", "turned step"),
    "flats": lambda d: (f"{num(d.get('across'))} across", "flat"),
    "step_levels": lambda d: (f"Z{num(d.get('z'))}", "level"),
    "slots": lambda d: (f"{num(d.get('width'))}{TIMES}{num(d.get('length'))}", "slot"),
    "plates": lambda d: (
        f"{num(abs(float(d.get('hi', 0)) - float(d.get('lo', 0))))} thick",
        "plate",
    ),
    "angled_steps": lambda d: (f"{num(d.get('angle'), 1)}{DEGREE}", "angled step"),
    "paired_ramp_steps": lambda d: (f"{num(d.get('angle'), 1)}{DEGREE}", "ramp"),
    "circular_blind_steps": lambda d: (f"R{num(d.get('radius'))}", "blind step"),
    "through_steps": lambda d: (f"L{num(d.get('length'))}", "through step"),
    "hole_patterns": lambda d: (
        f"{len(d.get('holes') or ())}{TIMES} {DIAMETER_CALLOUT}{num(d.get('diameter'))}",
        "bolt circle",
    ),
    "polygonal_bosses": lambda d: (
        f"{num(d['across_flats'])} A/F {TIMES}{d['side_count']}",
        "polygonal boss",
    ),
    "polygonal_stock": lambda d: (
        f"{num(d['across_flats'])} A/F {TIMES}{d['side_count']}",
        "polygonal stock",
    ),
    "double_d_bores": lambda d: (
        f"{DIAMETER_CALLOUT}{num(d['major_diameter'])} {TIMES}{num(d['across_flats'])}",
        "double-D bore",
    ),
    "countersinks": lambda d: (
        f"{COUNTERSINK}{DIAMETER_CALLOUT}{num(d['diameter'])}",
        "countersink",
    ),
    "oriented_slots": lambda d: (f"{num(d['width'])} wide", "oriented slot"),
    "section_recesses": lambda d: (
        f"{num(d['geometry']['run_interval'][1] - d['geometry']['run_interval'][0])} long",
        str(d["classification"]["feature_kind"]).replace("_", " "),
    ),
}


def _generic_callout(record: dict[str, Any], family: str) -> tuple[str, ...]:
    """A callout for a family with no rule: the largest scalar it carries.

    Better than echoing the terse label, which would repeat the family name once
    as a value and once as the descriptor.
    """
    numbers = [
        (k, v) for k, v in record.items() if isinstance(v, (int, float)) and not isinstance(v, bool)
    ]
    word = singular(family)
    if not numbers:
        return (word, "")
    key, value = max(numbers, key=lambda kv: abs(float(kv[1])))
    return (f"{num(value)} {key.replace('_', ' ')}", word)


def callout_for(family: str, record: dict[str, Any], fallback: tuple[str, ...]) -> tuple[str, ...]:
    """A drawing-style callout for one record.

    The notation is per family and written by hand, because how a feature is
    written -- a hole as diameter then depth, a chamfer as leg by angle -- is
    ASME Y14.5 convention rather than anything the geometry states. The values
    in it all come from the recognised record.
    """
    make = _CALLOUTS.get(family)
    if make is not None:
        try:
            return make(record)
        except (TypeError, ValueError, KeyError):
            pass
    return _generic_callout(record, family)


def annotate(result: Any, families: set[str]) -> tuple[list[Annotation], dict[str, int]]:
    """Adapt every record in ``result`` belonging to ``families``.

    Returns the annotations and a per-family count of records that carried no
    point an annotation could be anchored to.
    """
    annotations: list[Annotation] = []
    unplaced: dict[str, int] = {}
    for family in sorted(families):
        records = getattr(result, family, None)
        if not records:
            continue
        adapter = ADAPTERS.get(family)
        for record in records:
            to_dict = getattr(record, "to_dict", None)
            if to_dict is None:
                unplaced[family] = unplaced.get(family, 0) + 1
                continue
            d = to_dict()
            made = adapter(d) if adapter else generic_annotation(family, d)
            if made is None:
                unplaced[family] = unplaced.get(family, 0) + 1
            else:
                annotations.append(replace(made, callout=callout_for(family, d, made.text)))
    return annotations, unplaced


def available_families(result: Any) -> Iterator[str]:
    """Family names on ``result`` that hold at least one record."""
    for name in (*FEATURE_FAMILIES, *SUMMARY_FAMILIES):
        if getattr(result, name, None):
            yield name
