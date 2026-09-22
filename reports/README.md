# Upstream bug reports

Two crashes found while building quid2pmi, written up but **not filed**. Both reproducers
run 10/10 deterministically on an idle machine.

| draft | against | reproducer |
| --- | --- | --- |
| `occt-issue-commonlabel-segfault.md` | OCCT 7.9.3 | `occt_repro_commonlabel_after_read.py` (self-contained) |
| `cadassistant-thickness-crash.md` | CAD Assistant | two 343 KB STEP files, one typed `Size_Thickness` and one `Size_CurveLength` |

`CommonLabel` is still never written -- that one crashes OCCT's own writer, so it is ours to
avoid. The thickness workaround is **gone**: quid2pmi writes `Size_Thickness`, which is what the
standard and the NIST reference files use, and CAD Assistant is no longer a target. The
reproducer stands if anyone wants to file it.

## Findings that were investigated and are NOT worth filing

- *"Every `Location_*` dimension type crashes the writer."* Wrong. It came from reading bare
  exit codes with stderr discarded while a corpus sweep was loading the machine. On careful
  re-testing `Location_LinearDistance` is clean 10/10.
- *STEPCAFControl_Writer writes no AP242 saved view.* Real, and the reason graphical PMI is
  never displayed, but a missing feature rather than a defect.
- *Sub-shape names are not exported to STEP.* Observed, not isolated far enough to report.
- *`SetValue` takes radians while `GetValue` returns degrees after a read.* Seen once, not
  re-verified.
