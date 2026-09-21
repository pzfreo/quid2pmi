"""The optional plain-words explanation of each recognised feature."""

import json

import pytest

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


def test_explained_wraps_and_appends_to_the_drawn_text():
    annotation = Annotation("holes", ("HOLE",), (0.0, 0.0, 0.0), explanation="a " * 40)
    explained = annotation.explained(width=20)
    assert explained.text[0] == "HOLE"
    assert len(explained.text) > 2
    assert all(len(line) <= 20 for line in explained.text[2:])


def test_explained_keeps_the_terse_label_as_the_identifier():
    annotation = Annotation("holes", ("HOLE", "D6"), (0.0, 0.0, 0.0), explanation="A round hole.")
    assert annotation.explained().label == "HOLE D6"


def test_annotation_without_explanation_is_unchanged():
    annotation = Annotation("holes", ("HOLE",), (0.0, 0.0, 0.0))
    assert annotation.explained() is annotation


def test_explain_costs_nothing_unless_text_is_drawn(sample_step, tmp_path):
    """Explanations ride in the model-tree names, which are free."""
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


def test_draw_text_adds_the_labels_as_geometry(sample_step, tmp_path):
    """Text goes in as a named shape, not as an annotation a viewer ignores."""
    plain = convert(sample_step, tmp_path / "plain.step")
    drawn = convert(sample_step, tmp_path / "drawn.step", explain=True, draw_text=True)

    assert "quiddity labels" not in plain.output.read_text(errors="ignore")
    assert "quiddity labels" in drawn.output.read_text(errors="ignore")
    assert drawn.output.stat().st_size > plain.output.stat().st_size


def test_draw_text_keeps_the_pmi_presentations_small(sample_step, tmp_path):
    """Glyph outlines in a PMI presentation are never drawn and crash the
    importer at a part's worth of them, so only the leader goes in there."""
    plain = convert(sample_step, tmp_path / "plain.step")
    drawn = convert(sample_step, tmp_path / "drawn.step", explain=True, draw_text=True)

    plain_pmi = {name: edges for _, _, edges, name in read_pmi(plain.output)}
    drawn_pmi = {name: edges for _, _, edges, name in read_pmi(drawn.output)}
    assert plain_pmi == drawn_pmi
    assert all(edges < 20 for edges in drawn_pmi.values())


def test_explanation_is_reported_whether_or_not_it_is_drawn(sample_step, tmp_path):
    report = convert(sample_step, tmp_path / "o.step", explain=False)
    payload = json.loads(json.dumps(report.to_dict()))
    assert all(label["explanation"] for label in payload["labels"])


def test_narrower_wrapping_produces_more_lines():
    annotation = Annotation("holes", ("HOLE",), (0.0, 0.0, 0.0), explanation="word " * 30)
    assert len(annotation.explained(width=20).text) > len(annotation.explained(width=60).text)


@pytest.mark.parametrize("width", [20, 44, 80])
def test_explained_text_never_loses_the_terse_label(width):
    annotation = Annotation("slots", ("SLOT", "D4"), (0.0, 0.0, 0.0), explanation="A slot. " * 10)
    assert annotation.explained(width).text[:2] == ("SLOT", "D4")
