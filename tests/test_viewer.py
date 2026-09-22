"""Recognised features rendered through step-pmi-viewer."""

import base64
import json
import re

from quid2pmi import convert
from quid2pmi.palette import colour_for


def test_viewer_page_is_written(sample_step, tmp_path):
    page = tmp_path / "view.html"
    report = convert(sample_step, tmp_path / "o.step", viewer=page, quiet=True)
    assert page.is_file()
    assert page.read_text().lstrip().startswith("<!doctype html>")
    assert report.total > 0


def test_every_annotation_reaches_the_page(sample_step, tmp_path):
    page = tmp_path / "view.html"
    report = convert(sample_step, tmp_path / "o.step", viewer=page, quiet=True)
    payload = json.loads(re.search(r"const DATA = (\{.*?\});\n", page.read_text(), re.S).group(1))
    assert len(payload["labels"]) == report.total


def test_the_part_is_embedded(sample_step, tmp_path):
    page = tmp_path / "view.html"
    convert(sample_step, tmp_path / "o.step", viewer=page, quiet=True)
    blob = re.search(r'"glb":\s*"([A-Za-z0-9+/=]+)"', page.read_text())
    assert blob and base64.b64decode(blob.group(1)).startswith(b"glTF")


def test_families_keep_the_colours_the_step_file_gives_them(sample_step, tmp_path):
    """The page and the STEP file must agree on what a family looks like."""
    page = tmp_path / "view.html"
    report = convert(sample_step, tmp_path / "o.step", viewer=page, quiet=True)
    colours = json.loads(
        re.search(r"const GROUP_COLOUR = (\{.*?\});\n", page.read_text(), re.S).group(1)
    )
    for family in report.counts:
        red, green, blue = colour_for(family)
        assert (
            colours[family] == f"#{int(red * 255):02x}{int(green * 255):02x}{int(blue * 255):02x}"
        )


def test_labels_carry_their_explanations(sample_step, tmp_path):
    page = tmp_path / "view.html"
    convert(sample_step, tmp_path / "o.step", viewer=page, explain=True, quiet=True)
    payload = json.loads(re.search(r"const DATA = (\{.*?\});\n", page.read_text(), re.S).group(1))
    assert all(label["detail"] for label in payload["labels"])


def test_no_viewer_is_written_unless_asked(sample_step, tmp_path):
    convert(sample_step, tmp_path / "o.step", quiet=True)
    assert not list(tmp_path.glob("*.html"))


def test_labels_sit_off_their_anchors(sample_step, tmp_path):
    """A label on top of its anchor would have nothing to point at."""
    page = tmp_path / "view.html"
    convert(sample_step, tmp_path / "o.step", viewer=page, quiet=True)
    payload = json.loads(re.search(r"const DATA = (\{.*?\});\n", page.read_text(), re.S).group(1))
    for label in payload["labels"]:
        moved = sum((label["origin"][i] - label["anchor"][i]) ** 2 for i in range(3)) ** 0.5
        assert moved > 0


def test_a_leader_meets_a_sloped_face_square(sample_step, tmp_path):
    """The read direction is snapped to a bounding-box axis, which throws away
    the 45 degrees of a chamfer. Offsetting the label along the snapped axis and
    then bending to the true normal put a kink in every such leader."""
    import math

    page = tmp_path / "bend.html"
    convert(sample_step, tmp_path / "o.step", viewer=page, quiet=True)
    payload = json.loads(
        re.search(r"const DATA = (\{.*?\});\n", page.read_text(), re.S).group(1)
    )

    bent = [label for label in payload["labels"] if label["via"]]
    assert bent, "no leader stands off the surface"
    for label in bent:
        anchor, via, origin = label["anchor"], label["via"][0], label["origin"]
        into = [via[i] - anchor[i] for i in range(3)]
        onward = [origin[i] - via[i] for i in range(3)]
        cosine = sum(into[i] * onward[i] for i in range(3)) / (
            math.dist(into, (0, 0, 0)) * math.dist(onward, (0, 0, 0))
        )
        assert cosine > 0.999, (label["cells"], cosine)
