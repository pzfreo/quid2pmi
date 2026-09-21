"""Label placement: grouping onto bounding box faces, clearance and collisions."""

from quid2pmi.layout import BoundingBox, layout
from quid2pmi.model import Annotation

BOX = BoundingBox((-10.0, -10.0, 0.0), (10.0, 10.0, 20.0))


def _annotation(anchor, normal=None, text=("LABEL",)):
    return Annotation("holes", text, anchor, normal)


def test_label_is_placed_clear_of_the_bounding_box():
    (placed,) = layout([_annotation((0.0, 0.0, 20.0), (0.0, 0.0, 1.0))], BOX)
    assert placed.origin[2] > BOX.max[2]


def test_label_plane_faces_the_direction_it_is_read_from():
    (placed,) = layout([_annotation((10.0, 0.0, 10.0), (1.0, 0.0, 0.0))], BOX)
    normal = tuple(
        round(v, 9)
        for v in (
            placed.x_dir[1] * placed.y_dir[2] - placed.x_dir[2] * placed.y_dir[1],
            placed.x_dir[2] * placed.y_dir[0] - placed.x_dir[0] * placed.y_dir[2],
            placed.x_dir[0] * placed.y_dir[1] - placed.x_dir[1] * placed.y_dir[0],
        )
    )
    assert normal == (1.0, 0.0, 0.0)


def test_text_is_upright_for_a_horizontally_read_label():
    (placed,) = layout([_annotation((10.0, 0.0, 10.0), (1.0, 0.0, 0.0))], BOX)
    assert placed.y_dir == (0.0, 0.0, 1.0)


def test_labels_without_a_normal_are_pushed_away_from_the_part_centre():
    (placed,) = layout([_annotation((0.0, 0.0, 20.0))], BOX)
    assert placed.origin[2] > BOX.max[2]


def test_coincident_labels_do_not_overlap():
    anchor = (0.0, 0.0, 20.0)
    normal = (0.0, 0.0, 1.0)
    placed = layout([_annotation(anchor, normal) for _ in range(4)], BOX)
    heights = sorted(p.origin[1] for p in placed)
    assert len(set(heights)) == 4
    gaps = [b - a for a, b in zip(heights, heights[1:], strict=False)]
    assert all(gap >= placed[0].height for gap in gaps)


def test_leader_ends_at_the_feature():
    annotation = _annotation((3.0, 4.0, 20.0), (0.0, 0.0, 1.0))
    (placed,) = layout([annotation], BOX)
    assert placed.leader[-1] == annotation.anchor
    assert len(placed.leader) >= 2


def test_explicit_text_height_and_standoff_are_honoured():
    (placed,) = layout(
        [_annotation((0.0, 0.0, 20.0), (0.0, 0.0, 1.0))], BOX, text_height=2.0, standoff=5.0
    )
    assert placed.height == 2.0
    # A label read along +Z lies in a plane offset from the box's top face; its rows
    # are stacked in Y, so the standoff appears whole in Z.
    assert round(placed.origin[2] - BOX.max[2], 6) == 5.0


def test_empty_input_places_nothing():
    assert layout([], BOX) == []
