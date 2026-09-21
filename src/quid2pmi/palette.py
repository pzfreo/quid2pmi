"""Colours for feature families.

Colouring the faces a recogniser claimed is the one form of feature
visualisation every viewer renders, so it carries the result when annotation
text does not. Families have fixed colours so the same feature reads the same
way across parts; anything unlisted gets a stable colour derived from its name
rather than an arbitrary one that shifts between runs.
"""

from __future__ import annotations

import colorsys
import hashlib

RGB = tuple[float, float, float]

#: Fixed colours for the families a reader is most likely to be comparing.
FAMILY_COLOURS: dict[str, RGB] = {
    "holes": (0.85, 0.25, 0.25),
    "countersinks": (0.75, 0.15, 0.35),
    "double_d_bores": (0.70, 0.30, 0.45),
    "bosses": (0.20, 0.55, 0.85),
    "polygonal_bosses": (0.25, 0.45, 0.75),
    "slots": (0.95, 0.50, 0.20),
    "oriented_slots": (0.90, 0.40, 0.15),
    "section_recesses": (0.85, 0.40, 0.70),
    "pads": (0.60, 0.75, 0.30),
    "gusset_ribs": (0.50, 0.65, 0.25),
    "plates": (0.55, 0.75, 0.85),
    "chamfers": (0.95, 0.70, 0.20),
    "fillets": (0.40, 0.75, 0.40),
    "blends": (0.30, 0.65, 0.50),
    "grooves": (0.20, 0.70, 0.65),
    "flats": (0.65, 0.55, 0.40),
    "through_steps": (0.55, 0.50, 0.80),
    "angled_steps": (0.50, 0.40, 0.70),
    "paired_ramp_steps": (0.60, 0.45, 0.75),
    "circular_blind_steps": (0.45, 0.35, 0.65),
    "turned_steps": (0.65, 0.40, 0.80),
    "step_levels": (0.45, 0.65, 0.75),
}


def colour_for(family: str) -> RGB:
    """The colour for ``family``: fixed where known, else stable and distinct."""
    known = FAMILY_COLOURS.get(family)
    if known is not None:
        return known
    digest = hashlib.sha256(family.encode("utf-8")).digest()
    hue = digest[0] / 255.0
    saturation = 0.45 + (digest[1] / 255.0) * 0.30
    value = 0.60 + (digest[2] / 255.0) * 0.25
    return colorsys.hsv_to_rgb(hue, saturation, value)
