"""End-to-end conversion, and the PMI the written file actually carries."""

import importlib
import json

import pytest
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDF import TDF_LabelSequence
from OCP.TDocStd import TDocStd_Document
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopExp import TopExp_Explorer
from OCP.XCAFApp import XCAFApp_Application
from OCP.XCAFDoc import XCAFDoc_Dimension, XCAFDoc_DocumentTool

from quid2pmi import convert, resolve_families
from quid2pmi.adapters import FEATURE_FAMILIES, SUMMARY_FAMILIES


def read_pmi(path):
    """Every dimension in ``path``, as (type name, value, presentation edge count, name)."""
    fmt = TCollection_ExtendedString("MDTV-XCAF")
    doc = TDocStd_Document(fmt)
    XCAFApp_Application.GetApplication_s().NewDocument(fmt, doc)
    reader = STEPCAFControl_Reader()
    reader.SetGDTMode(True)
    reader.ReadFile(str(path))
    reader.Transfer(doc)
    tool = XCAFDoc_DocumentTool.DimTolTool_s(doc.Main())
    labels = TDF_LabelSequence()
    tool.GetDimensionLabels(labels)
    out = []
    for i in range(1, labels.Length() + 1):
        obj = XCAFDoc_Dimension.Set_s(labels.Value(i)).GetObject()
        presentation = obj.GetPresentation()
        edges = 0
        if not presentation.IsNull():
            explorer = TopExp_Explorer(presentation, TopAbs_EDGE)
            while explorer.More():
                edges += 1
                explorer.Next()
        name = obj.GetPresentationName()
        out.append(
            (
                str(obj.GetType()).split(".")[-1].removeprefix("XCAFDimTolObjects_DimensionType_"),
                obj.GetValue(),
                edges,
                name.ToCString() if name else "",
            )
        )
    return out


@pytest.fixture(scope="module")
def converted(sample_step, tmp_path_factory):
    output = tmp_path_factory.mktemp("pmi") / "sample-pmi.step"
    return convert(sample_step, output)


def test_conversion_writes_a_step_file(converted):
    assert converted.output.is_file()
    assert converted.output.read_text(errors="ignore").startswith("ISO-10303-21;")


def test_output_is_ap242(converted):
    header = converted.output.read_text(errors="ignore")[:600]
    assert "AP242" in header


def test_report_counts_match_the_annotations(converted):
    assert converted.total == len(converted.annotations)
    assert sum(converted.counts.values()) == converted.total
    assert converted.total > 0


def test_every_annotation_reaches_the_file_as_pmi(converted):
    written = read_pmi(converted.output)
    assert len(written) == converted.total


def test_every_annotation_carries_drawable_geometry(converted):
    assert all(edges > 0 for _, _, edges, _ in read_pmi(converted.output))


def test_labels_survive_the_round_trip(converted):
    names = {name for _, _, _, name in read_pmi(converted.output)}
    assert names == {a.label for a in converted.annotations}


def test_dimension_types_are_single_shape_safe(converted):
    """AP242 location dimensions need a second shape reference this tool never has."""
    for kind, _, _, _ in read_pmi(converted.output):
        assert not kind.startswith("Location"), kind
        assert kind != "CommonLabel"


def test_semantic_values_are_written_for_sized_features(converted):
    written = {name: (kind, value) for kind, value, _, name in read_pmi(converted.output)}
    for annotation in converted.annotations:
        if annotation.dimension and annotation.value is not None:
            kind, value = written[annotation.label]
            assert kind.startswith("Size")
            assert value == pytest.approx(annotation.value, rel=1e-6)


def test_anchors_lie_within_the_part(converted, sample_step):
    from quiddity import import_step_geometry

    box = import_step_geometry(str(sample_step)).bounding_box()
    lo = (box.min.X, box.min.Y, box.min.Z)
    hi = (box.max.X, box.max.Y, box.max.Z)
    slack = max(hi[i] - lo[i] for i in range(3)) * 0.02
    for annotation in converted.annotations:
        for i in range(3):
            assert lo[i] - slack <= annotation.anchor[i] <= hi[i] + slack, annotation


def test_json_report_is_serialisable(converted):
    payload = json.loads(json.dumps(converted.to_dict()))
    assert payload["annotations"] == converted.total
    assert len(payload["labels"]) == converted.total


def test_narrowing_families_narrows_the_output(sample_step, tmp_path):
    only_holes = convert(sample_step, tmp_path / "holes.step", families={"holes"})
    assert set(only_holes.counts) == {"holes"}
    assert only_holes.total < convert(sample_step, tmp_path / "all.step").total


def test_no_leaders_still_writes_every_label(sample_step, tmp_path):
    report = convert(sample_step, tmp_path / "plain.step", leaders=False)
    assert len(read_pmi(report.output)) == report.total


def test_resolve_families_defaults_to_features():
    assert resolve_families(None) == set(FEATURE_FAMILIES)


def test_resolve_families_expands_keywords():
    assert resolve_families(["all"]) == set(FEATURE_FAMILIES) | set(SUMMARY_FAMILIES)
    assert resolve_families(["summary"]) == set(SUMMARY_FAMILIES)
    assert resolve_families(["holes, slots"]) == {"holes", "slots"}


def test_resolve_families_rejects_evidence_families():
    with pytest.raises(ValueError, match="evidence"):
        resolve_families(["cylinders"])


def test_report_counts_only_what_reached_the_file(sample_step, tmp_path, monkeypatch):
    """A label with nothing drawable is reported as undrawn, not as an annotation."""
    # ``quid2pmi.convert`` is the re-exported function, so reach the module by name.
    convert_module = importlib.import_module("quid2pmi.convert")

    real = convert_module.build_document

    def drop_one(shape, labels, **kwargs):
        doc, written, coloured = real(shape, labels, **kwargs)
        return doc, written[:-1], coloured

    monkeypatch.setattr(convert_module, "build_document", drop_one)
    report = convert_module.convert(sample_step, tmp_path / "short.step")

    assert sum(report.undrawn.values()) == 1
    assert report.total == sum(report.counts.values())
    assert len(read_pmi(report.output)) == report.total + 1
