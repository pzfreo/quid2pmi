"""The record adapters: label wording, anchors and semantic values."""

import math

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


def test_hole_callout_reads_as_a_drawing_writes_it():
    """The STEP label leads with the family; a drawing leads with the size."""
    from quid2pmi.adapters import callout_for

    record = {
        "axis": [0, 0, 1],
        "location": [0, 0, 0],
        "diameter": 8.0,
        "depth": 12.0,
        "bottom": "flat",
    }
    assert callout_for("holes", record, ("HOLE",)) == ("⌀8 ↧12", "hole")

    through = dict(record, bottom="through")
    assert callout_for("holes", through, ("HOLE",)) == ("⌀8 THRU", "hole")


def test_entry_treatments_add_their_symbols():
    from quid2pmi.adapters import callout_for

    record = {"diameter": 8.0, "depth": 12.0, "bottom": "flat", "cbore": {"diameter": 14.0}}
    assert callout_for("holes", record, ("HOLE",))[0].endswith("⌴")


def test_a_boss_takes_no_depth_symbol():
    """A boss stands proud; the depth symbol means into the material."""
    from quid2pmi.adapters import DEPTH, callout_for

    value, word = callout_for("bosses", {"diameter": 130.0, "height": 3.0}, ("BOSS",))
    assert DEPTH not in value
    assert value == "⌀130 ×3" and word == "boss"


def test_polygonal_boss_states_its_size_not_its_name():
    """With no rule it fell through to a fallback that echoed the family name."""
    from quid2pmi.adapters import callout_for

    record = {"side_count": 6, "across_flats": 100.0, "base": 0.0, "top": 50.0}
    assert callout_for("polygonal_bosses", record, ("POLYGONAL BOSS",)) == (
        "100 A/F ×6",
        "polygonal boss",
    )


def test_a_family_with_no_rule_still_gets_a_size():
    from quid2pmi.adapters import callout_for

    value, word = callout_for("widgets", {"span": 12.5, "count": 2}, ("WIDGET",))
    assert value == "12.5 span" and word == "widget"


def test_callouts_never_repeat_the_family_as_its_own_value():
    from quid2pmi.adapters import FEATURE_FAMILIES, callout_for

    for family in FEATURE_FAMILIES:
        value, word = callout_for(family, {}, (family.upper(),))
        assert value != word, family


def test_every_annotation_gets_a_callout(sample_step, tmp_path):
    from quid2pmi import convert

    report = convert(sample_step, tmp_path / "o.step", quiet=True)
    assert report.annotations
    for annotation in report.annotations:
        assert annotation.callout, annotation.family
        assert annotation.callout[0]


def test_a_section_recess_carries_its_run_length():
    """The length was in the callout but not in the annotation, so a recess
    reached the file as a picture of text with a leader and no readable value."""
    from quid2pmi.model import DIM_LENGTH

    result = FakeResult(
        section_recesses=[
            Rec(
                {
                    "geometry": {
                        "frame": {
                            "origin": [0.0, 0.0, 0.0],
                            "run": [0.0, 0.0, 1.0],
                            "u": [1.0, 0.0, 0.0],
                            "v": [0.0, 1.0, 0.0],
                        },
                        "run_interval": [2.0, 14.0],
                    },
                    "classification": {"feature_kind": "channel", "section_shape": "rectangular"},
                }
            )
        ]
    )
    (annotation,), _ = annotate(result, {"section_recesses"})
    assert annotation.value == 12.0
    assert annotation.dimension == DIM_LENGTH


def _hex_pocket(across_flats=4.3, depth=1.9):
    """A regular hexagonal profile of the given size across flats."""
    radius = across_flats / math.sqrt(3.0)
    boundary = [
        {
            "point": [
                radius * math.cos(math.radians(30.0 + 60.0 * corner)),
                radius * math.sin(math.radians(30.0 + 60.0 * corner)),
            ],
            "bulge": 0.0,
        }
        for corner in range(6)
    ]
    return {
        "geometry": {
            "run_interval": [-depth, 0.0],
            "profile": {"closure": "closed", "boundary": boundary},
        },
        "classification": {"feature_kind": "pocket", "section_shape": "hexagonal"},
    }


def test_a_hex_pocket_is_called_out_across_its_flats():
    """It read as "1.9 long pocket": the same callout a round bore would get,
    with the sweep length standing in for the size of the socket."""
    from quid2pmi.adapters import callout_for

    assert callout_for("section_recesses", _hex_pocket(), ("POCKET HEXAGONAL",)) == (
        "4.3 A/F ↧1.9",
        "hexagonal pocket",
    )


def test_a_channel_keeps_its_run_as_a_length():
    """A channel runs along the part, so its run is not a depth."""
    from quid2pmi.adapters import callout_for

    record = {
        "geometry": {
            "run_interval": [2.0, 14.0],
            "profile": {
                "closure": "open",
                "boundary": [{"point": [0.4, -3.7], "bulge": -0.28}, {"point": [0.4, 3.7]}],
            },
        },
        "classification": {"feature_kind": "channel", "section_shape": "circular"},
    }
    assert callout_for("section_recesses", record, ("CHANNEL",)) == ("12 long", "circular channel")


def test_an_arc_sided_profile_has_no_size_across_flats():
    from quid2pmi.adapters import _across_flats

    boundary = [{"point": [1.0, 0.0], "bulge": 0.5}, {"point": [-1.0, 0.0], "bulge": 0.5}]
    assert _across_flats({"closure": "closed", "boundary": boundary}) is None
