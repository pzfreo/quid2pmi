# quid2pmi

Make [Quiddity](https://github.com/pzfreo/quiddity) feature recognition results visible in a
CAD viewer.

`quid2pmi` reads a STEP file, runs Quiddity's recognisers over it, and writes a new STEP file
in which every recognised feature carries an **AP242 PMI annotation**: a text label placed
clear of the part, with a leader line pointing at the feature it describes. Open the result in
[CAD Assistant](https://www.opencascade.com/products/cad-assistant/) and turn PMI on to see
what the recogniser found, where.

The original model is written unchanged. The annotations are added alongside it.

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
quid2pmi part.step                       # writes part-pmi.step beside the input
quid2pmi part.step -o annotated.step
quid2pmi part.step --families holes,slots
quid2pmi part.step --families all --json features.json
quid2pmi part.step --text-height 2.5 --standoff 15
quid2pmi part.step --explain             # add plain-words text under each label
```

The command prints a per-family count of what it annotated to stderr:

```
part-pmi.step: 14 annotations
  holes                    2
  section_recesses         4
  step_levels              3
  ...
```

The count is what actually reached the file. Records that carried no point to anchor a label
to, and labels that produced nothing drawable, are listed separately rather than counted in.

### Viewing in CAD Assistant

Open the output file, then enable PMI display. CAD Assistant reads both halves of what
`quid2pmi` writes:

* the **graphical** annotation — the label text and leader drawn in 3D, which is what you see
  in the viewport; and
* the **semantic** annotation — a typed dimension (diameter, radius, thickness, length, angle)
  with its value, which appears in the model tree and property panel.

### Explaining what was found

By default a label is terse, in the style of a drawing note:

```
HOLE Ø6 10 DEEP
```

`--explain` draws the same feature in plain words underneath, so the viewer shows what the
recogniser actually concluded rather than a code you have to decode:

```
HOLE Ø6 10 DEEP

Cylindrical hole of 6 diameter, 10 deep
with a flat bottom, opening towards -Z.
```

Explanations are written for every adapted family — what kind of feature it is, its sizes, the
axis it runs along and the direction it opens towards, plus family-specific detail such as a
hole's entry treatment, a recess's end conditions or a pattern's hole count. `--explain-width`
sets the wrap width (default 44 characters).

The explanation is always present in `--json` output and on the annotations returned by the
Python API, whether or not it is drawn. The annotation's *name* in the STEP file and the model
tree stays the terse label either way, so turning explanations on does not rename anything.

### Options

| Option | Meaning |
| --- | --- |
| `-o, --output` | output path (default `<stem>-pmi.step` beside the input) |
| `-f, --families` | comma-separated family names, or `features` (default), `summary`, `all` |
| `--text-height` | label height in model units (default: bounding box diagonal / 45) |
| `--standoff` | gap between the part's bounding box and the label plane (default: 10% of the diagonal) |
| `--font` | label font (default Arial) |
| `--no-leaders` | omit leader lines |
| `-e, --explain` | draw a plain-words explanation under each label |
| `--explain-width` | wrap explanation text at this many characters (default 44) |
| `--json` | also write the annotation list as JSON |
| `-q, --quiet` | suppress the summary |

## How labels are placed

Labels have to be readable without hiding the part, so placement is deliberate rather than
at the feature itself:

1. Each feature is given an outward direction — its own axis where the record has one,
   otherwise the direction from the part's centre to the feature.
2. That direction is snapped to the nearest principal axis, which assigns the label to one of
   the six faces of the part's bounding box. Every label on a face shares one text plane, so
   the text is upright and face-on when you look along that axis.
3. Within a face, each label starts at its feature's own projected position and is nudged up
   only if it would collide with a label already placed there.
4. A leader runs from the label, through the feature's projected position, to the feature.

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
* Labels are laid out against the part's overall bounding box, so on a long thin part the
  standoff may want raising with `--standoff`.
* Explanations restate the record Quiddity produced. They describe what was recognised, not
  how the feature was manufactured or why it is there.
* A feature is annotated with an AP242 *size* dimension or a presentation-only annotation.
  Location dimensions are measured between two shapes, which a single-feature annotation does
  not have, and OCCT's AP242 writer crashes when asked to write one from a single reference.
* Recognition runs in caller coordinates (`build_raw_recognition_result`) so that annotation
  positions match the incoming file. Quiddity's framed route is not used.

## Licence

Apache-2.0.
