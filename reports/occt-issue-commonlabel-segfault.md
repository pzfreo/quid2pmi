# STEPCAFControl_Writer segfaults on a CommonLabel dimension after any STEP read

## Summary

`STEPCAFControl_Writer::Transfer()` dies with SIGSEGV when the document contains an
`XCAFDoc_Dimension` of type `XCAFDimTolObjects_DimensionType_CommonLabel`, **and** a STEP
file has been read earlier in the same process. Either condition alone is harmless.

The crash is a null dereference inside `writeDGTsAP242`.

## Environment

- OCCT 7.9.3 (via `cadquery-ocp` 7.9.3.1, Python bindings)
- macOS 15.6 (Darwin 25.6.0), arm64
- Python 3.12

## Reproducer

`occt_repro_commonlabel_after_read.py`, attached. It is self-contained: it writes its own
seed STEP file, reads it back, then builds a one-box document with a single dimension.

```
python occt_repro_commonlabel_after_read.py                 # SIGSEGV
python occt_repro_commonlabel_after_read.py --no-read       # writes normally
python occt_repro_commonlabel_after_read.py Size_Diameter   # writes normally
```

Ten runs of each, on an otherwise idle machine:

| case | outcome |
| --- | --- |
| prior STEP read, `CommonLabel` | SIGSEGV 10/10 |
| no prior read, `CommonLabel` | writes normally 10/10 |
| prior STEP read, `Size_Diameter` | writes normally 10/10 |

## What the dimension looks like

Fully populated and attached with the single-shape overload of
`XCAFDoc_DimTolTool::SetDimension`:

```python
obj = XCAFDimTolObjects_DimensionObject()
obj.SetType(XCAFDimTolObjects_DimensionType_CommonLabel)
obj.SetValue(5.0)
obj.SetPoint(gp_Pnt(5, 5, 10))
obj.SetPlane(gp_Ax2(gp_Pnt(0, 0, 20), gp_Dir(0, 0, 1), gp_Dir(1, 0, 0)))
obj.SetPointTextAttach(gp_Pnt(0, 0, 20))
obj.SetPresentation(one_edge, TCollection_HAsciiString("label"))

dim_label = dimtol_tool.AddDimension()
XCAFDoc_Dimension.Set_s(dim_label).SetObject(obj)
dimtol_tool.SetDimension(shape_label, dim_label)
```

Neither the shape, the number of dimensions, nor the size of the presentation matters. One
dimension on a `BRepPrimAPI_MakeBox` solid with a one-edge presentation is enough. A
300-edge presentation on an imported 29-face solid behaves identically.

## Backtrace

```
frame #0  Standard_Transient::IsKind(opencascade::handle<Standard_Type> const&) const + 12
          libTKernel.7.9.3.dylib
frame #1  libTKDESTEP.7.9.3.dylib`___lldb_unnamed_symbol_69dd4 + 92
frame #2  STEPCAFControl_Writer::writeDGTsAP242(
              opencascade::handle<XSControl_WorkSession> const&,
              NCollection_Sequence<TDF_Label> const&,
              StepData_Factors const&) + 11444
frame #3  STEPCAFControl_Writer::transfer(STEPControl_Writer&,
              NCollection_Sequence<TDF_Label> const&, STEPControl_StepModelType,
              char const*, bool, Message_ProgressRange const&) + 3956
frame #4  STEPCAFControl_Writer::Transfer(opencascade::handle<TDocStd_Document> const&,
              DESTEP_Parameters const&, STEPControl_StepModelType, char const*,
              Message_ProgressRange const&) + 584
```

`EXC_BAD_ACCESS (code=1, address=0x0)` — a handle is null where `writeDGTsAP242` expects an
entity, and `IsKind` is called on it without a check.

## Expected vs actual

**Expected:** the document is written, or the writer skips the dimension and returns a
non-`RetDone` status.

**Actual:** the process dies. A caller cannot defend against this — there is no status to
check and nothing to catch.

## Why the prior read matters

That is the part we cannot explain. The dependence on an earlier, unrelated STEP read
suggests state left in a static registry or the work session rather than anything about the
document being written. The `--no-read` switch in the reproducer isolates it.

## Impact

Any application that reads STEP and writes STEP in one process — which is the normal shape
of a converter — cannot use `CommonLabel` dimensions at all.
