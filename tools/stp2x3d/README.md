# STP2X3D in Docker

NIST's [STEP to X3D translator](https://github.com/usnistgov/stp2x3d) built on Debian, so it
runs on macOS without fighting an OCCT build.

```bash
docker build -t stp2x3d .
docker run --rm -v "$PWD:/work" stp2x3d --input /work/part.step --html 1 --edge 1
# writes part.html next to the input; open it in a browser
```

## What it does and does not do

It converts **part geometry** to X3D/X3DOM. It does **not** export PMI annotation graphics.

That was measured rather than assumed, because the `--gdt` option ("geometric elements related
to GD&T") suggests otherwise:

| input | annotations in the STEP | `IndexedLineSet` in the X3D |
| --- | --- | --- |
| `nist_ctc_01_asme1_ap242-e1.stp` | 23 `TESSELLATED_ANNOTATION_OCCURRENCE` | 21 |
| a quid2pmi output | 60 `DRAUGHTING_CALLOUT` | 14 |

If those line sets were annotations, the file with 60 of them would not produce fewer than the
file with 23. They track solids. `--gdt 0/1` and `--sketch 0/1` make no difference to the
output at all, byte for byte.

So this cannot be used to check whether quid2pmi's graphical PMI is well formed. NIST's PMI
viewer is the [STEP File Analyzer and Viewer](https://github.com/usnistgov/SFA), which draws
the annotations itself in Tcl and is Windows-only because it reads STEP through the IFCsvr COM
toolkit.

## Two patches are applied during the build

STP2X3D 2.0 targets OCCT 8.0 on Windows. Debian trixie carries OCCT 7.8.1, which already uses
the `TKDESTEP`/`TKDE` library names it links against, so the distro packages suffice — but two
things need fixing:

1. `XCAFDoc_ShapeTool::GetShape` returns by value in 7.8 and by reference in 8.0, so it cannot
   bind to a `TopoDS_Shape&`. Taking a copy is correct under both.
2. `std::ofstream::open(const wchar_t*)` is an MSVC extension; libstdc++ has no wide-character
   overload. The path is narrowed, which is fine for ASCII paths.

## Known rough edge

`--output <path>` silently writes nothing. Leave it off and the tool writes next to the input.
