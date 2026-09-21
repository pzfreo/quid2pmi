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


def test_explain_draws_more_geometry_but_keeps_the_same_names(sample_step, tmp_path):
    plain = convert(sample_step, tmp_path / "plain.step")
    verbose = convert(sample_step, tmp_path / "verbose.step", explain=True)

    plain_pmi = {name: edges for _, _, edges, name in read_pmi(plain.output)}
    verbose_pmi = {name: edges for _, _, edges, name in read_pmi(verbose.output)}

    assert set(plain_pmi) == set(verbose_pmi)
    assert all(verbose_pmi[name] > plain_pmi[name] for name in plain_pmi)


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
