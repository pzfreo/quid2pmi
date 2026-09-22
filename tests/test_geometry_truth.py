"""The claims an annotation makes about geometry, checked against the geometry.

Every assertion here corresponds to a defect found by looking at the output in a
viewer: leaders that pointed into space, leaders that tunnelled through the part,
labels that ran away from it, and an angle displayed 57x too large.
"""

from __future__ import annotations

import math
import re

import pytest
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.gp import gp_Pnt
from quiddity import import_step_geometry

from quid2pmi import convert
from quid2pmi.layout import BoundingBox, layout
from quid2pmi.model import DIM_ANGLE, DIM_THICKNESS
from quid2pmi.sightlines import SightTester
from tests.test_convert import read_pmi


@pytest.fixture(scope="module")
def spool():
    """A turned part with 31 holes, 16 chamfers, bosses, fillets and step levels."""
    from tests.conftest import corpus_part

    return corpus_part("cadgenbench", "flanged_spool_132.step")


@pytest.fixture(scope="module")
def converted(spool, tmp_path_factory):
    output = tmp_path_factory.mktemp("truth") / "spool.step"
    return convert(spool, output, quiet=True), import_step_geometry(str(spool))


@pytest.fixture(scope="module")
def pocketed(sample_step, tmp_path_factory):
    """A part with swept recesses: the spool is turned and has none."""
    output = tmp_path_factory.mktemp("truth") / "pockets.step"
    return convert(sample_step, output, quiet=True), import_step_geometry(str(sample_step))


def _distance_to(part, point) -> float:
    vertex = BRepBuilderAPI_MakeVertex(gp_Pnt(*point)).Vertex()
    measure = BRepExtrema_DistShapeShape(vertex, part.wrapped)
    measure.Perform()
    return measure.Value()


def test_every_leader_tip_lies_on_the_part(converted):
    """Record-derived anchors put 39 of 60 tips off the part; a hole's location
    is a point on its axis, one radius inside the bore."""
    report, part = converted
    worst = max(_distance_to(part, a.anchor) for a in report.annotations)
    assert worst < 1e-6, worst


def test_no_leader_tunnels_through_the_solid(converted):
    report, part = converted
    box = _box(part)
    tester = SightTester(part.wrapped, box.diagonal * 4.0)
    for label in layout(list(report.annotations), box):
        assert tester.is_clear(label.annotation.anchor, label.normal), label.annotation


def test_report_agrees_that_nothing_is_obstructed(converted):
    report, _ = converted
    assert report.obstructed == 0


def _box(part) -> BoundingBox:
    bb = part.bounding_box()
    return BoundingBox((bb.min.X, bb.min.Y, bb.min.Z), (bb.max.X, bb.max.Y, bb.max.Z))


def test_labels_stay_within_reach_of_the_part(converted):
    """Unbounded collision resolution sent labels 6.4x the part's diagonal away."""
    report, part = converted
    box = _box(part)
    placed = layout(list(report.annotations), box)
    longest = max(math.dist(label.leader[0], label.leader[-1]) for label in placed)
    assert longest < 2.0 * box.diagonal, longest


def test_every_feature_is_attached_to_its_own_faces(converted):
    report, _ = converted
    assert report.attached == report.total


def test_every_feature_has_its_faces_coloured(converted):
    report, _ = converted
    assert report.coloured > 0
    assert all(a.faces for a in report.annotations)


def test_angles_are_written_in_radians(angular_step, tmp_path):
    """XCAF stores angles in radians; degrees display 57x too large, so a 45
    degree chamfer appeared as 2578.31 degrees.

    The assertion is against the file rather than a read-back: OCCT is
    asymmetric here, taking radians on SetValue but returning degrees from
    GetValue after a read. The file is what a viewer renders.
    """
    report = convert(angular_step, tmp_path / "ang.step", families={"angled_steps"}, quiet=True)
    angular = [a for a in report.annotations if a.dimension == DIM_ANGLE]
    assert angular, "fixture no longer exercises an angular dimension"

    written = report.output.read_text(errors="ignore")
    assert "PLANE_ANGLE_UNIT() SI_UNIT($,.RADIAN.)" in written
    measures = [
        float(m) for m in re.findall(r"POSITIVE_PLANE_ANGLE_MEASURE\(([0-9.eE+-]+)\)", written)
    ]
    assert measures
    for annotation in angular:
        radians = math.radians(float(annotation.value))
        assert any(abs(m - radians) < 1e-6 for m in measures), (annotation.value, measures)
        # The degree value must not appear where the radian one belongs.
        assert not any(abs(m - float(annotation.value)) < 1e-9 for m in measures)


def test_chamfers_carry_a_linear_size_not_an_angle(converted):
    """Angular sizes render as swept arcs; a part with 16 chamfers is unreadable."""
    report, _ = converted
    chamfers = [a for a in report.annotations if a.family == "chamfers"]
    assert chamfers
    assert all(a.dimension != DIM_ANGLE for a in chamfers)


