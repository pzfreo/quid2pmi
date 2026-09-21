"""The record adapters: label wording, anchors and semantic values."""

from quid2pmi.adapters import DIAMETER_SIGN, annotate, generic_annotation, num
from quid2pmi.model import DIM_DIAMETER, DIM_RADIUS


class FakeResult:
    def __init__(self, **families):
        for name, records in families.items():
            setattr(self, name, records)


class Rec:
    def __init__(self, d):
        self._d = d

    def to_dict(self):
        return self._d


def test_num_strips_trailing_zeros():
    assert num(3.10000) == "3.1"
    assert num(12.0) == "12"
    assert num(3.15662) == "3.157"


def test_hole_label_and_semantics():
    result = FakeResult(
        holes=[
            Rec(
                {
                    "axis": [0, 0, 1],
                    "location": [1, 2, 3],
                    "diameter": 6.0,
                    "depth": 10.0,
                    "bottom": "flat",
                }
            )
        ]
    )
    (annotation,), unplaced = annotate(result, {"holes"})
    assert unplaced == {}
    assert annotation.label == f"HOLE {DIAMETER_SIGN}6 10 DEEP"
    assert annotation.anchor == (1.0, 2.0, 3.0)
    assert annotation.value == 6.0
    assert annotation.dimension == DIM_DIAMETER
    # The axis points into the material, so the label reads from the other side.
    assert annotation.normal == (0.0, 0.0, -1.0)


def test_through_hole_says_thru():
    result = FakeResult(
        holes=[
            Rec(
                {
                    "axis": [0, 0, 1],
                    "location": [0, 0, 0],
                    "diameter": 4.0,
                    "depth": 9.0,
                    "bottom": "through",
                }
            )
        ]
    )
    (annotation,), _ = annotate(result, {"holes"})
    assert annotation.label.endswith("THRU")


def test_slot_anchor_is_reconstructed_from_axis_letters():
    result = FakeResult(
        slots=[
            Rec(
                {
                    "width_axis": "y",
                    "long_axis": "z",
                    "width": 4.0,
                    "length": 20.0,
                    "w_center": 7.0,
                    "lo": 5.0,
                    "hi": 25.0,
                    "d_lo": 0.0,
                    "d_hi": 13.0,
                }
            )
        ]
    )
    (annotation,), _ = annotate(result, {"slots"})
    # x is the remaining depth axis, so the anchor sits at its open end.
    assert annotation.anchor == (13.0, 7.0, 15.0)
    assert annotation.normal == (1.0, 0.0, 0.0)


def test_groove_anchor_moves_out_to_the_groove_diameter():
    result = FakeResult(
        grooves=[Rec({"axis": "z", "width": 5.0, "diameter": 40.0, "at": [0, 0, 10]})]
    )
    (annotation,), _ = annotate(result, {"grooves"})
    radius = sum(v * v for v in annotation.anchor[:2]) ** 0.5
    assert radius == 20.0
    assert annotation.anchor[2] == 10.0


def test_pad_anchor_sits_on_the_raised_face():
    result = FakeResult(
        pads=[
            Rec(
                {
                    "x0": 0,
                    "x1": 4,
                    "y0": 10,
                    "y1": 16,
                    "z0": 0,
                    "z1": 20,
                    "axis": "y",
                    "direction": 1,
                }
            )
        ]
    )
    (annotation,), _ = annotate(result, {"pads"})
    assert annotation.anchor == (2.0, 16.0, 10.0)
    assert annotation.normal == (0.0, 1.0, 0.0)
    assert annotation.value == 6.0


def test_blend_uses_its_path_circle():
    result = FakeResult(
        blends=[
            Rec(
                {
                    "radius": 1.0,
                    "side": "convex",
                    "path": {"center": [0, 0, 1], "normal": [0, 0, 1], "radius": 48.0},
                }
            )
        ]
    )
    (annotation,), _ = annotate(result, {"blends"})
    assert annotation.dimension == DIM_RADIUS
    assert round(sum(v * v for v in annotation.anchor[:2]) ** 0.5, 6) == 48.0


def test_records_with_no_anchor_are_reported_not_dropped_silently():
    result = FakeResult(holes=[Rec({"diameter": 6.0})])
    annotations, unplaced = annotate(result, {"holes"})
    assert annotations == []
    assert unplaced == {"holes": 1}


def test_generic_fallback_labels_an_unknown_family():
    annotation = generic_annotation("widgets", {"location": [1, 2, 3], "size": 4.0})
    assert annotation is not None
    assert annotation.anchor == (1.0, 2.0, 3.0)
    assert "WIDGET" in annotation.label


def test_singular_handles_doubled_sibilants():
    """Stripping a trailing 's' turns 'bosses' into 'bosse'."""
    from quid2pmi.adapters import singular

    assert singular("polygonal_bosses") == "polygonal boss"
    assert singular("section_recesses") == "section recess"
    assert singular("holes") == "hole"
    assert singular("turned_steps") == "turned step"


def test_blend_on_a_straight_edge_is_labelled():
    """A blend's path is a circle or a straight edge; only handling the circle
    left every straight-edge blend with a bare family name and no radius."""
    result = FakeResult(
        blends=[
            Rec(
                {
                    "radius": 10.0,
                    "side": "concave",
                    "path": {"at": [-323.152, -115.0, -60.0], "direction": [1.0, 0.0, 0.0]},
                }
            )
        ]
    )
    (annotation,), unplaced = annotate(result, {"blends"})
    assert unplaced == {}
    assert annotation.label.startswith("BLEND R10")
    assert annotation.anchor == (-323.152, -115.0, -60.0)
    assert annotation.value == 10.0
    assert annotation.dimension == DIM_RADIUS
    assert "radius 10" in annotation.explanation


def test_blend_on_a_circle_still_anchors_on_the_circle():
    result = FakeResult(
        blends=[
            Rec(
                {
                    "radius": 1.0,
                    "side": "convex",
                    "path": {"center": [0, 0, 1], "normal": [0, 0, 1], "radius": 48.0},
                }
            )
        ]
    )
    (annotation,), _ = annotate(result, {"blends"})
    assert round(sum(v * v for v in annotation.anchor[:2]) ** 0.5, 6) == 48.0
    assert "circular path" in annotation.explanation
