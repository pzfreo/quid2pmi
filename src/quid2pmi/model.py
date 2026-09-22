"""The neutral annotation record that sits between Quiddity and the STEP PMI writer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

Vec = tuple[float, float, float]

#: Semantic AP242 dimension kinds this tool emits alongside the graphical label.
DIM_DIAMETER = "diameter"
DIM_RADIUS = "radius"
DIM_THICKNESS = "thickness"
DIM_LENGTH = "length"
DIM_ANGLE = "angle"


@dataclass(frozen=True)
class Annotation:
    """One recognised feature, reduced to what a PMI annotation needs.

    ``anchor`` is the point the leader line points at, in the coordinates of the
    input STEP file. ``normal`` is the direction the label should be read from,
    and is ``None`` when the record carries no usable direction -- the layout
    then derives one from the part's bounding box.

    ``text`` is the terse callout. ``explanation`` is the same feature in plain
    words; it reaches the model-tree name, the JSON report and the viewer, never
    the STEP file's own geometry. ``label`` stays the terse identifier either way.
    """

    family: str
    text: tuple[str, ...]
    anchor: Vec
    normal: Vec | None = None
    value: float | None = None
    dimension: str | None = None
    explanation: str = ""
    #: The same feature written as a drawing callout -- value first, with the
    #: symbols a drawing uses -- paired with the feature word. Used where the
    #: annotation is drawn as text rather than baked into STEP, so recognised
    #: features read like the dimensions an engineer would have written.
    callout: tuple[str, ...] = ()
    name: str = ""
    #: The part's own faces this feature is made of, when recognition proved them.
    #: Excluded from equality: they carry live topology, not comparable values.
    faces: tuple[Any, ...] = field(default_factory=tuple, compare=False, repr=False)
    detail: dict[str, object] = field(default_factory=dict)
    #: The part's own normal where the leader lands, kept apart from ``normal``
    #: because the sight test replaces that with the direction the label is read
    #: from. A leader that leaves the surface along this reads as a drawing's does.
    #: Last in the field list: the adapters build annotations positionally.
    surface: Vec | None = None

    @property
    def label(self) -> str:
        """The terse identifier, independent of how much text is drawn."""
        return self.name or " ".join(self.text)

