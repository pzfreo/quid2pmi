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


def _boxes(placed):
    """Each label's footprint in its own plane's 2D coordinates."""
    out = []
    for label in placed:
        u = sum(label.origin[i] * label.x_dir[i] for i in range(3))
        v = sum(label.origin[i] * label.y_dir[i] for i in range(3))
        width = max(len(line) for line in label.annotation.text) * 0.62 * label.height
        tall = len(label.annotation.text) * 1.45 * label.height
        out.append((u, v - tall, u + width, v))
    return out


def _overlap(a, b):
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def test_coincident_labels_do_not_overlap():
    anchor = (0.0, 0.0, 20.0)
    normal = (0.0, 0.0, 1.0)
    placed = layout([_annotation(anchor, normal) for _ in range(4)], BOX)
    assert len({p.origin for p in placed}) == 4
    boxes = _boxes(placed)
    assert not any(
        _overlap(boxes[i], boxes[j]) for i in range(len(boxes)) for j in range(i + 1, len(boxes))
    )


def test_crowded_face_stays_near_the_part():
    """The old layout pushed labels up one line at a time with no bound."""
    normal = (0.0, 0.0, 1.0)
    crowded = [_annotation((0.0, 0.0, 20.0), normal, ("A LONGISH LABEL",)) for _ in range(40)]
    placed = layout(crowded, BOX)
    reach = max(max(abs(p.origin[i] - BOX.centre[i]) for i in range(3)) for p in placed)
    assert reach < 4 * BOX.diagonal


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