def test_labels_survive_into_the_step_file_whole(converted):
    """OCCT drops the semantic name's first token, so the family leads it."""
    report, _ = converted
    written = report.output.read_text(errors="ignore")
    for annotation in report.annotations:
        head = annotation.label.encode("ascii", "ignore").decode().split()[0]
        assert f"SHAPE_ASPECT('{head}" in written, annotation.label


def test_a_thickness_like_size_is_written_as_one(converted):
    """Size_Thickness is what the NIST PMI reference files use for these, and it
    is what the standard means. It was avoided for a while because
    DIMENSIONAL_SIZE(...,'thickness') segfaults CAD Assistant's importer -- their
    bug, not the standard's, and no longer ours to work around."""
    report, _ = converted
    assert "'thickness'" in report.output.read_text(errors="ignore")


def test_the_drawn_pmi_uses_the_entities_the_nist_files_use(spool, tmp_path):
    """The NIST CTC reference files carry drawn PMI as tessellated annotation
    occurrences over tessellated curve sets. So does ours."""
    report = convert(spool, tmp_path / "drawn.step", quiet=True)
    text = report.output.read_text(errors="ignore")
    for entity in (
        "TESSELLATED_ANNOTATION_OCCURRENCE",
        "TESSELLATED_CURVE_SET",
        "TESSELLATED_GEOMETRIC_SET",
        "DRAUGHTING_MODEL",
    ):
        assert entity in text, entity


def test_thickness_families_still_carry_their_value(converted):
    report, _ = converted
    sized = [a for a in report.annotations if a.dimension == DIM_THICKNESS]
    assert sized, "fixture no longer exercises a thickness-like size"
    written = {name: (kind, value) for kind, value, _, name in read_pmi(report.output)}
    for annotation in sized:
        kind, value = written[annotation.label]
        assert kind.startswith("Size")
        assert value == pytest.approx(float(annotation.value), rel=1e-6)


def test_a_turned_step_supersedes_the_boss_on_the_same_face(spool, tmp_path):
    """A turned cylinder is also, technically, a boss. Labelling it both ways put
    two callouts on one face that did not even agree: the boss measured its
    height from a different place than the turned step measured its length."""
    report = convert(spool, tmp_path / "turned.step", quiet=True)
    owner: dict[object, set[str]] = {}
    for annotation in report.annotations:
        for face in annotation.faces:
            owner.setdefault(face, set()).add(annotation.family)
    assert report.superseded > 0, "the fixture no longer exercises the overlap"
    assert not [f for f, families in owner.items() if {"bosses", "turned_steps"} <= families]


def test_a_leader_arrives_along_the_surface_normal(converted):
    """Into a bore wall, the difference between radial and sideways.

    Only where the surface faces the way the label is read from: a hole's own
    normal points into the bore, and standing off along it would send the leader
    back out through the material.
    """
    from quid2pmi.geometry import normalise, sub
    from quid2pmi.layout import _stands_off, layout

    report, part = converted
    placed = [p for p in layout(list(report.annotations), _box(part)) if _stands_off(p.annotation)]
    assert placed, "no annotation stands its leader off the surface"
    for label in placed:
        last = normalise(sub(label.leader[-2], label.leader[-1]))
        assert last is not None
        along = sum(last[i] * label.annotation.surface[i] for i in range(3))
        assert along == pytest.approx(1.0, abs=1e-6), label.annotation.label


def test_a_hole_points_at_its_rim_not_down_the_bore(converted):
    """The evidence view anchors halfway down a bore, where the leader vanishes
    into the opening. A drawing points at the rim."""
    report, _ = converted
    holes = [a for a in report.annotations if a.family == "holes"]
    assert holes, "the fixture no longer has holes"
    at_mouth = [
        a
        for a in holes
        if abs(sum((a.anchor[i] - a.detail["mouth"][i]) * a.detail["axis"][i] for i in range(3)))
        < 1e-6
    ]
    assert len(at_mouth) > len(holes) // 2, f"only {len(at_mouth)} of {len(holes)} reached a rim"


def test_a_pocket_points_at_its_mouth_not_a_wall_inside_it(pocketed):
    """Recognition proves a recess's walls, so the leader landed mid-depth on one
    of them: on a printed frame's hex pockets it came out of a wall 0.95 under the
    surface, where a drawing points at the rim of the socket."""
    report, part = pocketed
    recesses = [
        a for a in report.annotations if a.family == "section_recesses" and a.detail.get("mouth")
    ]
    assert recesses, "the fixture no longer has a recess that opens at one end"
    at_mouth = [
        a
        for a in recesses
        if abs(sum((a.anchor[i] - a.detail["mouth"][i]) * a.detail["axis"][i] for i in range(3)))
        < 1e-6
    ]
    reached = f"only {len(at_mouth)} of {len(recesses)} reached a mouth"
    assert len(at_mouth) > len(recesses) // 2, reached
    # The slide is allowed to land on a rim, an edge between two faces, so judge
    # it by the tolerance convert itself accepts the moved point within.
    tolerance = _box(part).diagonal * 1e-6
    for annotation in recesses:
        assert _distance_to(part, annotation.anchor) < tolerance, annotation.label
