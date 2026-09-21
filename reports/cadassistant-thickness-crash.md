# CAD Assistant segfaults importing a STEP file with a 'thickness' dimensional_size

## Summary

CAD Assistant dies with `SIGSEGV 'segmentation violation' detected. Address 0.` while
importing an AP242 file whose only unusual feature is a `DIMENSIONAL_SIZE` named
`'thickness'`. The identical file with that dimension named `'curve length'` or `'radius'`,
or written as an `ANGULAR_SIZE`, imports and displays normally.

`'thickness'` is valid AP242 — the NIST PMI reference suite uses it
(`nist_ctc_03_asme1_ap242-e2.stp` carries one).

## Environment

- CAD Assistant (macOS), from /Applications
- macOS 15.6 (Darwin 25.6.0), arm64
- Files written by OCCT 7.9.3 `STEPCAFControl_Writer`, schema `AP242DIS`

## Reproducer

Two attached files, both 343 KB, generated from the same solid by the same code path. They
differ only in how sixteen chamfer dimensions are typed:

| file | the 16 dimensions | result |
| --- | --- | --- |
| `repro-A-thickness.step` | `DIMENSIONAL_SIZE(...,'thickness')` | **SIGSEGV on import** |
| `repro-B-control.step` | `DIMENSIONAL_SIZE(...,'curve length')` | imports and displays |

```
diff <(grep -c "'thickness'"   repro-A-thickness.step) ...   # 16 vs 0
diff <(grep -c "'curve length'" repro-B-control.step) ...    # 0 vs 16
```

Everything else — geometry, colours, sub-shapes, annotation planes, draughting callouts,
entity count — is the same.

## Wider evidence

Observed across nine files during unrelated work, before the cause was isolated. Every file
containing a `'thickness'` dimension crashed; every file without one opened. Both groups
spanned a range of file sizes (0.3 MB to 80 MB), with and without face colours, with and
without drawn annotation geometry.

| variant of one 60-feature part | thickness dims | import |
| --- | --- | --- |
| chamfers as `ANGULAR_SIZE` | 0 | opens |
| chamfers as `'curve length'` | 0 | opens |
| chamfers as `'radius'` | 0 | opens, drawn as `R1` |
| chamfers as `'thickness'` | 16 | **SIGSEGV** |

## This appears to be in CAD Assistant, not in the STEP data

OCCT's own `STEPCAFControl_Reader` reads the crashing file without complaint, with
`SetGDTMode`, `SetViewMode`, `SetNameMode`, `SetColorMode`, `SetLayerMode`, `SetPropsMode`,
`SetSHUOMode`, `SetMatMode`, `SetMetaMode` and `SetProductMetaMode` all enabled, then meshes
every shape via `BRepMesh_IncrementalMesh`. That completed cleanly on 5 of 5 files tested,
including the ones CAD Assistant refuses.

So the STEP parses and the shapes tessellate; whatever fails is further along, likely in the
GD&T presentation path that the plain reader does not exercise.

## Impact

A writer has no way to know this is dangerous — `'thickness'` is standard and OCCT emits it
for `XCAFDimTolObjects_DimensionType_Size_Thickness`, which is the semantically correct type
for a chamfer leg, a slot width, a pad height or a plate thickness. Any of those produces a
file CAD Assistant cannot open.
