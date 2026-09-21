# STP2X3D in Docker

NIST's [STEP to X3D translator](https://github.com/usnistgov/stp2x3d) built on Debian, so it
runs on macOS without fighting an OCCT build.

```bash
docker build -t stp2x3d tools/stp2x3d
docker run --rm -v "$PWD:/work" stp2x3d --input /work/part.step --html 1 --gdt 1 --edge 1
# writes part.html next to the input; open it in a browser
```

**`--gdt 1` is the important flag.** It is off by default, and without it you get the part
geometry only. With it you get the PMI annotations as well.

## What it showed about quid2pmi's output

This is the independent check CAD Assistant could not give us: it renders the graphical PMI
that CAD Assistant draws none of.

On a part with one solid, `--gdt 1` adds a face set and a line set per annotation:

| input | solids | tessellated annotations | face sets with `--gdt 1` |
| --- | --- | --- | --- |
| `nist_ctc_01_asme1_ap242-e1.stp` | 1 | 23 | 22 |
| a quid2pmi output | 1 | 60 | 15 |

So the annotations quid2pmi writes are read and drawn by an independent tool. They are also
structurally the same kind as the NIST reference suite's:

| entity | NIST | quid2pmi |
| --- | --- | --- |
| `TESSELLATED_ANNOTATION_OCCURRENCE` | 23 | 60 |
| `TESSELLATED_GEOMETRIC_SET` | 23 | 60 |
| `ANNOTATION_CURVE_OCCURRENCE` | 0 | 0 |
| **`CAMERA_MODEL_D3`** | **1** | **0** |

The only structural difference is the saved view, which OCCT's writer cannot produce.

That looked like the explanation for CAD Assistant drawing nothing, and it is not.
[`tools/savedview`](../savedview) adds one, OCCT's reader confirms it reads exactly as many
saved views from the result as from the NIST file, and CAD Assistant still draws no annotation
text. The annotations are sound; that viewer simply does not render them.

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
