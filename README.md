# quid2pmi

Make [Quiddity](https://github.com/pzfreo/quiddity) feature recognition results visible in a
CAD viewer.

`quid2pmi` reads a STEP file, runs Quiddity's recognisers over it, and writes a new STEP file
in which every recognised feature is made visible:

* each feature's **faces are coloured** by family, so the recognition result reads at a glance;
* each feature carries an **AP242 PMI dimension** -- a typed, valued annotation with a leader
  line to a point proved to lie on the feature;
* the full inventory, including a plain-words explanation of every feature, is available as
  **JSON** alongside.

Open the result in [CAD Assistant](https://www.opencascade.com/products/cad-assistant/).

The original geometry is written unchanged; nothing is added to or removed from the solid.

## Install

```bash
uv pip install -e .
```

Quiddity and build123d (which supplies the OCCT kernel via OCP) are the only dependencies. If
the required Quiddity version is not yet on PyPI, install it from its checkout first:

```bash
uv pip install -e ../quiddity -e .
```

The tests read Quiddity's STEP corpus, which this package does not redistribute. They look for
it beside this repo and skip if it is absent; set `QUIDDITY_CORPUS` to point elsewhere.

## Use

```bash
quid2pmi part.step                       # progress, then a summary per family
quid2pmi part.step                       # writes part-pmi.step beside the input
quid2pmi part.step -o annotated.step
quid2pmi part.step --families holes,slots
quid2pmi part.step --families all --json features.json
quid2pmi part.step --text-height 2.5 --standoff 15
quid2pmi part.step --viewer features.html # a web page showing the features
quid2pmi part.step --json features.json  # full inventory, with explanations
quid2pmi part.step --no-colour           # PMI dimensions only
```

While it works it shows the phase it is in — reading, recognising, choosing leader directions,
placing labels, writing — and then a summary in which each family is swatched in **the colour
its faces are given in the STEP file**, so the terminal and the viewer agree:

```
    feature       found
  ■■ holes            31
  ■■ chamfers         16
  ■■ step levels       5
  ■■ bosses            3
  ■■ turned steps      3
  ■■ fillets           2

  60 annotations  58 faces coloured  409.5 kB  [cad-assistant]
  /path/to/part-pmi.step
```

The count is what actually reached the file. Records that carried no point to anchor a label
to, and labels that produced nothing drawable, are listed separately in yellow rather than
counted in.

Piped or redirected, the spinner and colour are dropped and the summary becomes one plain line
per family, so build logs stay readable. `--plain` forces that in a terminal too, and `-v`
lets the STEP writer's own output through.

### Viewing in a browser instead

`--viewer` writes a self-contained web page through
[step-pmi-viewer](https://github.com/pzfreo/step-pmi-viewer): the part in its feature colours,
with every label as HTML text rather than geometry. That keeps labels crisp at any zoom and
costs almost nothing -- a 65-feature part is under 400 kB, against 11 MB for the same labels
drawn into the STEP file with `--draw-text`.

It also sidesteps the viewer limits documented above: the page draws what it is given, so there
is no question of saved views or which annotation forms a viewer honours.

```bash
quid2pmi part.step --viewer features.html && open features.html
```

The same package reads *authored* PMI out of an AP242 file, so the features quid2pmi recovers
and the dimensions and tolerances an engineer wrote can be looked at the same way.

### Shell completion

```bash
quid2pmi --completion zsh  > "${fpath[1]}/_quid2pmi"
quid2pmi --completion bash > /usr/local/etc/bash_completion.d/quid2pmi
quid2pmi --completion fish > ~/.config/fish/completions/quid2pmi.fish
```

Completes options, family names, profiles and `.step` paths. The scripts are generated from
the argument parser, so a new flag becomes completable as soon as it is added rather than when
someone remembers to update a checked-in script.

### What is visible where

This was determined by measurement against CAD Assistant, not assumed. STEP can carry several
kinds of annotation and they do not all survive to the screen:

| Channel | Reaches the STEP file | Visible in CAD Assistant |
| --- | --- | --- |
| Face colour per feature family | yes | **yes** — the main signal |
| Semantic PMI dimension (Ø, R, angle) | yes | **yes**, with its own leader |
| Label text as geometry (`--draw-text`) | yes | **yes** |
| Dimension name (`HOLE Ø8 THRU`) | yes | in the annotation's properties |
| Label text as AP242 graphical PMI | yes | **no** (see below) |
| Sub-shape names on faces | **no** — OCCT does not export them | no |

**Why annotation text is written as geometry.** OCCT does write the label into the PMI
presentation: 60 `DRAUGHTING_CALLOUT` entities on a `DRAUGHTING_MODEL`, carried as
`TESSELLATED_ANNOTATION_OCCURRENCE` — the same form the NIST PMI reference suite uses, and
NIST's own STP2X3D renders them (see [`tools/stp2x3d`](tools/stp2x3d)). The annotations are
sound.

What is missing is the **AP242 saved view**: zero `CAMERA_MODEL_D3` and `PRESENTATION_VIEW`
entities, because `STEPCAFControl_Writer` has no view mode at all — only the *reader* has
`SetViewMode`. Against the NIST reference, that is the *only* structural difference. Viewers
drive graphical PMI display from saved views, so CAD Assistant has nothing to switch on and
draws none of it. The same outlines added as ordinary geometry, in a separate shape named
`quiddity labels`, render everywhere, and that is what `--draw-text` does — at the cost of
turning text into B-rep.

A saved view was tried and does **not** help. `tools/savedview` injects a `CAMERA_MODEL_D3`
wired as the NIST reference files wire it, and OCCT's reader confirms it: one saved view, the
same count it reads from `nist_ctc_01_asme1_ap242-e1.stp`. CAD Assistant still draws none of
the annotation text. So the missing saved view was not the explanation, and text as geometry
remains the only route that works there.

### Viewer profiles

Two of the choices above are workarounds for one consumer, not properties of the standard, so
they live behind `--profile`:

| | `cad-assistant` (default) | `ap242` |
| --- | --- | --- |
| thickness-like sizes | `Size_CurveLength` | `Size_Thickness` |
| `--draw-text` puts text | in the model as geometry | in the PMI presentation |
| spool with `--draw-text` | 11.3 MB | 2.1 MB |

`ap242` is the standard-correct output. Use it for a viewer that renders graphical PMI and does
not crash on a thickness dimension. It has not been verified against such a viewer here --
only CAD Assistant and FreeCAD were available, and both are built on OCCT.

**A dimension named `thickness` crashes CAD Assistant.** `Size_Thickness` makes OCCT write
`DIMENSIONAL_SIZE(...,'thickness')`, and importing that segfaults CAD Assistant. Measured on one
part with sixteen chamfers, holding everything else constant: `'thickness'` crashes, while
`'curve length'`, `'radius'` and `ANGULAR_SIZE` all open. Six families carry a thickness-like
size, so this is not a corner case. `Size_Thickness` is never used; thickness and length both
map to `Size_CurveLength`, both being linear sizes of a single feature. A test asserts the
string never appears in output.

### Explaining what was found

Every adapted family gets a plain-words explanation — what kind of feature it is, its sizes,
the axis it runs along and the direction it opens towards, plus family-specific detail such as
a hole's entry treatment or a recess's end conditions:

```
HOLE Ø6 10 DEEP
  Cylindrical hole of 6 diameter, 10 deep with a flat bottom, opening towards -Z.

CHAMFER 1x1 45deg
  Turned chamfer about the Z axis, legs 1 and 1 at 45 degrees.
```

These are always in `--json` and on the annotations the Python API returns. `--draw-text` also
puts them on the model as geometry, where a viewer will actually render them.

Text becomes B-rep geometry, at roughly 14 KB per character, so what you draw sets the file
size. Measured on a 60-feature part:

| drawn | characters | file |
| --- | --- | --- |
| nothing — colour and PMI only (default) | 0 | 0.4 MB |
| terse labels (`--draw-text`) | 810 | 11.3 MB |
| full explanations (`--draw-text --explain`) | 5209 | 80.4 MB |

Narrow the families or the explanation width if that matters; both reduce the character count
directly.

### Options

| Option | Meaning |
| --- | --- |
| `-o, --output` | output path (default `<stem>-pmi.step` beside the input) |
| `-f, --families` | comma-separated family names, or `features` (default), `summary`, `all` |
| `--text-height` | label height in model units (default: bounding box diagonal / 45) |
| `--standoff` | gap between the part's bounding box and the label plane (default: 10% of the diagonal) |
| `--font` | label font (default Arial) |
| `--no-leaders` | omit leader lines |
| `-e, --explain` | include the plain-words explanation in drawn labels (needs `--draw-text`) |
| `--explain-width` | wrap explanation text at this many characters (default 44) |
| `--no-colour` | do not colour each feature's faces by family |
| `--profile` | viewer to write for: `cad-assistant` (default) or `ap242` |
| `--draw-text` | add the label text to the model (see size cost below) |
| `--text-in` | where `--draw-text` puts it: `geometry` or `annotation` |
| `--json` | also write the annotation list as JSON |
| `-q, --quiet` | suppress the summary |
| `-v, --verbose` | also show the STEP writer's own progress output |
| `--plain` | plain terminal output, without colour or a spinner |
| `--viewer HTML` | also write a self-contained web page showing the features |
| `--completion SHELL` | print a completion script for bash, zsh or fish |
| `--version` | print the version |

## Where a leader points

An annotation is only worth anything if it addresses the geometry it claims to. Three things
make that true, and each is measured in the tests rather than assumed:

1. **The tip lands on the feature.** Anchors come from Quiddity's evidence view, which resolves
   each accepted feature to the caller's own faces, and from `inspect_face()`, which proves a
   point on a face's real trim. Deriving the anchor from a record's values instead does not
   work: a hole's `location` is a point on its *axis*, so the tip sits one radius inside the
   bore, and a step level's is the centre of a bounding rectangle, which on an annular flange
   is out in mid-air. Measured on a 60-feature part, that approach put 39 of 60 tips off the
   part, the worst 32.6 away.
2. **The leader does not tunnel through the part.** Each candidate reading direction is checked
   by sampling the solid's point classification along it. Testing ray/face intersection instead
   would be wrong: a leader running up the wall of a bore lies *in* that bore's own face for its
   whole length, which registers as a hit at every step while being perfectly readable.
3. **The labels stay near the part.** Each is assigned a cell on a bounded grid on one of the
   six bounding box faces, taking the free cell nearest its own feature. Pushing labels apart
   one line at a time instead is unbounded — 31 holes on one face stacked into a tower reaching
   1454 on a 130-wide part, with leaders 6.4x the part's diagonal.

## Python API

```python
from pathlib import Path
from quid2pmi import convert

report = convert(Path("part.step"), Path("part-pmi.step"), explain=True)
print(report.total, report.counts)
for annotation in report.annotations:
    print(annotation.family, annotation.label, annotation.anchor)
    print("   ", annotation.explanation)
```

## Coverage and limits

Most Quiddity families have an explicit adapter that produces a drawing-style label and,
where the record carries one, a semantic dimension value:

`holes` · `bosses` · `slots` · `oriented_slots` · `section_recesses` · `pads` · `plates` ·
`chamfers` · `fillets` · `blends` · `grooves` · `flats` · `through_steps` · `angled_steps` ·
`paired_ramp_steps` · `circular_blind_steps` · `turned_steps` · `step_levels` ·
`hole_patterns`

A family without an explicit adapter falls back to a generic label built from the record's
own fields. Records carrying no point an annotation can be anchored to are counted and
reported as `N record(s) with no anchor point` rather than silently dropped.

Known limits:

* Quiddity's `import_step_geometry()` loads B-Rep geometry only. Assembly structure, product
  names, colours and layers in the input are **not** carried into the output.
* `cylinders`, `risers`, `rotational`, `section_recess_refusals` and `step_ladder` are raw
  evidence or diagnostics rather than features, and are not annotated.
* OCCT's STEP writer flattens the attachment: the XCAF document references each feature's own
  faces, but every `SHAPE_ASPECT` in the written file points at the product. The document is
  right; the file cannot express it through this writer.
* A feature's faces may be claimed by more than one family. The last one written wins the
  colour, and the count of coloured faces reflects distinct faces, not annotations.
* Labels are laid out against the part's overall bounding box, so on a long thin part the
  standoff may want raising with `--standoff`.
* Explanations restate the record Quiddity produced. They describe what was recognised, not
  how the feature was manufactured or why it is there.
* Angular dimensions are stored in radians, as XCAF requires. Writing degrees produces a value
  57x too large -- a 45 degree chamfer displays as 2578.31 degrees.
* A feature is annotated with an AP242 *size* dimension or a presentation-only annotation.
  Location dimensions are measured between two shapes, which a single-feature annotation does
  not have, and OCCT's AP242 writer crashes when asked to write one from a single reference.
* Recognition runs in caller coordinates (`build_raw_recognition_result`) so that annotation
  positions match the incoming file. Quiddity's framed route is not used.

## Licence

Apache-2.0.
