"""Minimal reproducer: writing a CommonLabel dimension segfaults after a STEP read.

STEPCAFControl_Writer crashes with a null dereference inside writeDGTsAP242 when
the document contains an XCAFDoc_Dimension of type CommonLabel *and* a STEP file
has been read earlier in the same process. Either alone is fine:

    read a STEP file, then write CommonLabel   -> SIGSEGV   (10/10 runs)
    write CommonLabel with no prior read       -> writes normally
    read a STEP file, then write Size_Diameter -> writes normally

The dimension is fully populated and attached with the single-shape overload of
XCAFDoc_DimTolTool::SetDimension. Neither the shape nor the number of dimensions
nor the size of the presentation matters: one dimension on a box, with a
one-edge presentation, is enough.

Self-contained: it writes its own seed file, reads it back, then reproduces.

    python occt_repro_commonlabel_after_read.py                  # SIGSEGV
    python occt_repro_commonlabel_after_read.py --no-read        # writes normally
    python occt_repro_commonlabel_after_read.py Size_Diameter    # writes normally

Backtrace (OCCT 7.9.3, macOS 15 arm64, Python 3.12 via cadquery-ocp 7.9.3.1):

    Standard_Transient::IsKind(opencascade::handle<Standard_Type> const&) const
    STEPCAFControl_Writer::writeDGTsAP242(handle<XSControl_WorkSession> const&,
                                          NCollection_Sequence<TDF_Label> const&,
                                          StepData_Factors const&)
    STEPCAFControl_Writer::transfer(...)
    STEPCAFControl_Writer::Transfer(handle<TDocStd_Document> const&, ...)

Expected: the document is written, or the writer reports a failure status.
Actual:   the process dies with SIGSEGV at address 0.
"""

import sys

import OCP.XCAFDimTolObjects as DimTol
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
from OCP.Interface import Interface_Static
from OCP.STEPCAFControl import STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Reader, STEPControl_Writer
from OCP.TCollection import TCollection_ExtendedString, TCollection_HAsciiString
from OCP.TDocStd import TDocStd_Document
from OCP.XCAFApp import XCAFApp_Application
from OCP.XCAFDoc import XCAFDoc_Dimension, XCAFDoc_DocumentTool

SEED = "/tmp/occt_repro_seed.step"
kind = next((a for a in sys.argv[1:] if not a.startswith("-")), "CommonLabel")
do_read = "--no-read" not in sys.argv

box = BRepPrimAPI_MakeBox(10.0, 10.0, 10.0).Shape()

# 1. Produce a STEP file and read it back. Any STEP read will do.
if do_read:
    seed_writer = STEPControl_Writer()
    seed_writer.Transfer(box, STEPControl_AsIs)
    seed_writer.Write(SEED)
    reader = STEPControl_Reader()
    reader.ReadFile(SEED)
    reader.TransferRoots()
    print(f"read back {reader.NbShapes()} shape(s) from {SEED}", flush=True)

# 2. Build a document with one dimension of the requested type.
app = XCAFApp_Application.GetApplication_s()
fmt = TCollection_ExtendedString("MDTV-XCAF")
doc = TDocStd_Document(fmt)
app.NewDocument(fmt, doc)
shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
dimtol_tool = XCAFDoc_DocumentTool.DimTolTool_s(doc.Main())
shape_label = shape_tool.AddShape(box, False)

obj = DimTol.XCAFDimTolObjects_DimensionObject()
obj.SetType(getattr(DimTol, f"XCAFDimTolObjects_DimensionType_{kind}"))
obj.SetValue(5.0)
obj.SetPoint(gp_Pnt(5, 5, 10))
obj.SetPlane(gp_Ax2(gp_Pnt(0, 0, 20), gp_Dir(0, 0, 1), gp_Dir(1, 0, 0)))
obj.SetPointTextAttach(gp_Pnt(0, 0, 20))
obj.SetPresentation(
    BRepBuilderAPI_MakeEdge(gp_Pnt(0, 0, 20), gp_Pnt(9, 0, 20)).Edge(),
    TCollection_HAsciiString("label"),
)
dim_label = dimtol_tool.AddDimension()
XCAFDoc_Dimension.Set_s(dim_label).SetObject(obj)
dimtol_tool.SetDimension(shape_label, dim_label)

# 3. Write. This is where it dies.
Interface_Static.SetCVal_s("write.step.schema", "AP242DIS")
writer = STEPCAFControl_Writer()
writer.SetDimTolMode(True)
print(f"transferring a {kind} dimension (prior STEP read: {do_read}) ...", flush=True)
writer.Transfer(doc)
print("status:", writer.Write("/tmp/occt_repro_out.step"))
