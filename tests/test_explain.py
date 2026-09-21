"""The optional plain-words explanation of each recognised feature."""

import json

from quid2pmi import convert
from quid2pmi.adapters import annotate, generic_annotation
from quid2pmi.model import Annotation
from tests.test_convert import read_pmi


class FakeResult:
    def __init__(self, **families):
        for name, records in families.items():
            setattr(self, name, records)


class Rec:
    def __init__(self, d):
        self._d = d

    def to_dict(self):
        return self._d


def test_hole_explanation_reads_as_a_sentence():
    result = FakeResult(
        holes=[
            Rec(
                {
                    "axis": [0, 0, 1],
                    "location": [0, 0, 0],
                    "diameter": 6.0,
                    "depth": 10.0,
                    "bottom": "flat",
                }
            )
        ]
    )
    (annotation,), _ = annotate(result, {"holes"})
    assert annotation.explanation == (
        "Cylindrical hole of 6 diameter, 10 deep with a flat bottom, opening towards -Z."
    )


def test_through_hole_explanation_says_so():
    result = FakeResult(
        holes=[
            Rec({"axis": [0, 0, 1], "location": [0, 0, 0], "diameter": 6.0, "bottom": "through"})
        ]
    )
    (annotation,), _ = annotate(result, {"holes"})
    assert "passing right through the part" in annotation.explanation


def test_entry_treatments_are_named():
    result = FakeResult(
        holes=[
            Rec(
                {
                    "axis": [0, 0, 1],
                    "location": [0, 0, 0],
                    "diameter": 6.0,
                    "depth": 4.0,
                    "bottom": "flat",
                    "cbore": {"diameter": 10.0},
                }
            )
        ]
    )
    (annotation,), _ = annotate(result, {"holes"})
    assert "Entry treatment: cbore." in annotation.explanation


def test_every_adapted_family_produces_an_explanation(sample_step, tmp_path):
    report = convert(sample_step, tmp_path / "o.step", families=None)
    assert report.total > 0
    assert all(a.explanation for a in report.annotations)
    assert all(a.explanation.endswith(".") for a in report.annotations)


def test_generic_fallback_explains_what_it_can():
    annotation = generic_annotation("widgets", {"location": [0, 0, 0], "span": 3.0})
    assert annotation is not None
    assert annotation.explanation == "Recognised widget with span 3."


def test_explain_costs_the_step_file_nothing(sample_step, tmp_path):
    """Explanations ride in the model-tree names, which are free. Nothing is ever
    drawn from them, so the annotations and the file size do not move."""
    plain = convert(sample_step, tmp_path / "plain.step")
    verbose = convert(sample_step, tmp_path / "verbose.step", explain=True)

    plain_pmi = {name: edges for _, _, edges, name in read_pmi(plain.output)}
    verbose_pmi = {name: edges for _, _, edges, name in read_pmi(verbose.output)}

    assert set(plain_pmi) == set(verbose_pmi)
    assert plain_pmi == verbose_pmi
    assert verbose.output.stat().st_size < plain.output.stat().st_size * 1.1


def test_labels_reach_the_file_without_losing_a_word(sample_step, tmp_path):
    """OCCT drops the semantic name's first token, so the family leads it."""
    report = convert(sample_step, tmp_path / "named.step")
    written = report.output.read_text(errors="ignore")
    for annotation in report.annotations:
        ascii_label = annotation.label.encode("ascii", "ignore").decode()
        head = ascii_label.split()[0]
        assert head, annotation.label
        assert f"SHAPE_ASPECT('{head}" in written, annotation.label


def test_explanations_live_in_the_json_report_not_the_step(sample_step, tmp_path):
    """CAD Assistant shows neither annotation text nor sub-shape names, so the
    prose belongs in the sidecar rather than pretending to be in the model."""
    report = convert(sample_step, tmp_path / "e.step", explain=True)
    payload = report.to_dict()
    assert all(label["explanation"] for label in payload["labels"])


def test_no_label_text_is_drawn_into_the_model(sample_step, tmp_path):
    """Glyph outlines -- as a second shape beside the part, or inside the PMI
    presentation -- were a workaround for CAD Assistant, which draws no graphical
    PMI either way. The presentation carries the leader and nothing else."""
    report = convert(sample_step, tmp_path / "o.step", explain=True)
    written = report.output.read_text(errors="ignore")

    assert "quiddity labels" not in written
    # A leader is an elbow and a stem: a handful of edges, not a glyph outline.
    assert all(edges <= 4 for _, _, edges, _ in read_pmi(report.output))


def test_explanation_is_reported_whether_or_not_it_is_drawn(sample_step, tmp_path):
    report = convert(sample_step, tmp_path / "o.step", explain=False)
    payload = json.loads(json.dumps(report.to_dict()))
    assert all(label["explanation"] for label in payload["labels"])


def test_the_explanation_never_displaces_the_terse_label():
    """The label is the identifier in the STEP file and the model tree; the
    explanation rides alongside it and never rewrites it."""
    annotation = Annotation("slots", ("SLOT", "D4"), (0.0, 0.0, 0.0), explanation="A slot. " * 10)
    assert annotation.label == "SLOT D4"
    assert annotation.text == ("SLOT", "D4")
