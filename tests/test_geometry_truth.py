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
from quid2pmi.model import DIM_ANGLE
from quid2pmi.sightlines import SightTester


@pytest.fixture(scope="module")
def spool():
    """A turned part with 31 holes, 16 chamfers, bosses, fillets and step levels."""
    from tests.conftest import corpus_part

    return corpus_part("cadgenbench", "flanged_spool_132.step")


@pytest.fixture(scope="module")
def converted(spool, tmp_path_factory):
    output = tmp_path_factory.mktemp("truth") / "spool.step"
    return convert(spool, output, quiet=True), import_step_geometry(str(spool))


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
