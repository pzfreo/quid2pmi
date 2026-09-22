"""Render recognised features through step-pmi-viewer.

The viewer draws PMI read from a STEP file. Recognised features are the same
shape of thing -- a label, a point on the part, a description -- so they are
adapted to its vocabulary and drawn by the same page, in the colours the STEP
output gives their faces.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.Message import Message_ProgressRange
from OCP.RWGltf import RWGltf_CafWriter
from OCP.TCollection import TCollection_AsciiString
from OCP.TColStd import TColStd_IndexedDataMapOfStringString
from OCP.TDF import TDF_LabelSequence
from OCP.TDocStd import TDocStd_Document
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from step_pmi_viewer import Annotation as ViewerAnnotation
from step_pmi_viewer import Scene
from step_pmi_viewer import write as write_page

from .layout import BoundingBox
from .model import Annotation, Vec
from .palette import colour_for

#: How far off its anchor a label sits, as a share of the part's diagonal. Small,
#: because the page pushes labels apart on screen rather than in the model.
STANDOFF = 0.055

#: How far the leader stands off the surface before turning, as a share of the
#: diagonal. The last leg runs along the part's own normal, so the leader meets a
#: bore wall radially rather than at whatever angle the label ended up at.
STUB = 0.012


def _hex(family: str) -> str:
    red, green, blue = colour_for(family)
    return f"#{int(red * 255):02x}{int(green * 255):02x}{int(blue * 255):02x}"


def _glb(doc: TDocStd_Document, deflection: float, destination: Path) -> bytes:
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    shapes = TDF_LabelSequence()
    shape_tool.GetShapes(shapes)
    for i in range(1, shapes.Length() + 1):
        BRepMesh_IncrementalMesh(
            shape_tool.GetShape_s(shapes.Value(i)), deflection, False, 0.25, True
        )
    writer = RWGltf_CafWriter(TCollection_AsciiString(str(destination)), True)
    writer.Perform(doc, TColStd_IndexedDataMapOfStringString(), Message_ProgressRange())
    return destination.read_bytes()


def _adapt(annotation: Annotation, diagonal: float) -> ViewerAnnotation:
    """One recognised feature, in the viewer's vocabulary."""
    direction = annotation.normal or (0.0, 0.0, 1.0)
    step = diagonal * STANDOFF
    x, y, z = annotation.anchor
    origin: Vec = (x + direction[0] * step, y + direction[1] * step, z + direction[2] * step)
    via: tuple[Vec, ...] = ()
    # Only where the surface faces the way the label is read from: a bore wall's
    # normal points into the hole, and a leader standing off along it would have
    # to come back out through the material.
    surface = annotation.surface
    if surface is not None and sum(surface[i] * direction[i] for i in range(3)) > 0.2:
        out = diagonal * STUB
        via = ((x + surface[0] * out, y + surface[1] * out, z + surface[2] * out),)
    return ViewerAnnotation(
        kind="dimension",
        # The drawing callout where the adapter produced one: the page draws text,
        # so a recognised feature can read like a dimension rather than a label.
        cells=annotation.callout or annotation.text,
        anchor=annotation.anchor,
        origin=origin,
        via=via,
        group=annotation.family,
        detail=annotation.explanation,
        value=annotation.value,
    )


def build_scene(
    name: str,
    doc: TDocStd_Document,
    annotations: list[Annotation],
    box: BoundingBox,
) -> Scene:
    """A viewer scene for a part and the features recognised in it."""
    with tempfile.TemporaryDirectory() as tmp:
        glb = _glb(doc, (box.diagonal or 1.0) / 2000, Path(tmp) / "part.glb")
    # Say so on the page: these are inferences from the geometry, not dimensions
    # and tolerances an engineer specified, and must not be read as though they were.
    scene = Scene(name, glb, box.min, box.max, origin="recognised features")
    scene.annotations.extend(_adapt(a, box.diagonal or 1.0) for a in annotations)
    return scene


def write_viewer(
    destination: Path | str,
    name: str,
    doc: TDocStd_Document,
    annotations: list[Annotation],
    box: BoundingBox,
) -> Path:
    """Write a self-contained page showing the recognised features."""
    scene = build_scene(name, doc, annotations, box)
    palette: dict[str, Any] = {a.family: _hex(a.family) for a in annotations}
    return write_page(scene, destination, title=name, colours=palette)
