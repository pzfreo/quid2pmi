# add_saved_view.py

Adds an AP242 saved view (`CAMERA_MODEL_D3`) to a STEP file written by OCCT, wired as the NIST
PMI reference files wire it.

```bash
python tools/savedview/add_saved_view.py part.step -o viewed.step
```

## Does it help?

**No, not with CAD Assistant** — which is what it was written for.

OCCT's `STEPCAFControl_Writer` emits graphical PMI but no saved view, and that was the only
structural difference between quid2pmi's output and the NIST reference suite. Since viewers
drive graphical PMI display from saved views, it looked like the explanation for CAD Assistant
rendering none of the annotation text.

It is not. With the view added, OCCT's reader reports one saved view — the same count it reads
from `nist_ctc_01_asme1_ap242-e1.stp` — and CAD Assistant still draws nothing. The conclusion
is that CAD Assistant does not render OCCT-written graphical PMI at all, saved view or not.

Kept because the output is standards-correct and a viewer that does honour saved views may
make use of it, and the text-as-geometry workaround that did has been removed: use `--viewer`
to see the labels instead.

## What it writes

    PLANAR_BOX          the view frame
    VIEW_VOLUME         anchored on a cartesian point, not a placement
    CAMERA_MODEL_D3     the saved view itself
    REPRESENTATION_MAP  publishes the camera
    MAPPED_ITEM         instantiates it
    ( CHARACTERIZED_OBJECT / CHARACTERIZED_REPRESENTATION /
      DRAUGHTING_MODEL / REPRESENTATION )   the combined view, listing the camera
                                            alongside the existing callouts
    MECHANICAL_DESIGN_AND_DRAUGHTING_RELATIONSHIP   ties it to the plain draughting model

Ablating the NIST file showed that only the `REPRESENTATION_MAP` and the combined
draughting-model-and-representation are load-bearing: removing the `MAPPED_ITEM` or the
relationship leaves the view readable. Both are written anyway, to match the reference.
