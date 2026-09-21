"""Build an XCAF document holding the part plus PMI annotations, and write AP242 STEP.

Each placed label becomes one XCAF dimension carrying two things:

* a **graphical** presentation -- the label text and its leader line as edges,
  which is what a viewer such as CAD Assistant draws in 3D; and
* a **semantic** value and dimension type where the feature has one, so the
  annotation is also machine-readable rather than only a picture of text.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from build123d import Compound, FontStyle, Location, Plane, Vector
from OCP.BRep import BRep_Builder
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
from OCP.Interface import Interface_Static
from OCP.Message import Message, Message_Gravity
from OCP.STEPCAFControl import STEPCAFControl_Writer
from OCP.TCollection import TCollection_ExtendedString, TCollection_HAsciiString
from OCP.TDataStd import TDataStd_Name
from OCP.TDocStd import TDocStd_Document
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS_Compound, TopoDS_Shape
from OCP.XCAFApp import XCAFApp_Application
from OCP.XCAFDimTolObjects import (
    XCAFDimTolObjects_DimensionObject,
    XCAFDimTolObjects_DimensionType_DimensionPresentation,
    XCAFDimTolObjects_DimensionType_Size_Angular,
    XCAFDimTolObjects_DimensionType_Size_CurveLength,
    XCAFDimTolObjects_DimensionType_Size_Diameter,
    XCAFDimTolObjects_DimensionType_Size_Radius,
    XCAFDimTolObjects_DimensionType_Size_Thickness,
)
from OCP.XCAFDoc import XCAFDoc_Dimension, XCAFDoc_DocumentTool

from .layout import LINE_PITCH, PlacedLabel
from .model import (
    DIM_ANGLE,
    DIM_DIAMETER,
    DIM_LENGTH,
    DIM_RADIUS,
    DIM_THICKNESS,
    Annotation,
)

# Every annotation quid2pmi writes describes one feature, so it is attached to a
# single shape label. AP242 location dimensions are measured *between* two shapes,
# and OCCT's AP242 writer dereferences the missing second reference and crashes --
# so only size dimensions, and the presentation-only type, are used here.
DIMENSION_TYPES: dict[str, Any] = {
    DIM_DIAMETER: XCAFDimTolObjects_DimensionType_Size_Diameter,
    DIM_RADIUS: XCAFDimTolObjects_DimensionType_Size_Radius,
    DIM_THICKNESS: XCAFDimTolObjects_DimensionType_Size_Thickness,
    DIM_LENGTH: XCAFDimTolObjects_DimensionType_Size_CurveLength,
    DIM_ANGLE: XCAFDimTolObjects_DimensionType_Size_Angular,
}

#: Used when a feature has no semantic value: a graphical annotation and nothing more.
PRESENTATION_ONLY = XCAFDimTolObjects_DimensionType_DimensionPresentation

_XCAF_FORMAT = TCollection_ExtendedString("MDTV-XCAF")


def _pnt(value: tuple[float, float, float]) -> gp_Pnt:
    return gp_Pnt(float(value[0]), float(value[1]), float(value[2]))


def _dir(value: tuple[float, float, float]) -> gp_Dir:
    return gp_Dir(float(value[0]), float(value[1]), float(value[2]))


def _text_edges(label: PlacedLabel, font: str) -> list[TopoDS_Shape]:
    """Outlines of the label's text, as edges lying in the label's plane.

    OCCT writes a PMI presentation from the edges of the presentation shape, so
    the text is emitted as glyph outlines rather than filled faces.
    """
    plane = Plane(
        origin=Vector(*label.origin),
        x_dir=Vector(*label.x_dir),
        z_dir=Vector(*_plane_normal(label)),
    )
    edges: list[TopoDS_Shape] = []
    for row, line in enumerate(label.annotation.text):
        if not line.strip():
            continue
        try:
            glyphs = Compound.make_text(line, label.height, font=font, font_style=FontStyle.REGULAR)
        except Exception:  # pragma: no cover - font resolution differs per platform
            glyphs = Compound.make_text(line, label.height)
        # make_text centres on the origin; move it to a left-aligned row baseline.
        bbox = glyphs.bounding_box()
        placed = (
            Location((-bbox.min.X, -bbox.max.Y - row * LINE_PITCH * label.height, 0.0)) * glyphs
        )
        placed = plane.location * placed
        explorer = TopExp_Explorer(placed.wrapped, TopAbs_EDGE)
        while explorer.More():
            edges.append(explorer.Current())
            explorer.Next()
    return edges


def _plane_normal(label: PlacedLabel) -> tuple[float, float, float]:
    x, y = label.x_dir, label.y_dir
    return (
        x[1] * y[2] - x[2] * y[1],
        x[2] * y[0] - x[0] * y[2],
        x[0] * y[1] - x[1] * y[0],
    )


def _presentation(label: PlacedLabel, font: str, leaders: bool) -> TopoDS_Compound | None:
    """The graphical annotation: text outlines plus the leader polyline.

    Returns ``None`` when nothing could be drawn. OCCT's AP242 writer crashes on a
    dimension whose presentation holds no edges, so such a label is dropped rather
    than written.
    """
    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    count = 0
    for edge in _text_edges(label, font):
        builder.Add(compound, edge)
        count += 1
    if leaders:
        points = label.leader
        for start, end in zip(points, points[1:], strict=False):
            if _distance(start, end) < 1e-9:
                continue
            builder.Add(compound, BRepBuilderAPI_MakeEdge(_pnt(start), _pnt(end)).Edge())
            count += 1
    return compound if count else None


def _distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return sum((a[i] - b[i]) ** 2 for i in range(3)) ** 0.5


def build_document(
    shape: TopoDS_Shape,
    labels: list[PlacedLabel],
    *,
    name: str = "part",
    font: str = "Arial",
    leaders: bool = True,
) -> tuple[TDocStd_Document, list[PlacedLabel]]:
    """Assemble an XCAF document containing ``shape`` and one dimension per label.

    Returns the document and the labels actually written. A label whose text and
    leader yield no drawable geometry is skipped, because OCCT's AP242 writer
    crashes on a dimension with an empty presentation.
    """
    app = XCAFApp_Application.GetApplication_s()
    doc = TDocStd_Document(_XCAF_FORMAT)
    app.NewDocument(_XCAF_FORMAT, doc)
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    dimtol_tool = XCAFDoc_DocumentTool.DimTolTool_s(doc.Main())

    shape_label = shape_tool.AddShape(shape, False)
    TDataStd_Name.Set_s(shape_label, TCollection_ExtendedString(name))
    subshapes: dict[int, Any] = {}

    def attach_to(annotation: Annotation) -> Any:
        """The label a dimension should reference: the feature's own faces if known.

        Attaching to the top-level shape would make every annotation address the
        whole solid. Adding the feature's faces as XCAF sub-shapes makes the PMI
        reference the geometry it actually describes, so selecting the annotation
        in a viewer highlights that feature.
        """
        for face in annotation.faces:
            wrapped = getattr(face, "wrapped", None)
            if wrapped is None:
                continue
            key = wrapped.HashCode(0x7FFFFFFF) if hasattr(wrapped, "HashCode") else id(wrapped)
            existing = subshapes.get(key)
            if existing is not None:
                return existing
            sub_label = shape_tool.AddSubShape(shape_label, wrapped)
            if not sub_label.IsNull():
                TDataStd_Name.Set_s(sub_label, TCollection_ExtendedString(annotation.label))
                subshapes[key] = sub_label
                return sub_label
        return shape_label

    written: list[PlacedLabel] = []
    for label in labels:
        annotation = label.annotation
        presentation = _presentation(label, font, leaders)
        if presentation is None:
            continue
        written.append(label)
        obj = XCAFDimTolObjects_DimensionObject()
        kind = DIMENSION_TYPES.get(annotation.dimension or "")
        value = annotation.value if kind is not None else None
        obj.SetType(kind if value is not None else PRESENTATION_ONLY)
        if value is not None:
            obj.SetValue(float(value))
        obj.SetPoint(_pnt(annotation.anchor))
        obj.SetPlane(gp_Ax2(_pnt(label.origin), _dir(_plane_normal(label)), _dir(label.x_dir)))
        obj.SetPointTextAttach(_pnt(label.origin))
        obj.SetSemanticName(TCollection_HAsciiString(annotation.label))
        obj.SetPresentation(presentation, TCollection_HAsciiString(annotation.label))

        dim_label = dimtol_tool.AddDimension()
        TDataStd_Name.Set_s(dim_label, TCollection_ExtendedString(annotation.label))
        dimension = XCAFDoc_Dimension.Set_s(dim_label)
        dimension.SetObject(obj)
        dimtol_tool.SetDimension(attach_to(annotation), dim_label)

    return doc, written


@contextmanager
def _occt_info_suppressed(suppress: bool) -> Iterator[None]:
    """Raise OCCT's console trace level so its transfer banner stays out of the way.

    Warnings and failures still print; only informational chatter is held back.
    """
    printers = Message.DefaultMessenger_s().Printers()
    if not suppress:
        yield
        return
    levels = []
    for index in range(1, printers.Length() + 1):
        printer = printers.Value(index)
        levels.append((printer, printer.GetTraceLevel()))
        printer.SetTraceLevel(Message_Gravity.Message_Warning)
    try:
        yield
    finally:
        for printer, level in levels:
            printer.SetTraceLevel(level)


def write_step(doc: TDocStd_Document, path: str, *, quiet: bool = False) -> None:
    """Write ``doc`` as an AP242 STEP file including its PMI."""
    Interface_Static.SetCVal_s("write.step.schema", "AP242DIS")
    Interface_Static.SetIVal_s("write.step.nonmanifold", 0)
    with _occt_info_suppressed(quiet):
        writer = STEPCAFControl_Writer()
        writer.SetDimTolMode(True)
        writer.SetNameMode(True)
        writer.SetColorMode(True)
        writer.Transfer(doc)
        status = writer.Write(path)
    # IFSelect_RetDone is the only success status the STEP writer reports.
    if str(status) != "IFSelect_ReturnStatus.IFSelect_RetDone":
        raise RuntimeError(f"STEP write failed: {status}")
